"""In-memory panel state: last 20 evidence events, latest explainer and status, current role."""
from __future__ import annotations

from collections import OrderedDict
from typing import Any

EVIDENCE_HISTORY = 20
SEEN_IDS = 1000


class PanelState:
    def __init__(self) -> None:
        self.evidence: list[dict[str, Any]] = []
        self.explainer: dict[str, Any] | None = None
        self.status: dict[str, Any] | None = None
        self.role = "unknown"
        self._seen: OrderedDict[str, int] = OrderedDict()  # event_id -> arrival order
        self._counter = 0

    def apply(self, event: dict[str, Any]) -> bool:
        """Apply a validated event. Returns False for a duplicate event_id (already applied)."""
        event_id = event["event_id"]
        if event_id in self._seen:
            return False
        self._counter += 1
        self._seen[event_id] = self._counter
        if len(self._seen) > SEEN_IDS:
            self._seen.popitem(last=False)
        if event.get("role", "unknown") != "unknown":
            self.role = event["role"]
        kind = event["type"]
        if kind == "evidence":
            self.evidence.append(event)
            del self.evidence[:-EVIDENCE_HISTORY]
        elif kind == "explainer":
            self.explainer = event
        elif kind == "status":
            self.status = event
        elif kind == "reset":
            self.evidence, self.explainer, self.status = [], None, None
        return True

    def events(self) -> list[dict[str, Any]]:
        """What a fresh page needs, oldest first."""
        out = [*self.evidence, *(e for e in (self.explainer, self.status) if e)]
        return sorted(out, key=lambda e: self._seen.get(e["event_id"], 0))
