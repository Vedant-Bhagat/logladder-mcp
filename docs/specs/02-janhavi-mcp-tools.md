# 02 — Janhavi: the MCP tool layer

**You build the brain of the MCP server: the tool envelope, receipts, the 14 tools, the reasoning helpers, the role prompts and the resources.** Vedant gives you a database connection and wires your registries into the server; Ayoub renders what your display tools send. Read `00-team-contract.md` first.

## 1. What you own

`loglad_mcp/core/{context,envelope,receipts,limits,console,timeparse}.py`, `loglad_mcp/tools/**`, `loglad_mcp/reasoning/**`, `loglad_mcp/prompts/**`, `loglad_mcp/resources/**`, `tests/tools/**`, `tests/reasoning/**`, `docs/tools.md`, `docs/tool_selection.md`, `docs/handoff/janhavi.md`.

You do **not** edit: `server.py`, `config.py`, `core/db.py`, `sql/`, `ingest/`, `contracts/`, `console/`, `pyproject.toml`. Need a dependency? Ask Vedant. Already available: `mcp` (FastMCP), `psycopg[binary]`, `pydantic`, `jsonschema`, `pytest`.

## 2. What you get from Vedant (and how to work before it exists)

| You need | Contract | Available | Until then |
| --- | --- | --- | --- |
| `Settings`, `load_settings()` | `contracts/interfaces.py` | V0 (Sat 14:00) | construct `Settings(serenedb_dsn="")` in tests |
| `SereneDb` implementing `Db.query/execute/ping`, raising `DbError` | `contracts/interfaces.py` | V0–V1 | write `tests/tools/fakes.py::FakeDb` that returns canned rows and records SQL |
| Tables + indexes | `contracts/db_schema.sql` | V1 sample data (Sat 15:30), V2 full data (Sat 20:00) | create the tables yourself in a local SereneDB from the DDL and insert a few rows by hand |

Run SereneDB locally exactly as in the README (`python tasks.py db`), then `python tasks.py data --sample` once V1 lands. Connect your coding agent to the SereneDB docs MCP: `claude mcp add --transport http serenedb-docs https://api.serenedb.com/mcp`.

## 3. Core modules

### 3.1 `core/limits.py` — every number that bounds output

| Constant | Value |
| --- | --- |
| `LINES_DEFAULT` / `LINES_MAX` | 20 / 50 |
| `MESSAGE_MAX_CHARS` | 400 (then `…`, so ≤ 401) |
| `TIMELINE_GROUPS_MAX` | 40 per side |
| `TIMELINE_WINDOW_MAX_S` | 21 600 (6 h) per side |
| `TOP_N_DEFAULT` / `TOP_N_MAX` | 10 / 25 |
| `RISKS_DEFAULT` / `RISKS_MAX` | 5 / 10 |
| `TREND_SERIES_DEFAULT` / `TREND_SERIES_MAX` | 5 / 8 |
| `HYPOTHESIS_WINDOW_MAX_S` | 3 600 |
| `EXPLAINER_MAX_CHARS` | 8 000 |

Helpers: `clamp(value, lo, hi)`, `truncate_message(s)`. Clamping is silent but added to `caveats` ("limit clamped from 200 to 50").

### 3.2 `core/timeparse.py`

