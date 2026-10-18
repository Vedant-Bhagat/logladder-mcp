"""show_evidence and show_explainer (display). Panel events are built ONLY from stored receipt data."""
import json
import os
import re
import sys
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from loglad_mcp.core.console import make_event, tone_for_level
from loglad_mcp.core.context import ctx
from loglad_mcp.core.envelope import make_scope
from loglad_mcp.core.limits import EXPLAINER_MAX_CHARS
from loglad_mcp.core.receipts import normalise_id, receipt_ref
from loglad_mcp.tools._base import ROOT, Role, ToolError, ToolResult, tool_call

ROLE_FIELD = Field(description="Who the answer is for; pass it on every call.")
Tone = Literal["critical", "error", "warning", "info", "accent", "good"]
VALID_KIND = {
    "lines": ("search_logs", "get_timeline", "trace_request"),
    "table": ("count_by", "recurring_problems", "describe_corpus"),
    "trend": ("trend",),
    "risks": ("rank_risks",),
}
TABLE_ROWS_MAX = 26
RISK_ITEMS_MAX = 5


class Annotation(BaseModel):
    line_id: int = Field(description="id of a line shown in the panel (lines kind only).")
    label: str = Field(description="Short label, max 60 characters, e.g. 'first FATAL'.")
    tone: Tone = Field(default="accent", description="critical|error|warning|info|accent|good")


# --------------------------------------------------------------------------- body builders

def panel_line(line: dict, repeat_count: int | None = None, is_anchor: bool = False) -> dict:
    out = {
        "id": line["id"], "ts": line["ts"], "dataset": line["dataset"], "source": line["source"],
        "component": line.get("component"), "level": line["level"], "tone": tone_for_level(line["level"]),
        "message": line["message"], "highlights": line.get("highlights") or [],
        "repeat_count": max(1, int(repeat_count or line.get("repeat_count") or 1)),
    }
    if is_anchor:
        out["is_anchor"] = True
    return out


def lines_body(tool: str, data: dict) -> dict:
    if tool == "search_logs":
        groups = [{"label": "matches", "lines": [panel_line(ln) for ln in data["lines"]]}]
    elif tool == "trace_request":
        groups = [{"label": "trace", "lines": [panel_line(ln) for ln in data["lines"]]}]
    else:
        groups = [{"label": "before", "lines": [panel_line(g["sample"], g["count"]) for g in data["before"]]}]
        if data.get("anchor"):
            groups.append({"label": "anchor", "lines": [panel_line(data["anchor"], 1, is_anchor=True)]})
        groups.append({"label": "after", "lines": [panel_line(g["sample"], g["count"]) for g in data["after"]]})
    groups = [{"label": g["label"], "lines": g["lines"][:50]} for g in groups if g["lines"]]
    if not groups:
        raise ValueError("This receipt returned no lines, so there is nothing to show.")
    return {"groups": groups}


def table_body(tool: str, data: dict) -> dict:
    if tool == "count_by":
        unit = "Episodes" if data["unit"] == "episodes" else "Lines"
        cols = [{"key": "label", "label": data["group_by"].replace("_", " ").title(), "type": "text"}]
        if any("team" in r for r in data["rows"]) and data["group_by"] != "team":
            cols.append({"key": "team", "label": "Team", "type": "team"})
        cols += [{"key": "count", "label": unit, "type": "int"}, {"key": "share", "label": "Share", "type": "percent"}]
        rows = [{"label": r["label"], "team": r.get("team"), "count": r["count"], "share": r["share"]}
                for r in data["rows"]]
        if data.get("other"):
            o = data["other"]
            rows.append({"label": f"Other ({o['groups']} groups)", "team": None, "count": o["count"],
                         "share": o["share"]})
        total = {"label": "Total", "team": None, "count": data["total"], "share": 1.0 if data["total"] else 0}
        return {"columns": cols, "rows": rows[:TABLE_ROWS_MAX], "total_row": total}
    if tool == "recurring_problems":
        items = data["items"]
        both = len({i["dataset"] for i in items}) > 1
        cols = [{"key": "rank", "label": "#", "type": "int"},
                {"key": "template_text", "label": "Problem", "type": "text"}]
        if both:
            cols.append({"key": "dataset", "label": "Dataset", "type": "text"})
        cols += [{"key": "team", "label": "Team", "type": "team"},
                 {"key": "episodes", "label": "Episodes", "type": "int"},
                 {"key": "lines", "label": "Lines", "type": "int"},
                 {"key": "distinct_scopes", "label": "Scopes", "type": "int"},
                 {"key": "max_level", "label": "Max level", "type": "level"},
                 {"key": "change_pct", "label": "vs prev period", "type": "change"}]
        keys = [c["key"] for c in cols]
        return {"columns": cols, "rows": [{k: i[k] for k in keys} for i in items][:TABLE_ROWS_MAX], "total_row": None}
    # describe_corpus: components of every dataset
    rows = [{"dataset": d["dataset"], "name": c["name"], "team": c["team"], "rows": c["rows"]}
            for d in data["datasets"] for c in d["components"]]
    rows.sort(key=lambda r: -r["rows"])
    cols = [{"key": "dataset", "label": "Dataset", "type": "text"}, {"key": "name", "label": "Component", "type": "text"},
            {"key": "team", "label": "Team", "type": "team"}, {"key": "rows", "label": "Lines", "type": "int"}]
    total = {"dataset": None, "name": "Total", "team": None, "rows": sum(d["rows"] for d in data["datasets"])}
    return {"columns": cols, "rows": rows[:TABLE_ROWS_MAX], "total_row": total}


