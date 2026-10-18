"""Claim extraction and matching for check_answer (spec 02 §4.10). Pure functions.

A draft is split into units (each bullet, or each sentence of a paragraph). Every number, percentage, date
or time in a unit is a claim: `backed` if it equals a value in the receipts the unit cites (rounded to the
precision written), `mismatched` if receipts are cited but none holds it, `unbacked` if nothing is cited.
Causal words are flagged inside Observed; impact words everywhere except Unknowns.
"""
from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

RID_RE = re.compile(r"\bR-(\d{4,})\b")
BULLET_RE = re.compile(r"^\s*(?:[-*+•]|\d{1,2}[.)])\s+")
SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z\[(*_\"'])")
SECTIONS = {"scope": "scope", "observed": "observed", "observations": "observed", "hypotheses": "hypotheses",
            "hypothesis": "hypotheses", "unknowns": "unknowns", "unknown": "unknowns", "next step": "next step",
            "next steps": "next step"}
BOLD_LABEL_RE = re.compile(r"^(\*\*|__)\s*([A-Za-z ]+?)\s*:?\s*\1\s*:?\s*(.*)$")
COLON_LABEL_RE = re.compile(r"^([A-Za-z ]+?)\s*:\s*(.*)$")

DATE_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d{1,6})?)?)?\b")
TIME_RE = re.compile(r"(?<![\d:])\d{1,2}:\d{2}(?::\d{2}(?:\.\d{1,6})?)?(?![\d:])")
PERCENT_RE = re.compile(r"(?<![\w.])[-+−]?\d[\d,]*(?:\.\d+)?\s?%")
NUMBER_RE = re.compile(r"(?<![\w.\-/:])[-+−]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?![\w\-/:%]|\.\d)")
STRUCTURAL_RE = re.compile(r"\b(?:top|first|last|bottom)\s+(?:[1-9]|10)\b", re.IGNORECASE)
BACKTICK_RE = re.compile(r"`[^`]*`")
UNIT_WORD_RE = re.compile(r"^\s*([A-Za-z][A-Za-z\-]{0,24})")
DURATION = {"s": 1, "sec": 1, "secs": 1, "second": 1, "seconds": 1, "m": 60, "min": 60, "mins": 60,
            "minute": 60, "minutes": 60, "h": 3600, "hr": 3600, "hrs": 3600, "hour": 3600, "hours": 3600,
            "day": 86400, "days": 86400, "week": 604800, "weeks": 604800}

CAUSAL_RE = re.compile(r"\b(caused|because|due to|led to|resulted in)\b", re.IGNORECASE)
IMPACT_RE = re.compile(r"(\bdowntime\b|\boutages?\b|\brevenue\b|\bcosts?\b|€|\$|\bcustomers?\b|\busers affected\b|"
                       r"\bSLAs?\b|\bloss(?:es)?\b)", re.IGNORECASE)


@dataclass
class Unit:
    text: str
    section: str | None
    receipt_ids: list[str] = field(default_factory=list)


def normalise_rid(n: str) -> str:
    return f"R-{int(n):04d}"


def heading(line: str) -> tuple[str | None, str]:
    """(section, text after the label) when the line is an answer-contract heading, else (None, '').

    Accepts '## Observed', '**Observed**', '**Observed:** text', 'Observed:' and 'Observed: text'.
    """
    if line.startswith("#"):
        name = line.lstrip("#").strip().strip("*_").strip().rstrip(":").strip().lower()
        return SECTIONS.get(name), ""
    for pat, gi in ((BOLD_LABEL_RE, 2), (COLON_LABEL_RE, 1)):
        m = pat.match(line)
        if m and m.group(gi).strip().lower() in SECTIONS:
            return SECTIONS[m.group(gi).strip().lower()], m.group(gi + 1).strip()
    return SECTIONS.get(line.lower()), ""


def split_units(draft: str) -> list[Unit]:
    """Bullets are one unit each; paragraphs split into sentences. Headings set the current section."""
    units: list[Unit] = []
    section: str | None = None
    para: list[str] = []

    def flush():
        if para:
            text = " ".join(para)
            for s in SENTENCE_SPLIT.split(text):
                if s.strip():
                    units.append(Unit(s.strip(), section))
            para.clear()

    for raw in (draft or "").splitlines():
        line = raw.strip()
        if not line:
            flush()
            continue
        section_name, rest = heading(line)
        if section_name:
            flush()
            section = section_name
            if rest:
                units.append(Unit(rest, section))
            continue
        if line.startswith("#"):
            flush()
            continue
        if BULLET_RE.match(line):
            flush()
            units.append(Unit(BULLET_RE.sub("", line, count=1), section))
        else:
            para.append(line)
    flush()
    for u in units:
        u.receipt_ids = list(dict.fromkeys(normalise_rid(n) for n in RID_RE.findall(u.text)))
    return units


# --------------------------------------------------------------------------- values in receipts

@dataclass
class Values:
    numbers: list[float] = field(default_factory=list)
    strings: list[str] = field(default_factory=list)


def collect_values(record: dict) -> Values:
    vals = Values()

    def walk(o: Any) -> None:
        if isinstance(o, bool) or o is None:
            return
        if isinstance(o, (int, float)):
            vals.numbers.append(float(o))
        elif isinstance(o, str):
            vals.strings.append(o)
            if DATE_RE.match(o):
                vals.numbers.append(float(o[:4]))  # a year written alone, e.g. "in 2005"
        elif isinstance(o, dict):
            for v in o.values():
                walk(v)
        elif isinstance(o, (list, tuple)):
            for v in o:
                walk(v)

    walk(record.get("data"))
    walk(record.get("scope"))
    for k in ("total_matches", "returned"):
        walk(record.get(k))
    return vals


