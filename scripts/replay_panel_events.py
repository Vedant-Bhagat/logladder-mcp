"""
Replay panel-event fixtures into a running console, exactly as the MCP display tools will.
Lets the console be built and demoed with no database and no MCP server.

    python scripts/replay_panel_events.py                      # all fixtures, 1.5 s apart
    python scripts/replay_panel_events.py --delay 0            # all at once
    python scripts/replay_panel_events.py 01_evidence_lines    # one fixture (name without .json)
    python scripts/replay_panel_events.py --url http://127.0.0.1:7777

Standard library only. Exit code 1 if the console rejects any event.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "contracts" / "fixtures" / "panel_events"


def post(url: str, event: dict) -> tuple[int, str]:
    req = urllib.request.Request(
        url.rstrip("/") + "/api/panel",
        data=json.dumps(event).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=3) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except urllib.error.URLError as e:
        return 0, f"console not reachable: {e.reason}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("names", nargs="*", help="fixture names without .json (default: all)")
    ap.add_argument("--url", default=os.environ.get("LOGLAD_CONSOLE_URL", "http://127.0.0.1:7777"))
    ap.add_argument("--delay", type=float, default=1.5)
    args = ap.parse_args()

    files = [FIXTURES / f"{n}.json" for n in args.names] if args.names else sorted(FIXTURES.glob("*.json"))
    failed = 0
    for path in files:
        event = json.loads(path.read_text(encoding="utf-8"))
        event["event_id"] = f"replay-{uuid.uuid4().hex[:12]}"          # fresh id so the console does not dedupe
        event["ts"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        status, body = post(args.url, event)
        ok = status in (200, 202)
        failed += not ok
        print(f"[{status or '---'}] {path.stem:22} {'' if ok else body[:200]}")
        if args.delay:
            time.sleep(args.delay)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
