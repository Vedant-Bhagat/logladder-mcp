"""Settings from env (+ optional .env in the repo root). Contract: contracts/interfaces.py."""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DSN = "postgresql://postgres:loglad@127.0.0.1:7890/"  # keep in sync with .env.example


@dataclass(frozen=True)
class Settings:
    serenedb_dsn: str
    console_url: str = "http://127.0.0.1:7777"
    session_id: str = ""
    query_timeout_s: float = 10.0
    log_level: str = "INFO"


def load_settings() -> Settings:
    load_dotenv(ROOT / ".env", override=False)
    env = os.environ.get
    return Settings(
        serenedb_dsn=env("SERENEDB_DSN") or DEFAULT_DSN,
        console_url=(env("LOGLAD_CONSOLE_URL") or "http://127.0.0.1:7777").rstrip("/"),
        session_id=env("LOGLAD_SESSION_ID") or datetime.now(UTC).strftime("%Y%m%dT%H%M"),
        query_timeout_s=float(env("LOGLAD_QUERY_TIMEOUT_S") or 10),
        log_level=(env("LOGLAD_LOG_LEVEL") or "INFO").upper(),
    )
