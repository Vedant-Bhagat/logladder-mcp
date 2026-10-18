"""PROMPTS and RESOURCES registries, and the real server wiring with all three registries."""
import asyncio

from loglad_mcp.core.db import DbError
from loglad_mcp.prompts.registry import PROMPTS
from loglad_mcp.resources.registry import RESOURCES


def test_prompts():
    by = {p.name: p for p in PROMPTS}
    assert list(by) == ["engineer", "team_lead", "manager", "investigate"]
    assert by["investigate"].arguments == ["question"]
    for role in ("engineer", "team_lead", "manager"):
        text = by[role].text
        assert f'role="{role}"' in text and "check_answer" in text and "**Observed**" in text
    for name in ("Engineer", "Team lead", "Manager"):
        assert name in by["investigate"].text


def test_resources(env):
    by = {r.uri: r for r in RESOURCES}
    assert list(by) == ["loglad://schema", "loglad://ownership", "loglad://answer-contract", "loglad://glossary"]
    assert "CREATE TABLE receipts" in by["loglad://schema"].load()
    assert all(s in by["loglad://answer-contract"].load() for s in ("Scope", "Observed", "Hypotheses", "Unknowns",
                                                                    "Next step"))
    glossary = by["loglad://glossary"].load()
    assert all(f"**{w}**" in glossary for w in ("Line", "Template", "Episode", "Risk", "Receipt", "Lift", "Ladder"))
    env.db.on(r"FROM ownership", [{"dataset": "bgl", "component": "KERNEL", "team": "HPC Kernel & Runtime",
                                   "team_lead": "Mira Hoffmann"}])
    assert "| bgl | KERNEL | HPC Kernel & Runtime | Mira Hoffmann |" in by["loglad://ownership"].load()
    env.db.on(r"FROM ownership", DbError("db_error", "down"))
    assert "not available" in by["loglad://ownership"].load()


def test_server_builds_with_real_registries():
    from loglad_mcp import server
    app = server.build_app()

    async def probe():
        return await app.list_tools(), await app.list_prompts(), await app.list_resources(), \
            await app.get_prompt("investigate", {"question": "why did R23 fail?"})

    tools, prompts, resources, prompt = asyncio.run(probe())
    assert len(tools) == 14 and len(prompts) == 4 and len(resources) == 4
    assert "question: why did R23 fail?" in prompt.messages[0].content.text
