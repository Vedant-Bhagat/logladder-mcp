"""test_hypothesis, check_answer, verify_receipt, get_receipt (reason)."""
from typing import Annotated, Literal

from pydantic import Field

from loglad_mcp.core.console import make_event
from loglad_mcp.core.context import ctx
from loglad_mcp.core.db import DbError
from loglad_mcp.core.envelope import digest, make_scope
from loglad_mcp.core.limits import HYPOTHESIS_WINDOW_MAX_S, clamp
from loglad_mcp.core.receipts import normalise_id
from loglad_mcp.reasoning import claims as claims_mod
from loglad_mcp.reasoning import hypothesis as hyp
from loglad_mcp.tools._base import (
    EVENTS,
    Role,
    Sql,
    ToolError,
    ToolResult,
    check_dataset,
    gap_label,
    in_verify_mode,
    run_verify,
    template_texts,
    to_int,
    tool_call,
    windows_for,
)

ROLE_FIELD = Field(description="Who the answer is for; pass it on every call.")

# --------------------------------------------------------------------------- test_hypothesis

HYP_SCOPES = {"bgl": ("midplane", "node"), "openstack": ("service", "instance")}
LINE_SCOPE_COL = {"node": "node", "instance": "instance_id"}


def _intervals(q: Sql, ds: str, scope: str, tid: int, start, end) -> list[hyp.Interval]:
    """Episode intervals of one template. midplane/service: rows of `episodes`; node/instance: each episode
    split by node / instance from the event lines."""
    if scope in ("midplane", "service"):
        rows = q("SELECT episode_id, scope_key AS s, start_ts AS a, end_ts AS b FROM episodes "
                 "WHERE dataset = %s AND template_id = %s AND start_ts >= %s AND start_ts < %s", (ds, tid, start, end))
    else:
        col = LINE_SCOPE_COL[scope]
        rows = q(f"SELECT episode_id, {col} AS s, min(ts) AS a, max(ts) AS b FROM {EVENTS[ds]} "
                 f"WHERE template_id = %s AND ts >= %s AND ts < %s AND {col} IS NOT NULL "
                 f"GROUP BY episode_id, {col}", (tid, start, end))
    return [hyp.Interval(to_int(r["episode_id"]), str(r["s"]), r["a"], r["b"]) for r in rows]


