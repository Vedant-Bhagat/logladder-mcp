# 01 — Vedant: data layer, server wiring and integration

**You own the foundation (SereneDB, ingest, schema, the DB connection, the server entry point) and the finish (merges, smoke tests, investigation, README, demo).** Everyone else builds against `contracts/`; your job is to make the real system match those contracts early and keep `main` green.

## 1. What you own

`contracts/**` (frozen), `CLAUDE.md`, `README.md`, `tasks.py`, `pyproject.toml`, `.mcp.json`, `.env.example`, `.gitignore`, `.gitattributes`, `.github/**`, `infra/**`, `ingest/**`, `sql/**`, `data/samples/**`, `loglad_mcp/{__init__,__main__,server,config}.py`, `loglad_mcp/core/db.py`, `scripts/**`, `tests/contract/**`, `tests/ingest/**`, `tests/integration/**`, `docs/investigation.md`, `docs/validation.md`, `docs/handoff/vedant.md`.

## 2. V0 — bootstrap (Sat 14:00, unblocks everyone)

1. Create the **public** GitHub repo from this starter; push; invite Janhavi and Ayoub; replace the placeholders in `.github/CODEOWNERS`.
2. `infra/docker-compose.yml`: image `serenedb/serenedb`, port `7890:7890`, named volume `serenedb-data:/var/lib/serenedb`, bind mount `../data:/data` (read-only is fine).
3. Find the working connection string (`psql -h localhost -p 7890` → which user/database?) and put it in `.env.example` as `SERENEDB_DSN`.
4. Probe two things on a tiny table and write the answers in your handoff — Janhavi depends on them:
   - Does psycopg's server-side binding work inside `ts_phrase(%s)` / `@@ %s`? If not, `SereneDb` uses `psycopg.ClientCursor` (client-side binding) for everything.
   - Exact syntax that works for: text-search dictionary, `CREATE INDEX … USING inverted`, `VACUUM (REFRESH_TABLE)`, `ts_offsets`, `date_trunc`, a percentile function.
5. Write `loglad_mcp/config.py` (`Settings`, `load_settings()` reading env and an optional `.env`) and `loglad_mcp/core/db.py` (`SereneDb` implementing `Db` from `contracts/interfaces.py`): one connection with autocommit, `statement_timeout` from settings if supported (otherwise a client-side timeout), rows as dicts, `sql_rendered` via `ClientCursor.mogrify`, all driver errors mapped to `DbError('db_error'|'timeout', …)`, reconnect once on a dropped connection.
6. `loglad_mcp/server.py` + `__main__.py`: FastMCP app named **`loglad`**, logging to stderr, registries imported from Janhavi's modules. Until her J1 lands, register empty lists so Claude Code can already connect.
7. `.mcp.json` (project scope) so Claude Code started in the repo root finds the server. Decide how the venv's Python is found on Windows (`.venv\Scripts\python.exe`) vs elsewhere; the console's `LOGLAD_STARTUP_COMMAND` can activate the venv before `claude`. Document it in the README.
8. `pyproject.toml`: Python ≥ 3.11; deps `mcp`, `psycopg[binary]`, `pydantic`, `pyarrow`, `drain3`, `python-dotenv`; dev `pytest`, `jsonschema`, `ruff`. Pin after the first successful install.
9. `tasks.py` with at least `db`, `db-stop`, `fetch`, `data [--sample]`, `mcp`, `console`, `check`, `smoke`, `validate` (stubs are fine at V0).

## 3. V1 — sample pipeline end-to-end (Sat 15:30, unblocks Janhavi's SQL)

Commit `data/samples/BGL_2k.log` and `data/samples/OpenStack_2k.log` from the Loghub GitHub repo. `python tasks.py data --sample` must run parse → templates → load → episodes → ownership → indexes → checks on them in under a minute. The sample OpenStack file has no anomaly labels: `log_part = 'sample'`, `labelled_anomaly = false`.

## 4. Ingest details (V1 on samples, V2 on full data)

### 4.1 Fetch

`python tasks.py fetch` downloads `BGL.zip` and `OpenStack.tar.gz` from Zenodo (`?download=1`, follow redirects) into `data/raw/`, extracts, and prints sizes. Skip if already present.

### 4.2 Parse (`ingest/parse_bgl.py`, `ingest/parse_openstack.py`)

Stream line by line (`encoding="utf-8", errors="replace"`), write Parquet with an explicit pyarrow schema equal to `contracts/db_schema.sql`, ids sequential from 1. Malformed lines go to `data/parsed/rejects_<dataset>.txt` and are counted — reported, never silently dropped.

- **BGL**: `line.split(maxsplit=9)` → label, unix, date, node, timestamp (`%Y-%m-%d-%H.%M.%S.%f`), node, type, component, level, message (empty string if absent). `alert_category = None if label == '-'`. `rack`/`midplane` from `^(R\d\d)-(M\d)`.
- **OpenStack**: regex `^(?P<file>\S+) (?P<date>\S+) (?P<time>\S+) (?P<pid>\d+) (?P<level>[A-Z]+) (?P<logger>\S+) (?:\[(?P<ctx>[^\]]*)\] )?(?P<msg>.*)$`; context tokens → request, user, tenant; `[instance: <uuid>]` → `instance_id`; HTTP pattern `"<METHOD> <path> HTTP/x" status: N len: N time: F` → method, path, status, len, latency; `service` from the file token prefix (`nova-api`, `nova-compute`, `nova-scheduler`); `log_part` from which raw file; `labelled_anomaly` from the label file's instance ids. Verify the raw file names after extraction and note them in the README.