def _decimals(token: str) -> int:
    t = token.replace(",", "")
    return len(t.split(".")[1]) if "." in t else 0


def _to_float(token: str) -> float:
    return float(token.replace(",", "").replace("−", "-").replace("%", "").strip())


def match_number(x: float, d: int, numbers: list[float], percent: bool = False,
                 scales: tuple[float, ...] = (1.0,)) -> tuple[bool, float | None]:
    """True when some receipt value rounds (at the precision written) to |x|. Returns the value used."""
    target = round(abs(x), d)
    for v in numbers:
        cands = [abs(v) * s for s in scales]
        if percent:
            cands.append(abs(v) * 100)
        for c in cands:
            if round(c, d) == target:
                return True, c
    return False, None


def closest(x: float, numbers: list[float]) -> float | None:
    return min(numbers, key=lambda v: abs(abs(v) - abs(x))) if numbers else None


def match_date(token: str, strings: list[str]) -> bool:
    t = token.replace(" ", "T")
    if DATE_RE.fullmatch(token):
        return any(s.replace(" ", "T").startswith(t) for s in strings)
    return any(f"T{t}" in s.replace(" ", "T") or f"T0{t}" in s.replace(" ", "T") for s in strings)


# --------------------------------------------------------------------------- the check

def _mask(text: str, pattern: re.Pattern) -> str:
    return pattern.sub(lambda m: " " * len(m.group(0)), text)


def extract(text: str) -> list[tuple[str, str, int]]:
    """(kind, token, end offset) for every date/time/percent/number claim, structural numbers removed."""
    t = _mask(_mask(_mask(text, BACKTICK_RE), RID_RE), re.compile(r"\[[^\]]*R-\d{4,}[^\]]*\]"))
    t = _mask(t, STRUCTURAL_RE)
    out = []
    for kind, pat in (("date", DATE_RE), ("date", TIME_RE), ("percent", PERCENT_RE), ("number", NUMBER_RE)):
        for m in pat.finditer(t):
            out.append((kind, m.group(0).strip(), m.end(), m.start()))
        t = _mask(t, pat)
    out.sort(key=lambda o: o[3])
    return [(k, tok, end) for k, tok, end, _ in out]


def check(draft: str, lookup: Callable[[str], dict | None]) -> dict:
    """CheckAnswerData for a draft; `lookup(receipt_id)` returns a ReceiptRecord or None."""
    claims: list[dict] = []
    cache: dict[str, Values | None] = {}

    def values_for(rid: str) -> Values | None:
        if rid not in cache:
            rec = lookup(rid)
            cache[rid] = collect_values(rec) if rec else None
        return cache[rid]

    for u in split_units(draft):
        known = [r for r in u.receipt_ids if values_for(r) is not None]
        missing = [r for r in u.receipt_ids if values_for(r) is None]
        nums = [n for r in known for n in values_for(r).numbers]
        strs = [s for r in known for s in values_for(r).strings]
        for kind, tok, end in extract(u.text):
            word = UNIT_WORD_RE.match(u.text[end:])
            follow = word.group(1) if word else ""
            text = f"{tok} {follow}".strip() if kind == "number" and follow else tok
            claim = {"text": text, "kind": kind, "status": "backed", "receipt_ids": list(u.receipt_ids), "note": None}
            if not u.receipt_ids:
                claim["status"] = "unbacked"
                claim["note"] = "No receipt cited; add [R-…] from the tool call that measured it, or remove it."
            elif not known:
                claim["status"] = "mismatched"
                claim["note"] = f"Cited receipt(s) not found: {', '.join(missing)}."
            elif kind == "date":
                if not match_date(tok, strs):
                    claim["status"] = "mismatched"
                    claim["note"] = f"No date/time {tok} in {', '.join(known)}."
            else:
                try:
                    x = _to_float(tok)
                except ValueError:
                    continue
                d = _decimals(tok.replace("%", "").strip())
                scale = DURATION.get(follow.lower())
                ok, v = match_number(x, d, nums, percent=kind == "percent",
                                     scales=(1.0,) if not scale else (1.0, 1.0 / scale))
                if not ok:
                    claim["status"] = "mismatched"
                    near = closest(x, nums)
                    claim["note"] = (f"{', '.join(known)} hold no value {tok}" +
                                     (f" (closest: {near:g})." if near is not None else "."))
                elif v is not None and abs(v - abs(x)) > 1e-9:
                    claim["note"] = f"rounded from {round(v, 4):g}"
            claims.append(claim)
        if u.section == "observed":
            for m in dict.fromkeys(w.group(0).lower() for w in CAUSAL_RE.finditer(u.text)):
                claims.append({"text": m, "kind": "causal_word", "status": "flagged", "receipt_ids": list(u.receipt_ids),
                               "note": "Observed states what the logs show; move cause to Hypotheses with "
                                       "test_hypothesis support numbers."})
        if u.section != "unknowns":
            for m in dict.fromkeys(w.group(0).lower() for w in IMPACT_RE.finditer(u.text)):
                claims.append({"text": m, "kind": "impact_word", "status": "flagged", "receipt_ids": [],
                               "note": f"No receipt measures {m}; move it to Unknowns."})
    counts = {k: sum(1 for c in claims if c["status"] == k) for k in ("backed", "unbacked", "mismatched", "flagged")}
    ok = counts["unbacked"] == 0 and counts["mismatched"] == 0 and counts["flagged"] == 0
    return {"ok": ok, "counts": counts, "claims": claims}
