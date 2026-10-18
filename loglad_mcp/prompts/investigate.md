# LogLadder — investigate one question for all three roles

Answer the question below **three times, in this order: engineer, team lead, manager** — the same issue climbing the ladder from one incident to a decision. Each part uses its own tool calls, its own evidence in the console, and ends with its own next step.

## Part 1 — Engineer (`role="engineer"` on every call)

`describe_corpus` if unsure → `search_logs` → `get_timeline` (or `trace_request` for one OpenStack request) → `test_hypothesis` for any suspected precursor → `show_evidence(kind="lines")` with annotations → `show_explainer`.

## Part 2 — Team lead (`role="team_lead"` on every call)

`recurring_problems` (is this incident's template recurring?) → `trend` with `metric="episodes"` grouped by team or template → `count_by` with `unit="episodes"` for whole-corpus context → `show_evidence(kind="table")` and `show_evidence(kind="trend")` → `show_explainer`.

## Part 3 — Manager (`role="manager"` on every call)

`rank_risks` → drill the top item (or this issue, if it ranks) with `recurring_problems` → `show_evidence(kind="risks", actions=[…])` → `show_explainer`. Short: decisions, not diagnostics.

## Answer contract (each part)

**Scope · Observed (each bullet with its receipt [R-…]) · Hypotheses (with support numbers and how to confirm/refute) · Unknowns · Next step.**

- Observed contains only tool results — no "caused", "because", "due to", "led to", "resulted in".
- Impact words (downtime, outage, revenue, cost, customers, users affected, SLA, loss, €, $) only under Unknowns — no tool measures impact.
- Numbers exactly as the tools returned them; say whether they are lines or episodes.

## Before you answer

For each part, call `check_answer` with that part's draft and fix every `unbacked`, `mismatched` or `flagged` claim. Then give the three parts in order, each headed **Engineer**, **Team lead**, **Manager**.

## Avoid

- Re-using one role's evidence as another's without new tool calls where the playbook asks for them.
- Counting from `search_logs` samples; presenting `test_hypothesis` as proof; impact claims.
- Sending raw text to the evidence panel — `show_evidence` takes receipt ids only.
