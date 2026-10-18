# Handoff — Janhavi — J1–J3 done, J4 partly (tool-selection runs pending) — Sun

Branch: `janhavi/tools` (to be created — this work was done on an unpacked copy of `main`, not a git checkout) · Rebased on `main` at: `69c7df4` (zip of main) · Contract version: `1`

## 1. Done

| Item from my spec | Status | Notes |
| --- | --- | --- |
| `core/limits.py`, `timeparse.py`, `envelope.py` | done | date-only `end` covers the whole day; missing bounds → cached dataset span |
| `core/receipts.py` (`ReceiptStore`) | done | lazy id read (no DB at start-up); memory + `receipts` table; 30 s backoff after a DB failure (see §4) |
| `core/console.py`, `core/context.py` | done | `HttpConsoleClient` 1.5 s, never raises; `ctx()` before init → `RuntimeError` |
| `@tool_call` (`tools/_base.py`) | done | exception → error code mapping, receipt, `LOGLAD_VALIDATE=1` self-validation, signature kept for FastMCP |
| `describe_corpus` | done | cached per `dataset`; still one receipt per call |
| `search_logs` | done | terms / phrase / fuzzy, BM25 + ts, count query, byte→char highlights |
| `get_timeline` | done | anchor or `at`+`scope_value`; collapsed by template, ≤ 40 groups per side |
| `trace_request` | done | request → its instances; hops, outcome (never invented), ≤ 50 lines |
| `count_by` | done | full valid-combination matrix; rows + other = total; `both` label prefix |
| `trend` | done | Monday weeks, filled buckets, top series, change per series |
| `recurring_problems` | done | default last 30 days of each dataset's own span; previous period |
| `rank_risks` + `reasoning/risk.py` | done | F/S/T/V/L, renormalised weights, 10-variant stability, per-dataset percentiles |
| `test_hypothesis` + `reasoning/hypothesis.py` | done | episode intervals, support / baseline / lift / reverse, verdict |
| `check_answer` + `reasoning/claims.py` | done | numbers / % / dates / times vs cited receipts; causal + impact words by section; status event |
| `verify_receipt`, `get_receipt` | done | re-run in verify mode (no receipt, no console post), digest compare |
| `show_evidence`, `show_explainer` | done | events built from stored receipt data only; console down → `delivered: false` + caveat |
| 4 prompts (`prompts/*.md`, `PROMPTS`) | done | engineer, team_lead, manager, investigate(`question`) |
| 4 resources (`RESOURCES`) | done | schema, ownership (live), answer-contract, glossary |
| `docs/tools.md` | done | generated |
| `docs/tool_selection.md` (J4) | **partial** | 15 questions + expected paths written; **the Claude Code runs are not done** (no SereneDB on this machine) |

## 2. How to run it

Windows 11, PowerShell / Git Bash, Python 3.12, from the repo root:

```
python tasks.py setup                                    # .venv + deps (unchanged)
python tasks.py check                                    # contract + unit + tool tests, ruff
$env:LOGLAD_VALIDATE=1; pytest tests/tools tests/reasoning tests/contract -q
python tasks.py db; python tasks.py data --sample        # then:
pytest -m db -q                                          # my DB tests + Vedant's smoke test
python -m loglad_mcp.tools.registry --markdown > docs/tools.md
```

## 3. Proof

```
LOGLAD_VALIDATE=1 pytest tests/tools tests/reasoning tests/contract -q   ->  88 passed, 4 skipped (db) in 12.95s
python tasks.py check                                                    ->  98 passed, 6 deselected · ruff: All checks passed!
pytest -m db -q   (SereneDB not running here)                            ->  6 skipped, 98 deselected
```

MCP server over stdio (`python -m loglad_mcp`, launched by an MCP client exactly as Claude Code does, DB and console down):

```
server: loglad init 1.85s
tools: 14 prompts: 4 resources: 4
bad input -> invalid_input "'end' (2005-06-01) is not after 'start' (2005-07-01)."  R-0001  caveat: receipt not persisted to database
db down   -> db_error "SereneDB unreachable: connection timeout expired"   (10.0 s = one connect timeout in core/db.py)
check_answer -> "1 claims checked: … 1 mismatched" + caveat "Console not reachable; status not shown."
```

**Real SQL on the real sample data (DuckDB stand-in).** SereneDB/Docker wasn't available on this machine, so I loaded
`data/samples/*_2k.log` through Vedant's own `ingest.load.parse_dataset` + `sql/01–04` into DuckDB (the functions
Vedant lists — `date_trunc`, `quantile_cont`, `arg_max`, `mode`, window functions — are DuckDB's) and ran 56 tool calls
covering every tool, every error path and all 4 evidence kinds. The FTS parts (`@@`, `BM25`, `ts_offsets`,
`ts_between`) were translated to plain SQL in that harness, so **this does not prove the SereneDB full-text syntax** —
`pytest -m db` does. Result: `56 calls, 10 panel events; invalid outputs: 0`; saved outputs re-checked with
`python scripts/validate_contracts.py envelope|panel <file>` → `valid`. Sample summaries (real values):

```
describe_corpus   BGL: 2,000 lines from 2005-06-03 to 2006-01-03, 106 templates, 1,595 episodes; OpenStack: 2,000 lines … 35 templates, 82 episodes.
count_by          BGL episodes … grouped by component: 5 groups, 1,595 episodes in total; top: KERNEL 1,448 (90.8%).
verify_receipt    Re-ran R-0025 (recurring_problems) with its stored parameters: result identical …   (all 9 re-runs identical)
check_answer      8 claims checked: 3 backed, 1 unbacked, 1 mismatched, 3 flagged   ("90.8%" backed, "rounded from 90.78")
```

