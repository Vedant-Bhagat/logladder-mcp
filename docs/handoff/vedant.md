# Handoff — Vedant — V0–V4 done (rehearsal + backup video left) — Sun

Branch: `main` · Contract version: `1`

## 1. Done

| Item from my spec | Status | Notes |
| --- | --- | --- |
| `infra/docker-compose.yml` | done | SereneDB 7890, password `loglad` (see §5) |
| DSN in `.env.example` | done | `postgresql://postgres:loglad@127.0.0.1:7890/` |
| `config.py` (`Settings`, `load_settings`) | done | reads env + optional `.env` |
| `core/db.py` (`SereneDb`, `QueryResult`, `DbError`) | done, verified | binding, timeout, reconnect tested live |
| `server.py`, `__main__.py` | done | FastMCP `loglad`; empty registries until J1; verified over stdio |
| `.mcp.json` | done | runs `python tasks.py mcp`, which picks `.venv`'s Python itself |
| `pyproject.toml` | pinned | **`mcp==1.30.0`** (see §4) |
| `tasks.py` | done | `setup db db-stop fetch data [--sample] mcp console check smoke validate` |
| `data/samples/*_2k.log` | done | from Loghub GitHub |
| `ingest/` parse, templates (Drain3), fetch, load | done | full: BGL 4,747,963 rows / 392 templates, OpenStack 207,820 / 56, 0 rejects |
| `sql/01–06` | done, verified on full data | BGL 183,090 episodes, OpenStack 7,568 |
| `tests/ingest`, `tests/integration` | done | smoke test skips cleanly without DB/console |
| Probe of `ts_*` param binding | done | all work with `%s` — see §5 |

## 2. How to run it

```
python tasks.py setup            # .venv + deps
python tasks.py db               # SereneDB in Docker, waits until it answers
python tasks.py data --sample    # parse samples -> data/parsed/*.parquet -> load SereneDB
python tasks.py check            # contract + unit tests + ruff (no DB)
python tasks.py smoke            # every registered tool against the DB
claude                           # in the repo root; /mcp shows `loglad`
```

## 3. Proof

```
python tasks.py check  ->  25 passed, 2 deselected · ruff: All checks passed!
MCP stdio probe        ->  server: loglad | tools: 0
tasks.py data (full)   ->  bgl: 4,747,963 rows, 392 templates, 0 rejects (parse 235 s)
                          openstack: 207,820 rows, 56 templates, 0 rejects (parse 15 s)
                          SQL: load 13 s, episodes 0.5 s, indexes 2 s; unenriched rows 0
                          episodes: bgl 183,090 · openstack 7,568 · unowned BGL lines 319 · labelled OpenStack lines 100
search on full BGL     ->  ts_phrase / plainto_tsquery + BM25: 6–11 ms
data --sample (parse)  ->  bgl: 2,000 rows, 106 templates, 0 rejects · openstack: 2,000 rows, 35 templates, 0 rejects
```

## 4. Deviations from the spec

- **`mcp` pinned below 2.** mcp 2.x renamed `FastMCP` to `MCPServer`; contracts and specs assume FastMCP. Janhavi: use `mcp.server.fastmcp` / pydantic `Field` as written.
- **Episode ids are assigned during the load** (`sql/02_load.sql`, `INSERT … SELECT` with `lag` / running `sum` / `dense_rank` over `read_parquet`), not via a later UPDATE. `04_episodes.sql` only aggregates. The tables are identical to the spec.
- Templates table stats are computed in Python during parsing; template text comes from Drain3 after all lines are seen.
- `DbError` and `QueryResult` live in `loglad_mcp.core.db` — import them from there.
- `.mcp.json` uses `python tasks.py mcp` so it works on Windows and macOS/Linux without activating the venv.

## 5. SereneDB notes (backend only)

