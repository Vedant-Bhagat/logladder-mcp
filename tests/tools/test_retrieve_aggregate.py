"""describe_corpus, search_logs, get_timeline, trace_request, count_by, trend with FakeDb."""
from fakes import assert_valid, bgl_line, os_line, templates_rule, ts

from loglad_mcp.core.db import DbError
from loglad_mcp.tools._base import char_highlights
from loglad_mcp.tools.aggregate import buckets, count_by, series_change, trend
from loglad_mcp.tools.orient import describe_corpus
from loglad_mcp.tools.retrieve import get_timeline, search_logs, trace_request


def _describe_rules(db):
    db.on(r"count\(\*\) AS n, min\(ts\) AS lo, max\(ts\) AS hi, sum", lambda s, p: [{
        "n": 2000, "lo": ts("2005-06-03T15:42:50"), "hi": ts("2006-01-03T07:13:09"), "labelled": 30}])
    db.on(r"SELECT component AS name", [{"name": "KERNEL", "n": 1800}, {"name": "iar", "n": 2}])
    db.on(r"SELECT service AS name", [{"name": "nova-api", "n": 1500}])
    db.on(r"SELECT level AS name", [{"name": "INFO", "n": 1900}, {"name": "FATAL", "n": 100}])
    db.on(r"FROM templates WHERE dataset", [{"n": 106}])
    db.on(r"FROM episodes WHERE dataset = %s$", [{"n": 1595}])


def test_describe_corpus_valid_and_cached(env):
    _describe_rules(env.db)
    a = describe_corpus()
    assert_valid(a)
    assert a["error"] is None and a["data"]["ownership_unmapped_rows"] == 2 * 1  # 'iar' (bgl) unowned
    bgl = a["data"]["datasets"][0]
    assert bgl["components"][1] == {"name": "iar", "team": "Unowned", "rows": 2}
    n = len(env.db.queries)
    b = describe_corpus()
    assert len(env.db.queries) == n and b["data"] == a["data"] and b["receipt_id"] != a["receipt_id"]


def _search_rules(db, total=120):
    rows = [bgl_line(1201, "2005-06-14T09:12:03.512345", "über TLB error interrupt", "FATAL", 42, offsets=[6, 9]),
            bgl_line(1207, "2005-06-14T09:12:04", "data TLB error interrupt", "FATAL", 42, offsets=[5, 8, 9, 14])]
    db.on(r"FROM bgl_idx WHERE .*ORDER BY BM25", rows)
    db.on(r"SELECT count\(\*\) AS n FROM bgl_idx", [{"n": total}])


def test_search_logs_envelope_truncation_and_highlights(env):
    _search_rules(env.db)
    out = search_logs(query="TLB error", dataset="bgl", level="fatal", start="2005-06-01", end="2005-06-30",
                      match="phrase", limit=500, role="engineer")
    assert_valid(out)
    assert out["total_matches"] == 120 and out["returned"] == 2 and out["truncated"] is True
    assert any(c.startswith("Sample of 2 of 120") for c in out["caveats"])
    assert "limit clamped from 500 to 50" in out["caveats"]
    assert out["data"]["lines"][0]["highlights"] == [[5, 8]]  # bytes 6..9 after 'ü' -> chars 5..8
    assert out["scope"]["filters"] == {"level": "FATAL"} and out["scope"]["to"] == "2005-06-30"
    sql = [q for q, _ in env.db.queries if "bgl_idx" in q]
    assert all("ts_phrase(%s)" in q and "TLB" not in q for q in sql)  # user text is parameterised
    assert len(out["sql"]) == 2 and out["receipt_id"] == "R-0001"


def test_search_logs_fuzzy_builds_one_term_per_word(env):
    _search_rules(env.db, total=2)
    out = search_logs(query="TLB eror", dataset="bgl", match="fuzzy")
    assert out["error"] is None and out["truncated"] is False
    q, params = env.db.queries[0]
    assert q.count("ts_levenshtein(%s, 1)") == 2 and params[:2] == ["tlb", "eror"]


def test_search_logs_errors_become_envelopes(env):
    bad = search_logs(query="x", dataset="bgl", start="2005-07-01", end="2005-06-01")
    assert_valid(bad)
    assert bad["error"]["code"] == "invalid_input" and bad["receipt_id"] == "R-0001"
    env.db.on(r"FROM bgl_idx", DbError("timeout", "query exceeded 10s"))
    t = search_logs(query="x", dataset="bgl")
    assert t["error"] == {"code": "timeout", "message": "query exceeded 10s"}
    env.db.on(r"FROM bgl_idx", ZeroDivisionError("boom"))
    i = search_logs(query="x", dataset="bgl")
    assert i["error"]["code"] == "internal"
    assert search_logs(query="  ", dataset="bgl")["error"]["code"] == "invalid_input"


