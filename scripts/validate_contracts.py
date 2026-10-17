"""
Validate JSON against the LogLadder contracts.

    python scripts/validate_contracts.py                 # validate every fixture in contracts/fixtures
    python scripts/validate_contracts.py envelope a.json # validate one envelope file
    python scripts/validate_contracts.py panel e.json    # validate one panel event file

Importable from tests:  from scripts.validate_contracts import validate_envelope, validate_panel_event
Requires: jsonschema>=4.18
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = ROOT / "contracts"

_ENVELOPE = Draft202012Validator(json.loads((CONTRACTS / "envelope.schema.json").read_text(encoding="utf-8")))
_PANEL = Draft202012Validator(json.loads((CONTRACTS / "panel_event.schema.json").read_text(encoding="utf-8")))


def _errors(validator: Draft202012Validator, obj: dict) -> list[str]:
    return [f"{'/'.join(map(str, e.absolute_path)) or '<root>'}: {e.message}" for e in sorted(validator.iter_errors(obj), key=str)]


def validate_envelope(obj: dict) -> list[str]:
    """Return a list of human-readable errors (empty list = valid)."""
    return _errors(_ENVELOPE, obj)


def validate_panel_event(obj: dict) -> list[str]:
    return _errors(_PANEL, obj)


def _check_dir(kind: str, folder: Path) -> int:
    fn = validate_envelope if kind == "envelope" else validate_panel_event
    bad = 0
    for path in sorted(folder.glob("*.json")):
        errs = fn(json.loads(path.read_text(encoding="utf-8")))
        status = "ok " if not errs else "BAD"
        print(f"[{status}] {kind:8} {path.relative_to(ROOT)}")
        for e in errs:
            print(f"        - {e}")
        bad += bool(errs)
    return bad


def main(argv: list[str]) -> int:
    if len(argv) == 3:
        kind, file = argv[1], Path(argv[2])
        fn = validate_envelope if kind == "envelope" else validate_panel_event
        errs = fn(json.loads(file.read_text(encoding="utf-8")))
        print("valid" if not errs else "\n".join(errs))
        return 1 if errs else 0
    bad = _check_dir("envelope", CONTRACTS / "fixtures" / "envelopes")
    bad += _check_dir("panel", CONTRACTS / "fixtures" / "panel_events")
    print("all fixtures valid" if not bad else f"{bad} invalid file(s)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
