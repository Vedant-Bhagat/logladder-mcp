"""Paths and settings. Everything comes from env vars, plus the repo-root .env for keys not already set."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

CONSOLE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = CONSOLE_ROOT.parent
SCHEMA_PATH = REPO_ROOT / "contracts" / "panel_event.schema.json"
WEB_DIST = CONSOLE_ROOT / "dist" / "web"


def load_dotenv(path: Path = REPO_ROOT / ".env") -> None:
    """Minimal KEY=VALUE reader; never overrides variables that are already set."""
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        os.environ.setdefault(key, value)


@dataclass(frozen=True)
class Settings:
    host: str = "127.0.0.1"
    port: int = 7777
    terminal: bool = True
    shell: str = ""
    startup_command: str = "claude"


def read_settings(env: dict[str, str] | None = None) -> Settings:
    env = os.environ if env is None else env
    try:
        port = int(env.get("LOGLAD_CONSOLE_PORT", "") or 7777)
    except ValueError:
        port = 7777
    startup = env.get("LOGLAD_STARTUP_COMMAND")  # unset -> claude; set but empty -> nothing
    return Settings(
        port=port if port > 0 else 7777,
        terminal=(env.get("LOGLAD_TERMINAL", "on") or "on").strip().lower() != "off",
        shell=(env.get("LOGLAD_SHELL") or "").strip(),
        startup_command="claude" if startup is None else startup.strip(),
    )
