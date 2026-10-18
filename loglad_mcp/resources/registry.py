"""RESOURCES: loglad:// resources (contracts/interfaces.py ResourceSpec). Each load() returns markdown."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


@dataclass(frozen=True)
class ResourceSpec:
    uri: str
    name: str
    description: str
    load: Callable[[], str]


def load_schema() -> str:
    ddl = (ROOT / "contracts" / "db_schema.sql").read_text(encoding="utf-8")
    return ("# LogLadder database schema (SereneDB)\n\nFull-text search runs on the inverted indexes `bgl_idx` and "
            "`os_idx`; aggregates run on the base tables.\n\n```sql\n" + ddl.strip() + "\n```\n")


def load_ownership() -> str:
    from loglad_mcp.core.context import ctx
    try:
        rows = ctx().db.query("SELECT dataset, component, team, team_lead FROM ownership "
                              "ORDER BY dataset, team, component").rows
    except Exception as e:  # noqa: BLE001 - a resource must still answer when the database is down
        return f"# Ownership\n\nOwnership table not available: {e}\n"
    lines = ["# Ownership (fictional teams)", "",
             "Components without a row here are counted under team `Unowned`.", "",
             "| Dataset | Component / service | Team | Team lead |", "| --- | --- | --- | --- |"]
    lines += [f"| {r['dataset']} | {r['component']} | {r['team']} | {r['team_lead']} |" for r in rows]
    return "\n".join(lines) + "\n"


def _file(name: str) -> Callable[[], str]:
    return lambda: (HERE / name).read_text(encoding="utf-8")


RESOURCES: list[ResourceSpec] = [
    ResourceSpec("loglad://schema", "schema", "Tables, columns and full-text indexes in SereneDB (the frozen DDL).",
                 load_schema),
    ResourceSpec("loglad://ownership", "ownership", "Which team owns each BGL component / OpenStack service "
                                                   "(fictional), live from the ownership table.", load_ownership),
    ResourceSpec("loglad://answer-contract", "answer-contract", "The five sections every answer must have: Scope, "
                                                               "Observed, Hypotheses, Unknowns, Next step.",
                 _file("answer_contract.md")),
    ResourceSpec("loglad://glossary", "glossary", "Definitions: line, template, episode, risk, receipt, lift, ladder.",
                 _file("glossary.md")),
]
