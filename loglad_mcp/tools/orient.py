"""describe_corpus (orient, every rung)."""
import threading
from typing import Annotated, Literal

from pydantic import Field

from loglad_mcp.core.envelope import make_scope
from loglad_mcp.core.timeparse import iso
from loglad_mcp.tools._base import (
    EPISODE_GAP,
    EVENTS,
    LABEL,
    Role,
    Sql,
    ToolResult,
    datasets_of,
    fmt_int,
    in_verify_mode,
    ownership,
    to_int,
    tool_call,
)

_cache: dict[str, tuple[dict, list[str]]] = {}
_lock = threading.Lock()

COMPONENT_COL = {"bgl": "component", "openstack": "service"}
LABELLED = {"bgl": "is_alert", "openstack": "labelled_anomaly"}


def _describe_one(q: Sql, ds: str, owners: dict) -> tuple[dict, int]:
    table, comp = EVENTS[ds], COMPONENT_COL[ds]
    head = q(f"SELECT count(*) AS n, min(ts) AS lo, max(ts) AS hi, "
             f"sum(CASE WHEN {LABELLED[ds]} THEN 1 ELSE 0 END) AS labelled FROM {table}")[0]
    comps = q(f"SELECT {comp} AS name, count(*) AS n FROM {table} GROUP BY {comp} ORDER BY n DESC, name")
    levels = q(f"SELECT level AS name, count(*) AS n FROM {table} GROUP BY level ORDER BY n DESC, name")
    templates = q("SELECT count(*) AS n FROM templates WHERE dataset = %s", (ds,))[0]["n"]
    episodes = q("SELECT count(*) AS n FROM episodes WHERE dataset = %s", (ds,))[0]["n"]
    components, unmapped = [], 0
    for r in comps:
        name = r["name"] if r["name"] is not None else "(none)"
        team = owners.get((ds, r["name"]), "Unowned")
        unmapped += to_int(r["n"]) if team == "Unowned" else 0
        components.append({"name": name, "team": team, "rows": to_int(r["n"])})
    return {
        "dataset": ds,
        "rows": to_int(head["n"]),
        "from": iso(head["lo"]),
        "to": iso(head["hi"]),
        "components": components,
        "levels": [{"name": r["name"] or "(none)", "rows": to_int(r["n"])} for r in levels],
        "templates": to_int(templates),
        "episodes": to_int(episodes),
        "episode_gap": EPISODE_GAP[ds],
        "labelled_rows": to_int(head["labelled"]),
    }, unmapped


def _compute(dataset: str) -> tuple[dict, list[str]]:
    q = Sql()
    owners = ownership(q)
    items, unmapped = [], 0
    for ds in datasets_of(dataset):
        item, n = _describe_one(q, ds, owners)
        if item["rows"]:
            items.append(item)
            unmapped += n
    notes = [
        "Timestamps are as logged (no time-zone conversion).",
        ("BGL episodes: repeats of one template on one midplane (node if no midplane) less than 10m apart. "
        "OpenStack episodes: repeats of one template in one service less than 60s apart."),
        "Teams come from the ownership table and are fictional; components without an owner count as 'Unowned'.",
        ("BGL labelled_rows = lines with an alert category; OpenStack labelled_rows = lines of instances in "
        "Loghub's anomaly label file."),
    ]
    if not items:
        notes.append("No rows are loaded for the requested dataset(s).")
    return {"datasets": items, "ownership_unmapped_rows": unmapped, "notes": notes}, q.statements


@tool_call("describe_corpus")
def describe_corpus(
    dataset: Annotated[Literal["bgl", "openstack", "both"], Field(description="Which dataset to describe.")] = "both",
    role: Annotated[Role, Field(description="Who the answer is for; pass it on every call.")] = "unknown",
) -> ToolResult:
    datasets_of(dataset)
    caveats: list[str] = []
    with _lock:
        cached = None if in_verify_mode() else _cache.get(dataset)
    if cached:
        data, sql = cached
        caveats.append("Served from the in-memory cache of the first call (the data is static); sql shows the "
                       "statements of that first run.")
    else:
        data, sql = _compute(dataset)
        with _lock:
            _cache.setdefault(dataset, (data, sql))
    items = data["datasets"]
    parts = [f"{LABEL[d['dataset']]}: {fmt_int(d['rows'])} lines from {d['from'][:10]} to {d['to'][:10]}, "
             f"{fmt_int(d['templates'])} templates, {fmt_int(d['episodes'])} episodes" for d in items]
    summary = "; ".join(parts) + "." if parts else "No data loaded."
    frm = min((d["from"] for d in items), default=None)
    to = max((d["to"] for d in items), default=None)
    scope = make_scope(dataset, frm, to)
    total = sum(d["rows"] for d in items)
    return ToolResult(summary, scope, data, total, len(items), False, sql, caveats)
