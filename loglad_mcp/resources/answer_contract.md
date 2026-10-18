# Answer contract

Every LogLadder answer — engineer, team lead or manager — has these five sections, in this order.

## Scope
Dataset(s), time window, scope (midplane, node, service, instance or whole dataset) and unit (**lines** or **episodes**, with the episode gap: BGL 10m, OpenStack 60s). If the window was defaulted to "the last 30 days", say it is the last 30 days of the dataset's own span (BGL 2005–06, OpenStack 2017).

## Observed
Only what tools returned. Every bullet ends with the receipt that measured it, e.g. `[R-0003]`. Numbers are copied exactly (or rounded to fewer digits) from that receipt. No causal words here: "caused", "because", "due to", "led to", "resulted in".

## Hypotheses
Possible explanations, labelled as such, each with its `test_hypothesis` numbers when available (support, baseline, lift, reverse lift, verdict) and how to confirm or refute it. Precedence is association, not proof.

## Unknowns
What the logs cannot tell: business impact, downtime, cost, users or customers affected, SLA, hardware changes, fixes deployed. Impact words belong here and nowhere else.

## Next step
One concrete action and who takes it.

---

Before answering, call `check_answer` with the full draft and fix every claim it marks `unbacked`, `mismatched` or `flagged`.
