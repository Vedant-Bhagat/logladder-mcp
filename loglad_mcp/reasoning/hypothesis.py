"""Precedence statistics for test_hypothesis (spec 02 §4.9). Pure functions over episode intervals.

support  = share of effect episodes with a cause interval on the same scope overlapping [start − W, start)
baseline = share of (scope, W-window) pairs, over scopes with any effect episode, overlapped by a cause interval
lift     = support / baseline
"""
from __future__ import annotations

import math
from bisect import bisect_left
from dataclasses import dataclass
from datetime import datetime

EPOCH = datetime(1970, 1, 1)


def secs(dt: datetime) -> float:
    """Seconds since 1970 for a naive 'as logged' timestamp (no local-time / DST conversion)."""
    return (dt.replace(tzinfo=None) - EPOCH).total_seconds()


@dataclass(frozen=True)
class Interval:
    episode_id: int
    scope: str
    start: datetime
    end: datetime


@dataclass
class Side:
    effect_episodes: int
    supported: int
    baseline_windows: int
    baseline_hits: int
    support: float | None
    baseline: float | None
    lift: float | None
    examples: list[dict]
    counter_examples: list[dict]


def _by_scope(intervals: list[Interval]) -> dict[str, list[Interval]]:
    out: dict[str, list[Interval]] = {}
    for iv in intervals:
        out.setdefault(iv.scope, []).append(iv)
    for v in out.values():
        v.sort(key=lambda i: i.start)
    return out


def preceding_causes(effect: Interval, causes: list[Interval], starts: list[float], window_s: float,
                     max_len_s: float = float("inf")) -> list[Interval]:
    """Cause intervals (same scope, sorted by start) overlapping [effect.start − W, effect.start)."""
    t = secs(effect.start)
    lo = t - window_s
    hi_idx = bisect_left(starts, t)  # causes starting strictly before the effect
    lo_idx = 0 if max_len_s == float("inf") else bisect_left(starts, lo - max_len_s)
    return [c for c in causes[lo_idx:hi_idx] if secs(c.end) >= lo]


def baseline_hits(causes_by_scope: dict[str, list[Interval]], scopes: set[str], p0: datetime, p1: datetime,
                  window_s: float) -> tuple[int, int]:
    """(windows, hits): consecutive W windows over [p0, p1) per scope; hit = a cause interval overlaps it."""
    span = (p1 - p0).total_seconds()
    k = max(1, math.ceil(span / window_s))
    hits = 0
    t0 = secs(p0)
    for s in scopes:
        ranges = []
        for c in causes_by_scope.get(s, []):
            a = math.floor((secs(c.start) - t0) / window_s)
            b = math.floor((secs(c.end) - t0) / window_s)
            a, b = max(a, 0), min(b, k - 1)
            if a <= b:
                ranges.append((a, b))
        ranges.sort()
        cur_a = cur_b = None
        for a, b in ranges:
            if cur_b is None or a > cur_b + 1:
                if cur_b is not None:
                    hits += cur_b - cur_a + 1
                cur_a, cur_b = a, b
            else:
                cur_b = max(cur_b, b)
        if cur_b is not None:
            hits += cur_b - cur_a + 1
    return k * len(scopes), hits


def one_direction(causes: list[Interval], effects: list[Interval], p0: datetime, p1: datetime, window_s: float,
                  scope_name: str, n_examples: int = 3) -> Side:
    by_scope = _by_scope(causes)
    starts = {s: [secs(c.start) for c in v] for s, v in by_scope.items()}
    max_len = {s: max(secs(c.end) - secs(c.start) for c in v) for s, v in by_scope.items()}
    supported, examples, counters = 0, [], []
    for e in sorted(effects, key=lambda i: (i.start, i.episode_id)):
        prior = preceding_causes(e, by_scope.get(e.scope, []), starts.get(e.scope, []), window_s,
                                 max_len.get(e.scope, 0.0))
        if prior:
            supported += 1
            if len(examples) < n_examples:
                last = max(prior, key=lambda c: c.end)
                examples.append({"episode_id": e.episode_id, scope_name: e.scope, "effect_start": _iso(e.start),
                                 "cause_episode_id": last.episode_id, "cause_last_seen": _iso(last.end)})
        elif len(counters) < n_examples:
            counters.append({"episode_id": e.episode_id, scope_name: e.scope, "effect_start": _iso(e.start),
                             "cause_last_seen": None})
    n = len(effects)
    windows, hits = baseline_hits(by_scope, {e.scope for e in effects}, p0, p1, window_s)
    support = supported / n if n else None
    baseline = hits / windows if windows else None
    lift = support / baseline if support is not None and baseline else None
    return Side(n, supported, windows, hits, _r(support), _r(baseline), _r(lift, 2), examples, counters)


def verdict(forward: Side, reverse: Side, min_effects: int = 5) -> str:
    if forward.effect_episodes < min_effects:
        return "insufficient_data"
    lift, support = forward.lift, forward.support or 0.0
    if lift is None:
        return "none"
    rev = reverse.lift if reverse.lift is not None else 0.0
    if lift >= 3 and support >= 0.5 and lift > rev:
        return "strong"
    if lift >= 1.5 and support >= 0.25:
        return "moderate"
    if lift > 1:
        return "weak"
    return "none"


def _r(v: float | None, nd: int = 4) -> float | None:
    return None if v is None else round(v, nd)


def _iso(dt: datetime) -> str:
    return dt.replace(tzinfo=None).isoformat()
