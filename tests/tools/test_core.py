"""core/: limits, timeparse, envelope, receipts, console, context."""
import time
from datetime import datetime

import pytest
from fakes import FakeDb, assert_valid

from loglad_mcp.core import context as context_mod
from loglad_mcp.core.console import HttpConsoleClient, make_event, tone_for_level
from loglad_mcp.core.envelope import digest, error_envelope, make_envelope, make_scope
from loglad_mcp.core.limits import clamp, truncate_message
from loglad_mcp.core.receipts import NOT_PERSISTED, ReceiptStore
from loglad_mcp.core.timeparse import parse_iso, resolve_window


def test_clamp_reports_caveat():
    cav = []
    assert clamp(200, 1, 50, cav, "limit") == 50
    assert cav == ["limit clamped from 200 to 50"]
    assert clamp(10, 1, 50, cav) == 10 and len(cav) == 1


def test_truncate_message():
    assert truncate_message("a" * 400) == "a" * 400
    out = truncate_message("a" * 500)
    assert len(out) == 401 and out.endswith("…")


def test_date_only_end_includes_whole_day(env):
    w = resolve_window(env.db, "bgl", "2005-06-01", "2005-06-30")
    assert w.start == datetime(2005, 6, 1) and w.end == datetime(2005, 7, 1)
    assert (w.frm, w.to) == ("2005-06-01", "2005-06-30")
    w = resolve_window(env.db, "bgl", "2005-06-01T10:00", "2005-06-01T11:00")
    assert w.end == datetime(2005, 6, 1, 11)


def test_missing_bounds_use_dataset_span(env):
    w = resolve_window(env.db, "bgl", None, None)
    assert w.full_span and w.frm.startswith("2005-06-03") and w.to.startswith("2006-01-03")
    assert w.end > datetime(2006, 1, 3, 7, 13, 9)  # inclusive of the last line


@pytest.mark.parametrize("start,end", [("2005-07-01", "2005-06-01"), ("2005-06-01T10:00", "2005-06-01T10:00"),
                                       ("June", None), ("2005-13-01", None)])
def test_bad_windows_raise(env, start, end):
    with pytest.raises(ValueError):
        resolve_window(env.db, "bgl", start, end)


def test_parse_iso_formats():
    assert parse_iso("2005-06-14T09:12:03.512345") == datetime(2005, 6, 14, 9, 12, 3, 512345)
    assert parse_iso("2005-06-14 09:12") == datetime(2005, 6, 14, 9, 12)


def test_envelope_and_error_envelope_shape():
    env = make_envelope("count_by", "manager", "x " * 300, make_scope("bgl"), {}, total_matches=None, returned=0,
                        truncated=False, sql=[], runtime_ms=-3, caveats=["a", "a"])
    assert len(env["summary"]) <= 400 and env["runtime_ms"] == 0 and env["caveats"] == ["a"]
    err = error_envelope("search_logs", "engineer", "invalid_input", "bad", make_scope("bgl", "2005-06-01"))
    err["receipt_id"] = "R-0001"
    assert_valid(err)
    assert make_scope("weird", "not a date")["dataset"] == "none"


def test_digest_is_canonical():
    assert digest({"b": 1, "a": [1, 2]}) == digest({"a": [1, 2], "b": 1})
    assert len(digest({})) == 64


def _env(tool="describe_corpus"):
    return make_envelope(tool, "unknown", "s", make_scope("none"), {"x": 1}, total_matches=None, returned=1,
                         truncated=False, sql=["SELECT 1"], runtime_ms=1, caveats=[])


def test_receipt_ids_continue_after_db_max():
    db = FakeDb().on(r"max\(CAST", [{"n": 41}])
    store = ReceiptStore(db, "s")
    assert store.write(_env(), {}) == "R-0042"
    assert store.write(_env(), {}) == "R-0043"
    assert len(db.inserts) == 2 and store.count() == 2
    rec = store.get("r-42")
    assert rec["result_digest"] == digest({"x": 1}) and rec["sql"] == ["SELECT 1"]


def test_receipt_survives_failed_insert():
    db = FakeDb()
    db.fail_inserts = True
    store = ReceiptStore(db, "s")
    env = _env()
    rid = store.write(env, {"dataset": "both"})
    assert env["receipt_id"] == rid and NOT_PERSISTED in env["caveats"]
    assert store.get(rid)["params"] == {"dataset": "both"}


def test_receipt_loaded_from_db():
    db = FakeDb().on(r"FROM receipts WHERE receipt_id", [{
        "receipt_id": "R-0007", "created_at": datetime(2026, 10, 18, 12), "session_id": "old", "tool": "count_by",
        "role": "manager", "params_json": '{"dataset":"bgl"}', "sql_json": '["SELECT 1"]',
        "scope_json": '{"dataset":"bgl","from":null,"to":null,"filters":{}}', "total_matches": 5, "returned": 1,
        "truncated": False, "runtime_ms": 3, "result_digest": "d", "data_json": '{"total":5}', "error": None}])
    rec = ReceiptStore(db, "s").get("R-0007")
    assert rec["created_at"] == "2026-10-18T12:00:00" and rec["data"] == {"total": 5}
    assert ReceiptStore(FakeDb(), "s").get("R-0099") is None
    assert ReceiptStore(FakeDb(), "s").get("nonsense") is None


def test_tone_for_level():
    assert [tone_for_level(x) for x in ("FATAL", "failure", "CRITICAL", "SEVERE", "ERROR", "WARNING", "INFO", None)] \
        == ["critical", "critical", "critical", "error", "error", "warning", "info", "info"]


def test_make_event_fields():
    e = make_event("status", "manager", {"receipt_count": 1, "claims": None})
    assert e["contract"] == 1 and len(e["event_id"]) == 32 and e["ts"].endswith("Z")


def test_console_down_returns_false_quickly():
    t = time.perf_counter()
    assert HttpConsoleClient("http://127.0.0.1:9").post({"x": 1}) is False
    assert time.perf_counter() - t < 5


def test_ctx_before_init_raises(monkeypatch):
    monkeypatch.setattr(context_mod, "_CTX", None)
    with pytest.raises(RuntimeError, match="init_context"):
        context_mod.ctx()


def test_init_context_does_not_touch_db():
    db = FakeDb()
    from loglad_mcp.config import Settings
    c = context_mod.init_context(db, Settings(serenedb_dsn="", session_id="x"))
    assert db.queries == [] and c.receipts.session_id == "x" and isinstance(c.console, HttpConsoleClient)


def test_receipt_store_backs_off_after_db_failure(monkeypatch):
    from loglad_mcp.core import receipts as receipts_mod
    from loglad_mcp.core.db import DbError
    db = FakeDb().on(r"max\(CAST", DbError("db_error", "SereneDB unreachable"))
    store = ReceiptStore(db, "s")
    assert store.write(_env(), {}) == "R-0001"  # numbered from memory
    n_queries, n_inserts = len(db.queries), len(db.inserts)
    e2 = _env()
    assert store.write(e2, {}) == "R-0002" and NOT_PERSISTED in e2["caveats"]
    assert len(db.queries) == n_queries and len(db.inserts) == n_inserts  # database skipped during backoff
    with pytest.raises(DbError):
        store.get("R-0050")  # not in memory, database known to be down
    monkeypatch.setattr(receipts_mod, "BACKOFF_S", 0.0)
    store._down_until = 0.0
    db.on(r"max\(CAST", [{"n": 1}])  # back, with an older receipt in the table
    assert store.write(_env(), {}) == "R-0003" and len(db.inserts) == n_inserts + 1
