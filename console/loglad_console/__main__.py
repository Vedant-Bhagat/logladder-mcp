"""`python -m loglad_console` (run from console/) — serves the console on 127.0.0.1:7777."""
from __future__ import annotations

import errno
import logging
import socket
import sys

try:
    import fastapi  # noqa: F401
    import uvicorn
    import websockets  # noqa: F401  (uvicorn needs it for /ws/panels)
except ImportError as e:  # pragma: no cover
    sys.exit(f"Missing Python package ({e.name}). From the repo root: pip install -r console/requirements.txt")

from .app import create_app
from .config import load_dotenv, read_settings
from .terminal import Terminal


def main() -> int:
    load_dotenv()
    settings = read_settings()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stderr)

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        if sys.platform != "win32":  # same as uvicorn, so a just-closed console doesn't look busy
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind((settings.host, settings.port))
        except OSError as e:
            if e.errno in (errno.EADDRINUSE, getattr(errno, "WSAEADDRINUSE", -1)):
                print(f"Port {settings.port} is already in use. Is the console already running?", file=sys.stderr)
                return 1
            raise

    terminal = Terminal(enabled=settings.terminal, shell=settings.shell, startup_command=settings.startup_command)
    print(f"LogLadder console on http://{settings.host}:{settings.port}", file=sys.stderr)
    uvicorn.run(create_app(terminal=terminal), host=settings.host, port=settings.port, log_level="warning")
    return 0


if __name__ == "__main__":
    sys.exit(main())
