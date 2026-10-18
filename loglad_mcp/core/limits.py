"""Every number that bounds tool output (spec 02 §3.1). Clamping is silent but reported in caveats."""
from __future__ import annotations

LINES_DEFAULT = 20
LINES_MAX = 50
MESSAGE_MAX_CHARS = 400
TIMELINE_GROUPS_MAX = 40
TIMELINE_WINDOW_MAX_S = 21_600
TOP_N_DEFAULT = 10
TOP_N_MAX = 25
RISKS_DEFAULT = 5
RISKS_MAX = 10
TREND_SERIES_DEFAULT = 5
TREND_SERIES_MAX = 8
HYPOTHESIS_WINDOW_MAX_S = 3_600
EXPLAINER_MAX_CHARS = 8_000


def clamp(value: int, lo: int, hi: int, caveats: list[str] | None = None, name: str = "limit") -> int:
    """Clamp value into [lo, hi]; when it moves and `caveats` is given, say so there."""
    clamped = max(lo, min(hi, value))
    if clamped != value and caveats is not None:
        caveats.append(f"{name} clamped from {value} to {clamped}")
    return clamped


def truncate_message(s: str) -> str:
    """At most MESSAGE_MAX_CHARS characters, then '…' (so at most 401)."""
    return s if len(s) <= MESSAGE_MAX_CHARS else s[:MESSAGE_MAX_CHARS] + "…"
