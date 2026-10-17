# Instructions for Janhavi's coding agent

> **Janhavi — how to use this file.** Open a terminal in the repo root on your branch (`git checkout -b janhavi/<milestone>` from latest `main`), start `claude`, and send:
> `Read instructions/JANHAVI.md and follow it. Current milestone: J1.` (change J1 to J2/J3/J4 later).
> Review the agent's plan before it codes, and read `docs/handoff/janhavi.md` before you open a PR.

---

You are working for **Janhavi**. She owns the MCP tool layer of LogLadder: envelope, receipts, the 14 tools, reasoning helpers, prompts and resources. Vedant integrates and runs everything on Windows; Ayoub's console renders what the display tools send.

## Step 1 — load context (do not skip)

Read in this order, fully:

1. `CLAUDE.md`
2. `docs/specs/00-team-contract.md`
3. `docs/specs/02-janhavi-mcp-tools.md` — **your spec; it is the source of truth for behaviour**
4. `contracts/interfaces.py`, `contracts/db_schema.sql`, `contracts/envelope.schema.json`, `contracts/panel_event.schema.json`
5. The fixtures in `contracts/fixtures/envelopes/` and `contracts/fixtures/panel_events/`
6. `docs/handoff/janhavi.md` if it exists (where the last session stopped)

Then tell Janhavi, in five lines or fewer: the milestone you're doing, the files you'll create or change, and anything in the spec that's unclear. Wait for her OK.

## Step 2 — your boundaries

You may create/edit only:
`loglad_mcp/core/{context,envelope,receipts,limits,console,timeparse}.py`, `loglad_mcp/tools/**`, `loglad_mcp/reasoning/**`, `loglad_mcp/prompts/**`, `loglad_mcp/resources/**`, `tests/tools/**`, `tests/reasoning/**`, `docs/tools.md`, `docs/tool_selection.md`, `docs/handoff/janhavi.md`.

You must not edit `server.py`, `config.py`, `core/db.py`, `contracts/`, `sql/`, `ingest/`, `console/`, `pyproject.toml`, or other people's handoffs. If `SereneDb`/`load_settings` don't exist yet, code against the Protocols in `contracts/interfaces.py` and use a `FakeDb` in `tests/tools/fakes.py`.

## Step 3 — build rules

- Implement exactly the names, parameters, defaults and limits in the spec. Parameter names are `start`/`end`; every tool ends with `role: Literal["engineer","team_lead","manager","unknown"] = "unknown"`.
- All tools go through the `@tool_call` wrapper (spec §3.7). No tool raises; errors become `envelope.error`.
- Every SQL statement is parameterised; user text never goes into SQL by string formatting.
- Full-text `@@` queries select `FROM bgl_idx` / `FROM os_idx`; aggregates use base tables.
- Summaries and caveats are generated from real values in `data`. Never hard-code numbers from fixtures.
- Display tools build panel events **only from stored receipt data**, never from text Claude passes in (except `title`, `annotations` labels, `actions`, explainer `markdown`).
- Log to stderr only. Keep functions small; put pure maths in `reasoning/` with unit tests.
- Unsure about SereneDB syntax → ask the `serenedb-docs` MCP or run `SELECT * FROM sdb_docs.search('…')`; record findings in the handoff.

## Step 4 — prove it

Run and paste the real output into the handoff:

```bash
LOGLAD_VALIDATE=1 pytest tests/tools tests/reasoning tests/contract -q
pytest -m db -q            # only if SereneDB with sample data is running
python -m loglad_mcp.tools.registry --markdown > docs/tools.md   # from J2 on
```

For each tool you finished, save one real output to `/tmp` (not the repo) and run `python scripts/validate_contracts.py envelope <file>`; for display tools validate the posted event with `… panel <file>`.

## Step 5 — hand off

Update `docs/handoff/janhavi.md` from `docs/handoff/TEMPLATE.md` (replace the previous milestone's content, keep a one-line history at the bottom). Include: done / not done per tool, exact commands + output, every deviation from the spec and why, SereneDB notes (syntax that worked, EXPLAIN showing `IRESEARCH_SCAN`), open questions for Vedant. Commit with `tools:` / `reasoning:` / `test:` / `docs:` prefixes, rebase on `main`, and tell Janhavi it's ready for her review. Do not open or merge the PR yourself unless she asks.
