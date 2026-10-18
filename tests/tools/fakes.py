"""FakeDb / FakeConsole for tool tests: canned rows by SQL pattern, every statement recorded."""
from __future__ import annotations

import re
from collections.abc import Callable
from datetime import datetime
from typing import Any

from loglad_mcp.core.db import DbError, QueryResult

Rows = list[dict[str, Any]] | Callable[[str, Any], list[dict[str, Any]]]


class FakeDb:
    """`on(pattern, rows)` registers a response (regex searched in the SQL; first match wins, newest first).
    Unmatched SQL raises AssertionError so a test never silently gets empty data."""

    def __init__(self) -> None:
        self.rules: list[tuple[re.Pattern, Rows | Exception]] = []
        self.queries: list[tuple[str, Any]] = []
        self.inserts: list[tuple[str, Any]] = []
        self.fail_inserts = False
        self.on(r"max\(CAST\(substr\(receipt_id", [{"n": None}])
        self.on(r"FROM receipts WHERE receipt_id", [])

    def on(self, pattern: str, rows: Rows | Exception) -> FakeDb:
        self.rules.insert(0, (re.compile(pattern, re.DOTALL), rows))
        return self

    def query(self, sql: str, params: Any = None, *, timeout_s: float | None = None) -> QueryResult:
        self.queries.append((sql, params))
        for pat, rows in self.rules:
            if pat.search(sql):
                if isinstance(rows, Exception):
                    raise rows
                out = rows(sql, params) if callable(rows) else rows
                cols = list(out[0]) if out else []
                return QueryResult(cols, [dict(r) for r in out], 1, f"{sql} -- {params!r}")
        raise AssertionError(f"FakeDb: no rule for SQL: {sql}")

    def execute(self, sql: str, params: Any = None) -> None:
        if self.fail_inserts:
            raise DbError("db_error", "insert failed")
        self.inserts.append((sql, params))

    def ping(self) -> bool:
        return True


class FakeConsole:
    def __init__(self, up: bool = True) -> None:
        self.up = up
        self.events: list[dict] = []

    def post(self, event: dict) -> bool:
        self.events.append(event)
        return self.up


def ts(s: str) -> datetime:
    return datetime.fromisoformat(s)


def bgl_line(i: int, t: str, message: str, level: str = "INFO", template_id: int = 1, midplane: str = "R02-M1",
             node: str = "R02-M1-N0-C:J12-U11", component: str = "KERNEL", episode_id: int = 1, **extra) -> dict:
    return {"id": i, "ts": ts(t), "node": node, "component": component, "level": level, "message": message,
            "template_id": template_id, "episode_id": episode_id, "midplane": midplane, "alert_category": None,
            **extra}


def os_line(i: int, t: str, message: str, service: str = "nova-api", level: str = "INFO", template_id: int = 100001,
            request_id: str | None = "req-1", instance_id: str | None = None, **extra) -> dict:
    return {"id": i, "ts": ts(t), "service": service, "level": level, "message": message, "template_id": template_id,
            "episode_id": 10_000_000 + i, "request_id": request_id, "instance_id": instance_id, "http_status": None,
            "latency_s": None, "labelled_anomaly": False, **extra}


OWNERS = [{"dataset": "bgl", "component": "KERNEL", "team": "HPC Kernel & Runtime"},
          {"dataset": "bgl", "component": "APP", "team": "HPC Applications Support"},
          {"dataset": "openstack", "component": "nova-api", "team": "Cloud API Platform"},
          {"dataset": "openstack", "component": "nova-compute", "team": "Cloud Compute & Hypervisors"}]


def templates_rule(texts: dict[int, tuple[str, str]]) -> Callable:
    """texts: template_id -> (dataset, text)."""
    def fn(sql: str, params: Any) -> list[dict]:
        return [{"template_id": t, "dataset": texts[t][0], "template_text": texts[t][1], "component": "KERNEL",
                 "max_level": "FATAL"} for t in (params or []) if t in texts]
    return fn


def assert_valid(envelope: dict) -> None:
    from scripts.validate_contracts import validate_envelope
    errs = validate_envelope(envelope)
    assert errs == [], errs


def assert_valid_panel(event: dict) -> None:
    from scripts.validate_contracts import validate_panel_event
    errs = validate_panel_event(event)
    assert errs == [], errs
