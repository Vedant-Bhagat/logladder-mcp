"""TOOLS: the 14 LogLadder tools with their model-facing descriptions (contracts/interfaces.py ToolSpec).

    python -m loglad_mcp.tools.registry --markdown > docs/tools.md
"""
from __future__ import annotations

import json
import sys
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from loglad_mcp.tools.aggregate import count_by, trend
from loglad_mcp.tools.analyse import rank_risks, recurring_problems
from loglad_mcp.tools.display import show_evidence, show_explainer
from loglad_mcp.tools.orient import describe_corpus
from loglad_mcp.tools.reason import check_answer, get_receipt, test_hypothesis, verify_receipt
from loglad_mcp.tools.retrieve import get_timeline, search_logs, trace_request


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    fn: Callable[..., dict[str, Any]]


TAIL = "plus receipt_id, summary, total_matches, truncated, sql and caveats."

D = {
    "describe_corpus": f"""Describe what is loaded: datasets, time spans, components and their teams, levels, template and episode counts.
Use it to: orient before any other call; find exact component/level names, the time span to query, which team owns what.
Do NOT use it to: count or rank problems in a period — use count_by or recurring_problems instead.
Inputs: dataset bgl|openstack|both (default both); role.
Returns: datasets[] with rows, from/to, components (name, team, rows), levels, templates, episodes, episode_gap, labelled_rows; ownership_unmapped_rows; notes; {TAIL}""",

    "search_logs": f"""Full-text search of log lines in SereneDB (BM25-ranked), returning a small sample of the most relevant lines with highlights.
Use it to: find concrete examples of a message, error or node; get line ids to anchor get_timeline.
Do NOT use it to: count how often something happens or compare frequencies — the lines are a sample; use count_by or recurring_problems instead.
Inputs: query (required); dataset bgl|openstack (required); start/end ISO (date-only end includes the day); component; level; source (BGL node / OpenStack service); match terms (all words, default)|phrase (exact order)|fuzzy (1 edit per word); limit default 20, max 50; role.
Returns: lines[] (id, ts, source, component, level, message, template_id, episode_id, highlights), query, match; total_matches = all matching lines; {TAIL}""",

    "get_timeline": f"""Show what happened around one line or moment on the same midplane/node (BGL) or service/instance (OpenStack), repeats collapsed by template.
Use it to: see precursors and consequences of an error; build the engineer's incident story.
Do NOT use it to: test whether a precursor is a general pattern — one timeline is one case; use test_hypothesis instead.
Inputs: dataset; exactly one of anchor_id (line id from search_logs) or at (ISO time, then scope_value is required); scope node|midplane|service|instance|dataset (default midplane / service); before_s default 600, after_s default 300 (max 21600 each); collapse default true; role.
Returns: anchor line, window, before[] and after[] groups (template_id, template_text, level, count, first_ts, last_ts, sample line; max 40 per side); total_matches = lines in window; {TAIL}""",

    "trace_request": f"""Follow one OpenStack request (or instance) across nova services in time order.
Use it to: see which services a request passed through, gaps between hops, and how it ended.
Do NOT use it to: analyse BGL or find many failing requests — use search_logs or count_by instead.
Inputs: exactly one of request_id ('req-…') or instance_id (UUID); role. Lines of instances touched by the request are included.
Returns: hops[] (service, first_ts, last_ts, lines, max_level, gap_from_prev_s), outcome (template of the last ERROR/CRITICAL line, or null — never guessed), labelled_anomaly, lines[] (max 50); {TAIL}""",

    "count_by": f"""Exact counts of episodes (default) or lines grouped by one dimension, with shares; rows + other = total.
Use it to: answer 'how many / which component, team, level, template, midplane, service or HTTP status has most'; whole-corpus context for a team lead.
Do NOT use it to: find example lines — use search_logs; or rank problems over time — use recurring_problems.
Inputs: dataset bgl|openstack|both; group_by dataset|team|level|template (all), component|midplane|alert_category (BGL), service|http_status (OpenStack); alert_category/http_status need unit=lines; unit episodes|lines; start/end; level; component; team; top_n default 10, max 25; role.
Returns: rows[] (key, label, count, share, team), other (count, share, groups) or null, total, group_by, unit; scope states unit and episode_gap; {TAIL}""",

    "trend": f"""Time series per day or week (weeks start Monday) of lines, episodes, error rate or OpenStack p95 latency, optionally split into series.
Use it to: show whether something is rising or falling and for which team/component/level/template.
Do NOT use it to: explain one incident — use get_timeline; or rank what matters most — use rank_risks.
Inputs: dataset bgl|openstack; metric lines|episodes|error_rate|latency_p95 (OpenStack only); bucket day|week (default week); group_by none|team|component|service|level|template; start/end; filters level, component, team, template_id; top_series default 5, max 8; role.
Returns: series[] (name, points t/v), change[] per series (first_half, second_half, slope_per_bucket, last_vs_prev_pct), unit_label; {TAIL}""",

    "recurring_problems": f"""Top recurring problems (log templates) by number of episodes in a period, with spread, severity, owning team and change vs the previous period.
Use it to: give a team lead the list of what keeps happening and whether it is growing.
Do NOT use it to: investigate a single incident — use search_logs and get_timeline instead.
Inputs: dataset bgl|openstack|both (default both); start/end (default: last 30 days of each dataset's own span — the data is from 2005–06 and 2017); team; min_level; top_n default 10, max 25; compare_to_previous default true; role.
Returns: items[] (rank, template_id, template_text, dataset, component, team, episodes, lines, distinct_scopes, max_level, prev_episodes, change_pct or null); total_matches = templates with episodes; {TAIL}""",

    "rank_risks": f"""Rank problems for a manager by a transparent score from measured frequency (F), spread (S), trend (T), severity (V) and labelled share (L), with a stability check.
Use it to: decide what to fix first and who owns it.
Do NOT use it to: find an engineer's root cause — use get_timeline and test_hypothesis; the score says nothing about business impact.
Inputs: dataset bgl|openstack|both (default both); start/end (default last 30 days of each dataset); top_n default 5, max 10; min_episodes default 2; weights optional {{F,S,T,V,L}} (default .30/.25/.20/.15/.10, renormalised); role.
Returns: weights, items[] (rank, template_id, title, dataset, team, score 0–100, inputs F..L, raw measured values, stability_top3 = share of 10 weight variants keeping it in the top 3); {TAIL}""",

    "test_hypothesis": f"""Test whether one template tends to occur shortly BEFORE another on the same scope: support, baseline, lift, reverse lift and a verdict.
Use it to: check a suspected precursor seen in a timeline across all episodes, with examples and counter-examples.
Do NOT use it to: prove cause — precedence is association; report it under Hypotheses, never under Observed.
Inputs: dataset bgl|openstack; cause_template_id; effect_template_id (from search_logs/get_timeline/recurring_problems); window_s default 600, max 3600; scope midplane|node (BGL, default midplane) or service|instance (OpenStack, default service); start/end; role.
Returns: effect_episodes, supported_episodes, forward/reverse (support, baseline, lift), baseline_windows/hits, 3 examples, 3 counter_examples, verdict strong|moderate|weak|none|insufficient_data; {TAIL}""",

    "check_answer": f"""Check a draft answer before sending it: every number, percentage and date must match a receipt the sentence cites.
Use it to: catch unbacked, mismatched or invented claims, causal words in Observed and impact words outside Unknowns. Call it LAST, fix every problem it lists, then answer.
Do NOT use it to: look up data — it runs no queries; use get_receipt to read a receipt.
Inputs: draft (markdown with [R-0001]-style citations, ideally Scope / Observed / Hypotheses / Unknowns / Next step); role.
Returns: ok, counts (backed, unbacked, mismatched, flagged), claims[] (text, kind, status, receipt_ids, note); also updates the console status bar; {TAIL}""",

    "verify_receipt": f"""Re-run the tool call behind a receipt with its stored parameters and compare result digests.
Use it to: prove a cited number is reproducible from SereneDB right now.
Do NOT use it to: re-run display tools or check_answer (not re-runnable) — verify the receipts they cite instead.
Inputs: receipt_id (e.g. R-0003); role.
Returns: receipt_id, match, original_digest, new_digest, original_runtime_ms, new_runtime_ms; {TAIL}""",

    "get_receipt": f"""Return a stored receipt: tool, parameters, the exact SQL with values, scope, counts and the stored result data.
Use it to: show how a number was obtained, or re-read a result before citing it.
Do NOT use it to: re-check that the result still holds — use verify_receipt instead.
Inputs: receipt_id (e.g. R-0001); role.
Returns: receipt (receipt_id, created_at, session_id, tool, role, params, sql, scope, total_matches, returned, truncated, runtime_ms, result_digest, data, error); {TAIL}""",

    "show_evidence": f"""Display the stored result of a receipt in the console's evidence panel (lines, table, trend chart or risk list). The panel is built from the receipt's data only.
Use it to: show the user the evidence behind what you say, after the tool call that produced it.
Do NOT use it to: display text or numbers you wrote — pass a receipt_id, never raw lines; use show_explainer for prose.
Inputs: receipt_id; kind lines (search_logs, get_timeline, trace_request) | table (count_by, recurring_problems, describe_corpus) | trend (trend) | risks (rank_risks); title (max 120); annotations [{{line_id, label, tone}}] on shown line ids (max 10); actions (risks only: one action per ranked item); role.
Returns: delivered (false if the console is down — not an error), panel, event_id; {TAIL}""",

    "show_explainer": f"""Display your explanation (markdown) in the console's explainer panel with clickable receipt chips.
Use it to: present the answer-contract write-up (Scope, Observed, Hypotheses, Unknowns, Next step) next to the evidence.
Do NOT use it to: show claims without receipts — every [R-…] cited must exist, otherwise the call is refused; show data with show_evidence.
Inputs: title (max 120); markdown (max 8000 chars, cite as [R-0001]); receipt_ids (all receipts cited); role.
Returns: delivered (false if the console is down — not an error), panel, event_id; {TAIL}""",
}

