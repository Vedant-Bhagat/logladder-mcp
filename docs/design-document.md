# LogLadder — Design Document

National AI Hackathon 2026 · SereneDB challenge "Making Sense of Logs" · Oct 17, 2026 · @Vedant

## TL;DR

**LogLadder is an evidence-first MCP server over SereneDB that lets Claude Code answer log questions for an engineer, a team lead and a manager — where every number traces to a query that actually ran.** ("LogLadder" is a working name; rename freely.)

The one-line pitch: *most teams give Claude a pipe to the database; we give Claude a toolkit that thinks about logs the way a senior SRE does — and refuses to let it make things up.*

Four ideas carry the design:

1. **The zoom ladder.** Raw lines are enriched at load time into *templates* (recurring message shapes) and *episodes* (bursts of the same problem = incidents). The engineer works at the bottom of the ladder, the team lead in the middle, the manager at the top — same data, same agent, different altitude.
2. **Evidence receipts.** Every tool call stores the SQL, filters, row counts, truncation flag and runtime under a receipt ID. Claude cites receipt IDs; anyone (including the judges) can re-run them.
3. **Reasoning as tools.** Hypotheses are tested in the database ("does X precede Y more than chance?"), and a claim checker rejects any number in the final answer that no receipt backs.
4. **The LogLadder console.** A three-panel screen: Claude Code on the left, a live panel of colour-highlighted log evidence top-right, and a panel for longer explanations bottom-right — both driven by Claude through MCP display tools.

The result maps directly onto the 100% main score (role insight 30%, search + analytics 25%, recommendation quality 25%, execution 20%) and onto the separate **Best MCP Server** award.

## 1. The challenge in one page

**SereneDB's challenge asks for a working prototype in which an AI agent answers log questions for three roles, with the database doing the search and maths and the agent doing the explaining.** Millions of log lines don't fit in a prompt, so the agent must ask focused questions through tools.

**Timeline.** Opening 16 Oct · build 17–18 Oct (48 h) · evaluation 19–20 Oct · closing 21 Oct.

### The three roles (same agent, same data, different evidence)

| Role | Their question | What the answer must contain |
| --- | --- | --- |
| Engineer | What failed, in which component, what happened just before and after? | Relevant error lines + nearby events, a possible cause, the next check |
| Team lead | Which problems recur, how often, which components/teams? | Counts and trends over a stated period, grouped by team via the ownership table; what to investigate first |
| Manager | Which observed problems deserve attention first, what next? | Short prioritized risks + actions from measured frequency and affected components; **no invented money, downtime or customer impact** |

Changing only the length of the answer per role does not count — the questions, the evidence selected and the actions must differ.

### Data (base corpus)

| Dataset | Size | Role in the brief | Notable fields |
| --- | --- | --- | --- |
| BGL (Blue Gene/L supercomputer) | 4,747,963 lines · 709 MB · 214.7 days | Search + trend data | Alert label (12 categories), timestamp, node ID, component, severity level, message |
| OpenStack (nova) | 207,820 lines · 58.6 MB | Aggregation data | nova-api / scheduler / compute, request ID, tenant ID, inline latency, labelled anomalies |

Optional: 50 billion OpenTelemetry rows as remote Parquet on S3, larger Loghub sets (Thunderbird 211M lines, Windows 114M), and RCAEval / Nezha for logs + traces + metrics.

### What we build ourselves

The brief says loader, schema and ownership table are "supplied", but the organisers' Q&A clarifies **we build all three** and run SereneDB locally (Docker, Postgres wire protocol on port 7890, no credentials by default).

### Minimum requirements (all must hold)

- [ ] At least one answer per role, each with relevant evidence, fitting detail and a role-appropriate next step
- [ ] Both retrieval and aggregation, on both BGL and OpenStack
- [ ] At least one answer uses full-text search
- [ ] At least one answer uses a whole-corpus aggregation (not a sample), with data scope and filters stated
- [ ] Practical recommendations supported by findings; a plausible next diagnostic step is fine when the cause is unproven
- [ ] Search and summary exposed as tools with clear purpose / inputs / outputs
- [ ] Show the work: executed queries + results behind every claim; hypotheses and limits labelled
- [ ] Runs from a clean checkout with setup instructions

### Deliverables

Public repo + README (workflow, setup, run, limitations) · working prototype (MCP server recommended) · tool documentation · **one worked investigation** across all three roles with queries and results · demo ≤ 5 minutes · slides.

### Scoring

| Criterion | Weight |
| --- | --- |
| Role-appropriate insight | 30% |
| Search and analytics together | 25% |
| Recommendation quality (evidence-backed, facts vs hypotheses separated) | 25% |
| Execution (clean checkout, demo, novelty, presentation) | 20% |

Separate awards: **Best MCP Server** (clear tool descriptions, correct tool selection, useful result limits, Claude connects from our instructions) and **Working with Huge Datasets**. Informal bonuses: agent-managed indexes, row-level security per role, log–trace correlation.

Sources: the challenge brief, the participant Q&A and the "Getting started with SereneDB" guide (shared PDFs).

## 2. Our thesis: smart tools, not smart prompts

**The baseline most teams will ship is a table of parsed lines, four or five thin SQL wrappers, and three role prompts — the intelligence lives in Claude's prose, and the tools are pipes.** That meets the brief, but it leaves three weaknesses the judges are explicitly looking for:

- **Lines are counted as incidents.** 10,000 matching lines may be three real events; the brief warns against exactly this.
- **Claims drift from evidence.** Nothing stops the model from writing a plausible number or cause that no query established.
- **Roles differ only in tone.** Same evidence, rephrased — which the brief says is not enough.

LogLadder moves the intelligence *into the tools and the data model*, so that the easiest path for Claude is also the correct one.

|  | Typical approach | LogLadder |
| --- | --- | --- |
| Unit of analysis | Raw lines | Lines → templates → episodes → risks |
| Recurrence | Keyword counts | Template frequency + episode counts over a stated window |
| Context around an error | ±N raw lines (often 500 copies of one message) | Timeline collapsed by template, distinct events first |
| Provenance | SQL pasted into the answer, maybe | Every tool call stores a receipt; answers cite receipt IDs; any receipt can be re-run |
| Causes | Model's guess in prose | Hypothesis tested in SQL (precedence lift + counter-examples) and labelled as hypothesis |
| Honesty guard | Prompt instructions | `check_answer` tool flags any number not backed by a receipt |
| Manager priorities | Model's opinion | Transparent risk score from measured inputs only |
| Demo surface | Terminal scroll | Console with live evidence panel driven by the agent |

### Design principles

1. **The database computes, the agent explains.** No aggregate is ever estimated by the model from sample rows.
2. **Every number has a receipt.** If it can't be traced to a stored query, it doesn't appear as a fact.
3. **Bounded outputs, honest truncation.** Every tool has a limit, returns the *total* match count alongside the sample, and says when it truncated.
4. **Few tools, sharp descriptions.** A small, well-named set beats many overlapping ones; tool selection is judged.
5. **Roles change altitude, not the system.** One server, one agent, one corpus; the role decides which rung of the ladder and which answer shape.
6. **Facts, hypotheses, unknowns — always separated.** The answer format makes mixing them hard.
7. **Reproducible from a clean checkout.** One command to start SereneDB, one to load, one to connect Claude.

