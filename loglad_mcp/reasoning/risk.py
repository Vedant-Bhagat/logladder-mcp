"""Risk scoring for rank_risks (spec 02 §4.8). Pure functions; the tool only fetches inputs.

score = 100 × Σ wᵢ·xᵢ over F (frequency), S (spread), T (trend), V (severity), L (labelled share).
"""
from __future__ import annotations

from dataclasses import dataclass, field

KEYS = ("F", "S", "T", "V", "L")
DEFAULT_WEIGHTS = {"F": 0.30, "S": 0.25, "T": 0.20, "V": 0.15, "L": 0.10}
SEVERITY = {"FATAL": 1.0, "FAILURE": 1.0, "CRITICAL": 1.0, "SEVERE": 0.7, "ERROR": 0.7, "WARNING": 0.4}


@dataclass
class Candidate:
    key: object                    # e.g. (dataset, template_id)
    dataset: str
    episodes: int
    distinct_scopes: int
    first_half: int
    second_half: int
    max_level: str
    lines: int
    labelled_lines: int
    inputs: dict = field(default_factory=dict)
    score: float = 0.0


def normalise_weights(weights: dict | None) -> dict:
    """Defaults for missing keys, then scale to sum 1. ValueError on unknown keys or negatives."""
    w = dict(DEFAULT_WEIGHTS)
    if weights:
        unknown = set(weights) - set(KEYS)
        if unknown:
            raise ValueError(f"weights keys must be among F, S, T, V, L; got {', '.join(sorted(unknown))}.")
        for k, v in weights.items():
            v = float(v)
            if v < 0:
                raise ValueError(f"weight {k} must be >= 0.")
            w[k] = v
    total = sum(w.values())
    if total <= 0:
        raise ValueError("weights must not all be 0.")
    return {k: w[k] / total for k in KEYS}


def percentile_ranks(values: list[float]) -> list[float]:
    """Mid-rank percentile in [0, 1]: highest unique value = 1, lowest = 0, ties share; one value = 1."""
    n = len(values)
    if n == 1:
        return [1.0]
    out = []
    for v in values:
        less = sum(1 for x in values if x < v)
        equal = sum(1 for x in values if x == v)
        out.append((less + (equal - 1) / 2) / (n - 1))
    return out


def trend_input(first_half: int, second_half: int) -> float:
    total = first_half + second_half
    g = 0.0 if total == 0 else (second_half - first_half) / total
    return (g + 1) / 2


def severity(level: str | None) -> float:
    return SEVERITY.get((level or "").upper(), 0.1)


def compute_inputs(cands: list[Candidate]) -> None:
    """Fill .inputs; percentiles are computed within each dataset."""
    by_ds: dict[str, list[Candidate]] = {}
    for c in cands:
        by_ds.setdefault(c.dataset, []).append(c)
    for group in by_ds.values():
        f = percentile_ranks([c.episodes for c in group])
        s = percentile_ranks([c.distinct_scopes for c in group])
        for c, fi, si in zip(group, f, s):
            c.inputs = {
                "F": round(fi, 4),
                "S": round(si, 4),
                "T": round(trend_input(c.first_half, c.second_half), 4),
                "V": severity(c.max_level),
                "L": round(c.labelled_lines / c.lines, 4) if c.lines else 0.0,
            }


def score(inputs: dict, weights: dict) -> float:
    return 100 * sum(weights[k] * inputs[k] for k in KEYS)


def rank(cands: list[Candidate], weights: dict) -> list[Candidate]:
    """Sorted by score desc; ties broken by episodes desc then key, so ranking is deterministic."""
    return sorted(cands, key=lambda c: (-score(c.inputs, weights), -c.episodes, str(c.key)))


def weight_variants(weights: dict, delta: float = 0.05) -> list[dict]:
    """10 variants: each weight ±delta (floored at 0), renormalised."""
    out = []
    for k in KEYS:
        for d in (delta, -delta):
            w = dict(weights)
            w[k] = max(0.0, w[k] + d)
            total = sum(w.values())
            out.append({kk: w[kk] / total for kk in KEYS})
    return out


def stability_top3(cands: list[Candidate], weights: dict) -> dict:
    """key -> share of the 10 weight variants in which the candidate is still in the top 3."""
    variants = weight_variants(weights)
    hits = {c.key: 0 for c in cands}
    for w in variants:
        for c in rank(cands, w)[:3]:
            hits[c.key] += 1
    return {k: v / len(variants) for k, v in hits.items()}


def score_all(cands: list[Candidate], weights: dict | None = None) -> tuple[list[Candidate], dict, dict]:
    """(ranked candidates with .score, normalised weights, stability by key)."""
    w = normalise_weights(weights)
    compute_inputs(cands)
    for c in cands:
        c.score = round(score(c.inputs, w), 1)
    ranked = rank(cands, w)
    return ranked, w, stability_top3(cands, w)
