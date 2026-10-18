"""Console client: POST panel events to {LOGLAD_CONSOLE_URL}/api/panel (spec 02 §3.5). Never raises."""
from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime
from urllib import request

log = logging.getLogger(__name__)


class HttpConsoleClient:
    def __init__(self, url: str, timeout_s: float = 1.5) -> None:
        self.url = (url or "http://127.0.0.1:7777").rstrip("/")
        self.timeout_s = timeout_s

    def post(self, event: dict) -> bool:
        try:
            req = request.Request(f"{self.url}/api/panel", data=json.dumps(event).encode("utf-8"), method="POST",
                                  headers={"Content-Type": "application/json"})
            with request.urlopen(req, timeout=self.timeout_s) as resp:
                return 200 <= resp.status < 300
        except Exception as e:  # noqa: BLE001  # console down, refused, timeout, bad status
            log.info("console post failed: %s", e)
            return False


def make_event(type: str, role: str, payload: dict) -> dict:
    return {
        "contract": 1,
        "event_id": uuid.uuid4().hex,
        "ts": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "type": type,
        "role": role,
        "payload": payload,
    }


def tone_for_level(level: str | None) -> str:
    lv = (level or "").upper()
    if lv in ("FATAL", "FAILURE", "CRITICAL"):
        return "critical"
    if lv in ("ERROR", "SEVERE"):
        return "error"
    if lv == "WARNING":
        return "warning"
    return "info"
