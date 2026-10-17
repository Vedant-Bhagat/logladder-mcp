"""OpenStack (nova) line -> row dict matching os_events in contracts/db_schema.sql (minus id/template_id/episode_id)."""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

LINE_RE = re.compile(
    r"^(?P<file>\S+) (?P<date>\S+) (?P<time>\S+) (?P<pid>\d+) (?P<level>[A-Z]+) (?P<logger>\S+) ?"
    r"(?:\[(?P<ctx>[^\]]*)\] )?(?P<msg>.*)$"
)
HTTP_RE = re.compile(
    r'^(?P<ip>\S+) "(?P<method>[A-Z]+) (?P<path>\S+) HTTP/[\d.]+" status: (?P<status>\d+) '
    r"len: (?P<len>\d+) time: (?P<lat>[\d.]+)"
)
UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
INSTANCE_RE = re.compile(rf"\[instance: ({UUID})\]")


def load_labels(path: Path) -> set[str]:
    """Instance ids from Loghub's anomaly_labels.txt (any UUID in the file)."""
    return set(re.findall(UUID, path.read_text(encoding="utf-8", errors="replace"))) if path.exists() else set()


def _tok(v: str | None) -> str | None:
    return None if v in (None, "", "-") else v


def parse_line(line: str, log_part: str, labelled: set[str]) -> dict | None:
    m = LINE_RE.match(line.rstrip("\r\n"))
    if not m:
        return None
    try:
        ts = datetime.strptime(f"{m['date']} {m['time']}", "%Y-%m-%d %H:%M:%S.%f")
    except ValueError:
        return None
    ctx = (m["ctx"] or "").split()
    request = ctx[0] if ctx and ctx[0].startswith("req-") else None
    msg = m["msg"]
    inst = INSTANCE_RE.search(msg)
    http = HTTP_RE.match(msg)
    instance_id = inst[1] if inst else None
    return {
        "ts": ts, "source_file": m["file"], "log_part": log_part,
        "service": m["file"].split(".log")[0], "pid": int(m["pid"]), "level": m["level"],
        "logger": m["logger"], "request_id": request,
        "user_id": _tok(ctx[1]) if request and len(ctx) > 1 else None,
        "tenant_id": _tok(ctx[2]) if request and len(ctx) > 2 else None,
        "instance_id": instance_id,
        "client_ip": http["ip"].split(",")[0] if http else None,
        "http_method": http["method"] if http else None, "http_path": http["path"] if http else None,
        "http_status": int(http["status"]) if http else None, "resp_len": int(http["len"]) if http else None,
        "latency_s": float(http["lat"]) if http else None,
        "labelled_anomaly": instance_id in labelled, "message": msg,
    }
