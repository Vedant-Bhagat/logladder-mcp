"""recurring_problems, rank_risks, test_hypothesis, check_answer, receipts tools, display tools, registry."""
import inspect
import json
import typing
from pathlib import Path

from fakes import assert_valid, assert_valid_panel, bgl_line, templates_rule, ts

from loglad_mcp.tools.analyse import rank_risks, recurring_problems
from loglad_mcp.tools.display import show_evidence, show_explainer
from loglad_mcp.tools.reason import check_answer, get_receipt, verify_receipt
from loglad_mcp.tools.reason import test_hypothesis as hypothesis_tool
from loglad_mcp.tools.registry import TOOLS
from loglad_mcp.tools.retrieve import search_logs

ROOT_SCHEMA = json.loads((Path(__file__).resolve().parents[2] / "contracts" / "envelope.schema.json").read_text(encoding="utf-8"))


def _stats(sql, params):
    rows = [{"template_id": 42, "episodes": 30, "lines": 300, "scopes": 9, "lvl_rank": 8, "labelled": 150,
             "team": "HPC Kernel & Runtime", "component": "KERNEL", "first_half": 10},
            {"template_id": 17, "episodes": 20, "lines": 900, "scopes": 3, "lvl_rank": 3, "labelled": 0,
             "team": "HPC Kernel & Runtime", "component": "KERNEL", "first_half": 15},
            {"template_id": 88, "episodes": 5, "lines": 5, "scopes": 5, "lvl_rank": 5, "labelled": 5,
             "team": "HPC Applications Support", "component": "APP", "first_half": 2},
            {"template_id": 99, "episodes": 1, "lines": 1, "scopes": 1, "lvl_rank": 3, "labelled": 0,
             "team": "Unowned", "component": "iar", "first_half": 1}]
    return rows if "bgl" in params else []


def _analyse_rules(db):
    db.on(r"GROUP BY template_id ORDER BY episodes DESC", _stats)
    db.on(r"SELECT template_id, count\(\*\) AS n FROM episodes", [{"template_id": 42, "n": 15}, {"template_id": 88, "n": 0}])
    db.on(r"FROM templates WHERE template_id IN", templates_rule({42: ("bgl", "data TLB error interrupt"),
                                                                 17: ("bgl", "instruction cache parity <*>"),
                                                                 88: ("bgl", "ciod: failed <*>"),
                                                                 99: ("bgl", "odd <*>")}))
    db.on(r"count\(DISTINCT instance_id\)", [])


def test_recurring_problems_default_window_and_change(env):
    _analyse_rules(env.db)
    out = recurring_problems(dataset="bgl", top_n=2, role="team_lead")
    assert_valid(out)
    items = out["data"]["items"]
    assert [i["template_id"] for i in items] == [42, 17] and items[0]["max_level"] == "FATAL"
    assert items[0]["prev_episodes"] == 15 and items[0]["change_pct"] == 100.0
    assert items[1]["prev_episodes"] == 0 and items[1]["change_pct"] is None
    assert out["scope"]["from"].startswith("2005-12-04") and out["truncated"] is True
    assert any("historical" in c for c in out["caveats"])
    stats_call = next(p for q, p in env.db.queries if "ORDER BY episodes DESC" in q)
    assert (stats_call[2] - stats_call[1]).days == 30
    assert recurring_problems(min_level="LOUD")["error"]["code"] == "invalid_input"


def test_rank_risks_scores_and_stability(env):
    _analyse_rules(env.db)
    out = rank_risks(dataset="both", role="manager")
    assert_valid(out)
    items = out["data"]["items"]
    assert len(items) == 3 and items[0]["template_id"] == 42  # 99 has 1 episode < min_episodes
    assert items[0]["raw"] == {"episodes": 30, "distinct_scopes": 9, "first_half_episodes": 10,
                               "second_half_episodes": 20, "max_level": "FATAL", "labelled_share": 0.5}
    assert 0 <= items[0]["stability_top3"] <= 1 and items[0]["score"] >= items[1]["score"]
    assert abs(sum(out["data"]["weights"].values()) - 1) < 1e-3
    assert rank_risks(weights={"Q": 1})["error"]["code"] == "invalid_input"
    assert rank_risks(weights={"F": 0, "S": 0, "T": 0, "V": 0, "L": 0})["error"]["code"] == "invalid_input"


