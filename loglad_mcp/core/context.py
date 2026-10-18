"""ToolContext: the one db / settings / console / receipt store the tools use (contracts/interfaces.py)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from loglad_mcp.core.console import HttpConsoleClient
from loglad_mcp.core.receipts import ReceiptStore


@dataclass
class ToolContext:
    db: Any
    settings: Any
    console: Any
    receipts: Any


_CTX: ToolContext | None = None


def init_context(db, settings) -> ToolContext:
    """Called once by server.py at start-up. Does not touch the database."""
    global _CTX
    _CTX = ToolContext(db=db, settings=settings, console=HttpConsoleClient(settings.console_url),
                       receipts=ReceiptStore(db, settings.session_id))
    return _CTX


def set_context(context: ToolContext) -> ToolContext:
    """Tests: install a context built by hand (e.g. with a fake console)."""
    global _CTX
    _CTX = context
    return _CTX


def ctx() -> ToolContext:
    if _CTX is None:
        raise RuntimeError("loglad tool context not initialised: call loglad_mcp.core.context.init_context(db, settings) first")
    return _CTX
