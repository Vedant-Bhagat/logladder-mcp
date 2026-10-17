"""Parsers, template mining and SQL files — no database needed."""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from ingest import parse_bgl, parse_openstack
from ingest.load import statements
from ingest.templates import make_miner

SAMPLES = ROOT / "data" / "samples"


def test_bgl_sample_parses_fully():
    lines = (SAMPLES / "BGL_2k.log").read_text(encoding="utf-8").splitlines()
    rows = [parse_bgl.parse_line(x) for x in lines]
    assert len(rows) == 2000 and all(rows)
    first = rows[0]
    assert first["midplane"] == "R02-M1" and first["rack"] == "R02" and first["component"] == "KERNEL"
    assert first["alert_category"] is None and first["is_alert"] is False
    assert first["message"] == "instruction cache parity error corrected"
    assert any(r["is_alert"] for r in rows)


def test_bgl_rejects_garbage_and_handles_missing_message():
    assert parse_bgl.parse_line("not a log line") is None
    row = parse_bgl.parse_line("- 1 2005.06.03 NULL 2005-06-03-15.42.50.675872 NULL RAS KERNEL INFO")
    assert row["message"] == "" and row["node"] is None and row["midplane"] is None


def test_openstack_sample_parses_fully():
    lines = (SAMPLES / "OpenStack_2k.log").read_text(encoding="utf-8").splitlines()
    rows = [parse_openstack.parse_line(x, "sample", set()) for x in lines]
    assert len(rows) == 2000 and all(rows)
    api = rows[0]
    assert api["service"] == "nova-api" and api["http_method"] == "GET" and api["http_status"] == 200
    assert api["request_id"].startswith("req-") and api["latency_s"] > 0 and api["client_ip"] == "10.11.10.1"
    assert {r["service"] for r in rows} == {"nova-api", "nova-compute", "nova-scheduler"}
    assert any(r["instance_id"] for r in rows) and not any(r["labelled_anomaly"] for r in rows)


def test_openstack_labels_and_dash_context():
    uuid = "b9000564-fe1a-409b-b8cc-1e88b294cd1d"
    line = (f"nova-compute.log.1.2017-05-16_13:55:31 2017-05-16 00:00:10.302 2931 INFO nova.virt.libvirt.driver "
            f"[-] [instance: {uuid}] Instance spawned successfully.")
    row = parse_openstack.parse_line(line, "abnormal", {uuid})
    assert row["request_id"] is None and row["instance_id"] == uuid and row["labelled_anomaly"] is True


def test_templates_mask_variables():
    miner = make_miner()
    a = miner.add_log_message("ciod: failed to read message prefix on control stream (CioStream socket to 172.16.96.116:33569")
    b = miner.add_log_message("ciod: failed to read message prefix on control stream (CioStream socket to 172.16.96.117:40001")
    assert a["cluster_id"] == b["cluster_id"]
    assert "<*>" in miner.drain.id_to_cluster[a["cluster_id"]].get_template()


def _columns(sql: str) -> dict[str, list[str]]:
    tables = re.findall(r"CREATE TABLE (?:IF NOT EXISTS )?(\w+) \((.*?)\n\);", sql, re.DOTALL)
    return {t: re.findall(r"^\s+(\w+)\s+[A-Z]", body, re.MULTILINE) for t, body in tables}


def test_schema_sql_matches_contract():
    contract = _columns((ROOT / "contracts/db_schema.sql").read_text(encoding="utf-8"))
    ours = _columns((ROOT / "sql/01_schema.sql").read_text(encoding="utf-8"))
    assert ours == contract and len(contract) == 6


def test_sql_files_split_into_statements():
    counts = {p.name: len(statements(p)) for p in sorted((ROOT / "sql").glob("0*.sql"))}
    assert counts["01_schema.sql"] == 11 and counts["02_load.sql"] == 3 and counts["05_indexes.sql"] == 6


def test_openstack_line_with_empty_message_parses():
    line = "nova-compute.log.1.2017-05-16_13:55:31 2017-05-16 03:19:45.356 2931 ERROR oslo_service.periodic_task"
    row = parse_openstack.parse_line(line, "normal1", set())
    assert row["logger"] == "oslo_service.periodic_task" and row["message"] == "" and row["level"] == "ERROR"


def test_duplicate_templates_merge_and_parquet_is_rewritten(tmp_path):
    from datetime import datetime

    import pyarrow as pa
    import pyarrow.parquet as pq

    from ingest.load import _merge_duplicate_templates

    t0, t1 = datetime(2005, 1, 1), datetime(2005, 1, 2)

    def stat(n, level, ts):
        from collections import Counter
        return {"count": n, "example": "x", "components": Counter({"KERNEL": n}), "max_level": level,
                "first": ts, "last": ts}

    events = tmp_path / "e.parquet"
    pq.write_table(pa.table({"template_id": pa.array([1, 2, 3, 2], pa.int32())}), events)
    merged = _merge_duplicate_templates({1: stat(1, "INFO", t1), 2: stat(2, "FATAL", t0), 3: stat(1, "INFO", t0)},
                                        {1: "<*>", 2: "a <*>", 3: "<*>"}, events)
    assert sorted(merged) == [1, 2]
    assert merged[1]["count"] == 2 and merged[1]["first"] == t0 and merged[1]["last"] == t1
    assert pq.read_table(events)["template_id"].to_pylist() == [1, 2, 1, 2]
