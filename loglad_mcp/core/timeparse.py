"""ISO time inputs -> query windows (spec 02 §3.2).

`start` is inclusive. A date-only `end` covers that whole day; a timestamp `end` is exclusive.
Missing bounds fall back to the dataset's full span (cached `SELECT min(ts), max(ts)`).
"""
from __future__ import annotations

import re
import threading
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}(:\d{2}(\.\d{1,6})?)?)?$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
EVENT_TABLE = {"bgl": "bgl_events", "openstack": "os_events"}

_span_cache: dict[str, tuple[datetime, datetime]] = {}
_span_lock = threading.Lock()


def parse_iso(value: str, name: str = "time") -> datetime:
    """Parse one of YYYY-MM-DD, YYYY-MM-DDTHH:MM, YYYY-MM-DDTHH:MM:SS[.ffffff]; ValueError otherwise."""
    v = (value or "").strip().replace(" ", "T")
    if not ISO_RE.match(v):
        raise ValueError(f"'{name}' must be YYYY-MM-DD, YYYY-MM-DDTHH:MM or YYYY-MM-DDTHH:MM:SS[.ffffff]; got {value!r}.")
    try:
        return datetime.fromisoformat(v)
    except ValueError as e:
        raise ValueError(f"'{name}' is not a real date/time: {value!r}.") from e


def iso(value: Any) -> str | None:
    """datetime/date -> ISO string without timezone (contract IsoTime); None stays None."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None).isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value).replace(" ", "T")


def iso_day(value: Any) -> str:
    """A bucket start -> 'YYYY-MM-DD'."""
    return (value.date() if isinstance(value, datetime) else value).isoformat()


@dataclass(frozen=True)
class Window:
    """[start, end) for SQL plus the strings the envelope scope shows as from/to."""
    start: datetime
    end: datetime          # exclusive
    frm: str
    to: str
    full_span: bool        # True when both bounds came from the dataset span

    @property
    def seconds(self) -> float:
        return (self.end - self.start).total_seconds()


def dataset_span(db, dataset: str) -> tuple[datetime, datetime]:
    """(min ts, max ts) of one dataset, cached for the process (the data is static)."""
    with _span_lock:
        if dataset in _span_cache:
            return _span_cache[dataset]
    row = db.query(f"SELECT min(ts) AS lo, max(ts) AS hi FROM {EVENT_TABLE[dataset]}").rows[0]
    if row["lo"] is None:
        raise ValueError(f"Dataset '{dataset}' has no rows loaded.")
    span = (row["lo"], row["hi"])
    with _span_lock:
        _span_cache[dataset] = span
    return span


def clear_span_cache() -> None:
    with _span_lock:
        _span_cache.clear()


def resolve_window(db, dataset: str, start: str | None, end: str | None) -> Window:
    """Turn user `start`/`end` into a Window; missing bounds use the dataset's own span."""
    s = parse_iso(start, "start") if start else None
    e = parse_iso(end, "end") if end else None
    e_excl = None
    if e is not None:
        e_excl = e + timedelta(days=1) if DATE_RE.match(end.strip()) else e
    if s is not None and e_excl is not None and e_excl <= s:
        raise ValueError(f"'end' ({end}) is not after 'start' ({start}).")
    if s is None or e is None:
        lo, hi = dataset_span(db, dataset)
        if s is None:
            s = lo
        if e_excl is None:
            e_excl = hi + timedelta(microseconds=1)
            e = hi
        if e_excl <= s:
            raise ValueError(f"The window from {iso(s)} to {iso(e)} is empty for dataset '{dataset}'.")
    return Window(s, e_excl, start.strip() if start else iso(s), end.strip() if end else iso(e),
                  full_span=start is None and end is None)


def check_pair(start: str | None, end: str | None) -> None:
    """Validate start/end without a database (for dataset=both callers before per-dataset windows)."""
    s = parse_iso(start, "start") if start else None
    e = parse_iso(end, "end") if end else None
    if s and e:
        e_excl = e + timedelta(days=1) if DATE_RE.match(end.strip()) else e
        if e_excl <= s:
            raise ValueError(f"'end' ({end}) is not after 'start' ({start}).")