## 3. Goals, non-goals, anti-goals

**Our priority order: a project we're proud of beyond the hackathon, then the main prize, then Best MCP Server.**

### Goals

- Meet every minimum requirement on BGL and OpenStack with margin.
- Make the three role answers visibly different in *evidence*, not just wording.
- Make every factual claim checkable in under 10 seconds (receipt → SQL → result).
- An MCP server the judges can connect Claude to from the README alone.
- A console that makes the evidence visible during the 5-minute demo.

### Non-goals (for the core submission)

- Open-ended text-to-SQL. The brief says parameterized tools are enough, and free SQL undermines tool selection and safety.
- Separate systems or MCP servers per role.
- Vector / hybrid search — optional in the brief; add only if the core is done.
- Huge datasets, RLS and trace correlation — stretch goals after the core works.
- Supporting arbitrary log formats. New datasets plug in through a parser + ownership mapping, but we only ship two.

### Anti-goals (would make this a failure even if it "works")

- Claude states a number, cause or impact that no query established.
- Matching lines presented as separate incidents.
- A polished UI hiding thin evidence.
- A demo that only works on our laptops.

## 4. Architecture: SereneDB at the centre

**SereneDB is not a storage bucket in this design — it is the engine that does every search, count, trend, episode build and hypothesis test, and the MCP server is a thin, disciplined layer that turns those capabilities into tools.** SereneDB isn't one of the three roles; it is what all three roles stand on, and the sponsor's own judges will look at how deeply we use it.

### 4.1 Components

| Layer | Component | Responsibility |
| --- | --- | --- |
| Engine | **SereneDB** (Docker, Postgres protocol, port 7890) | Stores events, templates, episodes, ownership and receipts; runs all full-text search, aggregation, window functions and scoring |
| Ingest | Python parsers + SQL load scripts | Raw files → Parquet → tables; template mining; episode build; indexes |
| Tools | `loglad-mcp` (Python, MCP SDK) | 12 parameterized tools + 2 display tools; writes receipts; enforces limits |
| Agent | Claude Code CLI, running in PowerShell in the console's main window | Chooses tools, reasons, writes the role-specific answer |
| Surface | LogLadder console (FastAPI + TypeScript) | Three-panel screen: agent, evidence, explainer |

### 4.2 SereneDB capability map — what we use, and for whom

| SereneDB capability | How LogLadder uses it | Serves |
| --- | --- | --- |
| Inverted index + `@@` match operator, queried from the index by name | `search_logs` over BGL and OpenStack messages | Engineer |
| BM25 ranking | Most relevant lines first, so 20 lines are the *right* 20 | Engineer |
| Phrase and proximity search (`ts_phrase`, `##`) | Exact error phrases ("failed to read message prefix") | Engineer |
| Fuzzy search (`ts_levenshtein`) | Typo-tolerant queries from humans | Engineer |
| Verbatim + timestamp fields in the same index | One query filters text AND component AND level AND time range | Engineer, team lead |
| `ts_offsets` / `ts_highlight` | Matched words highlighted in the console's evidence panel | Engineer (demo) |
| SQL aggregation, `GROUP BY`, percentiles | `count_by`, `trend`, latency p95, error rates — whole corpus | Team lead, manager |
| Window functions (`LAG`, running `SUM`) | Gaps-and-islands episode building; timelines; week-over-week | All |
| Joins (events × ownership) | Counts and trends per team | Team lead, manager |
| `read_csv` / `read_parquet` / `COPY` | Loading the parsed corpus from the mounted data folder | Setup |
| `EXPLAIN` (`IRESEARCH_SCAN` plans) | Plan stored in receipts on request — proves search ran in the index | Judges |
| Partial inverted indexes (`CREATE INDEX … WHERE`) | Optional agent-managed workspace index for one time range | Optional extension |
| Indexes over views of remote Parquet + `REINDEX INDEX` | Optional huge-dataset track (OpenTelemetry on S3) without downloading | Optional award |
| Vector / hybrid search | Optional: "find lines similar to this one" | Optional |
| Built-in docs (`sdb_docs.search`) and docs MCP | Our coding agents look up syntax while we build | Team |

