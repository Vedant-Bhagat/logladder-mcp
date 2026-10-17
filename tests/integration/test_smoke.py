"""Proves the three branches fit: server wiring (no DB), then every registered tool against SereneDB.

    python tasks.py check   # runs the wiring test
    python tasks.py smoke   # runs the DB tests (SereneDB up + `tasks.py data --sample`); console optional
"""
import asyncio
import json
import os
import sys
import urllib.request
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ["LOGLAD_VALIDATE"] = "1"

from loglad_mcp import server
from scripts.validate_contracts import validate_envelope


def test_server_registers_tools_prompts_resources(monkeypatch):
    def echo(text: str, role: str = "unknown") -> dict:
        return {"text": text}

    specs = (
        [SimpleNamespace(name="describe_corpus", description="d", fn=echo)],
        [SimpleNamespace(name="investigate", description="p", text="Investigate.", arguments=["question"])],
        [SimpleNamespace(uri="loglad://glossary", name="glossary", description="g", load=lambda: "# Glossary")],
        None,
    )
    monkeypatch.setattr(server, "_registries", lambda: specs)
    app = server.build_app()

    async def probe():
        tools = await app.list_tools()
        prompt = await app.get_prompt("investigate", {"question": "why?"})
        res = await app.read_resource("loglad://glossary")
        return tools, prompt, list(res)

    tools, prompt, res = asyncio.run(probe())
    assert [t.name for t in tools] == ["describe_corpus"]
    assert "Investigate." in prompt.messages[0].content.text and "question: why?" in prompt.messages[0].content.text
    assert res[0].content == "# Glossary"


# ----------------------------------------------------------------------------- needs SereneDB + sample data

def _db():
    from loglad_mcp.config import load_settings
    from loglad_mcp.core.db import SereneDb

    settings = load_settings()
    db = SereneDb(settings)
    if not db.ping():
        pytest.skip("SereneDB not reachable")
    return db, settings


@pytest.mark.db
def test_every_tool_returns_a_valid_envelope():
    db, settings = _db()
    init_context = pytest.importorskip("loglad_mcp.core.context", reason="Janhavi J1 not merged").init_context
    TOOLS = pytest.importorskip("loglad_mcp.tools.registry", reason="Janhavi J1 not merged").TOOLS

    init_context(db, settings)
    tools = {t.name: t.fn for t in TOOLS}
    q = lambda sql: db.query(sql).rows[0]
    anchor = q("SELECT min(id) AS id FROM bgl_events WHERE level = 'FATAL'")["id"]
    t1, t2 = (r["template_id"] for r in db.query(
        "SELECT template_id FROM templates WHERE dataset = 'bgl' ORDER BY line_count DESC LIMIT 2").rows)
    req = q("SELECT min(request_id) AS r FROM os_events WHERE request_id IS NOT NULL")["r"]

    calls = [
        ("describe_corpus", {}),
        ("search_logs", {"query": "error", "dataset": "bgl"}),
        ("get_timeline", {"dataset": "bgl", "anchor_id": anchor}),
        ("trace_request", {"request_id": req}),
        ("count_by", {"dataset": "bgl", "group_by": "component"}),
        ("trend", {"dataset": "bgl", "metric": "lines", "bucket": "day"}),
        ("recurring_problems", {}),
        ("rank_risks", {}),
        ("test_hypothesis", {"dataset": "bgl", "cause_template_id": t1, "effect_template_id": t2}),
    ]
    receipts = {}
    for name, params in calls:
        if name not in tools:
            continue
        env = tools[name](**params)
        assert validate_envelope(env) == [], (name, validate_envelope(env))
        assert env.get("error") is None, (name, env["error"])
        receipts[name] = env["receipt_id"]

    rid = receipts.get("search_logs")
    follow_ups = [
        ("get_receipt", {"receipt_id": rid}),
        ("verify_receipt", {"receipt_id": rid}),
        ("show_evidence", {"receipt_id": rid, "kind": "lines", "title": "smoke"}),
        ("show_explainer", {"title": "smoke", "markdown": f"Smoke [{rid}]", "receipt_ids": [rid]}),
        ("check_answer", {"draft": f"**Observed**\n- Search returned results [{rid}]."}),
    ]
    for name, params in follow_ups:
        if name in tools and rid:
            env = tools[name](**params)
            assert validate_envelope(env) == [], (name, validate_envelope(env))
            assert env.get("error") is None, (name, env["error"])


@pytest.mark.db
def test_console_accepts_a_panel_event_if_running():
    url = os.environ.get("LOGLAD_CONSOLE_URL", "http://127.0.0.1:7777")
    try:
        urllib.request.urlopen(f"{url}/api/health", timeout=1.5)
    except OSError:
        pytest.skip("console not running")
    event = json.loads((ROOT / "contracts/fixtures/panel_events/06_status.json").read_text(encoding="utf-8"))
    req = urllib.request.Request(f"{url}/api/panel", data=json.dumps(event).encode(), method="POST",
                                 headers={"Content-Type": "application/json"})
    assert urllib.request.urlopen(req, timeout=3).status == 202
