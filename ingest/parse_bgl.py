"""BGL line -> row dict matching bgl_events in contracts/db_schema.sql (minus id/template_id/episode_id)."""
from __future__ import annotations

import re
from datetime import datetime

NODE_RE = re.compile(r"^(R\d\d)-(M\d)")


def parse_line(line: str) -> dict | None:
    parts = line.rstrip("\r\n").split(maxsplit=9)
    if len(parts) < 9:
        return None
    label, unix, _date, node, ts, _node2, msg_type, component, level = parts[:9]
    try:
        ts = datetime.strptime(ts, "%Y-%m-%d-%H.%M.%S.%f")
        unix = int(unix)
    except ValueError:
        return None
    node = None if node == "NULL" else node
    m = NODE_RE.match(node or "")
    return {
        "ts": ts, "unix_ts": unix, "node": node,
        "rack": m[1] if m else None, "midplane": f"{m[1]}-{m[2]}" if m else None,
        "msg_type": msg_type, "component": component, "level": level.upper(),
        "alert_category": None if label == "-" else label, "is_alert": label != "-",
        "message": parts[9] if len(parts) == 10 else "",
    }