References: [Inverted Index](https://serenedb.com/docs/sql/indexes/inverted) · [Full-Text Search](https://serenedb.com/docs/sql/indexes/inverted/full-text-search).

### 4.3 The rule that keeps SereneDB central

The agent never computes a number. If an answer needs a count, a rate, a percentile, a trend, an episode boundary or a lift, it comes back from a SereneDB query with a receipt. The model's job is to choose the question and explain the answer — exactly the split the brief asks for.

### 4.4 Request flow

A question travels: user → agent (role set) → MCP tool → parameterized SQL on SereneDB → result + receipt stored → envelope back to the agent → (optionally) `show_evidence` to the console → answer in the five-part contract → `check_answer` → reply. The diagram below shows the same flow.

&#91;embedded content: LogLadder architecture · roles, agent, MCP server, SereneDB, ingest\]

Roles talk to one agent; the agent only reaches data through the MCP tools, and every tool reaches SereneDB through parameterized SQL that leaves a receipt.

## 5. Data layer

**One table per dataset with parsed fields, three derived tables (templates, episodes, ownership), one receipts table, and inverted indexes on the message text.** Field names below are our proposal; confirm them against the raw files in hour 0–2.

### 5.1 Raw formats (what we parse)

BGL line (space-separated, message is the remainder):

```
- 1117838570 2005.06.03 R02-M1-N0-C:J12-U11 2005-06-03-15.42.50.675872 R02-M1-N0-C:J12-U11 RAS KERNEL INFO instruction cache parity error corrected
```

Fields in order: alert label (`-` = not an alert, otherwise an alert category code) · unix seconds · date · node · full timestamp · node (repeat) · type · component · level · message.

OpenStack line (nova, one file per service in the source names):

```
nova-api.log.1.2017-05-16_13:53:08 2017-05-16 00:00:00.008 25746 INFO nova.osapi_compute.wsgi.server [req-38101a0b-... 113d3a99... 54fadb41... - - -] 10.11.10.1 "GET /v2/54fadb41.../servers/detail HTTP/1.1" status: 200 len: 1893 time: 0.2477829
```

Fields: source file (gives the service) · date + time · pid · level · logger · `[request_id user_id tenant_id …]` · message, from which we extract HTTP method, path, status, response length, latency (`time:` seconds) and any `[instance: <uuid>]`. Loghub ships the abnormal and normal logs plus an anomaly label file listing affected instance IDs — verify the exact file names after download.

### 5.2 Schema

| Table | Purpose | Key columns |
| --- | --- | --- |
| `bgl_events` | One row per BGL line | `id` PK, `ts`, `node`, `rack` (e.g. R02), `midplane` (R02-M1), `component`, `level`, `alert_category` (NULL when `-`), `is_alert`, `message`, `template_id`, `episode_id` |
| `os_events` | One row per OpenStack line | `id` PK, `ts`, `service` (nova-api / nova-compute / nova-scheduler), `pid`, `level`, `logger`, `request_id`, `tenant_id`, `instance_id`, `http_method`, `http_path`, `http_status`, `latency_s`, `message`, `template_id`, `episode_id`, `labelled_anomaly` |
| `templates` | One row per recurring message shape | `dataset`, `template_id`, `template_text`, `example_message`, `line_count`, `first_seen`, `last_seen` |
| `episodes` | One row per burst of one problem (our "incident" unit) | `dataset`, `episode_id`, `template_id`, `component`, `team`, `start_ts`, `end_ts`, `line_count`, `distinct_nodes` / `distinct_instances`, `max_level` |
| `ownership` | Fictional component → team map | `dataset`, `component`, `team`, `team_lead` (fictional), `notes` |
| `receipts` | Provenance of every tool call (section 7) | `receipt_id`, `created_at`, `tool`, `role`, `params`, `sql`, `rows_returned`, `total_matches`, `truncated`, `runtime_ms`, `result_digest`, `result_preview` |

Notes:

- Store request, tenant and instance IDs as `VARCHAR`: SereneDB's inverted index cannot index the `UUID` type ([docs](https://serenedb.com/docs/sql/indexes/inverted)).
- `team` is denormalised onto `episodes` at build time so team-level aggregates need no join; the `ownership` table remains the source of truth.
- We keep both datasets in separate tables. The brief allows whole-corpus counts per dataset reported together; merging is not required.

### 5.3 Ownership table (fictional, documented in the README)

One fictional platform org owning both systems. Component values are confirmed with `SELECT DISTINCT component` after load; the list below is the expected shape.

| Dataset | Component | Team |
| --- | --- | --- |
| BGL | KERNEL | HPC Kernel & Runtime |
| BGL | APP | HPC Applications Support |
| BGL | MMCS, BGLMASTER, CMCS | HPC Control System |
| BGL | LINKCARD, HARDWARE, DISCOVERY, MONITOR | HPC Hardware & Interconnect |
| OpenStack | nova-api | Cloud API Platform |
| OpenStack | nova-scheduler | Cloud Scheduling |
| OpenStack | nova-compute | Cloud Compute & Hypervisors |

Anything unmapped falls to `Unowned` — and the team-lead tool reports how many lines that covers, so a gap in the mapping is visible rather than silently dropped.

### 5.4 Indexes (SereneDB inverted index)

Full-text search uses SereneDB's inverted index: `CREATE INDEX … USING inverted`, a text-search dictionary on the message column, and queries that select **from the index by name** with the `@@` match operator ([docs](https://serenedb.com/docs/sql/indexes/inverted/full-text-search)).

```sql
CREATE TEXT SEARCH DICTIONARY log_dict AS
    split_text(case := 'lower') | normalize_tokens('en_US.UTF-8', accent := false)
    WITH (frequency, position, offset);

CREATE INDEX bgl_idx ON bgl_events
    USING inverted (id, message log_dict, component, level, node, ts)
    INCLUDE (template_id, episode_id, alert_category);

VACUUM (REFRESH_TABLE) bgl_events;   -- make loaded rows searchable now

SELECT id, ts, node, component, level, message
FROM bgl_idx
WHERE message @@ ts_phrase('parity error')
  AND level @@ 'FATAL'
ORDER BY BM25(bgl_idx.tableoid) DESC
LIMIT 20;
```

Why this matters for the design:

- `position` enables phrase search (`ts_phrase`, `##` proximity); `offset` enables `ts_offsets` / `ts_highlight`, which the console uses to colour matched words.
- Verbatim columns (`component`, `level`, `node`) and the timestamp are indexed alongside the text, so one index serves "text AND component AND time range" filters.
- The index is eventually consistent; the loader runs `VACUUM (REFRESH_TABLE)` after each load.
- `ts_levenshtein` gives typo-tolerant search for free — an easy "fuzzy matching" bonus.

Exact dictionary and option names should be re-checked through the SereneDB docs MCP before coding.

### 5.5 Loading pipeline

1. **Fetch.** `scripts/fetch_data.sh` downloads `BGL.zip` and `OpenStack.tar.gz` from Zenodo (keep `?download=1` and `curl -L`).
2. **Parse.** `ingest/parse_bgl.py` and `ingest/parse_openstack.py` stream the raw files, apply one regex each, and write Parquet (or CSV) to `data/`. Malformed lines go to a `rejects` file with a count — reported in the README, never silently dropped.
3. **Load.** `sql/01_schema.sql` + `sql/02_load.sql` create tables and fill them from the mounted `/data` folder with `read_parquet` / `read_csv`.
4. **Enrich.** `ingest/templates.py` assigns `template_id`; `sql/03_episodes.sql` builds episodes (section 6).
5. **Index.** `sql/04_indexes.sql` creates the inverted indexes and refreshes them.
6. **Verify.** `sql/05_checks.sql` prints row counts per dataset (expected 4,747,963 BGL lines and 207,820 OpenStack lines), time spans and null rates — the first receipts in the system.

All of this runs from `make data` (or one `bootstrap.sh`), so judges reproduce it from a clean checkout.

## 6. Enrichment: building the zoom ladder

**At load time we add two layers above raw lines — templates and episodes — so the database can answer "what recurs" and "how many incidents" with real counts instead of keyword guesses.** This is the single most important engineering choice in the project.

### 6.1 Rung 1 → 2: lines become templates

A *template* is the stable shape of a message with the variable parts masked out:

```
instruction cache parity error corrected        → template 17
data TLB error interrupt                         → template 42
ciod: failed to read message prefix on control stream (CioStream socket to 172.16.96.116:37543) → template 88
      "ciod: failed to read message prefix on control stream (CioStream socket to <IP>:<NUM>)"
```

Two implementations, in order of preference:

1. **Drain3** (Python, the standard online log-template miner used in the Loghub research). Streams all lines once and emits a template ID per line. BGL is documented with about 320 distinct event templates, which gives us a sanity check on our output.
2. **Fallback: deterministic masking.** Replace numbers, hex, IPs, UUIDs, node IDs and paths with placeholders and hash the result. Fast, reproducible, slightly coarser. We switch to it if Drain3 on 4.7M lines is too slow on our laptops — measure in hour 1.

Template IDs are stored on every row and summarised in `templates`. A template inherits the highest severity seen for it and its first/last timestamp.

### 6.2 Rung 2 → 3: templates become episodes (our "incident" unit)

The brief warns that matching lines are not separate incidents. An *episode* is a burst of the same template in the same scope, where consecutive lines are no more than **G** apart. A new line after a longer silence starts a new episode.

| Dataset | Scope | Default gap G | Why |
| --- | --- | --- | --- |
| BGL | template + midplane (e.g. R02-M1) | 10 minutes | Hardware/kernel storms cluster on a midplane; a node-level scope would split one storm into hundreds |
| OpenStack | template + service | 60 seconds | Request-level failures are short; logs cover a much shorter span |

Episodes are computed entirely in SQL with window functions (gaps-and-islands):

```sql
WITH ordered AS (
  SELECT id, ts, template_id, midplane, component,
         CASE WHEN ts - LAG(ts) OVER w > INTERVAL '10 minutes'
                   OR LAG(ts) OVER w IS NULL THEN 1 ELSE 0 END AS is_start
  FROM bgl_events
  WINDOW w AS (PARTITION BY template_id, midplane ORDER BY ts)
), numbered AS (
  SELECT *, SUM(is_start) OVER (PARTITION BY template_id, midplane ORDER BY ts) AS seq
  FROM ordered
)
SELECT template_id, midplane, seq,
       MIN(ts) AS start_ts, MAX(ts) AS end_ts, COUNT(*) AS line_count
FROM numbered
GROUP BY template_id, midplane, seq;
```

G is a stated, tunable parameter — every answer that counts episodes says which G it used. A small sensitivity table (episode counts at G = 1, 10, 60 minutes) goes in the README so judges see the choice is deliberate, not convenient.

### 6.3 Rung 3 → 4: episodes become risks

The top rung is not stored; it is computed on demand by `rank_risks` (section 11) from episode frequency, spread, trend and severity.

### 6.4 OpenStack request stitching

OpenStack gives us a second, different kind of structure: **a request's journey across services.** nova-api lines carry the request ID and latency; scheduler and compute lines carry the instance ID. We link them so one tool call can return the whole life of a request or instance — API call → scheduling → spawn on a compute host → outcome — with timings between the hops. Instances in the anomaly label file are flagged `labelled_anomaly`, giving us ground truth to test against.

### 6.5 The ladder at a glance

| Rung | Unit | Typical size (to be measured) | Who works here | Typical question |
| --- | --- | --- | --- | --- |
| 1 | Raw line | \~5M | Engineer | "Show me what happened on R02-M1 around 15:42" |
| 2 | Template | \~hundreds | Team lead | "Which messages recur most this month, per team?" |
| 3 | Episode | thousands (depends on G) | Team lead, manager | "How many distinct storms, not lines?" |
| 4 | Risk | top \~10 | Manager | "What do we fix first?" |

Every rung links down to the one below it, so any manager-level claim can be drilled to the exact lines behind it — which is what makes the demo convincing.

## 7. Evidence receipts: every number has a paper trail

**Every tool call writes a receipt — the exact SQL, its parameters, scope, counts, truncation and runtime — and returns its ID; Claude must cite receipt IDs for every factual claim.** This turns the brief's "show your work" requirement into a property of the system rather than a habit of the model.

### 7.1 What a tool returns

Every tool returns the same envelope, so Claude learns one shape:

```json
{
  "receipt_id": "R-0042",
  "summary": "1,284 lines in 37 episodes matched 'parity error' on BGL, 2005-06-01 to 2005-06-30",
  "scope": {"dataset": "BGL", "from": "2005-06-01", "to": "2005-06-30", "filters": {"level": "FATAL"}},
  "total_matches": 1284,
  "returned": 20,
  "truncated": true,
  "data": [ ... ],
  "sql": "SELECT ... FROM bgl_idx WHERE message @@ ts_phrase('parity error') AND ...",
  "runtime_ms": 38,
  "caveats": ["Sample of 20 of 1,284 rows; use count_by for frequencies"]
}
```

The `caveats` field is written by the tool, not the model. It nudges Claude away from the classic mistakes: generalising from a sample, or treating lines as incidents.

### 7.2 How receipts are stored

- Receipts live in the `receipts` table inside SereneDB, so they survive restarts and can be queried like anything else.
- `result_digest` is a hash of the full result; `result_preview` keeps the first rows. A re-run that produces a different digest is flagged.
- IDs are short and sequential per session (`R-0001`, `R-0002`, …) so they are readable on a slide.

### 7.3 How receipts are used

| Who | How |
| --- | --- |
| Claude | Cites `[R-0042]` next to every measured claim in the final answer |
| `check_answer` tool | Matches every number in the draft against receipt values (section 9) |
| Console UI | Every receipt ID is clickable: shows SQL, scope, result and runtime |
| Judges | `verify_receipt R-0042` re-runs the SQL and compares digests |
| README | The worked investigation is exported as a receipt log — questions, tool calls, SQL and results in order |

The last row is a quiet win: the "worked investigation" deliverable is generated from receipts rather than written by hand, so it can never disagree with what actually ran.

## 8. MCP server: tools, prompts and resources

**One Python MCP server (`loglad-mcp`, official MCP Python SDK) exposes 12 core tools in four groups, 2 display tools for the console, 4 role prompts and 4 read-only resources.** Every tool returns the receipt envelope from section 7 and enforces hard limits.

### 8.1 Tool catalog

| # | Tool | Group | Rung | Mainly for | Key inputs | Returns |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | `describe_corpus` | Orient | all | everyone (first call) | `dataset?` | Row counts, time span, components, levels, teams, episode gap G, known limits |
| 2 | `search_logs` | Retrieve | 1 | Engineer | `query`, `dataset`, `from`, `to`, `component?`, `level?`, `node?`/`service?`, `match: terms\|phrase\|fuzzy`, `limit ≤ 50` | BM25-ranked lines with highlight offsets, template + episode IDs, **total match count** |
| 3 | `get_timeline` | Retrieve | 1–2 | Engineer | `anchor_id` or `at`, `scope: node\|midplane\|service\|instance`, `before`, `after`, `collapse` | Distinct events before and after the anchor, grouped by template with counts and first/last time |
| 4 | `trace_request` | Retrieve | 1 | Engineer | `request_id` or `instance_id` | OpenStack journey across api → scheduler → compute with time between hops and outcome |
| 5 | `count_by` | Aggregate | 2–3 | Team lead, manager | `dataset`, `group_by: component\|team\|level\|template\|alert_category\|service\|http_status`, `unit: lines\|episodes`, `from?`, `to?`, `filters?`, `top_n` | Whole-corpus counts with share of total and an "other" bucket |
| 6 | `trend` | Aggregate | 2–3 | Team lead, manager | `dataset`, `metric: lines\|episodes\|error_rate\|latency_p95`, `bucket: day\|week`, `group_by?`, `filters?` | Time series + simple slope and week-over-week change |
| 7 | `recurring_problems` | Analyse | 2–3 | Team lead | `dataset?`, `team?`, `from`, `to`, `top_n`, `compare_to_previous` | Templates ranked by episode count, lines, nodes affected, owning team, change vs previous period |
| 8 | `rank_risks` | Analyse | 4 | Manager | `from`, `to`, `top_n`, `weights?` | Scored risk list with every score input shown (section 11) |
| 9 | `test_hypothesis` | Reason | 2–3 | Engineer, team lead | `cause` (template or query), `effect`, `window`, `scope` | Precedence lift, support, counter-examples (section 9) |
| 10 | `check_answer` | Reason | — | everyone (last call) | `draft`, `cited_receipts` | Each number/claim: backed, unbacked, or mismatched |
| 11 | `verify_receipt` | Reason | — | judges, Claude | `receipt_id` | Re-run result, digest match yes/no, runtime |
| 12 | `get_receipt` | Reason | — | console, Claude | `receipt_id` | Stored SQL, params, result preview |
| D1 | `show_evidence` | Display | — | console | `receipt_id`, `line_ids?`, `highlight_terms?`, `title`, `annotations?` | Pushes highlighted log lines to the evidence panel |
| D2 | `show_explainer` | Display | — | console | `markdown`, `receipt_ids` | Pushes long-form explanation to the explainer panel |

Optional (only after the core works): `create_workspace_index(dataset, from, to)` and `drop_workspace_index(name)` — partial inverted indexes for a time range, using SereneDB's `CREATE INDEX … WHERE <predicate>` ([docs](https://serenedb.com/docs/sql/indexes/inverted)).

### 8.2 Why this set and not more

- **12 is deliberate.** Each tool answers one kind of question; no two overlap. Judges score tool selection, and overlapping tools make selection ambiguous.
- **No free SQL tool.** The brief says parameterized queries are sufficient; a raw-SQL tool would bypass receipts, limits and safety.
- **Every aggregate supports `unit: episodes`.** The "lines are not incidents" rule is enforced by the API, not by prompting.
- **Every retrieval tool returns `total_matches`.** A sample can never be mistaken for a frequency.

### 8.3 Hard limits (the "useful limits" judges look for)

| Limit | Value | Reason |
| --- | --- | --- |
| Lines per retrieval call | default 20, max 50 | Fits in context; truncation flagged |
| Message length per line | 400 characters, then `…` | BGL/OpenStack messages are short; protects context |
| Distinct events in a timeline | max 40 groups | Collapsed by template, counts kept |
| Rows in an aggregate | `top_n` max 25 + an "other" row | Totals always add up |
| Query timeout | 10 s, reported in receipt | Demo never hangs |
| Time range | must be stated or defaults to full dataset, echoed in `scope` | Data scope is always explicit |

### 8.4 What a good tool description looks like

Tool descriptions are written for the model as carefully as the code. Example:

```
search_logs — Full-text search over one dataset's log messages (BGL or OpenStack),
ranked by BM25. Use it to FIND specific evidence: error messages, a node, a phrase.
Do NOT use it to measure how often something happens — it returns at most 50 lines;
use count_by or recurring_problems for frequencies.
Inputs: query (words; match='phrase' for exact order, 'fuzzy' for typos),
        dataset, from/to (ISO time), optional component, level, node/service, limit.
Returns: receipt_id, total_matches (across the whole filtered scope), returned,
         truncated, lines[{id, ts, node|service, component, level, message,
         template_id, episode_id, highlight_offsets}], sql, caveats.
```

The "do NOT use it for…" line is the trick: it routes Claude to the right tool and is exactly what Best MCP Server judges reward.

### 8.5 Prompts and resources

| Kind | Name | What it does |
| --- | --- | --- |
| Prompt | `/engineer` | Sets role = engineer; playbook: search → timeline → hypothesis → next check |
| Prompt | `/team-lead` | Sets role = team lead; playbook: recurring problems → trend by team → what to investigate first |
| Prompt | `/manager` | Sets role = manager; playbook: rank risks → drill top item → actions |
| Prompt | `/investigate` | Runs the full three-role worked investigation on one issue (the demo script) |
| Resource | `loglad://schema` | Tables, fields and meanings |
| Resource | `loglad://ownership` | The ownership table |
| Resource | `loglad://answer-contract` | The four-part answer format (section 9) |
| Resource | `loglad://glossary` | Line, template, episode, risk, receipt — definitions Claude must use consistently |

## 9. Reasoning layer: making explanations checkable

**Reasoning gets three pieces of machinery: a fixed answer contract, hypothesis testing inside SereneDB, and a deterministic claim checker.** Recommendation quality is 25% of the score, and the brief repeatedly asks us to separate facts, explanations and unknowns — this layer is how we do it by construction.

### 9.1 The answer contract (all roles)

Every final answer has the same five parts, published as the `loglad://answer-contract` resource:

| Part | Contains | Rule |
| --- | --- | --- |
| Scope | Dataset(s), time window, filters, episode gap G | Always first; one line |
| Observed | Measured facts | Each carries a receipt ID; no causal words |
| Hypotheses | Possible explanations | Each states its support (from `test_hypothesis`) and what would confirm or refute it |
| Unknowns | What these logs cannot establish | e.g. user impact, root cause beyond the logs, cost |
| Next step | Role-appropriate action | Engineer: a check · Team lead: an investigation · Manager: a decision |

### 9.2 Hypothesis testing in the database

When Claude suspects "X leads to Y", it calls `test_hypothesis` instead of asserting it. The tool measures *precedence* — how often a cause template appears shortly before an effect, compared with how often it appears in any window of that length:

```latex
\text{support} = \frac{\#\{\text{effect episodes with a cause line in the } W \text{ before them, same scope}\}}{\#\{\text{effect episodes}\}}

\text{baseline} = \frac{\#\{W\text{-length windows (same scopes, same period) containing a cause line}\}}{\#\{W\text{-length windows}\}}

\text{lift} = \frac{\text{support}}{\text{baseline}}
```

The tool returns support, baseline, lift, the counts behind each, three supporting examples, three **counter-examples** (effect episodes with no cause before them) and the **reverse direction** (does Y precede X just as often?). A lift well above 1 in one direction only is evidence of an ordering, not proof of cause — and the contract labels it as a hypothesis with its numbers.

Why this matters: most teams' "possible cause" will be the model's guess. Ours is a measured association with its weak spots exposed.

### 9.3 The claim checker

`check_answer` is plain Python, no LLM. Claude calls it with its draft before replying. It:

1. Extracts every number, percentage and date from the draft.
2. Matches each against values in the receipts cited next to it (allowing rounding and derived percentages).
3. Flags causal words ("caused", "because", "due to") inside the Observed part.
4. For the manager role, flags invented-impact words ("downtime", "revenue", "€", "customers affected") unless a receipt measures them.
5. Returns `backed`, `unbacked` or `mismatched` per claim.

Claude revises until nothing is unbacked. In the console, unbacked claims would show as amber — a visual proof of honesty during the demo.

### 9.4 How reasoning differs per role

| Role | Reasoning question | Main evidence | Hypothesis type |
| --- | --- | --- | --- |
| Engineer | What chain of events led here, and what do I check next? | Timeline around the anchor, request trace | "Template X precedes the failure on this midplane" |
| Team lead | Why does this keep recurring? | Episode counts by template and team, week-over-week, spread across nodes | "It recurs on the same few midplanes" vs "it is everywhere" |
| Manager | Why is this ranked first, and what reduces the risk? | Risk score inputs, trend direction, team ownership | Kept to measured facts; actions framed as decisions (assign, investigate, monitor) |

## 10. Roles: one agent, three altitudes

**The role is always explicit — set by an MCP prompt in Claude Code or by the role switcher in the console — and it changes which rung of the ladder Claude works on, which tools it reaches for, and what kind of next step it gives.** Guessing the role from the question is only a fallback, and Claude says when it guessed ("answering as team lead").

Why explicit: "what's going on with R02?" could come from any of the three people, and a wrong guess returns the wrong evidence. An explicit role also makes row-level security per role possible later (section 15).

### 10.1 How the role is set

| Surface | Mechanism |
| --- | --- |
| Claude Code | `/engineer`, `/team-lead`, `/manager` MCP prompts inject the role playbook and set `role` on subsequent tool calls |
| Console | Role switcher in the header (Engineer · Team lead · Manager); the session restarts the agent context with that role's prompt |
| Receipts | Every receipt records the role, so the evidence log shows which role asked what |

### 10.2 Role playbooks

|  | Engineer | Team lead | Manager |
| --- | --- | --- | --- |
| Goal | Explain one failure | Find what recurs and who owns it | Decide what to fix first |
| Ladder rung | Lines and episodes | Templates and episodes by team | Risks |
| Typical tool path | `search_logs` → `get_timeline` / `trace_request` → `test_hypothesis` → `check_answer` | `recurring_problems` → `trend` by team → `count_by` → `check_answer` | `rank_risks` → drill top item with `recurring_problems` → `check_answer` |
| Evidence shown | Actual log lines, before/after, highlighted | Ranked tables and a trend | 3–5 ranked risks, each with its measured inputs |
| Hypotheses | Causal chains, tested for precedence | Concentration patterns (few nodes vs everywhere) | Minimal; only what the data supports |
| Next step shape | "Check X on node Y" (diagnostic) | "Team T investigates template Z first, because…" | "Assign / fund / monitor X; revisit when metric M changes" |
| Answer length | Detailed | Medium | Short |
| Must avoid | Generalising from a few lines | Counting lines as incidents | Inventing cost, downtime or customer impact |

### 10.3 Example questions (for testing and the demo)

**Engineer**

- "What happened on midplane R02-M1 in the hour before the first FATAL kernel error on \<date>?"
- "Search for 'parity error' in June 2005 and show the timeline around the most severe one."
- "Trace instance \<id> through nova and tell me where it failed."

**Team lead**

- "Which problems recurred most in the last 4 weeks of BGL, by episodes, per team?"
- "Is the top recurring problem concentrated on a few midplanes or spread out?"
- "How did OpenStack error rates and p95 latency per service change over the log period?"

**Manager**

- "Across both systems, what are the top 3 risks right now and what should we do about each?"
- "Which team should get engineering time first, based on what the logs show?"

### 10.4 Why the answers genuinely differ

The brief says changing only the length is not enough. In our design, the three roles differ in **tools called, ladder rung, evidence type, hypothesis type and action type** — five dimensions, all visible in the receipt log. The worked investigation (section 13) shows the same underlying issue through all three, so the difference is obvious side by side.

## 11. Manager risk score: transparent by design

**`rank_risks` scores each recurring problem from five measured inputs with visible weights, and reports how stable the top of the ranking is if the weights change.** The manager sees *why* something is first, and the brief's ban on invented losses is respected because nothing unmeasured enters the score.

### 11.1 Inputs (all computed in SereneDB)

| Input | Meaning | How measured |
| --- | --- | --- |
| F — frequency | How often it happens as incidents | Episode count in the window, as a percentile among all candidate problems |
| S — spread | How much of the system it touches | Distinct midplanes/nodes (BGL) or instances/services (OpenStack), percentile |
| T — trend | Whether it's getting worse | Episodes in the second half of the window vs the first half, clipped to \[0, 1\] |
| V — severity | How bad each occurrence looks | Highest level seen, mapped: FATAL/FAILURE 1.0 · SEVERE/ERROR 0.7 · WARNING 0.4 · INFO 0.1 |
| L — labelled | Whether the dataset's own labels call it an alert/anomaly | Share of its lines with a BGL alert label or a labelled OpenStack anomaly |

```latex
\text{risk} = 100 \times (0.30\,F + 0.25\,S + 0.20\,T + 0.15\,V + 0.10\,L)
```

The weights are a stated policy choice, not a fact. They are returned with every result and can be overridden with the `weights` input.

### 11.2 Rank stability (the non-obvious part)

A ranking is only useful if it doesn't flip on a whim. `rank_risks` re-scores the list under small weight changes (each weight ±0.05, renormalised) and reports, for each top item, **how often it stays in the top 3**. The manager answer can then say "ranked first in all weight variations" or "first by default, but sensitive to how much we weight trend" — an honest confidence signal without inventing anything.

### 11.3 Caveats Claude must carry

- BGL (2005–2006) and OpenStack (2017) come from different periods, so "recent" means the last part of **each dataset's own span**. Cross-dataset rankings are computed per dataset and presented side by side unless explicitly normalised.
- The score ranks *observed log problems*. It says nothing about business impact, which the logs don't contain — this goes in Unknowns.
- Labels (L) are a research artefact of the datasets; we use them as one signal and say so.

## 12. The LogLadder console

**One screen, three panels: Claude Code working on the left, colour-highlighted evidence top-right, and longer explanations bottom-right — with the right-hand panels driven by Claude itself through two MCP display tools.** The same layout serves all three roles; what fills the panels changes with the role.

&#91;embedded content: LogLadder console layout · header, agent panel, evidence panel, explainer panel\]

The layout follows the team's sketch: the agent's work is always visible, and the right side shows only what Claude chooses to demonstrate.

### 12.1 Panels

| Panel | Position | Driven by | Shows |
| --- | --- | --- | --- |
| Header | Top bar | User | Role switcher (Engineer · Team lead · Manager), dataset + time-window chips, receipt counter, claim-check status |
| Main: Claude Code execution | Left, \~55% width | The Claude Code CLI in a real PowerShell terminal | Claude Code's own output: each tool call and its result with the receipt ID, then the final answer in the five-part contract |
| Evidence | Top-right | `show_evidence` | Highlighted log lines, a ranked table, a trend chart or risk cards — whatever Claude wants to demonstrate |
| Explainer | Bottom-right | `show_explainer` + receipt clicks | Long-form reasoning: hypotheses with their numbers, unknowns, and the SQL/result of any clicked receipt |

### 12.2 What the evidence panel shows per role

`show_evidence` takes a `kind`, so one panel adapts to the role:

| Role | `kind` | Rendering |
| --- | --- | --- |
| Engineer | `lines` | Log lines coloured by severity, matched words highlighted (from SereneDB's `ts_offsets`), the anchor line outlined, "before" and "after" groups with collapsed repeats ("× 312"), Claude's annotations in the margin ("first FATAL", "possible precursor") |
| Team lead | `table` + `trend` | Recurring problems ranked by episodes with team badges, plus a weekly trend line per team |
| Manager | `risks` | 3–5 risk cards: score, the five inputs as small bars, rank stability, recommended action |

### 12.3 Colour language (consistent everywhere)

| Colour | Means |
| --- | --- |
| Red | FATAL / FAILURE lines, critical risks |
| Orange | ERROR / SEVERE |
| Amber | WARNING, and *unbacked claims* flagged by `check_answer` |
| Grey | INFO / context lines |
| Accent highlight | Words that matched the search |
| Green check | Claims backed by a receipt |

### 12.4 How it is wired

1. **Main window = the real Claude Code CLI.** PowerShell runs `claude` with the `loglad` MCP server configured. Judges see Claude Code's own output — every tool call, its inputs and its result with the receipt ID — and we write no agent code.
   - **Version 1 (first, fastest):** Windows Terminal with PowerShell snapped to the left half of the screen, a browser window with the two panels on the right. Visually the same as the sketch.
   - **Version 2 (the sketch as one window):** a web page with **xterm.js** on the left, connected over a WebSocket to a PowerShell process spawned by **node-pty** (ConPTY on Windows); the page launches `claude` in it on load.
2. **Console backend** — a small local server (Node, so node-pty and the panel WebSocket live in one process; FastAPI is fine for version 1). It holds the panel state and receives display-tool posts.
3. **Display tools** — `show_evidence` and `show_explainer` live in the same MCP server. They POST their payload to the console backend, which pushes it to the right-hand panels.
4. **Role switcher** — types the role prompt into the terminal for the user. In Claude Code, MCP prompts appear as slash commands (e.g. `/mcp__loglad__engineer`), so switching role is just a keystroke sequence.
5. **Graceful without the console** — if the console isn't running, the display tools return "console not connected; evidence summarised in text" and do nothing else. Plain Claude Code (and the judges' own Claude) still works fully.
6. **Frontend** — TypeScript; xterm.js plus the two panels, no other pages. Receipt IDs in the panels are clickable and open the SQL and result in the explainer.

This gives us both delivery paths the brief accepts — an MCP server Claude connects to, and a UI that shows the agent calling tools — from a single codebase.

## 13. Worked investigation and demo plan

**We pick one real issue from the data after loading — not before — and tell it three times: as the engineer, the team lead and the manager.** No finding is assumed in this document; everything below is the method and the script.

### 13.1 Choosing the issue (hours 2–6)

Run these on the loaded corpus and pick the issue that scores best on the criteria:

1. `recurring_problems` on BGL over the full span, by episodes — top 10 templates.
2. `count_by alert_category` on BGL — which labelled alert types dominate.
3. `trend` by week for the top candidates — look for a visible spike or growth.
4. `count_by http_status` and `trend metric=latency_p95` per service on OpenStack — where errors and slow requests concentrate; cross-check with labelled anomalous instances.

| Criterion | Why it matters for the demo |
| --- | --- |
| Has FATAL/FAILURE lines and a clear before/after story | Engineer timeline looks compelling |
| Recurs as many episodes, not one giant burst | Team lead answer shows the line-vs-incident distinction |
| Concentrated on some midplanes/services, owned by one team | Team-level recommendation is specific |
| Has a candidate precursor template with lift well above 1 | Hypothesis testing has something real to show |
| Ranks top 3 in `rank_risks` and is stable | Manager answer is confident and honest |

The main story may be BGL (richer text and span); OpenStack provides the whole-corpus aggregation and latency evidence. The brief explicitly allows this split.

### 13.2 Investigation write-up (README deliverable)

Generated from the receipt log, per role: question → tool calls → SQL → key results → answer in the five-part contract. Ends with a short "What the data does and does not establish" list.

### 13.3 Five-minute demo script

| Time | Beat | What's on screen |
| --- | --- | --- |
| 0:00–0:30 | The problem and our thesis: "smart tools, every number has a receipt" | Title slide → console |
| 0:30–1:45 | **Engineer** asks about the failure | Search → timeline in the evidence panel, highlighted lines, hypothesis with lift in the explainer |
| 1:45–2:45 | **Team lead** asks what recurs | Recurring-problems table by team + weekly trend; episodes vs lines called out |
| 2:45–3:40 | **Manager** asks what to fix first | Risk cards with inputs and stability; three actions, no invented impact |
| 3:40–4:25 | **Honesty moment**: we ask Claude a leading question ("how much downtime did this cause?") — `check_answer` flags it, Claude answers "the logs don't establish downtime" | Amber flag → corrected answer |
| 4:25–5:00 | Click a receipt → SQL → `verify_receipt` re-runs it; one architecture slide | Receipt drawer, diagram |

The honesty moment is the memorable beat: it shows the system refusing to invent, which is exactly what the brief's criteria reward. Record a backup video of the full run the evening before.

## 14. Validation: how we know it's right

**Hours 30–40 are for checking answers against query results; we make that systematic with four checks that run from one script and produce numbers for the README.**

| Check | What it tests | How | Pass bar |
| --- | --- | --- | --- |
| Load integrity | Nothing lost or mangled at ingest | Row counts vs the brief (4,747,963 BGL; 207,820 OpenStack), rejects count, null rates per field | Counts match; rejects explained |
| Episode quality | Our "incident" unit is sensible | Compare episodes against BGL alert labels and OpenStack labelled anomalous instances; report precision/recall-style overlap and the G sensitivity table | Numbers reported honestly, whatever they are |
| Answer grounding | No unbacked claims | Run 10–15 scripted questions (section 10.3) through Claude; count `check_answer` flags before and after revision | Zero unbacked claims in final answers |
| Receipt reproducibility | Evidence is re-runnable | `verify_receipt` on every receipt from the worked investigation | 100% digest match |
| Tool selection | Claude picks the right tool | For each scripted question, log which tools were called vs the expected path | Note mismatches; improve descriptions |

The tool-selection log doubles as Best MCP Server evidence: we can show the description changes that fixed wrong tool choices.

All results go in `docs/validation.md`, generated by `make validate`.

## 15. Optional extensions (only after the core works)

**Ranked by value per hour; each one reuses the receipts and tool envelope, so adding it doesn't touch the core.**

| Priority | Extension | What we'd build | What we'd show |
| --- | --- | --- | --- |
| 1 | Agent-managed workspace index | `create_workspace_index` / `drop_workspace_index` using a partial inverted index over one time range | Timing table: repeated queries with vs without the index, plus build time and the break-even number of queries |
| 2 | Row-level security per role | SereneDB roles/policies so e.g. the manager role sees aggregates only, the engineer sees lines | Same question, different visible rows per role |
| 3 | Huge datasets | A view over 1–N OpenTelemetry Parquet files on S3, an inverted index on `Body`, the same `search_logs`/`count_by` tools pointed at it | Rows queried, index build time, query times, disk used — as the brief asks |
| 4 | Similar-lines search | Vector or hybrid search on templates: "find problems like this one" | One engineer query that keyword search misses |
| 5 | Log–trace correlation | HDFS\_v3 TraceBench or Nezha | Only if everything else is done |

For the index trade-off (priority 1) the README states: build cost in seconds, per-query saving, and after how many repeated questions the index pays for itself — the exact comparison the brief requests.

## 16. Repo layout, README and reproducibility

**A judge with Docker, Python and Claude Code should go from `git clone` to asking Claude a question in four commands.**

```
loglad/
├── README.md                  # workflow, setup, tools, investigation, limitations
├── Makefile                   # make db | data | mcp | console | validate
├── docker-compose.yml         # SereneDB with ./data mounted at /data
├── scripts/fetch_data.sh      # Zenodo downloads (curl -L, ?download=1)
├── ingest/                    # parse_bgl.py, parse_openstack.py, templates.py
├── sql/                       # 01_schema … 05_checks, ownership.sql, episodes.sql
├── loglad_mcp/                # MCP server: tools/, receipts.py, limits.py, prompts/, resources/
├── console/                   # server/ (node-pty bridge + panel WebSocket), frontend/ (TypeScript)
├── docs/
│   ├── tools.md               # every tool: purpose, inputs, outputs, limits (generated from code)
│   ├── investigation.md       # worked investigation, generated from receipts
│   └── validation.md          # section 14 results
└── tests/                     # tool contract tests on the 2k Loghub samples
```

Quick start in the README:

```bash
make db        # docker compose up SereneDB on :7890
make data      # fetch, parse, load, enrich, index, verify (~minutes)
claude mcp add loglad -- python -m loglad_mcp   # connect Claude Code
make console   # optional: open the three-panel console
```

Reproducibility details:

- Pinned versions for SereneDB image, Python packages and Node.
- The 2,000-line Loghub samples are committed for tests, so CI and a quick smoke run work without downloading 770 MB.
- `docs/tools.md` is generated from the tool descriptions in code, so docs and behaviour never drift.
- A "Known limitations" section lists: template-mining approximations, the chosen episode gap G, fictional ownership, dataset periods differing, and what logs cannot establish (impact, root cause beyond the logs).

## 17. Build plan and workstreams

**Four workstreams in parallel, five phases with a gate each; nothing optional starts until gate 3 passes.** Times assume we start at Sat 13:00 and submit Sunday — confirm the exact submission time with the organisers.

### 17.1 Workstreams

| Stream | Owns | Depends on |
| --- | --- | --- |
| A — Data & SereneDB | Docker setup, parsers, schema, load, templates, episodes, indexes, ownership table, load checks | — |
| B — MCP tools & receipts | `loglad-mcp`, receipt envelope, limits, tools 1–8, tool descriptions, `docs/tools.md` | A's schema (can start on the 2k samples) |
| C — Reasoning & roles | `test_hypothesis`, `check_answer`, `verify_receipt`, answer contract, role prompts, scripted questions, validation | B's envelope |
| D — Console & demo | console backend, terminal embedding (xterm.js + node-pty), TypeScript panels, display tools, slides, demo script, backup video | B's display tools |

With fewer than four people, merge C into B and start D only after gate 2.

### 17.2 Phases and gates

1. **Sat 13:00–16:00 — Foundations.** SereneDB running, both datasets loaded, ownership table in, first FTS query and first aggregate working. *Gate 1: row counts match the brief.*
2. **Sat 16:00–22:00 — Ladder + core tools.** Templates, episodes, indexes; tools 1–6 with receipts; MCP server connected to Claude Code. *Gate 2: Claude Code answers one engineer question end to end with receipts.*
3. **Sat 22:00–Sun 10:00 (with sleep) — Analysis + reasoning.** `recurring_problems`, `rank_risks`, `test_hypothesis`, `check_answer`, role prompts. *Gate 3: one answer per role, all minimum requirements met.*
4. **Sun 10:00–14:00 — Investigation + console.** Pick the issue (section 13.1), generate the investigation from receipts, run validation; console wired to display tools. *Gate 4: the full demo runs once without help.*
5. **Sun 14:00–submission — Polish.** README, clean-checkout test on a teammate's machine, slides, two rehearsals, backup video; optional extensions only if time remains. *Gate 5: a fresh clone works by following the README alone.*

Cut order if we run late: console polish → optional extensions → `test_hypothesis` reverse-direction check → console itself (fall back to Claude Code + screen recording). Never cut: receipts, episodes, the three role answers, README.

## 18. Risks and mitigations

| Risk | Likelihood | Impact | Mitigation |
| --- | --- | --- | --- |
| Drain3 too slow on 4.7M lines | Medium | Delays the ladder | Measure in hour 1; fall back to deterministic masking (section 6.1) |
| SereneDB syntax differs from our assumptions | Medium | Tools break | Use the docs MCP and `sdb_docs.search`; test each tool on the 2k samples first |
| Episode gap G produces odd results | Medium | Weak team-lead story | Sensitivity table; pick G per dataset with evidence; state it in every answer |
| Window functions slow on full BGL | Low–medium | Slow load | Build episodes once at load time, never at query time |
| Console eats too much time | High | Core suffers | Console starts after gate 2; Claude Code alone is a valid submission |
| Claude picks the wrong tool | Medium | Weak answers, MCP award | "Do NOT use for…" lines; scripted tool-selection log (section 14) |
| No compelling issue in the data | Low | Flat demo | Selection criteria in 13.1; BGL labels guarantee real alerts exist |
| Demo fails live | Medium | Lost execution points | Backup video; pre-warmed queries; local only, no network dependency |
| Clean checkout fails for judges | Medium | Execution score | Gate 5: a teammate follows the README on a fresh machine |

## 19. Decisions, open questions, glossary

### 19.1 Decisions already made by the team

- Python for the MCP server and backend; TypeScript only for the UI.
- One MCP server, one agent, one corpus for all three roles; role is explicit.
- Claude Code as the primary agent; the console is the demo surface.
- Console layout: the real Claude Code CLI in PowerShell in the main window; tools drive highlighted evidence top-right and the explainer bottom-right.
- Targets: a project we're proud of → main prize → Best MCP Server.

### 19.2 Calls made in this design (challenge them)

- Working name "LogLadder".
- Episodes as the incident unit, with G = 10 min (BGL, per midplane) and 60 s (OpenStack, per service) as starting values.
- Five-input risk score with weights 0.30 / 0.25 / 0.20 / 0.15 / 0.10.
- Embedded terminal via xterm.js + node-pty for the one-window version; side-by-side windows as version 1.
- Fictional team names in the ownership table.
- No free-SQL tool.

### 19.3 Open questions

- [ ] How many people are on the team, and who takes which workstream?
- [ ] Exact submission time on Sunday?
- [ ] Which Claude Code account do we demo with, and does Claude Code run in PowerShell on every teammate's machine?
- [ ] Does Drain3 finish on BGL on our laptops in acceptable time?

### 19.4 Glossary

| Term | Meaning in this project |
| --- | --- |
| Line | One raw log entry |
| Template | The stable shape of a message with variables masked; many lines share one |
| Episode | A burst of one template in one scope with no gap longer than G — our incident unit |
| Risk | A recurring problem scored for prioritisation from measured inputs |
| Receipt | The stored record of one tool call: SQL, scope, counts, truncation, runtime, result digest |
| Lift | How much more often a cause appears before an effect than in any window of that length |
| Answer contract | Scope · Observed · Hypotheses · Unknowns · Next step |
| Ladder | Lines → templates → episodes → risks; roles work at different rungs |
