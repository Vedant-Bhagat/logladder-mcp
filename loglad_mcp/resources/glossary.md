# Glossary

**Line** — one log line as logged (a row of `bgl_events` or `os_events`). Line counts are inflated by bursts: one failing node can write thousands of identical lines.

**Template** — the message with variable parts replaced by `<*>` (Drain3 clustering), e.g. `generating core.<*>`. `template_id` is global: BGL 1–99,999, OpenStack 100,000+.

**Episode** — consecutive lines of one template on one scope with gaps shorter than the episode gap: BGL 10 minutes per (template, midplane — or node when there is no midplane); OpenStack 60 seconds per (template, service). Episodes count *occurrences of a problem*, not lines, so they are the default unit for "how often".

**Risk** — `rank_risks` score 0–100 = 100 × (0.30·F + 0.25·S + 0.20·T + 0.15·V + 0.10·L): F frequency (percentile of episodes), S spread (percentile of distinct midplanes / instances), T trend (second vs first half of the window), V severity (max level), L labelled share (alert-labelled BGL lines / anomaly-labelled OpenStack instances). The weights are a policy choice; `stability_top3` says how often an item stays in the top 3 when each weight moves ±0.05.

**Receipt** — the record every tool call writes (`R-0001`, …): tool, parameters, the exact SQL with values, scope, counts, runtime and a SHA-256 digest of the result data. Cite receipts as `[R-0001]`; `get_receipt` shows one, `verify_receipt` re-runs it and compares digests.

**Lift** — from `test_hypothesis`: support (share of effect episodes preceded by the cause within the window on the same scope) divided by baseline (share of all windows of that length on those scopes that contain the cause). Lift > 1 means the cause shows up before the effect more often than by chance; it is association, not proof. Reverse lift tests the opposite order.

**Ladder** — the three rungs of the same question: engineer (one incident: lines, timeline, precursor) → team lead (recurring problems, trends, ownership) → manager (ranked risks, owners, decisions).

**Datasets** — `bgl`: Blue Gene/L supercomputer RAS log, June 2005 – January 2006. `openstack`: nova-api / nova-scheduler / nova-compute logs, May 2017. Teams in `loglad://ownership` are fictional.