def test_char_highlights_clip_and_bad_input():
    assert char_highlights("abcdef", [1, 3, 4, 100], limit=5) == [[1, 3], [4, 5]]
    assert char_highlights("abc", "[0, 1]") == [[0, 1]]
    assert char_highlights("abc", None) == []


def _timeline_rules(db):
    anchor = bgl_line(50, "2005-06-14T09:12:03", "data TLB error interrupt", "FATAL", 42)
    db.on(r"FROM bgl_events WHERE id = %s", [anchor])

    def groups(sql, params):
        if "ts < %s OR" in sql:
            return [{"template_id": 17, "n": 312, "first_ts": ts("2005-06-14T09:02:10"),
                     "last_ts": ts("2005-06-14T09:12:01"), "sample_id": 40, "lvl_rank": 3}]
        return [{"template_id": 88, "n": 1, "first_ts": ts("2005-06-14T09:13:10"),
                 "last_ts": ts("2005-06-14T09:13:10"), "sample_id": 60, "lvl_rank": 8}]
    db.on(r"GROUP BY template_id", groups)
    db.on(r"FROM bgl_events WHERE id IN", [bgl_line(40, "2005-06-14T09:02:10", "instruction cache parity error", "INFO", 17),
                                           bgl_line(60, "2005-06-14T09:13:10", "ciod: failed", "FATAL", 88)])
    db.on(r"FROM templates WHERE template_id IN", templates_rule({17: ("bgl", "instruction cache parity <*>"),
                                                                 88: ("bgl", "ciod: failed <*>")}))


def test_get_timeline_groups(env):
    _timeline_rules(env.db)
    out = get_timeline(dataset="bgl", anchor_id=50, role="engineer")
    assert_valid(out)
    d = out["data"]
    assert d["window"] == {"before_s": 600, "after_s": 300, "scope": "midplane", "scope_value": "R02-M1"}
    assert d["before"][0]["count"] == 312 and d["before"][0]["sample"]["repeat_count"] == 312
    assert d["after"][0]["level"] == "FATAL" and out["total_matches"] == 314
    assert out["scope"]["filters"] == {"midplane": "R02-M1"}


def test_get_timeline_input_errors(env):
    _timeline_rules(env.db)
    assert get_timeline(dataset="bgl")["error"]["code"] == "invalid_input"
    assert get_timeline(dataset="bgl", anchor_id=1, at="2005-06-14")["error"]["code"] == "invalid_input"
    assert get_timeline(dataset="bgl", at="2005-06-14T09:00")["error"]["code"] == "invalid_input"  # no scope_value
    assert get_timeline(dataset="bgl", anchor_id=50, scope="service")["error"]["code"] == "invalid_input"
    env.db.on(r"FROM bgl_events WHERE id = %s", [])
    assert get_timeline(dataset="bgl", anchor_id=999)["error"]["code"] == "not_found"


def test_trace_request(env):
    env.db.on(r"SELECT DISTINCT instance_id", [{"instance_id": "i-1"}])
    env.db.on(r"GROUP BY service", [
        {"service": "nova-compute", "first_ts": ts("2017-05-16T00:00:05"), "last_ts": ts("2017-05-16T00:00:09"),
         "n": 3, "lvl_rank": 5, "labelled": 1},
        {"service": "nova-api", "first_ts": ts("2017-05-16T00:00:01"), "last_ts": ts("2017-05-16T00:00:02"),
         "n": 2, "lvl_rank": 3, "labelled": 0}])
    env.db.on(r"ORDER BY ts, id LIMIT", [os_line(1, "2017-05-16T00:00:01", "GET /servers")])
    env.db.on(r"JOIN templates t", [{"template_text": "Instance failed to spawn <*>"}])
    out = trace_request(request_id="req-1")
    assert_valid(out)
    hops = out["data"]["hops"]
    assert [h["service"] for h in hops] == ["nova-api", "nova-compute"]
    assert hops[0]["gap_from_prev_s"] is None and hops[1]["gap_from_prev_s"] == 3.0
    assert hops[1]["max_level"] == "ERROR" and out["data"]["outcome"] == "Instance failed to spawn <*>"
    assert out["data"]["labelled_anomaly"] is True and out["data"]["instance_id"] == "i-1"
    assert out["total_matches"] == 5 and out["truncated"] is True
    assert trace_request()["error"]["code"] == "invalid_input"
    env.db.on(r"GROUP BY service", [])
    assert trace_request(instance_id="nope")["error"]["code"] == "not_found"


