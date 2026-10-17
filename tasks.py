"""Task runner (Windows has no make).  python tasks.py <command> [args]

    setup                 create .venv and install the package with dev deps
    db | db-stop          start / stop SereneDB in Docker (infra/docker-compose.yml)
    fetch                 download full BGL + OpenStack into data/raw/
    data [--sample]       parse -> Parquet -> load SereneDB (sample = data/samples/*_2k.log)
    mcp                   run the MCP server on stdio (what .mcp.json calls)
    console               start the console on 127.0.0.1:7777
    check                 contract + unit tests (no DB) and ruff
    smoke                 integration smoke test (needs SereneDB + loaded data)
    validate              validate all contract fixtures
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV_PY = ROOT / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
PY = str(VENV_PY) if VENV_PY.exists() else sys.executable
COMPOSE = ["docker", "compose", "-f", str(ROOT / "infra" / "docker-compose.yml")]


def run(*cmd: str) -> int:
    return subprocess.call(list(cmd), cwd=ROOT)


def wait_for_db() -> int:
    for _ in range(60):
        if run(PY, "-c", "from loglad_mcp.config import load_settings; from loglad_mcp.core.db import SereneDb;"
                         "raise SystemExit(0 if SereneDb(load_settings()).ping() else 1)") == 0:
            print("SereneDB is up on localhost:7890")
            return 0
        time.sleep(2)
    print("SereneDB did not come up within 2 minutes", file=sys.stderr)
    return 1


COMMANDS = {
    "setup": lambda a: run(sys.executable, "-m", "venv", ".venv") or run(
        str(VENV_PY), "-m", "pip", "install", "-e", ".[dev]"),
    "db": lambda a: run(*COMPOSE, "up", "-d") or wait_for_db(),
    "db-stop": lambda a: run(*COMPOSE, "down"),
    "fetch": lambda a: run(PY, "-m", "ingest.fetch"),
    "data": lambda a: run(PY, "-m", "ingest.load", *a),
    "mcp": lambda a: run(PY, "-m", "loglad_mcp"),
    "console": lambda a: run("npm" + (".cmd" if os.name == "nt" else ""), "--prefix", "console", "start"),
    "check": lambda a: run(PY, "-m", "pytest", "-q", "-m", "not db")
    or run(PY, "-m", "ruff", "check", "loglad_mcp", "ingest", "tests", "tasks.py"),
    "smoke": lambda a: run(PY, "-m", "pytest", "-q", "-m", "db", "-rs", "tests/integration", *a),
    "validate": lambda a: run(PY, "scripts/validate_contracts.py"),
}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        sys.exit(__doc__)
    sys.exit(COMMANDS[sys.argv[1]](sys.argv[2:]))