@tool_call("test_hypothesis")
def test_hypothesis(
    dataset: Annotated[Literal["bgl", "openstack"], Field(description="Which dataset.")],
    cause_template_id: Annotated[int, Field(description="Template suspected to come first (precursor).")],
    effect_template_id: Annotated[int, Field(description="Template of the problem being explained.")],
    window_s: Annotated[int, Field(description="How far before each effect to look, seconds; default 600, "
                                               "max 3600.")] = 600,
    scope: Annotated[Literal["midplane", "node", "service", "instance"] | None, Field(
        description="Must happen on the same: BGL midplane|node (default midplane), OpenStack service|instance "
                    "(default service).")] = None,
    start: Annotated[str | None, Field(description="Inclusive ISO start; default dataset start.")] = None,
    end: Annotated[str | None, Field(description="ISO end; default dataset end.")] = None,
    role: Annotated[Role, ROLE_FIELD] = "unknown",
) -> ToolResult:
    ds = check_dataset(dataset)
    scope = scope or HYP_SCOPES[ds][0]
    if scope not in HYP_SCOPES[ds]:
        raise ValueError(f"scope for {ds} must be one of {', '.join(HYP_SCOPES[ds])}.")
    cause, effect = int(cause_template_id), int(effect_template_id)
    if cause == effect:
        raise ValueError("cause_template_id and effect_template_id must differ.")
    caveats: list[str] = []
    window_s = clamp(int(window_s), 1, HYPOTHESIS_WINDOW_MAX_S, caveats, "window_s")
    q = Sql()
    texts = template_texts(q, [cause, effect])
    for tid in (cause, effect):
        t = texts.get(tid)
        if t is None:
            raise ToolError("not_found", f"No template {tid}.")
        if t["dataset"] != ds:
            raise ValueError(f"Template {tid} belongs to {t['dataset']}, not {ds}.")
    wins, frm, to, _ = windows_for(q, [ds], start, end)
    w = wins[ds]
    from datetime import timedelta
    pad = timedelta(seconds=window_s)
    cause_iv = _intervals(q, ds, scope, cause, w.start - pad, w.end)
    effect_iv = _intervals(q, ds, scope, effect, w.start, w.end)
    effect_pad = _intervals(q, ds, scope, effect, w.start - pad, w.end)
    fwd = hyp.one_direction(cause_iv, effect_iv, w.start, w.end, window_s, scope)
    rev = hyp.one_direction(effect_pad, [c for c in cause_iv if c.start >= w.start], w.start, w.end, window_s, scope)
    verdict = hyp.verdict(fwd, rev)
    data = {
        "cause": {"template_id": cause, "template_text": texts[cause]["template_text"]},
        "effect": {"template_id": effect, "template_text": texts[effect]["template_text"]},
        "window_s": window_s, "scope": scope,
        "effect_episodes": fwd.effect_episodes, "supported_episodes": fwd.supported,
        "baseline_windows": fwd.baseline_windows, "baseline_hits": fwd.baseline_hits,
        "forward": {"support": fwd.support, "baseline": fwd.baseline, "lift": fwd.lift},
        "reverse": {"support": rev.support, "baseline": rev.baseline, "lift": rev.lift},
        "examples": fwd.examples, "counter_examples": fwd.counter_examples, "verdict": verdict,
    }
    caveats.append("Precedence is association, not proof of cause.")
    unit = "episodes" if scope in ("midplane", "service") else f"(episode, {scope}) intervals from the event lines"
    caveats.append(f"Approximation: {unit} are treated as [first line, last line] intervals; an effect is supported "
                   f"when a cause interval on the same {scope} overlaps the {window_s} s before it. Baseline = share "
                   f"of consecutive {window_s} s windows on the {scope}s that have the effect, overlapped by a cause.")
    if fwd.support is not None and fwd.baseline == 0:
        caveats.append("Baseline is 0 (the cause never occurs on these scopes), so lift is undefined.")
    if verdict == "insufficient_data":
        caveats.append(f"Only {fwd.effect_episodes} effect episodes (< 5): no verdict.")
    sc = make_scope(ds, frm, to, {"cause_template_id": cause, "effect_template_id": effect, "scope": scope},
                    unit="episodes", episode_gap=gap_label([ds]))
    lift_txt = "undefined" if fwd.lift is None else f"{fwd.lift:g}"
    summary = (f"Template {cause} overlapped the {window_s} s before {fwd.supported} of {fwd.effect_episodes} "
               f"template-{effect} episodes on the same {scope} (support {fwd.support if fwd.support is not None else 'n/a'}) "
               f"vs a baseline of {fwd.baseline if fwd.baseline is not None else 'n/a'} (lift {lift_txt}); reverse lift "
               f"{'undefined' if rev.lift is None else f'{rev.lift:g}'}; verdict {verdict}.")
    returned = len(fwd.examples) + len(fwd.counter_examples)
    return ToolResult(summary, sc, data, fwd.effect_episodes, returned, fwd.effect_episodes > returned, q.statements,
                      caveats)


# --------------------------------------------------------------------------- check_answer

