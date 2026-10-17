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


def main() -> int:
    load_dotenv()
    settings = read_settings()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stderr)

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        try:
            probe.bind((settings.host, settings.port))
        except OSError as e:
            if e.errno in (errno.EADDRINUSE, getattr(errno, "WSAEADDRINUSE", -1)):
                print(f"Port {settings.port} is already in use. Is the console already running?", file=sys.stderr)
                return 1
            raise

    print(f"LogLadder console on http://{settings.host}:{settings.port} (run claude in your own terminal)", file=sys.stderr)
    uvicorn.run(create_app(), host=settings.host, port=settings.port, log_level="warning")
    return 0


if __name__ == "__main__":
    sys.exit(main())
