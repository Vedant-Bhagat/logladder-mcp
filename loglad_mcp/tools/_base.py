"""The @tool_call wrapper and helpers shared by every tool (spec 02 §3.7).

A tool body returns ToolResult(summary, scope, data, total_matches, returned, truncated, sql, caveats).
The wrapper times it, maps exceptions to envelope errors, writes the receipt and (with LOGLAD_VALIDATE=1)
validates the envelope. Tools never raise.
"""
from __future__ import annotations

import contextvars
import functools
import inspect
import json
import logging
import os
import re
import sys
import time
import traceback
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Literal, NamedTuple

from loglad_mcp.core.context import ctx
from loglad_mcp.core.db import DbError
from loglad_mcp.core.envelope import error_envelope, make_envelope, make_scope
from loglad_mcp.core.limits import truncate_message
from loglad_mcp.core.timeparse import ISO_RE, iso

log = logging.getLogger("loglad.tools")
ROOT = Path(__file__).resolve().parents[2]

Role = Literal["engineer", "team_lead", "manager", "unknown"]
ROLES = ("engineer", "team_lead", "manager", "unknown")
DATASETS = ("bgl", "openstack")
EPISODE_GAP = {"bgl": "10m", "openstack": "60s"}
EVENTS = {"bgl": "bgl_events", "openstack": "os_events"}
INDEX = {"bgl": "bgl_idx", "openstack": "os_idx"}
LABEL = {"bgl": "BGL", "openstack": "OpenStack"}
ERROR_LEVELS = {"bgl": ("FATAL", "FAILURE", "SEVERE", "ERROR"), "openstack": ("ERROR", "CRITICAL")}
LEVEL_RANK = {"FATAL": 8, "FAILURE": 7, "CRITICAL": 7, "SEVERE": 6, "ERROR": 5, "WARNING": 4, "INFO": 3, "DEBUG": 2}

_VERIFY = contextvars.ContextVar("loglad_verify", default=False)


class ToolResult(NamedTuple):
    summary: str
    scope: dict
    data: dict
    total_matches: int | None
    returned: int
    truncated: bool
    sql: list[str]
    caveats: list[str]