FNS = [describe_corpus, search_logs, get_timeline, trace_request, count_by, trend, recurring_problems, rank_risks,
       test_hypothesis, check_answer, verify_receipt, get_receipt, show_evidence, show_explainer]

TOOLS: list[ToolSpec] = [ToolSpec(fn.tool_name, D[fn.tool_name], fn) for fn in FNS]


def input_schema(fn: Callable) -> dict:
    from mcp.server.fastmcp.utilities.func_metadata import func_metadata
    return func_metadata(fn).arg_model.model_json_schema()


def markdown() -> str:
    out = ["# LogLadder tools", "",
           "Generated by `python -m loglad_mcp.tools.registry --markdown > docs/tools.md` — do not edit by hand.", "",
           "Every tool returns the envelope in `contracts/envelope.schema.json` and writes a receipt.", ""]
    out += [f"- [`{t.name}`](#{t.name})" for t in TOOLS] + [""]
    for t in TOOLS:
        schema = input_schema(t.fn)
        req = set(schema.get("required", []))
        out += [f"## {t.name}", "", "```text", t.description, "```", "", "| Parameter | Type | Default | Description |",
                "| --- | --- | --- | --- |"]
        for name, p in schema.get("properties", {}).items():
            typ = _type(p, schema)
            default = "required" if name in req else f"`{json.dumps(p.get('default'))}`"
            out.append(f"| `{name}` | {typ} | {default} | {p.get('description', '').replace('|', '/')} |")
        out.append("")
    return "\n".join(out)


def _type(p: dict, schema: dict) -> str:
    if "enum" in p:
        return " \\| ".join(f"`{v}`" for v in p["enum"])
    if "anyOf" in p:
        return " \\| ".join(_type(x, schema) for x in p["anyOf"])
    if "$ref" in p:
        return p["$ref"].split("/")[-1]
    if p.get("type") == "array":
        return f"list of {_type(p.get('items', {}), schema)}"
    return f"`{p.get('type', 'any')}`"


if __name__ == "__main__":
    if "--markdown" in sys.argv:
        sys.stdout.reconfigure(encoding="utf-8")
        print(markdown())
    else:
        for t in TOOLS:
            print(f"{t.name:20} {len(t.description):5} chars")
