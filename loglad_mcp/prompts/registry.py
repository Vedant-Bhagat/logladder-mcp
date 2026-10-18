"""PROMPTS: role prompts loaded from loglad_mcp/prompts/*.md (contracts/interfaces.py PromptSpec)."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent


@dataclass(frozen=True)
class PromptSpec:
    name: str
    description: str
    text: str
    arguments: list[str] = field(default_factory=list)


def _text(name: str) -> str:
    return (HERE / f"{name}.md").read_text(encoding="utf-8")


PROMPTS: list[PromptSpec] = [
    PromptSpec("engineer", "On-call engineer: what happened in one incident, its precursor and the next diagnostic "
                           "step (search → timeline → hypothesis test → evidence → check_answer).", _text("engineer")),
    PromptSpec("team_lead", "Team lead: which problems keep recurring for my team, are they growing, and where to "
                            "spend time (recurring problems → trend → counts → evidence → check_answer).",
               _text("team_lead")),
    PromptSpec("manager", "Manager: what to fix first and who owns it (risk ranking → drill-down → risk panel with "
                          "actions → check_answer). Decisions, not diagnostics.", _text("manager")),
    PromptSpec("investigate", "Answer one question three times — engineer, team lead, manager — each with its own "
                              "evidence and next step.", _text("investigate"), ["question"]),
]
