"""The envelope every tool returns (contracts/envelope.schema.json, spec 02 §3.3)."""
from __future__ import annotations

import hashlib
import json
from typing import Any

from loglad_mcp.core.timeparse import ISO_RE

DATASET_SCOPES = ("bgl", "openstack", "both", "none")


def _iso_or_none(value: Any) -> str | None:
    return value if isinstance(value, str) and ISO_RE.match(value) else None


def make_scope(dataset: str, start: str | None = None, end: str | None = None, filters: dict | None = None, *,
               unit: str | None = None, episode_gap: str | None = None, group_by: str | None = None,
               bucket: str | None = None) -> dict:
    return {
        "dataset": dataset if dataset in DATASET_SCOPES else "none",
        "from": _iso_or_none(start),
        "to": _iso_or_none(end),
        "filters": {k: v for k, v in (filters or {}).items() if v is not None},
        "unit": unit,
        "episode_gap": episode_gap,
        "group_by": group_by,
        "bucket": bucket,
    }


def _summary(text: str) -> str:
    text = " ".join((text or "").split()) or "No summary."
    return text if len(text) <= 400 else text[:399] + "…"


def make_envelope(tool: str, role: str, summary: str, scope: dict, data: dict, *, total_matches: int | None,
                  returned: int, truncated: bool, sql: list[str], runtime_ms: int, caveats: list[str]) -> dict:
    return {
        "contract": 1,
        "receipt_id": "R-0000",  # replaced by ReceiptStore.write
        "tool": tool,
        "role": role,
        "summary": _summary(summary),
        "scope": scope,
        "total_matches": None if total_matches is None else int(total_matches),
        "returned": int(returned),
        "truncated": bool(truncated),
        "data": data,
        "sql": list(sql),
        "runtime_ms": max(0, int(runtime_ms)),
        "caveats": list(dict.fromkeys(caveats)),  # de-duplicated, order kept
        "error": None,
    }


def error_envelope(tool: str, role: str, code: str, message: str, scope: dict | None = None) -> dict:
    label = {"invalid_input": "Invalid input", "not_found": "Not found", "db_error": "Database error",
             "timeout": "Query timed out", "console_unavailable": "Console unavailable"}.get(code, "Internal error")
    env = make_envelope(tool, role, f"{label}: {message}", scope or make_scope("none"), {}, total_matches=None,
                        returned=0, truncated=False, sql=[], runtime_ms=0, caveats=[])
    env["error"] = {"code": code, "message": message}
    return env


def _json_default(o: Any) -> Any:
    # pydantic params (e.g. show_evidence annotations) must stay objects so receipts can be replayed
    return o.model_dump() if hasattr(o, "model_dump") else str(o)


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=_json_default)


def digest(data: dict) -> str:
    return hashlib.sha256(canonical_json(data).encode("utf-8")).hexdigest()