**Verified live on the sample DB:**
- `SereneDb` uses **client-side binding** (`psycopg.ClientCursor`) for everything, so `%s` inside `ts_phrase(%s)` / `@@ %s` works no matter what the server supports. `sql_rendered` = `cursor.mogrify`.
- Timeout: client-side, cancels the statement after `LOGLAD_QUERY_TIMEOUT_S` → `DbError('timeout')`. A dropped connection is retried once.
- Dictionary: `CREATE TEXT SEARCH DICTIONARY log_dict AS split_text(case := 'lower') WITH (frequency, position, offset)`.
- Index: `CREATE INDEX bgl_idx ON bgl_events USING inverted (id, message log_dict, component, …)` then `VACUUM (REFRESH_TABLE) bgl_events`. Columns without a dictionary are matched verbatim.
- Functions that exist (DuckDB-style): `date_trunc`, `quantile_cont(x, 0.95)`, `approx_quantile`, `arg_max`, `mode`, window functions, `read_parquet([...])`.
- `ts_offsets(bgl_idx.message)` returns **byte** offsets as interleaved start, end pairs (a list, e.g. `[18, 30]`).
- All of these work with `%s` parameters: `message @@ ts_phrase(%s)`, `@@ plainto_tsquery(%s)`, bare `message @@ %s`,
  `(ts_levenshtein(%s, 1) && ts_levenshtein(%s, 1))`, verbatim `level @@ %s` / `component @@ %s` / `request_id @@ %s`.
- `ORDER BY BM25(bgl_idx.tableoid) DESC` works. `EXPLAIN` on an `@@` query over `bgl_idx` shows `IRESEARCH_SCAN`.
- **BM25 must be the only sort key.** `ORDER BY BM25(idx.tableoid) DESC, ts` (or `, id`, or a BM25 alias plus a second key)
  segfaults SereneDB on the full data, or returns garbled bytes; the container restarts. BM25 alone passed 90+ runs.
  Equal scores come back in varying order. Sorting by a second key outside a BM25-only subquery is also safe.
- `date_trunc('week', ts)` starts weeks on Monday. `quantile_cont(latency_s, 0.95)` works.
- `count(*)` / `sum(...)` come back as `Decimal` from psycopg for some aggregates; cast to int/float before putting them in envelopes.
- Auth: `postgres` is only trusted on real loopback; Docker port-forwarding isn't, so compose sets `POSTGRES_PASSWORD=loglad`.
  The password is only seeded on first start: after changing it, `docker compose -f infra/docker-compose.yml down -v`.
- Sample load timings: whole SQL pipeline < 1 s.

## 6. Known issues

- Drain3 never matches an all-wildcard template (`<*>`), so it opens one cluster per such line (3,611 raw BGL clusters).
  `ingest/load.py` merges clusters with identical text into the lowest id: 392 BGL templates.
- 319 BGL lines have a malformed component field (`FATAL`, `a`, `0`, `iar`, `SERV_NET`) because of shifted fields in the raw log.
  They're kept and land in team `Unowned`.
- The OpenStack label file lists 4 instance ids → 100 labelled lines, all in `openstack_abnormal.log`.

- Connecting to a down DB takes about 10 s before `DbError`; the server doesn't ping at startup, so Claude Code still connects instantly.

## 7. Open questions for Vedant

1. Real GitHub usernames for `.github/CODEOWNERS`.
2. Repo public yet? Teammates invited?

## 8. V3 / V4 (Sun)

- Merged: Ayoub A1, A2 (FastAPI console), README; Janhavi J1–J3. Smoke + `pytest -m db` green on the full data.
- Fixed: `search_logs` crashed SereneDB (BM25 + second sort key, see §5); `describe_corpus` tie order broke `verify_receipt`.
- Console deps (`fastapi`, `websockets`, `pywinpty`) moved to `pyproject.toml`; `console/tests` in `testpaths`.
- `scripts/claude_runs.py` drives real Claude Code (`claude -p`) and records tool calls; `scripts/reports.py` writes
  `docs/investigation.md` and `docs/validation.md`. Commands: `tasks.py investigate | tool-selection | export-investigation | validation`.
- Results: 15/15 tool-selection questions on the expected path; 16/16 investigation receipts reproduce; honesty question
  answered "the logs don't record downtime".
- Clean checkout (fresh clone + fresh `.venv`): `setup` 2 m 19 s, `check` 117 passed, console builds and serves, MCP lists 14/4/4.
- Slides: real-data console screenshot and Results card. `docs/demo.md`: 5-minute cue card.

## 9. Still open

- Rehearse the demo twice; record the backup video (people, not code). Run `/login` in Claude Code first: it said the login expires in 3 days.
- Receipt ids clash when two Claude sessions run at once (`ReceiptStore` reads max id once); README says one session at a time.
- `rank_risks` with `dataset=both` and no dates does not record its window, so "30 days" can't be backed (Janhavi).

---
History: `V0/V1 code – Sat – server, db, ingest, sql written` · `V2 – Sat – full data loaded and verified`