def test_test_hypothesis_verdict(env):
    env.db.on(r"FROM templates WHERE template_id IN", templates_rule({17: ("bgl", "parity <*>"), 42: ("bgl", "TLB")}))

    def intervals(sql, params):
        tid = params[1]
        if tid == 42:  # effects: 6 episodes on 6 midplanes, one per day
            return [{"episode_id": i, "s": f"M{i}", "a": ts(f"2005-06-1{i}T10:00:00"), "b": ts(f"2005-06-1{i}T10:01:00")}
                    for i in range(6)]
        return [{"episode_id": 100 + i, "s": f"M{i}", "a": ts(f"2005-06-1{i}T09:55:00"),
                 "b": ts(f"2005-06-1{i}T09:58:00")} for i in range(5)]
    env.db.on(r"SELECT episode_id, scope_key AS s", intervals)
    out = hypothesis_tool(dataset="bgl", cause_template_id=17, effect_template_id=42, start="2005-06-10",
                          end="2005-06-16", role="engineer")
    assert_valid(out)
    d = out["data"]
    assert d["effect_episodes"] == 6 and d["supported_episodes"] == 5
    assert d["forward"]["support"] == round(5 / 6, 4) and d["verdict"] == "strong"
    assert len(d["examples"]) == 3 and len(d["counter_examples"]) == 1
    assert "Precedence is association, not proof of cause." in out["caveats"]
    assert hypothesis_tool(dataset="bgl", cause_template_id=1, effect_template_id=1)["error"]["code"] == "invalid_input"
    assert hypothesis_tool(dataset="bgl", cause_template_id=5, effect_template_id=6)["error"]["code"] == "not_found"


def _search(env):
    env.db.on(r"FROM bgl_idx WHERE .*ORDER BY BM25",
              [bgl_line(7, "2005-06-14T09:12:03", "data TLB error interrupt", "FATAL", 42, offsets=[5, 8])])
    env.db.on(r"SELECT count\(\*\) AS n FROM bgl_idx", [{"n": 1284}])
    return search_logs(query="TLB", dataset="bgl", role="engineer")


def test_receipt_tools(env):
    s = _search(env)
    g = get_receipt(receipt_id=s["receipt_id"])
    assert_valid(g)
    assert g["data"]["receipt"]["params"]["query"] == "TLB"
    v = verify_receipt(receipt_id=s["receipt_id"])
    assert_valid(v)
    assert v["data"]["match"] is True and v["data"]["original_digest"] == v["data"]["new_digest"]
    assert len(env.ctx.receipts._mem) == 3  # verify's re-run wrote no receipt of its own
    env.db.on(r"FROM bgl_idx WHERE .*ORDER BY BM25",
              [bgl_line(8, "2005-06-14T09:12:03", "data TLB error interrupt", "FATAL", 42)])  # data changed
    v2 = verify_receipt(receipt_id=s["receipt_id"])
    assert v2["data"]["match"] is False
    assert verify_receipt(receipt_id="R-0999")["error"]["code"] == "not_found"
    assert get_receipt(receipt_id="bogus")["error"]["code"] == "invalid_input"
    ca = check_answer(draft=f"- 1,284 lines [{s['receipt_id']}]")
    assert verify_receipt(receipt_id=ca["receipt_id"])["error"]["code"] == "invalid_input"


def test_show_evidence_lines_builds_valid_event(env):
    s = _search(env)
    out = show_evidence(receipt_id=s["receipt_id"], kind="lines", title="TLB errors",
                        annotations=[{"line_id": 7, "label": "first FATAL", "tone": "critical"},
                                     {"line_id": 12345, "label": "made up"}], role="engineer")
    assert_valid(out)
    assert out["data"]["delivered"] is True and out["scope"]["dataset"] == "none"
    event = env.console.events[-1]
    assert_valid_panel(event)
    body = event["payload"]["body"]
    assert body["groups"][0]["lines"][0]["tone"] == "critical"
    assert event["payload"]["annotations"] == [{"line_id": 7, "label": "first FATAL", "tone": "critical"}]
    assert event["payload"]["receipt"]["total_matches"] == 1284
    assert any("dropped" in c for c in out["caveats"])


def test_show_evidence_wrong_kind_and_console_down(env):
    s = _search(env)
    bad = show_evidence(receipt_id=s["receipt_id"], kind="table", title="x")
    assert bad["error"]["code"] == "invalid_input" and "Valid pairs" in bad["error"]["message"]
    assert show_evidence(receipt_id="R-0404", kind="lines", title="x")["error"]["code"] == "not_found"
    env.console.up = False
    down = show_evidence(receipt_id=s["receipt_id"], kind="lines", title="x")
    assert down["error"] is None and down["data"]["delivered"] is False
    assert any("Console not reachable" in c for c in down["caveats"])


