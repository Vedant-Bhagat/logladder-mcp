"""ReceiptStore: one receipt per tool call, in memory and in the `receipts` table (spec 02 §3.4).

The next id is read lazily from the database on the first write, so a down database never stalls
server start-up. If the INSERT fails the receipt stays in memory and the envelope gets a caveat. After a
database failure the store skips the database for BACKOFF_S seconds, so a down SereneDB costs each tool call
at most its own query timeout, not extra ones for the receipt.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from datetime import UTC, datetime
from typing import Any

from loglad_mcp.core.db import DbError
from loglad_mcp.core.envelope import canonical_json, digest

log = logging.getLogger(__name__)
NOT_PERSISTED = "receipt not persisted to database"
BACKOFF_S = 30.0

INSERT_SQL = (
    "INSERT INTO receipts (receipt_id, created_at, session_id, tool, role, params_json, sql_json, scope_json, "
    "total_matches, returned, truncated, runtime_ms, result_digest, data_json, error) "
    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
)


def format_id(n: int) -> str:
    return f"R-{n:04d}"


def parse_id(receipt_id: str) -> int | None:
    rid = (receipt_id or "").strip().upper()
    if rid.startswith("R-") and rid[2:].isdigit():
        return int(rid[2:])
    return None


def normalise_id(receipt_id: str) -> str | None:
    n = parse_id(receipt_id)
    return None if n is None else format_id(n)


class ReceiptStore:
    def __init__(self, db, session_id: str) -> None:
        self.db = db
        self.session_id = session_id or datetime.now(UTC).strftime("%Y%m%dT%H%M")
        self._mem: dict[str, dict] = {}
        self._next: int | None = None
        self._lock = threading.Lock()
        self._down_until = 0.0

    def _db_ok(self) -> bool:
        return time.monotonic() >= self._down_until

    def _mark_down(self, e: Exception) -> None:
        self._down_until = time.monotonic() + BACKOFF_S
        log.warning("receipts: database unavailable (%s); using memory only for %.0f s", e, BACKOFF_S)

    def _next_id(self) -> int:
        mem_max = max((parse_id(k) or 0 for k in self._mem), default=0)
        if self._next is None and self._db_ok():
            try:
                row = self.db.query(
                    "SELECT max(CAST(substr(receipt_id, 3) AS BIGINT)) AS n FROM receipts", timeout_s=3).rows
                self._next = max(int(row[0]["n"] or 0) if row else 0, mem_max) + 1
            except Exception as e:  # noqa: BLE001  # DB down: number after what we hold in memory
                self._mark_down(e)
        if self._next is None:
            return mem_max + 1
        n = self._next
        self._next += 1
        return n

    def write(self, envelope: dict, params: dict[str, Any]) -> str:
        """Assign the receipt id (also set on `envelope`), store the record; never raises."""
        with self._lock:
            rid = format_id(self._next_id())
            envelope["receipt_id"] = rid
            err = envelope.get("error")
            record = {
                "receipt_id": rid,
                "created_at": datetime.now(UTC).replace(tzinfo=None).isoformat(timespec="seconds"),
                "session_id": self.session_id,
                "tool": envelope["tool"],
                "role": envelope["role"],
                "params": json.loads(canonical_json(params)),
                "sql": list(envelope["sql"]),
                "scope": envelope["scope"],
                "total_matches": envelope["total_matches"],
                "returned": envelope["returned"],
                "truncated": envelope["truncated"],
                "runtime_ms": envelope["runtime_ms"],
                "result_digest": digest(envelope["data"]),
                "data": envelope["data"],
                "error": None if err is None else f"{err['code']}: {err['message']}",
            }
            self._mem[rid] = record
        if not self._db_ok():
            envelope["caveats"].append(NOT_PERSISTED)
            return rid
        try:
            self.db.execute(INSERT_SQL, (
                rid, datetime.fromisoformat(record["created_at"]), record["session_id"], record["tool"],
                record["role"], canonical_json(record["params"]), json.dumps(record["sql"]),
                canonical_json(record["scope"]), record["total_matches"], record["returned"], record["truncated"],
                record["runtime_ms"], record["result_digest"], canonical_json(record["data"]), record["error"],
            ))
        except Exception as e:  # noqa: BLE001
            log.warning("receipt %s not persisted: %s", rid, e)
            envelope["caveats"].append(NOT_PERSISTED)
            with self._lock:
                self._next = None  # re-read the max id when the database is back (avoids id clashes)
            self._mark_down(e)
        return rid

    def get(self, receipt_id: str) -> dict | None:
        """ReceiptRecord dict: memory first, then the database. Raises DbError if the DB is needed and down."""
        rid = normalise_id(receipt_id)
        if rid is None:
            return None
        with self._lock:
            if rid in self._mem:
                return self._mem[rid]
        if not self._db_ok():
            raise DbError("db_error", f"{rid} is not in this session's memory and SereneDB was unreachable in the "
                                      f"last {BACKOFF_S:.0f} s.")
        try:
            rows = self.db.query("SELECT * FROM receipts WHERE receipt_id = %s", (rid,)).rows
        except DbError as e:
            self._mark_down(e)
            raise
        if not rows:
            return None
        r = rows[0]
        record = {
            "receipt_id": r["receipt_id"],
            "created_at": _iso(r["created_at"]),
            "session_id": r["session_id"],
            "tool": r["tool"],
            "role": r["role"],
            "params": json.loads(r["params_json"]),
            "sql": json.loads(r["sql_json"]),
            "scope": json.loads(r["scope_json"]),
            "total_matches": None if r["total_matches"] is None else int(r["total_matches"]),
            "returned": int(r["returned"]),
            "truncated": bool(r["truncated"]),
            "runtime_ms": int(r["runtime_ms"]),
            "result_digest": r["result_digest"],
            "data": json.loads(r["data_json"]),
            "error": r["error"],
        }
        with self._lock:
            self._mem[rid] = record
        return record

    def count(self) -> int:
        with self._lock:
            return len(self._mem)


def _iso(value: Any) -> str:
    if isinstance(value, datetime):
        return value.replace(tzinfo=None).isoformat(timespec="seconds")
    return str(value).replace(" ", "T")


def receipt_ref(record: dict) -> dict:
    """ReceiptRef for panel events (contracts/panel_event.schema.json)."""
    return {k: record[k] for k in ("receipt_id", "tool", "sql", "scope", "total_matches", "returned", "truncated",
                                   "runtime_ms")}