class ToolError(Exception):
    """Raise from a tool body for a specific envelope error code (e.g. not_found)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def in_verify_mode() -> bool:
    return _VERIFY.get()


def run_verify(fn: Callable[..., dict], params: dict) -> dict:
    """Re-run a tool with stored params: no receipt, no console post."""
    token = _VERIFY.set(True)
    try:
        return fn(**params)
    finally:
        _VERIFY.reset(token)


# --------------------------------------------------------------------------- validation (tests)

_validator = None


def _validate(envelope: dict) -> None:
    global _validator
    if os.environ.get("LOGLAD_VALIDATE") != "1":
        return
    try:
        if _validator is None:
            from jsonschema import Draft202012Validator
            schema = json.loads((ROOT / "contracts" / "envelope.schema.json").read_text(encoding="utf-8"))
            _validator = Draft202012Validator(schema)
        for e in _validator.iter_errors(json.loads(json.dumps(envelope, default=str))):
            print(f"[loglad] envelope {envelope['tool']} invalid at {'/'.join(map(str, e.absolute_path))}: "
                  f"{e.message}", file=sys.stderr)
    except Exception as e:  # noqa: BLE001  # validation must never break a tool
        print(f"[loglad] envelope validation skipped: {e}", file=sys.stderr)


# --------------------------------------------------------------------------- the wrapper

def _error_scope(params: dict) -> dict:
    ds = params.get("dataset")
    s, e = params.get("start"), params.get("end")
    return make_scope(ds if ds in ("bgl", "openstack", "both") else "none",
                      s if isinstance(s, str) and ISO_RE.match(s) else None,
                      e if isinstance(e, str) and ISO_RE.match(e) else None)


def tool_call(name: str) -> Callable[[Callable[..., ToolResult]], Callable[..., dict]]:
    def deco(body: Callable[..., ToolResult]) -> Callable[..., dict]:
        sig = inspect.signature(body)

        @functools.wraps(body)
        def wrapper(*args: Any, **kwargs: Any) -> dict:
            started = time.perf_counter()
            try:
                bound = sig.bind(*args, **kwargs)
                bound.apply_defaults()
                params = dict(bound.arguments)
            except TypeError as e:
                params, bound = dict(kwargs), None
                bind_error = str(e)
            else:
                bind_error = None
            role = params.get("role", "unknown")
            if role not in ROLES:
                role = "unknown"
            try:
                if bind_error:
                    raise ValueError(bind_error)
                if params.get("role", "unknown") not in ROLES:
                    raise ValueError(f"role must be one of {', '.join(ROLES)}.")
                res = body(*bound.args, **bound.kwargs)
                env = make_envelope(name, role, res.summary, res.scope, res.data, total_matches=res.total_matches,
                                    returned=res.returned, truncated=res.truncated, sql=res.sql,
                                    runtime_ms=int((time.perf_counter() - started) * 1000), caveats=res.caveats)
            except ToolError as e:
                env = error_envelope(name, role, e.code, e.message, _error_scope(params))
            except ValueError as e:
                env = error_envelope(name, role, "invalid_input", str(e), _error_scope(params))
            except DbError as e:
                env = error_envelope(name, role, e.code, e.message, _error_scope(params))
            except Exception as e:  # noqa: BLE001
                print(f"[loglad] {name} failed:\n{traceback.format_exc()}", file=sys.stderr)
                env = error_envelope(name, role, "internal", f"{type(e).__name__}: {e}", _error_scope(params))
            env["runtime_ms"] = int((time.perf_counter() - started) * 1000)
            if not in_verify_mode():
                try:
                    ctx().receipts.write(env, params)
                except Exception as e:  # noqa: BLE001  # no context / store failure: still return the answer
                    print(f"[loglad] receipt write failed for {name}: {e}", file=sys.stderr)
                    env["caveats"].append("receipt not recorded")
            _validate(env)
            return env

        # FastMCP reads this signature: same parameters as the body, but the tool returns the envelope dict.
        wrapper.__signature__ = inspect.signature(body, eval_str=True).replace(  # type: ignore[attr-defined]
            return_annotation=dict[str, Any])
        wrapper.tool_name = name  # type: ignore[attr-defined]
        return wrapper

    return deco


# --------------------------------------------------------------------------- SQL helpers

class Sql:
    """Runs statements through ctx().db and records each rendered statement for the receipt."""

    def __init__(self) -> None:
        self.statements: list[str] = []

    def __call__(self, sql: str, params: Any = None) -> list[dict]:
        res = ctx().db.query(sql, params)
        self.statements.append(res.sql_rendered)
        return res.rows

    def query(self, sql: str, params: Any = None, **_: Any) -> Any:
        """Db-compatible view, so helpers like resolve_window record their statements too."""
        return SimpleNamespace(rows=self(sql, params))


def placeholders(values: list | tuple) -> str:
    return "(" + ", ".join(["%s"] * len(values)) + ")" if values else "(NULL)"


def level_rank_sql(col: str) -> str:
    whens = " ".join(f"WHEN '{lv}' THEN {r}" for lv, r in LEVEL_RANK.items())
    return f"CASE {col} {whens} ELSE 1 END"


def level_rank(level: str | None) -> int:
    return LEVEL_RANK.get((level or "").upper(), 1)


def level_from_rank(rank: Any, dataset: str) -> str:
    """Inverse of level_rank_sql for one dataset (rank 7 is FAILURE in BGL, CRITICAL in OpenStack)."""
    r = to_int(rank)
    if r == 7:
        return "FAILURE" if dataset == "bgl" else "CRITICAL"
    return {8: "FATAL", 6: "SEVERE", 5: "ERROR", 4: "WARNING", 3: "INFO", 2: "DEBUG"}.get(r, "INFO")


def max_level(levels: list[str | None]) -> str:
    present = [lv for lv in levels if lv]
    return max(present, key=level_rank) if present else "INFO"


def num(v: Any) -> int | float | None:
    """psycopg Decimal / numpy-ish -> plain int or float."""
    if v is None:
        return None
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, int):
        return v
    if isinstance(v, Decimal):
        return int(v) if v == v.to_integral_value() else float(v)
    return float(v)


def to_int(v: Any) -> int:
    return int(num(v) or 0)


def fmt_int(n: Any) -> str:
    return f"{to_int(n):,}"


def check_dataset(dataset: str, allowed: tuple[str, ...] = DATASETS) -> str:
    ds = (dataset or "").strip().lower()
    if ds not in allowed:
        raise ValueError(f"dataset must be one of {', '.join(allowed)}; got {dataset!r}.")
    return ds


def datasets_of(dataset: str) -> list[str]:
    ds = check_dataset(dataset, ("bgl", "openstack", "both"))
    return list(DATASETS) if ds == "both" else [ds]


def gap_label(datasets: list[str]) -> str:
    return " / ".join(f"{EPISODE_GAP[d]} ({d})" for d in datasets) if len(datasets) > 1 else EPISODE_GAP[datasets[0]]


# --------------------------------------------------------------------------- log lines

def char_highlights(message: str, offsets: Any, limit: int | None = None) -> list[list[int]]:
    """Byte offsets from ts_offsets() (interleaved start,end) -> [start, end) character offsets."""
    if not offsets:
        return []
    if isinstance(offsets, str):
        try:
            offsets = json.loads(offsets)
        except ValueError:
            offsets = [int(x) for x in re.findall(r"\d+", offsets)]
    flat: list[int] = []
    for o in offsets:
        flat.extend(o if isinstance(o, (list, tuple)) else [o])
    raw = message.encode("utf-8")
    out: list[list[int]] = []
    for i in range(0, len(flat) - 1, 2):
        b0, b1 = int(flat[i]), int(flat[i + 1])
        c0 = len(raw[:b0].decode("utf-8", errors="ignore"))
        c1 = len(raw[:b1].decode("utf-8", errors="ignore"))
        if limit is not None:
            c0, c1 = min(c0, limit), min(c1, limit)
        if c1 > c0 and [c0, c1] not in out:
            out.append([c0, c1])
    return sorted(out)


def log_line(dataset: str, row: dict, repeat_count: int | None = None) -> dict:
    """A bgl_events / os_events row -> contract LogLine."""
    message = row.get("message") or ""
    shown = truncate_message(message)
    line = {
        "id": to_int(row["id"]),
        "dataset": dataset,
        "ts": iso(row["ts"]),
        "source": "",
        "component": None,
        "level": (row.get("level") or "").upper() or "INFO",
        "message": shown,
        "template_id": None if row.get("template_id") is None else to_int(row["template_id"]),
        "episode_id": None if row.get("episode_id") is None else to_int(row["episode_id"]),
        "highlights": char_highlights(message, row.get("offsets"), limit=min(len(shown), 400)),
    }
    if dataset == "bgl":
        line["source"] = row.get("node") or row.get("midplane") or "unknown"
        line["component"] = row.get("component")
        line["extra"] = {"alert_category": row.get("alert_category"), "midplane": row.get("midplane")}
    else:
        line["source"] = row.get("service") or "unknown"
        line["component"] = row.get("service")
        lat = row.get("latency_s")
        line["extra"] = {
            "request_id": row.get("request_id"), "instance_id": row.get("instance_id"),
            "http_status": None if row.get("http_status") is None else to_int(row["http_status"]),
            "latency_s": None if lat is None else float(lat),
            "labelled_anomaly": None if row.get("labelled_anomaly") is None else bool(row["labelled_anomaly"]),
        }
    if repeat_count is not None:
        line["repeat_count"] = max(1, int(repeat_count))
    return line


LINE_COLUMNS = {
    "bgl": "id, ts, node, component, level, message, template_id, episode_id, midplane, alert_category",
    "openstack": "id, ts, service, level, message, template_id, episode_id, request_id, instance_id, http_status, "
                 "latency_s, labelled_anomaly",
}


def ownership(q: Sql) -> dict[tuple[str, str], str]:
    rows = q("SELECT dataset, component, team FROM ownership")
    return {(r["dataset"], r["component"]): r["team"] for r in rows}


def template_texts(q: Sql, ids: list[int]) -> dict[int, dict]:
    ids = sorted({int(i) for i in ids if i is not None})
    if not ids:
        return {}
    rows = q(f"SELECT template_id, dataset, template_text, component, max_level FROM templates "
             f"WHERE template_id IN {placeholders(ids)}", ids)
    return {to_int(r["template_id"]): r for r in rows}


def when_txt(frm: str | None, to: str | None, default: str) -> str:
    """'from A to B' for summaries (timestamps cut to seconds), else `default`."""
    return f"from {frm[:19]} to {to[:19]}" if frm and to else default


def short(text: str, n: int = 80) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= n else text[: n - 1] + "…"


# --------------------------------------------------------------------------- windows over one or both datasets

def windows_for(q: Sql, datasets: list[str], start: str | None, end: str | None, recent_days: int | None = None
                ) -> tuple[dict, str | None, str | None, list[str]]:
    """Per-dataset Windows plus scope from/to and caveats.

    recent_days: with no start/end, use the last N days of each dataset's own span (recurring_problems,
    rank_risks). Missing single bounds are filled from the dataset span (or end - N days).
    """
    from datetime import timedelta

    from loglad_mcp.core.timeparse import Window, check_pair, dataset_span, resolve_window

    check_pair(start, end)
    wins, caveats = {}, []
    for ds in datasets:
        if recent_days and not start:
            w_end = resolve_window(q, ds, None, end)
            lo, _ = dataset_span(q, ds)
            s = max(lo, w_end.end - timedelta(days=recent_days))
            w = Window(s, w_end.end, iso(s.replace(microsecond=0)), w_end.to, False)
        else:
            w = resolve_window(q, ds, start, end)
        wins[ds] = w
    if len(datasets) == 1:
        w = wins[datasets[0]]
        return wins, w.frm, w.to, caveats
    if not (start and end):
        caveats.append("Each dataset uses its own window: " + "; ".join(
            f"{d} {wins[d].frm[:19]} to {wins[d].to[:19]}" for d in datasets) + ".")
    return wins, start, end, caveats