def test_show_evidence_risks_with_actions(env):
    _analyse_rules(env.db)
    r = rank_risks(dataset="bgl")
    out = show_evidence(receipt_id=r["receipt_id"], kind="risks", title="Fix first", actions=["Assign kernel team"])
    assert_valid(out)
    items = env.console.events[-1]["payload"]["body"]["items"]
    assert items[0]["action"] == "Assign kernel team" and items[1]["action"] is None
    assert_valid_panel(env.console.events[-1])


def test_show_evidence_table_and_trend(env):
    _analyse_rules(env.db)
    rp = recurring_problems(dataset="bgl")
    show_evidence(receipt_id=rp["receipt_id"], kind="table", title="Recurring")
    assert_valid_panel(env.console.events[-1])
    env.db.on(r"date_trunc\('week'", [{"t": ts("2005-06-06"), "v": 3, "w": 3}])
    from loglad_mcp.tools.aggregate import count_by, trend
    t = trend(dataset="bgl", metric="lines", start="2005-06-01", end="2005-06-20")
    show_evidence(receipt_id=t["receipt_id"], kind="trend", title="Trend")
    assert_valid_panel(env.console.events[-1])
    env.db.on(r"AS k, count\(\*\) AS n", [{"k": f"C{i}", "n": 40 - i} for i in range(30)])
    c = count_by(dataset="bgl", group_by="component", top_n=25)
    show_evidence(receipt_id=c["receipt_id"], kind="table", title="All")
    ev = env.console.events[-1]
    assert_valid_panel(ev)
    assert len(ev["payload"]["body"]["rows"]) == 26 and ev["payload"]["body"]["total_row"]["share"] == 1.0


def test_show_explainer_blocks_fake_citations(env):
    s = _search(env)
    ok = show_explainer(title="Why", markdown=f"### Observed\n- 1,284 lines [{s['receipt_id']}]", receipt_ids=[])
    assert_valid(ok)
    assert_valid_panel(env.console.events[-1])
    assert [r["receipt_id"] for r in env.console.events[-1]["payload"]["receipts"]] == [s["receipt_id"]]
    fake = show_explainer(title="x", markdown="see [R-0777]", receipt_ids=[s["receipt_id"]])
    assert fake["error"]["code"] == "invalid_input" and "R-0777" in fake["error"]["message"]
    assert show_explainer(title="x", markdown="a" * 8001, receipt_ids=[s["receipt_id"]])["error"]["code"] == "invalid_input"
    assert show_explainer(title="x", markdown="no refs", receipt_ids=[])["error"]["code"] == "invalid_input"


def test_check_answer_counts_and_status_event(env):
    s = _search(env)
    rid = s["receipt_id"]
    draft = f"""**Observed**
- 1,284 FATAL lines matched [{rid}].
- The node crashed because of TLB errors [{rid}].
- 1,300 lines [{rid}].
- 17 nodes were affected.

**Unknowns**
- Any downtime.
"""
    out = check_answer(draft=draft, role="manager")
    assert_valid(out)
    c = out["data"]["counts"]
    assert c == {"backed": 1, "unbacked": 1, "mismatched": 1, "flagged": 1}, out["data"]["claims"]
    assert out["data"]["ok"] is False and out["sql"] == []
    status = env.console.events[-1]
    assert_valid_panel(status)
    assert status["type"] == "status" and status["payload"]["claims"] == c
    assert check_answer(draft="")["error"]["code"] == "invalid_input"


def test_registry_contract():
    names = [t.name for t in TOOLS]
    assert len(names) == 14 and len(set(names)) == 14
    assert set(names) <= set(ROOT_SCHEMA["$defs"]["ToolName"]["enum"])
    for t in TOOLS:
        assert len(t.description) <= 1200 and "Do NOT use it to:" in t.description, t.name
        params = list(inspect.signature(t.fn).parameters.values())
        assert params[-1].name == "role" and params[-1].default == "unknown", t.name
        hint = typing.get_type_hints(t.fn, include_extras=True)["role"]
        assert set(typing.get_args(typing.get_args(hint)[0])) == {"engineer", "team_lead", "manager", "unknown"}


def test_fastmcp_accepts_every_tool():
    import asyncio

    from mcp.server.fastmcp import FastMCP
    app = FastMCP("t")
    for t in TOOLS:
        app.add_tool(t.fn, name=t.name, description=t.description)
    tools = asyncio.run(app.list_tools())
    assert {t.name for t in tools} == {t.name for t in TOOLS}
    search = next(t for t in tools if t.name == "search_logs")
    assert search.inputSchema["required"] == ["query", "dataset"]