def risks_body(data: dict, actions: list | None) -> dict:
    items = []
    for i, it in enumerate(data["items"][:RISK_ITEMS_MAX]):
        action = actions[i] if actions and i < len(actions) else None
        items.append({"rank": it["rank"], "title": it["title"], "dataset": it["dataset"], "team": it["team"],
                      "score": it["score"], "inputs": it["inputs"], "stability_top3": it["stability_top3"],
                      "action": (str(action).strip() or None) if action is not None else None})
    return {"weights": data["weights"], "items": items}


def _line_ids(body: dict) -> set[int]:
    return {ln["id"] for g in body.get("groups", []) for ln in g["lines"]}


_panel_validator = None


def _validate_panel(event: dict) -> None:
    global _panel_validator
    if os.environ.get("LOGLAD_VALIDATE") != "1":
        return
    try:
        if _panel_validator is None:
            from jsonschema import Draft202012Validator
            schema = json.loads((ROOT / "contracts" / "panel_event.schema.json").read_text(encoding="utf-8"))
            _panel_validator = Draft202012Validator(schema)
        for e in _panel_validator.iter_errors(event):
            print(f"[loglad] panel event invalid at {'/'.join(map(str, e.absolute_path))}: {e.message}",
                  file=sys.stderr)
    except Exception as e:  # noqa: BLE001
        print(f"[loglad] panel validation skipped: {e}", file=sys.stderr)


LAST_EVENT: dict = {}  # tests and debugging: the last event built per panel


def _deliver(event: dict, caveats: list[str]) -> bool:
    _validate_panel(event)
    LAST_EVENT[event["type"]] = event
    delivered = ctx().console.post(event)
    if not delivered:
        caveats.append(f"Console not reachable at {ctx().settings.console_url}; the panel was not shown "
                       f"(the receipt is still valid).")
    return delivered


def _clip(text: str, n: int) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= n else text[: n - 1] + "…"


# --------------------------------------------------------------------------- show_evidence

