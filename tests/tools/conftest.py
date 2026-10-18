import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ["LOGLAD_VALIDATE"] = "1"

from fakes import OWNERS, FakeConsole, FakeDb, ts

from loglad_mcp.config import Settings
from loglad_mcp.core import timeparse
from loglad_mcp.core.context import ToolContext, set_context
from loglad_mcp.core.receipts import ReceiptStore
from loglad_mcp.tools import orient


class Env:
    def __init__(self) -> None:
        self.db = FakeDb()
        self.console = FakeConsole()
        self.settings = Settings(serenedb_dsn="", session_id="test")
        self.ctx = set_context(ToolContext(self.db, self.settings, self.console, ReceiptStore(self.db, "test")))
        self.db.on(r"FROM ownership", OWNERS)
        self.db.on(r"min\(ts\) AS lo, max\(ts\) AS hi FROM bgl_events",
                   [{"lo": ts("2005-06-03T15:42:50"), "hi": ts("2006-01-03T07:13:09")}])
        self.db.on(r"min\(ts\) AS lo, max\(ts\) AS hi FROM os_events",
                   [{"lo": ts("2017-05-16T00:00:00"), "hi": ts("2017-05-16T00:14:47")}])


@pytest.fixture
def env():
    timeparse.clear_span_cache()
    orient._cache.clear()
    return Env()