### 4.3 Templates (`ingest/templates.py`)

Drain3 with masking for numbers, hex, IPs, UUIDs, BGL node ids and paths. `template_id` offsets: BGL from 1, OpenStack from 100000. Measure runtime on full BGL in hour 1 of V2; if it's too slow, use the deterministic masking fallback (mask → hash → id). Sanity check: BGL should land in the hundreds of templates (the brief says 320 event templates). Write `template_id` into the Parquet before loading, and build `templates` rows (text with `<*>`, example, dominant component, counts, max level, first/last seen).

### 4.4 Load, episodes, ownership, indexes (`sql/`)

| File | Does |
| --- | --- |
| `01_schema.sql` | `contracts/db_schema.sql` tables, identical columns |
| `02_load.sql` | `INSERT INTO … SELECT … FROM read_parquet('/data/parsed/…')` with explicit column lists |
| `03_ownership.sql` | fictional mapping (below) |
| `04_episodes.sql` | gaps-and-islands: BGL per (template_id, coalesce(midplane, node)) gap 10 min; OpenStack per (template_id, service) gap 60 s; fill `episodes` and set `episode_id` on events |
| `05_indexes.sql` | dictionary, `bgl_idx`, `os_idx` with the frozen indexed columns; `VACUUM (REFRESH_TABLE)` |
| `06_checks.sql` | counts, spans, null rates, unmapped components, template/episode counts |

Episodes preferably in SereneDB SQL (shows off window functions). If setting `episode_id` on 4.7M rows via UPDATE is too slow, compute the assignment in Python before loading — the resulting tables are identical either way. Note which path you took in the handoff.

Ownership (fictional; confirm components with `SELECT DISTINCT component` after load, add any missing):

| dataset | component | team | team_lead |
| --- | --- | --- | --- |
| bgl | KERNEL | HPC Kernel & Runtime | Mira Hoffmann |
| bgl | APP | HPC Applications Support | Daniel Ortiz |
| bgl | MMCS, BGLMASTER, CMCS | HPC Control System | Lena Brandt |
| bgl | LINKCARD, HARDWARE, DISCOVERY, MONITOR | HPC Hardware & Interconnect | Sam Okafor |
| openstack | nova-api | Cloud API Platform | Priya Raman |
| openstack | nova-scheduler | Cloud Scheduling | Tom Becker |
| openstack | nova-compute | Cloud Compute & Hypervisors | Aisha Yilmaz |

Unmapped components → `team = 'Unowned'` in `episodes`.

### 4.5 Checks (also feed `docs/validation.md`)

Row counts (BGL 4,747,963; OpenStack 207,820 across its files), rejects, time spans, null rate per column, template counts, episode counts at G = 1, 10, 60 min (BGL) and 10, 60, 300 s (OpenStack), unmapped rows.

## 5. Integration (every merge window)

For each PR: read `docs/handoff/<name>.md` → check only owned files changed (`git diff --stat main...`) → `python tasks.py check` (contract tests, unit tests, ruff) → merge → `python tasks.py smoke` on `main`.

`tests/integration/test_smoke.py` (yours): with SereneDB and sample data loaded, call every registered tool through the registry with sensible params, validate each envelope with `scripts/validate_contracts.py`, and replay one `show_evidence` to a running console if `LOGLAD_CONSOLE_URL` responds. This is the one test that proves the three branches fit.

After W2: Claude Code session with the console, ask one question per role, fix wiring issues, and file contract questions immediately.

## 6. The finish (W3–freeze)

- Pick the worked investigation with the criteria in design doc §13.1; run it with `/mcp__loglad__investigate`.
- `python tasks.py export-investigation` → `docs/investigation.md` from the receipts table (questions, tool calls, SQL, results, answers per role).
- `docs/validation.md`: load checks, episode sensitivity, label overlap, receipt reproducibility (`verify_receipt` on every investigation receipt), Janhavi's tool-selection results.
- README: workflow, quick start (`tasks.py db → fetch → data → claude`), tools table (link `docs/tools.md`), ownership table, investigation link, known limitations.
- Clean-checkout test on Janhavi's or Ayoub's laptop following only the README.
- Rehearse the 5-minute demo twice; record a backup video.

## 7. Milestones

| Milestone | Due | Done when |
| --- | --- | --- |
| **V0** | Sat 14:00 | repo public + invites; SereneDB in Docker; DSN; Db + config + empty server; Claude Code connects to `loglad` |
| **V1** | Sat 15:30 | `tasks.py data --sample` loads all contract tables from the 2k samples |
| **V2** | Sat 20:00 | full BGL + OpenStack loaded, templates, episodes, indexes, checks pass |
| **V3** | W3 Sun 09:30 | smoke test green on `main`; one answer per role in the console |
| **V4** | freeze | investigation, validation, README, clean-checkout test, rehearsal |
