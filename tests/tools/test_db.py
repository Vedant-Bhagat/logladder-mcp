"""Against SereneDB with sample data (`python tasks.py db` + `python tasks.py data --sample`). Skipped otherwise.

    pytest -m db tests/tools -q
"""
import pytest
from fakes import FakeConsole, assert_valid, assert_valid_panel

pytestmark = pytest.mark.db


@pytest.fixture(scope="module")
def live():
    from loglad_mcp.config import load_settings
    from loglad_mcp.core import timeparse
    from loglad_mcp.core.context import ToolContext, set_context
    from loglad_mcp.core.db import SereneDb
    from loglad_mcp.core.receipts import ReceiptStore
    from loglad_mcp.tools import orient

    settings = load_settings()
    db = SereneDb(settings)
    if not db.ping():
        pytest.skip("SereneDB not reachable")
    if not db.query("SELECT count(*) AS n FROM bgl_events").rows[0]["n"]:
        pytest.skip("no data loaded")
    timeparse.clear_span_cache()
    orient._cache.clear()
    console = FakeConsole()
    set_context(ToolContext(db, settings, console, ReceiptStore(db, "pytest-db")))
    return db, console


@pytest.mark.parametrize("index,pred", [("bgl_idx", "message @@ plainto_tsquery('error')"),
                                        ("os_idx", "message @@ ts_phrase('instance')")])
def test_search_uses_inverted_index(live, index, pred):
    db, _ = live
    plan = "\n".join(str(v) for r in db.query(f"EXPLAIN SELECT id FROM {index} WHERE {pred}").rows for v in r.values())
    assert "IRESEARCH_SCAN" in plan.upper(), plan


def test_every_match_mode_and_time_filter(live):
    from loglad_mcp.tools.retrieve import search_logs
    for match in ("terms", "phrase", "fuzzy"):
        out = search_logs(query="error", dataset="bgl", match=match, start="2005-06-01", end="2006-12-31")
        assert_valid(out)
        assert out["error"] is None, out["error"]
    out = search_logs(query="instance", dataset="openstack", limit=3)
    assert out["error"] is None and out["returned"] <= 3
    if out["returned"]:
        line = out["data"]["lines"][0]
        for s, e in line["highlights"]:
            assert line["message"][s:e].lower() == "instance"


def test_all_tools_and_display(live):
    db, console = live
    from loglad_mcp.tools.registry import TOOLS
    t = {x.name: x.fn for x in TOOLS}
    q = lambda sql: db.query(sql).rows
    anchor = q("SELECT min(id) AS id FROM bgl_events WHERE level = 'FATAL'")[0]["id"]
    tids = [r["template_id"] for r in q("SELECT template_id FROM templates WHERE dataset = 'bgl' "
                                       "ORDER BY line_count DESC LIMIT 2")]
    req = q("SELECT min(request_id) AS r FROM os_events WHERE request_id IS NOT NULL")[0]["r"]
    outs = {
        "describe_corpus": t["describe_corpus"](),
        "get_timeline": t["get_timeline"](dataset="bgl", anchor_id=anchor),
        "trace_request": t["trace_request"](request_id=req),
        "count_by": t["count_by"](dataset="both", group_by="team"),
        "trend": t["trend"](dataset="openstack", metric="latency_p95", bucket="day"),
        "recurring_problems": t["recurring_problems"](),
        "rank_risks": t["rank_risks"](),
        "test_hypothesis": t["test_hypothesis"](dataset="bgl", cause_template_id=tids[1], effect_template_id=tids[0]),
    }
    for name, env in outs.items():
        assert_valid(env)
        assert env["error"] is None, (name, env["error"])
        v = t["verify_receipt"](receipt_id=env["receipt_id"])
        assert v["error"] is None and v["data"]["match"], (name, v)
    for rid, kind in ((outs["get_timeline"]["receipt_id"], "lines"), (outs["count_by"]["receipt_id"], "table"),
                      (outs["trend"]["receipt_id"], "trend"), (outs["rank_risks"]["receipt_id"], "risks")):
        assert t["show_evidence"](receipt_id=rid, kind=kind, title="db test")["error"] is None
        assert_valid_panel(console.events[-1])
    # receipts persisted: a fresh store reads them back from the database
    from loglad_mcp.core.receipts import ReceiptStore
    rec = ReceiptStore(db, "other").get(outs["count_by"]["receipt_id"])
    assert rec is not None and rec["tool"] == "count_by"
