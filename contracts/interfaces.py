"""
LogLadder Python interface contract v1 — the seams between Vedant's and Janhavi's code.

FROZEN. This file is a reference, not runtime code: it is imported by nothing in production.
The real implementations must match these names, signatures and behaviours exactly:

    loglad_mcp/config.py          -> Settings, load_settings()            (owner: Vedant)
    loglad_mcp/core/db.py         -> QueryResult, SereneDb (implements Db) (owner: Vedant)
    loglad_mcp/core/context.py    -> ToolContext, init_context(), ctx()    (owner: Janhavi)
    loglad_mcp/core/console.py    -> ConsoleClient                         (owner: Janhavi)
    loglad_mcp/tools/registry.py  -> TOOLS: list[ToolSpec]                 (owner: Janhavi)
    loglad_mcp/prompts/registry.py-> PROMPTS: list[PromptSpec]             (owner: Janhavi)
    loglad_mcp/resources/registry.py -> RESOURCES: list[ResourceSpec]      (owner: Janhavi)
    loglad_mcp/server.py          -> builds FastMCP app from the three registries (owner: Vedant)

Change only through the contract-change process in docs/specs/00-team-contract.md.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Literal, Mapping, Protocol, Sequence

# --------------------------------------------------------------------------- config (Vedant)

ENV_VARS = {
    "SERENEDB_DSN": "postgresql connection string for SereneDB; default decided by Vedant at M0 and written to .env.example",
    "LOGLAD_CONSOLE_URL": "default http://127.0.0.1:7777 ; display tools POST here",
    "LOGLAD_SESSION_ID": "optional; default = UTC timestamp at server start, e.g. 20261017T1530",
    "LOGLAD_QUERY_TIMEOUT_S": "default 10",
    "LOGLAD_LOG_LEVEL": "default INFO; server logs go to stderr ONLY (stdout is the MCP stdio channel)",
}


@dataclass(frozen=True)
class Settings:
    serenedb_dsn: str
    console_url: str = "http://127.0.0.1:7777"
    session_id: str = ""
    query_timeout_s: float = 10.0
    log_level: str = "INFO"


def load_settings() -> Settings:  # loglad_mcp/config.py — reads env (+ optional .env), never raises on missing optional vars
    ...


# --------------------------------------------------------------------------- database (Vedant)

@dataclass
class QueryResult:
    columns: list[str]
    rows: list[dict[str, Any]]      # one dict per row, keys = column names; datetimes as datetime objects
    runtime_ms: int
    sql_rendered: str               # the SQL with parameters rendered in (what goes into receipts and is re-runnable)


class Db(Protocol):
    """loglad_mcp/core/db.py: class SereneDb implements this."""

    def query(self, sql: str, params: Sequence[Any] | Mapping[str, Any] | None = None, *, timeout_s: float | None = None) -> QueryResult:
        """Run ONE read-only statement. Placeholders use psycopg style: %s or %(name)s.
        Raises DbError(code='db_error'|'timeout', message=...) — never a raw driver exception."""
        ...

    def execute(self, sql: str, params: Sequence[Any] | Mapping[str, Any] | None = None) -> None:
        """Write path. ONLY ReceiptStore may call this (INSERT INTO receipts). Tools never write."""
        ...

    def ping(self) -> bool:
        ...


class DbError(Exception):
    def __init__(self, code: Literal["db_error", "timeout"], message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


# --------------------------------------------------------------------------- tool context (Janhavi)

Role = Literal["engineer", "team_lead", "manager", "unknown"]


class ConsoleClient(Protocol):
    """loglad_mcp/core/console.py. Posts panel events (contracts/panel_event.schema.json)."""

    def post(self, event: dict[str, Any]) -> bool:
        """POST {console_url}/api/panel with a 1.5 s timeout. Returns False (never raises) when the console is down."""
        ...


@dataclass
class ToolContext:
    db: Db
    settings: Settings
    console: ConsoleClient
    receipts: Any                   # ReceiptStore (Janhavi): .write(envelope, params) -> receipt_id ; .get(receipt_id) -> dict | None ; .count() -> int


def init_context(db: Db, settings: Settings) -> ToolContext:
    """loglad_mcp/core/context.py — called ONCE by server.py at startup; builds console client + receipt store."""
    ...


def ctx() -> ToolContext:
    """Returns the context created by init_context(). Tools call this; they never construct their own Db."""
    ...


# --------------------------------------------------------------------------- registries (Janhavi) -> server (Vedant)

@dataclass(frozen=True)
class ToolSpec:
    name: str                       # must be one of envelope.schema.json $defs.ToolName
    description: str                # the full model-facing description (purpose, when NOT to use, inputs, returns)
    fn: Callable[..., dict[str, Any]]
    # fn: plain synchronous function with typed keyword parameters (Annotated[..., Field(description=...)])
    # so FastMCP derives the input schema. Every fn takes `role: Role = "unknown"` as its LAST parameter.
    # fn returns the envelope dict (contracts/envelope.schema.json). fn NEVER raises: errors go in envelope.error.


@dataclass(frozen=True)
class PromptSpec:
    name: str                       # 'engineer' | 'team_lead' | 'manager' | 'investigate'
    description: str
    text: str                       # full prompt text (loaded from loglad_mcp/prompts/*.md)
    arguments: list[str] = field(default_factory=list)   # e.g. ['question'] for 'investigate'


@dataclass(frozen=True)
class ResourceSpec:
    uri: str                        # 'loglad://schema' | 'loglad://ownership' | 'loglad://answer-contract' | 'loglad://glossary'
    name: str
    description: str
    load: Callable[[], str]         # returns markdown text; may query the db via ctx()


# server.py (Vedant) does, in this order:
#   settings = load_settings(); db = SereneDb(settings); init_context(db, settings)
#   app = FastMCP("loglad")
#   for t in TOOLS:     app.add_tool(t.fn, name=t.name, description=t.description)
#   for p in PROMPTS:   register p as an MCP prompt named p.name
#   for r in RESOURCES: register r as an MCP resource at r.uri
#   app.run()   # stdio transport