@tool_call("check_answer")
def check_answer(
    draft: Annotated[str, Field(description="Your full draft answer (markdown) with [R-0001]-style citations.")],
    role: Annotated[Role, ROLE_FIELD] = "unknown",
) -> ToolResult:
    if not (draft or "").strip():
        raise ValueError("draft must not be empty.")
    store = ctx().receipts
    unreachable: list[str] = []

    def lookup(rid: str) -> dict | None:
        try:
            return store.get(rid)
        except DbError:
            unreachable.append(rid)
            return None

    data = claims_mod.check(draft, lookup)
    c = data["counts"]
    caveats = []
    if unreachable:
        caveats.append(f"SereneDB unreachable: could not load {', '.join(sorted(set(unreachable)))}.")
    if not data["claims"]:
        caveats.append("No numbers, dates or flagged words found in the draft.")
    if not in_verify_mode():
        event = make_event("status", role, {"receipt_count": store.count(), "claims": c})
        if not ctx().console.post(event):
            caveats.append("Console not reachable; status not shown.")
    n = len(data["claims"])
    summary = (f"{n} claims checked: {c['backed']} backed, {c['unbacked']} unbacked, {c['mismatched']} mismatched, "
               f"{c['flagged']} flagged{'; ready to answer' if data['ok'] else '; fix these before answering'}.")
    return ToolResult(summary, make_scope("none"), data, None, n, False, [], caveats)


# --------------------------------------------------------------------------- receipts

NOT_RERUNNABLE = ("show_evidence", "show_explainer", "check_answer", "verify_receipt")


def _record(receipt_id: str) -> dict:
    rid = normalise_id(receipt_id)
    if rid is None:
        raise ValueError(f"receipt_id must look like R-0001; got {receipt_id!r}.")
    rec = ctx().receipts.get(rid)
    if rec is None:
        raise ToolError("not_found", f"No receipt {rid}.")
    return rec


@tool_call("get_receipt")
def get_receipt(
    receipt_id: Annotated[str, Field(description="Receipt id, e.g. R-0001.")],
    role: Annotated[Role, ROLE_FIELD] = "unknown",
) -> ToolResult:
    rec = _record(receipt_id)
    tm = "n/a" if rec["total_matches"] is None else f"{rec['total_matches']:,}"
    summary = (f"Receipt {rec['receipt_id']} from {rec['tool']} (role {rec['role']}, {rec['created_at']}): "
               f"{len(rec['sql'])} SQL statement(s), total matches {tm}, {rec['returned']} returned"
               f"{', error ' + rec['error'] if rec['error'] else ''}.")
    return ToolResult(summary, rec["scope"], {"receipt": rec}, rec["total_matches"], rec["returned"], rec["truncated"],
                      [], [])


@tool_call("verify_receipt")
def verify_receipt(
    receipt_id: Annotated[str, Field(description="Receipt id to re-run, e.g. R-0001.")],
    role: Annotated[Role, ROLE_FIELD] = "unknown",
) -> ToolResult:
    rec = _record(receipt_id)
    if rec["tool"] in NOT_RERUNNABLE:
        raise ValueError(f"{rec['receipt_id']} is from {rec['tool']}, which is not re-runnable; verify the receipts "
                         f"it cites instead.")
    from loglad_mcp.tools.registry import TOOLS
    fn = next((t.fn for t in TOOLS if t.name == rec["tool"]), None)
    if fn is None:
        raise ToolError("not_found", f"Tool {rec['tool']} is not registered.")
    new = run_verify(fn, rec["params"])
    if new.get("error"):
        raise ToolError(new["error"]["code"], f"Re-run of {rec['receipt_id']} failed: {new['error']['message']}")
    new_digest = digest(new["data"])
    match = new_digest == rec["result_digest"]
    data = {"receipt_id": rec["receipt_id"], "match": match, "original_digest": rec["result_digest"],
            "new_digest": new_digest, "original_runtime_ms": rec["runtime_ms"], "new_runtime_ms": new["runtime_ms"]}
    caveats = [] if match else [("Result differs from the stored one: the data or the code changed since the "
                                "receipt was written.")]
    summary = (f"Re-ran {rec['receipt_id']} ({rec['tool']}) with its stored parameters: result "
               f"{'identical' if match else 'DIFFERENT'} (digest {new_digest[:12]}…), {new['runtime_ms']} ms vs "
               f"{rec['runtime_ms']} ms originally.")
    return ToolResult(summary, rec["scope"], data, None, 1, False, new["sql"], caveats)