def test_count_by_rows_plus_other_equals_total(env):
    env.db.on(r"AS k, count\(\*\) AS n FROM episodes", [{"k": f"C{i}", "n": 100 - i} for i in range(12)])
    out = count_by(dataset="bgl", group_by="component", top_n=3, role="team_lead")
    assert_valid(out)
    d = out["data"]
    assert len(d["rows"]) == 3 and d["other"]["groups"] == 9
    assert sum(r["count"] for r in d["rows"]) + d["other"]["count"] == d["total"] == out["total_matches"]
    assert out["truncated"] is True and out["scope"]["unit"] == "episodes" and out["scope"]["episode_gap"] == "10m"
    assert d["rows"][0]["team"] == "Unowned"


def test_count_by_both_prefixes_labels_and_rejects_bad_combo(env):
    env.db.on(r"AS k, count\(\*\) AS n FROM episodes", lambda s, p: [{"k": "ERROR", "n": 5 if p[0] == "bgl" else 3}])
    out = count_by(dataset="both", group_by="level")
    assert_valid(out)
    assert [r["label"] for r in out["data"]["rows"]] == ["bgl · ERROR", "openstack · ERROR"]
    bad = count_by(dataset="bgl", group_by="http_status")
    assert bad["error"]["code"] == "invalid_input" and "Valid options: dataset, team" in bad["error"]["message"]
    assert count_by(dataset="bgl", group_by="alert_category")["error"]["code"] == "invalid_input"


def test_count_by_lines_team_joins_ownership(env):
    env.db.on(r"AS k, count\(\*\) AS n FROM bgl_events e LEFT JOIN ownership",
              [{"k": "HPC Kernel & Runtime", "n": 9}, {"k": "Unowned", "n": 1}])
    out = count_by(dataset="bgl", group_by="team", unit="lines", team="Unowned")
    assert_valid(out)
    assert out["data"]["rows"][0]["team"] == "HPC Kernel & Runtime" and out["scope"]["episode_gap"] is None


def test_buckets_and_change():
    from datetime import datetime
    b = buckets(datetime(2005, 6, 1), datetime(2005, 6, 20), "week")
    assert b[0].isoformat() == "2005-05-30" and len(b) == 3  # Mondays
    c = series_change([1, 2, 3, 4], use_mean=False)
    assert c == {"first_half": 3.0, "second_half": 7.0, "slope_per_bucket": 1.0, "last_vs_prev_pct": 33.3}
    assert series_change([5, 0], use_mean=False)["last_vs_prev_pct"] == -100.0
    assert series_change([0, 5], use_mean=False)["last_vs_prev_pct"] is None


def test_trend_fills_buckets_and_limits_series(env):
    rows = [{"t": ts("2005-06-06"), "g": f"T{i}", "v": 10 + i, "w": 10 + i} for i in range(10)]
    env.db.on(r"date_trunc\('week'", rows)
    out = trend(dataset="bgl", metric="episodes", group_by="team", start="2005-06-01", end="2005-06-20",
                top_series=99)
    assert_valid(out)
    d = out["data"]
    assert len(d["series"]) == 8 and "top_series clamped from 99 to 8" in out["caveats"]
    assert [p["t"] for p in d["series"][0]["points"]] == ["2005-05-30", "2005-06-06", "2005-06-13", "2005-06-20"]
    assert d["series"][0]["points"][0]["v"] == 0 and d["series"][0]["name"] == "T9"
    assert trend(dataset="bgl", metric="latency_p95")["error"]["code"] == "invalid_input"


def test_trend_error_rate_divides_by_lines(env):
    env.db.on(r"date_trunc\('day'", [{"t": ts("2017-05-16"), "v": 1, "w": 4}])
    out = trend(dataset="openstack", metric="error_rate", bucket="day")
    assert_valid(out)
    assert out["data"]["series"][0]["points"] == [{"t": "2017-05-16", "v": 0.25}]
    assert any("Only 1 day bucket" in c for c in out["caveats"])
