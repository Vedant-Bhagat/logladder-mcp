"""SereneDb: the one database connection (contract: contracts/interfaces.py).

Client-side parameter binding (ClientCursor) everywhere: it works inside ts_*() calls and gives us
sql_rendered via mogrify. Timeouts are enforced client-side by cancelling the running statement.
"""
from __future__ import annotations

import logging
import threading
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

import psycopg
from psycopg.rows import dict_row

from loglad_mcp.config import Settings

log = logging.getLogger(__name__)
Params = Sequence[Any] | Mapping[str, Any] | None


@dataclass
class QueryResult:
    columns: list[str]
    rows: list[dict[str, Any]]
    runtime_ms: int
    sql_rendered: str


class DbError(Exception):
    def __init__(self, code: Literal["db_error", "timeout"], message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class SereneDb:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._conn: psycopg.Connection | None = None
        self._lock = threading.Lock()  # one connection, tools may run on worker threads

    def _connect(self) -> psycopg.Connection:
        if self._conn is None or self._conn.closed:
            self._conn = psycopg.connect(
                self.settings.serenedb_dsn, autocommit=True, row_factory=dict_row,
                cursor_factory=psycopg.ClientCursor, connect_timeout=5,
            )
        return self._conn

    def _run(self, sql: str, params: Params, timeout_s: float | None, fetch: bool) -> QueryResult:
        timeout = timeout_s or self.settings.query_timeout_s
        with self._lock:
            for attempt in (1, 2):
                try:
                    conn = self._connect()
                    with conn.cursor() as cur:
                        rendered = cur.mogrify(sql, params)
                        timer = threading.Timer(timeout, conn.cancel)
                        start = time.perf_counter()
                        timer.start()
                        try:
                            cur.execute(sql, params)
                            rows = cur.fetchall() if fetch and cur.description else []
                        finally:
                            timer.cancel()
                        columns = [c.name for c in cur.description or []]
                        return QueryResult(columns, rows, int((time.perf_counter() - start) * 1000), rendered)
                except psycopg.errors.QueryCanceled as e:
                    raise DbError("timeout", f"query exceeded {timeout:g}s") from e
                except psycopg.OperationalError as e:
                    # dropped connection: reconnect once, then give up
                    self._conn = None
                    if attempt == 2:
                        raise DbError("db_error", f"SereneDB unreachable: {e}") from e
                    log.warning("db connection lost, reconnecting: %s", e)
                except psycopg.Error as e:
                    raise DbError("db_error", str(e).strip()) from e
        raise AssertionError("unreachable")

    def query(self, sql: str, params: Params = None, *, timeout_s: float | None = None) -> QueryResult:
        return self._run(sql, params, timeout_s, fetch=True)

    def execute(self, sql: str, params: Params = None) -> None:
        self._run(sql, params, None, fetch=False)

    def ping(self) -> bool:
        try:
            self.query("SELECT 1 AS ok", timeout_s=3)
            return True
        except DbError:
            return False