@tool_call("show_evidence")
def show_evidence(
    receipt_id: Annotated[str, Field(description="Receipt of the tool call whose result to show, e.g. R-0003.")],
    kind: Annotated[Literal["lines", "table", "trend", "risks"], Field(
        description="lines (search_logs, get_timeline, trace_request) | table (count_by, recurring_problems, "
                    "describe_corpus) | trend (trend) | risks (rank_risks).")],
    title: Annotated[str, Field(description="Panel title, max 120 characters.")],
    annotations: Annotated[list[Annotation] | None, Field(
        description="Up to 10 labels on line ids that are in the receipt (lines kind only).")] = None,
    actions: Annotated[list[str | None] | None, Field(
        description="risks kind only: one recommended action per ranked item, in rank order (null to skip).")] = None,
    role: Annotated[Role, ROLE_FIELD] = "unknown",
) -> ToolResult:
    rid = normalise_id(receipt_id)
    if rid is None:
        raise ValueError(f"receipt_id must look like R-0001; got {receipt_id!r}.")
    if kind not in VALID_KIND:
        raise ValueError(f"kind must be one of {', '.join(VALID_KIND)}.")
    rec = ctx().receipts.get(rid)
    if rec is None:
        raise ToolError("not_found", f"No receipt {rid}.")
    if rec["error"]:
        raise ValueError(f"{rid} recorded an error ({rec['error']}); there is no evidence to show.")
    if rec["tool"] not in VALID_KIND[kind]:
        pairs = "; ".join(f"{k}: {', '.join(v)}" for k, v in VALID_KIND.items())
        raise ValueError(f"kind '{kind}' cannot show a {rec['tool']} receipt. Valid pairs — {pairs}.")
    caveats: list[str] = []
    data = rec["data"]
    if kind == "lines":
        body = lines_body(rec["tool"], data)
    elif kind == "table":
        body = table_body(rec["tool"], data)
    elif kind == "trend":
        body = {k: data[k] for k in ("metric", "bucket", "unit_label", "series")}
    else:
        body = risks_body(data, actions)
        if actions and len(actions) > len(body["items"]):
            caveats.append(f"{len(actions) - len(body['items'])} action(s) beyond the shown items were ignored.")
    if actions and kind != "risks":
        caveats.append("actions are only used with kind='risks'; ignored.")
    anns, dropped = [], 0
    ids = _line_ids(body) if kind == "lines" else set()
    for a in annotations or []:
        a = a if isinstance(a, Annotation) else Annotation(**a)
        if a.line_id in ids and len(anns) < 10:
            anns.append({"line_id": a.line_id, "label": _clip(a.label, 60), "tone": a.tone})
        else:
            dropped += 1
    if dropped:
        caveats.append(f"{dropped} annotation(s) dropped: their line_id is not among the shown lines (or more than 10).")
    payload = {"kind": kind, "title": _clip(title, 120) or rec["tool"], "receipt": receipt_ref(rec),
               "annotations": anns, "body": body}
    event = make_event("evidence", role, payload)
    delivered = _deliver(event, caveats)
    n = {"lines": lambda: len(_line_ids(body)), "table": lambda: len(body["rows"]),
         "trend": lambda: len(body["series"]), "risks": lambda: len(body["items"])}[kind]()
    what = {"lines": "lines", "table": "rows", "trend": "series", "risks": "risks"}[kind]
    summary = (f"Evidence panel '{payload['title']}' with {n} {what} from {rid} ({rec['tool']}) "
               f"{'sent to the console' if delivered else 'NOT delivered (console down)'}.")
    return ToolResult(summary, make_scope("none"), {"delivered": delivered, "panel": "evidence",
                                                     "event_id": event["event_id"]},
                      None, n, False, [], caveats)


# --------------------------------------------------------------------------- show_explainer

CITE_RE = re.compile(r"\bR-\d{4,}\b")


@tool_call("show_explainer")
def show_explainer(
    title: Annotated[str, Field(description="Panel title, max 120 characters.")],
    markdown: Annotated[str, Field(description="The explanation (CommonMark, max 8000 characters) with [R-0001] "
                                               "citations; use the answer-contract sections.")],
    receipt_ids: Annotated[list[str], Field(description="Every receipt the markdown cites, e.g. ['R-0001'].")],
    role: Annotated[Role, ROLE_FIELD] = "unknown",
) -> ToolResult:
    if not (markdown or "").strip():
        raise ValueError("markdown must not be empty.")
    if len(markdown) > EXPLAINER_MAX_CHARS:
        raise ValueError(f"markdown is {len(markdown)} characters; the limit is {EXPLAINER_MAX_CHARS}. Shorten it.")
    wanted = []
    for r in list(receipt_ids or []) + CITE_RE.findall(markdown):
        nid = normalise_id(r)
        if nid is None:
            raise ValueError(f"Not a receipt id: {r!r}.")
        if nid not in wanted:
            wanted.append(nid)
    if not wanted:
        raise ValueError("Cite at least one receipt: the explainer must be backed by tool results.")
    store = ctx().receipts
    records, missing = [], []
    for rid in wanted:
        rec = store.get(rid)
        (records.append(rec) if rec else missing.append(rid))
    if missing:
        raise ValueError(f"Unknown receipt id(s): {', '.join(missing)}. Cite only receipts returned by tool calls.")
    caveats: list[str] = []
    payload = {"title": _clip(title, 120) or "Explanation", "markdown": markdown,
               "receipts": [receipt_ref(r) for r in records]}
    event = make_event("explainer", role, payload)
    delivered = _deliver(event, caveats)
    summary = (f"Explainer '{payload['title']}' citing {len(records)} receipt(s) "
               f"{'sent to the console' if delivered else 'NOT delivered (console down)'}.")
    return ToolResult(summary, make_scope("none"), {"delivered": delivered, "panel": "explainer",
                                                     "event_id": event["event_id"]},
                      None, len(records), False, [], caveats)
