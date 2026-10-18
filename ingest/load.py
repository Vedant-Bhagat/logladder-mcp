"""Parse raw logs -> Parquet (with template ids), then load SereneDB via sql/*.sql.

    python -m ingest.load [--sample] [--skip-parse]

Parquet goes to data/parsed/, which the SereneDB container sees as /data/parsed/ (infra/docker-compose.yml).
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from collections import Counter
from pathlib import Path

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from ingest import parse_bgl, parse_openstack
from ingest.templates import OFFSETS, make_miner

ROOT = Path(__file__).resolve().parents[1]
PARSED = ROOT / "data" / "parsed"
SQL = ROOT / "sql"
LEVEL_RANK = {"FATAL": 8, "FAILURE": 7, "CRITICAL": 7, "SEVERE": 6, "ERROR": 5, "WARNING": 4, "WARN": 4,
              "INFO": 3, "DEBUG": 2}
BATCH = 100_000

TS = pa.timestamp("us")
SCHEMAS = {
    "bgl": pa.schema([("id", pa.int64()), ("ts", TS), ("unix_ts", pa.int64()), ("node", pa.string()),
                      ("rack", pa.string()), ("midplane", pa.string()), ("msg_type", pa.string()),
                      ("component", pa.string()), ("level", pa.string()), ("alert_category", pa.string()),
                      ("is_alert", pa.bool_()), ("message", pa.string()), ("template_id", pa.int32())]),
    "openstack": pa.schema([("id", pa.int64()), ("ts", TS), ("source_file", pa.string()), ("log_part", pa.string()),
                            ("service", pa.string()), ("pid", pa.int32()), ("level", pa.string()),
                            ("logger", pa.string()), ("request_id", pa.string()), ("user_id", pa.string()),
                            ("tenant_id", pa.string()), ("instance_id", pa.string()), ("client_ip", pa.string()),
                            ("http_method", pa.string()), ("http_path", pa.string()), ("http_status", pa.int32()),
                            ("resp_len", pa.int32()), ("latency_s", pa.float64()), ("labelled_anomaly", pa.bool_()),
                            ("message", pa.string()), ("template_id", pa.int32())]),
}
TEMPLATE_SCHEMA = pa.schema([("template_id", pa.int32()), ("dataset", pa.string()), ("template_text", pa.string()),
                             ("example_message", pa.string()), ("component", pa.string()),
                             ("line_count", pa.int64()), ("max_level", pa.string()),
                             ("first_seen", TS), ("last_seen", TS)])


def sources(sample: bool) -> dict[str, list[tuple[Path, str]]]:
    """dataset -> [(file, log_part)]."""
    if sample:
        s = ROOT / "data" / "samples"
        return {"bgl": [(s / "BGL_2k.log", "")], "openstack": [(s / "OpenStack_2k.log", "sample")]}
    raw = ROOT / "data" / "raw"
    bgl = sorted(raw.rglob("BGL.log"))
    os_files = sorted(raw.rglob("openstack_*.log"))
    if not bgl or not os_files:
        sys.exit("raw logs missing: run `python tasks.py fetch` first")
    return {"bgl": [(bgl[0], "")],
            "openstack": [(p, p.stem.removeprefix("openstack_")) for p in os_files]}


def parse_dataset(dataset: str, files: list[tuple[Path, str]]) -> None:
    schema, miner = SCHEMAS[dataset], make_miner()
    labelled = set()
    if dataset == "openstack":
        for p in files[0][0].parent.glob("anomaly_labels*.txt"):
            labelled |= parse_openstack.load_labels(p)
    stats: dict[int, dict] = {}
    rows, next_id, rejects = [], 1, []
    writer = pq.ParquetWriter(PARSED / f"{dataset}_events.parquet", schema)
    try:
        for path, part in files:
            with open(path, encoding="utf-8", errors="replace") as f:
                for line in f:
                    if not line.strip():
                        continue
                    row = (parse_bgl.parse_line(line) if dataset == "bgl"
                           else parse_openstack.parse_line(line, part, labelled))
                    if row is None:
                        rejects.append(f"{path.name}: {line.rstrip()}")
                        continue
                    tid = OFFSETS[dataset] + miner.add_log_message(row["message"])["cluster_id"]
                    row["id"], row["template_id"] = next_id, tid
                    next_id += 1
                    _track(stats, tid, row, row["component"] if dataset == "bgl" else row["service"])
                    rows.append(row)
                    if len(rows) >= BATCH:
                        writer.write_table(pa.Table.from_pylist(rows, schema))
                        rows = []
        if rows:
            writer.write_table(pa.Table.from_pylist(rows, schema))
    finally:
        writer.close()

    clusters = {OFFSETS[dataset] + c.cluster_id: c.get_template() for c in miner.drain.clusters}
    stats = _merge_duplicate_templates(stats, clusters, PARSED / f"{dataset}_events.parquet")
    templates = [{"template_id": tid, "dataset": dataset, "template_text": clusters[tid],
                  "example_message": s["example"], "component": s["components"].most_common(1)[0][0],
                  "line_count": s["count"], "max_level": s["max_level"],
                  "first_seen": s["first"], "last_seen": s["last"]} for tid, s in sorted(stats.items())]
    pq.write_table(pa.Table.from_pylist(templates, TEMPLATE_SCHEMA), PARSED / f"{dataset}_templates.parquet")
    (PARSED / f"rejects_{dataset}.txt").write_text("\n".join(rejects), encoding="utf-8")
    print(f"{dataset}: {next_id - 1:,} rows, {len(templates):,} templates, {len(rejects):,} rejects", flush=True)


def _track(stats: dict, tid: int, row: dict, component: str) -> None:
    s = stats.get(tid)
    if s is None:
        s = stats[tid] = {"count": 0, "example": row["message"], "components": Counter(),
                          "max_level": row["level"], "first": row["ts"], "last": row["ts"]}
    s["count"] += 1
    s["components"][component] += 1
    if LEVEL_RANK.get(row["level"], 1) > LEVEL_RANK.get(s["max_level"], 1):
        s["max_level"] = row["level"]
    s["first"], s["last"] = min(s["first"], row["ts"]), max(s["last"], row["ts"])


def _merge_duplicate_templates(stats: dict, clusters: dict, events: Path) -> dict:
    """Drain never matches an all-wildcard template (e.g. `<*>`), so it opens a new cluster per line.
    Fold clusters with identical final text into the lowest id and rewrite template_id in the Parquet."""
    canon: dict[str, int] = {}
    remap = {tid: canon.setdefault(clusters[tid], tid) for tid in sorted(stats)}
    merged: dict[int, dict] = {}
    for tid, s in sorted(stats.items()):
        m = merged.get(remap[tid])
        if m is None:
            merged[remap[tid]] = s
            continue
        m["count"] += s["count"]
        m["components"].update(s["components"])
        if LEVEL_RANK.get(s["max_level"], 1) > LEVEL_RANK.get(m["max_level"], 1):
            m["max_level"] = s["max_level"]
        m["first"], m["last"] = min(m["first"], s["first"]), max(m["last"], s["last"])
    if len(merged) < len(stats):
        table = pq.read_table(events)
        keys, vals = pa.array(list(remap), pa.int32()), pa.array(list(remap.values()), pa.int32())
        new_ids = pc.take(vals, pc.index_in(table["template_id"], keys))
        pq.write_table(table.set_column(table.schema.get_field_index("template_id"), "template_id", new_ids), events)
    return merged


def statements(path: Path) -> list[str]:
    """Split a .sql file on `;` at end of line; drop comment-only chunks."""
    chunks = path.read_text(encoding="utf-8").split(";\n")
    out = []
    for c in chunks:
        body = "\n".join(line for line in c.splitlines() if not line.strip().startswith("--")).strip().rstrip(";")
        if body:
            out.append(body)
    return out


def run_sql() -> None:
    from loglad_mcp.config import load_settings
    from loglad_mcp.core.db import SereneDb

    db = SereneDb(load_settings())
    if not db.ping():
        sys.exit("SereneDB not reachable: run `python tasks.py db` first")
    # where the SereneDB *server* reads data/parsed/ from (another SereneDB: a path or URL it can see)
    parquet_dir = os.environ.get("LOGLAD_PARQUET_DIR", "/data/parsed").rstrip("/")
    for path in sorted(SQL.glob("0*.sql")):
        t = time.perf_counter()
        for stmt in statements(path):
            stmt = stmt.replace("'/data/parsed/", f"'{parquet_dir}/")
            res = db.query(stmt, timeout_s=3600)
            if path.name.startswith("06_") and res.rows:
                print(f"  {res.rows}")
        print(f"{path.name}: {time.perf_counter() - t:.1f}s", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", action="store_true", help="use data/samples/*_2k.log")
    ap.add_argument("--skip-parse", action="store_true", help="reuse data/parsed/*.parquet")
    a = ap.parse_args()
    if not a.skip_parse:
        PARSED.mkdir(parents=True, exist_ok=True)
        for dataset, files in sources(a.sample).items():
            t = time.perf_counter()
            parse_dataset(dataset, files)
            print(f"  parsed in {time.perf_counter() - t:.1f}s", flush=True)
    run_sql()


if __name__ == "__main__":
    main()