- Inputs are ISO strings: `YYYY-MM-DD`, `YYYY-MM-DDTHH:MM`, `YYYY-MM-DDTHH:MM:SS[.ffffff]`.
- `start` is inclusive. A **date-only `end` includes that whole day** (becomes `< next day`); a timestamp `end` is exclusive.
- `end <= start` → `invalid_input`.
- Missing `start`/`end` → that dataset's full span (from a cached `SELECT min(ts), max(ts)`), and the scope says so.
- Tool parameters are called **`start` and `end`** (Python can't use `from`); the envelope's `scope` uses `from`/`to`.

### 3.3 `core/envelope.py`

```python
def make_scope(dataset, start=None, end=None, filters=None, *, unit=None, episode_gap=None, group_by=None, bucket=None) -> dict
def make_envelope(tool, role, summary, scope, data, *, total_matches, returned, truncated, sql, runtime_ms, caveats) -> dict
def error_envelope(tool, role, code, message, scope=None) -> dict
def digest(data: dict) -> str   # sha256 hex of json.dumps(data, sort_keys=True, separators=(",", ":"), default=str)
```

`contract` is always `1`. `receipt_id` is filled by the receipt store (below). The summary is **one sentence written by code from real values** — never a placeholder, never a number that isn't in `data`.

### 3.4 `core/receipts.py` — `ReceiptStore`

- `__init__(db, session_id)`: next id = `max(receipt_id)` in `receipts` + 1 (so ids keep increasing across restarts).
- `write(envelope, params) -> receipt_id`: assigns the id, inserts one row (`contracts/db_schema.sql` → `receipts`), keeps it in an in-memory dict too. If the insert fails, keep the in-memory copy and add the caveat "receipt not persisted to database" — never fail the tool.
- `get(receipt_id) -> dict | None`: returns a `ReceiptRecord` (envelope schema `$defs/ReceiptRecord`), memory first, then DB.
- `count() -> int`.

### 3.5 `core/console.py`

- `HttpConsoleClient(url).post(event) -> bool` using `urllib.request`, 1.5 s timeout, never raises.
- `make_event(type, role, payload) -> dict` filling `contract`, `event_id` (uuid4 hex), `ts` (UTC ISO).
- `tone_for_level(level)`: `FATAL|FAILURE|CRITICAL → critical`, `ERROR|SEVERE → error`, `WARNING → warning`, else `info`.

### 3.6 `core/context.py`

`init_context(db, settings) -> ToolContext` (builds `HttpConsoleClient` and `ReceiptStore`) and `ctx() -> ToolContext`, exactly as in `contracts/interfaces.py`. `ctx()` before `init_context()` raises a clear `RuntimeError`.

### 3.7 The `@tool_call` wrapper (in `tools/_base.py`)

Every tool function is decorated so that the boring parts are identical everywhere:

1. Start a timer; record input params.
2. Run the body, which returns `(summary, scope, data, total_matches, returned, truncated, sql_list, caveats)`.
3. Map exceptions: `ValueError` → `invalid_input`; `DbError` → its own code; anything else → `internal` (log the traceback to **stderr**).
4. Build the envelope, write the receipt, return the dict.
5. If env `LOGLAD_VALIDATE=1`, validate the envelope against `contracts/envelope.schema.json` and log any errors to stderr (tests always set it).

`sql_list` contains **every** statement the tool ran, with parameters rendered (`QueryResult.sql_rendered`), so receipts are re-runnable and the console can show them.

## 4. The tools

All tools are synchronous functions with typed keyword parameters using `Annotated[..., Field(description=...)]` so FastMCP generates good input schemas. **Every tool's last parameter is `role: Literal["engineer","team_lead","manager","unknown"] = "unknown"`.** Every tool returns the envelope; its `data` must match the per-tool shape in `contracts/envelope.schema.json` (`$defs`). Fixture examples for most tools are in `contracts/fixtures/envelopes/`.

### 4.0 SereneDB rules for your SQL

- Full-text predicates (`@@`) work **only** when selecting `FROM bgl_idx` / `FROM os_idx`. Aggregates and window functions run on base tables (`bgl_events`, `os_events`, `episodes`, `templates`).
- Relevance: `ORDER BY BM25(bgl_idx.tableoid) DESC`.
- Query builders: phrase `ts_phrase('...')`; all-words `plainto_tsquery('...')`; fuzzy `ts_levenshtein('word', 1)` per word combined with `&&`; highlights `ts_offsets(bgl_idx.message)` returns **byte** offsets as interleaved start,end pairs — convert to **character** offsets before returning.
- Always parameterise user text (`%s`); never format user input into SQL strings. If SereneDB rejects server-side parameters inside `ts_*` functions, tell Vedant — `SereneDb` can switch to client-side binding without you changing code.
- Check function names you're unsure of (`date_trunc`, percentile functions) with the docs MCP or `SELECT * FROM sdb_docs.search('...')`. Record any SereneDB surprises in your handoff under "SereneDB notes".
- Check one `EXPLAIN` per search tool shows `IRESEARCH_SCAN`; note it in the handoff.

### 4.1 `describe_corpus` (orient, rung: all)

Params: `dataset: bgl|openstack|both = both`.
Returns per dataset: rows, from/to, components with team and row counts, levels with counts, number of templates and episodes, episode gap, labelled rows; plus `ownership_unmapped_rows` and notes. Data is static, so cache the computed `data` in memory after the first call (still write a receipt each call).

### 4.2 `search_logs` (retrieve, rung 1, engineer)

Params: `query: str`, `dataset: bgl|openstack`, `start`, `end`, `component`, `level`, `source` (BGL node or OpenStack service), `match: terms|phrase|fuzzy = terms`, `limit = 20`.
Semantics: `terms` = all words must appear; `phrase` = exact order; `fuzzy` = every word within edit distance 1.
Runs two statements: the ranked page (BM25, then `ts`), and `count(*)` with identical predicates → `total_matches`. `truncated = total_matches > returned`.
Caveat always present when truncated: "Sample of N of M matching lines; use count_by or recurring_problems for frequencies."

### 4.3 `get_timeline` (retrieve, rungs 1–2, engineer)

Params: `dataset`, exactly one of `anchor_id: int` or `at: str`, `scope: node|midplane|service|instance|dataset` (default `midplane` for BGL, `service` for OpenStack), `before_s = 600`, `after_s = 300`, `collapse = true`.
Scope value comes from the anchor line (or is required as `scope_value` when `at` is used — add that param). Lines in the window are grouped by `template_id` separately for before/after (anchor itself excluded), each group with count, first/last ts, max level and its first line as `sample`. Groups ordered by `first_ts`; max 40 per side (caveat when cut). `collapse = false` returns each line as its own group with count 1 (still capped). `total_matches` = lines in window.

### 4.4 `trace_request` (retrieve, rung 1, engineer, OpenStack only)

Params: exactly one of `request_id` or `instance_id`.
Collect lines with that request id; if any of them carry an `instance_id`, add the lines of that instance. `hops` = per service in order of first appearance with first/last ts, line count, max level, gap from the previous hop. `outcome` = text of the template of the last ERROR/CRITICAL line, else `null` — never invented. `labelled_anomaly` = any line labelled. Lines capped at 50, ordered by ts.

### 4.5 `count_by` (aggregate, rungs 2–3, team lead / manager)

Params: `dataset: bgl|openstack|both`, `group_by`, `unit: episodes|lines = episodes`, `start`, `end`, `level`, `component`, `team`, `top_n = 10`.

| `group_by` | bgl | openstack | unit=episodes? |
| --- | --- | --- | --- |
| `dataset`, `team`, `level`, `template` | yes | yes | yes (level = episode `max_level`) |
| `component` / `midplane` / `alert_category` | yes | — | component, midplane yes; alert_category lines only |
| `service` / `http_status` | — | yes | service yes; http_status lines only |

Invalid combination → `invalid_input` whose message lists the valid options. Rows sorted by count desc; beyond `top_n` goes into `other` with the number of groups folded in, so **rows + other = total**. Teams for `unit=lines` come from joining `ownership`; unmapped → `Unowned`. `dataset=both` prefixes labels (`bgl · KERNEL`) unless grouping by dataset or team. Scope always states `unit` and `episode_gap`.

### 4.6 `trend` (aggregate, rungs 2–3)

Params: `dataset: bgl|openstack`, `metric: lines|episodes|error_rate|latency_p95`, `bucket: day|week = week`, `group_by: none|team|component|service|level|template`, `start`, `end`, filters `level|component|team|template_id`, `top_series = 5`.
Error levels: BGL `FATAL, FAILURE, SEVERE, ERROR`; OpenStack `ERROR, CRITICAL`. `error_rate` = error lines / all lines per bucket. `latency_p95` = 95th percentile of `latency_s` (OpenStack only). Series beyond `top_series` (by total) are dropped with a caveat. `change` per series: sum of first half vs second half of buckets, least-squares slope per bucket, last bucket vs previous in %. Weeks start Monday.

### 4.7 `recurring_problems` (analyse, rungs 2–3, team lead)

Params: `dataset: bgl|openstack|both = both`, `start`, `end`, `team`, `min_level`, `top_n = 10`, `compare_to_previous = true`.
Default window = **the last 30 days of each dataset's own span** (the datasets are from 2005–06 and 2017; say so in caveats). From `episodes ⋈ templates`: per template — episodes, lines, distinct `scope_key`s, max level, team (most frequent), component; previous period = same length immediately before; `change_pct = (cur − prev) / prev × 100`, `null` when prev is 0. Sort by episodes, then lines.

### 4.8 `rank_risks` (analyse, rung 4, manager)

Params: `dataset: bgl|openstack|both = both`, `start`, `end`, `top_n = 5`, `min_episodes = 2`, `weights` (optional object F,S,T,V,L).
Put the maths in `reasoning/risk.py` (pure functions, unit-tested); the tool only fetches inputs.

| Input | Definition |
| --- | --- |
| F | percentile rank of episode count among candidates of the same dataset (highest = 1; one candidate = 1) |
| S | percentile rank of distinct scopes (midplanes / instances) |
| T | g = (second-half − first-half) / (first-half + second-half) ∈ [−1, 1]; T = (g + 1) / 2 (0.5 = flat) |
| V | max level: FATAL/FAILURE/CRITICAL 1.0 · SEVERE/ERROR 0.7 · WARNING 0.4 · else 0.1 |
| L | labelled_lines / lines |

`score = 100 × Σ wᵢ·xᵢ`, default weights F .30, S .25, T .20, V .15, L .10 (renormalised if overridden). **Stability**: for each of the 10 variants (each weight ±0.05, renormalised), rank again; `stability_top3` = share of variants where the item is still top 3. `dataset=both` ranks within each dataset, then merges by score with a caveat that percentiles are per dataset. `raw` carries the measured inputs so every score is explainable.

### 4.9 `test_hypothesis` (reason, rungs 2–3, engineer / team lead)

Params: `dataset`, `cause_template_id`, `effect_template_id`, `window_s = 600` (max 3600), `scope: midplane|node|service|instance` (default midplane / service), `start`, `end`.
Use **episode intervals** (efficient, and lines-within-an-episode are covered by it):

- *support* = effect episodes that have a cause episode on the same `scope_key` overlapping `[effect.start_ts − W, effect.start_ts)`, divided by all effect episodes.
- *baseline* = over the scopes that have any effect episode, split the period into consecutive W-length windows; share of (scope, window) pairs overlapped by a cause episode.
- *lift* = support / baseline. *reverse* = the same with cause and effect swapped.
- Verdict: `insufficient_data` if fewer than 5 effect episodes; `strong` if lift ≥ 3, support ≥ 0.5 and forward lift > reverse lift; `moderate` if lift ≥ 1.5 and support ≥ 0.25; `weak` if lift > 1; else `none`.
- 3 examples (supported) and 3 counter-examples (unsupported) with episode id, scope, effect start, last cause time.
- Caveats always include: "Precedence is association, not proof of cause" and the approximation used.

### 4.10 `check_answer` (reason, every role, called last)

Params: `draft: str`. No SQL except receipt lookups.

1. Split the draft into sentences/bullets; find receipt citations `[R-0001]` in each.
2. For each number (with commas/decimals), percentage and date in a sentence: `backed` if it equals a value in the cited receipts' data, `total_matches`, `returned` or scope (tolerance: matches when rounded to the precision written; percentages also match `share × 100`); `mismatched` if receipts are cited but no value matches; `unbacked` if no receipt is cited.
3. Ignore structural numbers: receipt ids, list numbering, "top N" / "first N" with N ≤ 10, numbers inside backticks.
4. `causal_word` flagged inside an **Observed** section ("caused", "because", "due to", "led to", "resulted in").
5. `impact_word` flagged anywhere except an **Unknowns** section ("downtime", "outage", "revenue", "cost", "€", "$", "customers", "users affected", "SLA", "loss").
6. `ok` = no unbacked, mismatched or flagged claims.
7. Post a `status` panel event (`receipt_count`, claim counts) to the console — ignore failure.

### 4.11 `verify_receipt` and `get_receipt` (reason)

`get_receipt(receipt_id)` returns the stored `ReceiptRecord`. `verify_receipt(receipt_id)` re-invokes **the same tool function with the stored params** in verify mode (no new receipt, no console post), and compares `digest(new_data)` with the stored digest; display tools and `check_answer` → `invalid_input` ("not re-runnable"). Unknown id → `not_found`.

### 4.12 `show_evidence` and `show_explainer` (display)

`show_evidence(receipt_id, kind: lines|table|trend|risks, title, annotations = [], actions = None)`: loads the receipt, builds an `evidence` panel event (contract `panel_event.schema.json`) **from the receipt's stored data only**, posts it.

| `kind` | Valid source tools | Body built from |
| --- | --- | --- |
| `lines` | `search_logs` (group `matches`), `get_timeline` (`before` / `anchor` / `after`, each group's `sample` with `repeat_count = count`), `trace_request` (group `trace`) | `LogLine` → `PanelLine` with `tone_for_level` |
| `table` | `count_by`, `recurring_problems`, `describe_corpus` (components) | columns as in `fixtures/panel_events/02_evidence_table.json` |
| `trend` | `trend` | series as-is |
| `risks` | `rank_risks` | top 5 items + `actions[i]` (Claude's words, aligned by rank) |

Annotations must reference `line_id`s present in the body (drop others with a caveat). Wrong kind/tool pair → `invalid_input` listing the valid pairs. Console down → `delivered: false` plus a caveat, **not** an error.

`show_explainer(title, markdown, receipt_ids)`: every id must exist (`invalid_input` otherwise — this blocks fake citations); builds `ReceiptRef`s from the store; markdown ≤ 8 000 chars. Same delivery rules.

Display envelopes use `scope.dataset = "none"` and still get a receipt id.

## 5. Tool descriptions (judged for Best MCP Server)

Each `ToolSpec.description` follows this template (≤ 1 200 characters):

```
<one-line purpose>.
Use it to: <the questions it answers>.
Do NOT use it to: <the tempting wrong use> — use <other tool> instead.
Inputs: <each param, its default and limit, in one line each>.
Returns: <the data fields that matter>, plus receipt_id, total_matches, truncated, sql, caveats.
```

The "Do NOT use it to" line is mandatory. Key ones: `search_logs` is not for frequencies; `count_by` is not for finding examples; `recurring_problems` is not for one incident; `rank_risks` is not for engineers' root cause; `test_hypothesis` does not prove cause; `show_*` must reference receipts, never raw text.

## 6. Prompts and resources

**Prompts** (`prompts/*.md` + `prompts/registry.py → PROMPTS`). Each role prompt contains: the role and its goal; "pass `role=<role>` on every tool call"; the playbook (tool order); what to show in the console; the answer contract; "call `check_answer` on your draft, fix every unbacked/mismatched/flagged claim, then answer"; what to avoid.

| Prompt | Playbook |
| --- | --- |
| `engineer` | `describe_corpus` if unsure → `search_logs` → `get_timeline` (or `trace_request`) → `test_hypothesis` for any suspected precursor → `show_evidence(kind=lines)` + `show_explainer` → `check_answer` |
| `team_lead` | `recurring_problems` → `trend` grouped by team → `count_by` (unit episodes) for whole-corpus context → `show_evidence(kind=table/trend)` → `check_answer` |
| `manager` | `rank_risks` → drill the top item with `recurring_problems` → `show_evidence(kind=risks, actions=[…])` → `check_answer`; short answer, decisions not diagnostics, no invented impact |
| `investigate` (arg `question`) | answers the same issue three times — engineer, team lead, manager — in that order, each with its own evidence and next step |

Answer contract (also the `loglad://answer-contract` resource): **Scope · Observed (each with [R-…]) · Hypotheses (with support numbers, how to confirm/refute) · Unknowns · Next step**.

**Resources** (`resources/registry.py → RESOURCES`): `loglad://schema` (reads `contracts/db_schema.sql`), `loglad://ownership` (queries `ownership` → markdown table), `loglad://answer-contract`, `loglad://glossary` (line, template, episode, risk, receipt, lift, ladder).

## 7. Tests (how you prove it)

| Kind | Where | What |
| --- | --- | --- |
| Unit | `tests/reasoning/` | `risk.py` maths (percentiles, ties, stability), claim extraction and matching, hypothesis verdict thresholds |
| Tool | `tests/tools/` with `FakeDb` | each tool: valid envelope (`LOGLAD_VALIDATE=1`), limits clamp, error mapping, truncation flag |
| DB | `tests/tools/` marked `@pytest.mark.db` | each tool against the sample data; skipped automatically if SereneDB isn't reachable |
| Contract | `pytest tests/contract` | must stay green |

Commands: `pytest tests/tools tests/reasoning tests/contract` and `pytest -m db` with SereneDB running.

`docs/tool_selection.md` (J4): 15 questions (5 per role) run in Claude Code; for each, the tools Claude called vs the expected path, and any description change you made because of it.

`docs/tools.md` is generated from `TOOLS` (name, description, input schema) by `python -m loglad_mcp.tools.registry --markdown > docs/tools.md`.

## 8. Milestones

| Milestone | Due | Done when |
| --- | --- | --- |
| **J1** | W1 Sat 16:00 | core modules + `@tool_call`; `describe_corpus`, `search_logs` pass FakeDb tests and run on sample DB; registry exports them |
| **J2** | W2 Sat 21:00 | `get_timeline`, `trace_request`, `count_by`, `trend`, `recurring_problems`, `show_evidence`, `show_explainer`; display events validate against the panel schema |
| **J3** | W3 Sun 09:30 | `rank_risks`, `test_hypothesis`, `check_answer`, `verify_receipt`, `get_receipt`; 4 prompts; 4 resources |
| **J4** | W4 Sun 13:00 | descriptions tuned from `docs/tool_selection.md`; `docs/tools.md` generated |

Each milestone is one PR with an updated `docs/handoff/janhavi.md`.