## 4. Deviations from the spec

- **Receipt store backoff (30 s)** after any DB failure: skips the INSERT / id read / DB lookup and adds the caveat. Why: without it a down SereneDB cost every call 20–30 s (tool query + id read + insert, each ~10 s). Now one timeout per call. Ids continue from `max(db, memory) + 1` when the DB is back.
- **OpenStack `distinct_scopes` (recurring_problems) and S (rank_risks) = distinct `instance_id`s** from `os_events`, not distinct `episodes.scope_key`. The contract says "distinct midplanes (BGL) or instances (OpenStack)"; OpenStack `scope_key` is the service, so counting it would always give 1–3. Contract wins over spec. BGL uses `scope_key` as specified.
- **`test_hypothesis` with `scope=node|instance`**: `episodes` has no node/instance column, so intervals are built from event lines grouped by `(episode_id, node|instance_id)`. midplane/service use `episodes` rows as specified. Reverse direction uses effect episodes padded by W before the window.
- **`trend`**: for `error_rate` / `latency_p95`, `first_half`/`second_half` are **means** of the buckets (sums of rates are meaningless); caveat says so. Halves are the first ⌊n/2⌋ and last ⌊n/2⌋ buckets (middle bucket of an odd count ignored). `group_by=component` on OpenStack is treated as `service`.
- **`get_timeline`**: group `sample` = line with the smallest id in the group (ids are file order). When more than 40 groups on a side, the 40 **nearest the anchor** are kept (then ordered by `first_ts`).
- **`verify_receipt`** also refuses `verify_receipt` receipts (their runtime is in the data, so they can never match). `describe_corpus` bypasses its cache in verify mode.
- **`check_answer`**: a bullet is one unit (not split into sentences) so "… two sentences. [R-0001]" bullets work; durations like "10 minutes" also match `600` (seconds); years written alone match dates in receipts. Status event posted unless in verify mode.
- **`show_explainer`** also collects `[R-…]` written in the markdown, not just `receipt_ids`; unknown ones → `invalid_input`. Markdown over 8 000 chars → `invalid_input` (not silently cut).
- `ToolSpec` / `PromptSpec` / `ResourceSpec` dataclasses are defined in each registry module (same fields as `contracts/interfaces.py`, which is reference-only).

## 5. SereneDB notes (backend only)

Written from Vedant's V2 notes; **not yet verified by me against SereneDB**:

- Search SQL: `SELECT …, ts_offsets(bgl_idx.message) AS offsets FROM bgl_idx WHERE message @@ plainto_tsquery(%s) | ts_phrase(%s) | (ts_levenshtein(%s, 1) && …) AND level @@ %s AND component @@ %s AND node @@ %s ORDER BY BM25(bgl_idx.tableoid) DESC, ts LIMIT %s` — all forms Vedant verified.
- **Unverified: the time range inside an index query** — `ts @@ ts_between(%s, %s, true, false)` (taken from the contract fixture, `[start, end)`). It lives in one function, `retrieve.idx_time_sql()`. If SereneDB rejects it, change that one line (e.g. to `ts >= %s AND ts < %s`). `tests/tools/test_db.py::test_every_match_mode_and_time_filter` exercises it.
- Fuzzy words are lower-cased before `ts_levenshtein` (the dictionary is `split_text(case := 'lower')`).
- `EXPLAIN … IRESEARCH_SCAN` check: `tests/tools/test_db.py::test_search_uses_inverted_index` (both indexes) — run `pytest -m db`.
- Aggregates use base tables only; `Decimal` results are converted with `to_int` / `num`.

## 6. Known issues

- `pytest -m db` not run (no Docker on this machine). First thing to do on Vedant's laptop.
- `docs/tool_selection.md` runs not done → J4 description tuning not done.
- With SereneDB down, each tool call still waits ~10 s (`core/db.py`: `connect_timeout=5` × 2 attempts). Not mine to change; see Q1.
- Prompts/resources `.md` files are read from the package folder; fine with `pip install -e` (what `tasks.py setup` does). A non-editable install would need package-data in `pyproject.toml` (Vedant's).
- `trend` with one bucket: change figures are 0 / null and a caveat says they are not meaningful.

## 7. Open questions for Vedant

1. Can `SereneDb` fail fast for ~30 s after a connection error (like my receipt backoff), so a down DB doesn't cost 10 s per tool call?
2. Does `ts @@ ts_between(%s, %s, true, false)` work on `bgl_idx` / `os_idx`? If not, which range syntax should `idx_time_sql()` use?
3. OK with OpenStack spread = distinct instances (contract wording) rather than distinct `scope_key` (spec wording)?

## 8. Next

1. On Vedant's laptop: `python tasks.py db; python tasks.py data --sample; pytest -m db -q; python tasks.py smoke`.
2. Run the 15 questions in `docs/tool_selection.md` in Claude Code, fill the table, tune descriptions, regenerate `docs/tools.md`.

---
History: `J1–J3 + J4 docs – Sun – core, 14 tools, reasoning, 4 prompts, 4 resources; tasks.py check 98 passed; DB + tool-selection runs pending`
