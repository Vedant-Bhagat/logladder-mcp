# Tool selection log (J4)

**Status: run on the full data on 2026-10-18 — 15 of 15 questions took the expected path.** Results, including the tools Claude actually called, are in `docs/validation.md` §5 (re-run with `python tasks.py tool-selection` then `python tasks.py validation`). No description changes were needed.

How to run each question: start a fresh `claude` session, pick the role prompt (`/mcp__loglad__engineer`,
`/mcp__loglad__team_lead`, `/mcp__loglad__manager` — exact form per Vedant's M2 note), paste the question,
and copy the tool calls in order. "OK" = Claude's path matches the expected path or is an equally valid one.

## Engineer

| # | Question | Expected path | Claude called | OK? |
| --- | --- | --- | --- | --- |
| E1 | What happened right before the first FATAL `data TLB error interrupt` on BGL? | search_logs(phrase, level=FATAL) → get_timeline(anchor_id) → show_evidence(lines) → check_answer | | |
| E2 | Is the `instruction cache parity error corrected` burst a precursor of TLB errors on the same midplane? | search_logs → get_timeline → test_hypothesis(cause=parity, effect=TLB) → show_explainer → check_answer | | |
| E3 | Trace OpenStack request `<a req-… id from search_logs>` — where did it spend time and how did it end? | trace_request(request_id) → show_evidence(lines) → check_answer | | |
| E4 | Find lines mentioning "instanse" (typo) on nova-compute. | search_logs(match=fuzzy, component=nova-compute) | | |
| E5 | Which node logged the most KERNEL FATAL lines? | count_by(dataset=bgl, group_by=midplane, unit=lines, level=FATAL, component=KERNEL) — **not** search_logs | | |

## Team lead

| # | Question | Expected path | Claude called | OK? |
| --- | --- | --- | --- | --- |
| T1 | What keeps breaking for HPC Kernel & Runtime lately? | recurring_problems(team=…) → trend(episodes, group_by=template) → show_evidence(table, trend) → check_answer | | |
| T2 | Is OpenStack getting slower? | trend(dataset=openstack, metric=latency_p95) → show_evidence(trend) → check_answer | | |
| T3 | Which team has the most episodes overall? | count_by(dataset=both, group_by=team, unit=episodes) → show_evidence(table) | | |
| T4 | How did the BGL error rate develop week by week, per component? | trend(metric=error_rate, bucket=week, group_by=component) | | |
| T5 | Which HTTP status codes does nova-api return, and how often? | count_by(dataset=openstack, group_by=http_status, unit=lines) | | |

## Manager

| # | Question | Expected path | Claude called | OK? |
| --- | --- | --- | --- | --- |
| M1 | What should we fix first, and who owns it? | rank_risks → recurring_problems(top item) → show_evidence(risks, actions) → check_answer | | |
| M2 | Is the top risk stable if we weigh trend more? | rank_risks(weights={T: 0.4}) → compare stability_top3 | | |
| M3 | How much downtime did the TLB errors cause? | rank_risks / recurring_problems; answer must put downtime under **Unknowns** (check_answer flags it elsewhere) | | |
| M4 | Give me a one-paragraph status for OpenStack. | rank_risks(dataset=openstack) → show_explainer → check_answer | | |
| M5 | Can you prove the number you gave me? | verify_receipt(receipt_id) / get_receipt | | |

## Description changes made because of this log

None: all 15 questions took the expected path on the first run (docs/validation.md §5).

## Pre-run review of the descriptions

Before the runs, each description was checked for the mandatory spec §5 lines:

- `search_logs` — "Do NOT use it to: count how often…" (E5 is the trap question).
- `count_by` — "Do NOT use it to: find example lines".
- `recurring_problems` — "Do NOT use it to: investigate a single incident".
- `rank_risks` — "Do NOT use it to: find an engineer's root cause … says nothing about business impact" (M3).
- `test_hypothesis` — "Do NOT use it to: prove cause".
- `show_evidence` / `show_explainer` — receipt ids only, never raw text.

All 14 descriptions are 482–889 characters (limit 1 200); `tests/tools/test_analyse_reason_display.py::test_registry_contract` enforces the limit and the "Do NOT use it to:" line.
