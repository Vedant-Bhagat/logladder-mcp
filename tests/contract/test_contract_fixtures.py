"""Contract smoke tests. Everyone runs these; they must pass on every branch before a merge."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.validate_contracts import validate_envelope, validate_panel_event  # noqa: E402

ENVELOPES = sorted((ROOT / "contracts/fixtures/envelopes").glob("*.json"))
PANELS = sorted((ROOT / "contracts/fixtures/panel_events").glob("*.json"))


@pytest.mark.parametrize("path", ENVELOPES, ids=lambda p: p.stem)
def test_envelope_fixture_is_valid(path):
    assert validate_envelope(json.loads(path.read_text(encoding="utf-8"))) == []


@pytest.mark.parametrize("path", PANELS, ids=lambda p: p.stem)
def test_panel_fixture_is_valid(path):
    assert validate_panel_event(json.loads(path.read_text(encoding="utf-8"))) == []


def test_contract_version_is_1():
    assert (ROOT / "contracts/VERSION").read_text(encoding="utf-8").strip() == "1"
