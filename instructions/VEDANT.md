# Instructions for Vedant's coding agent

> **Vedant — how to use this file.** In the repo root, start `claude` and send:
> `Read instructions/VEDANT.md and follow it. Current milestone: V0.` (or V1–V4, or `Merge window W2`).

---

You are working for **Vedant**, the integrator. He owns SereneDB setup, ingest, the schema, the DB connection, the server entry point, the contracts, and every merge. His laptop (Windows, PowerShell, Docker Desktop) runs the final demo.

## Step 1 — load context

Read fully: `CLAUDE.md`, `docs/specs/00-team-contract.md`, `docs/specs/01-vedant-data-and-integration.md`, all of `contracts/`. Skim `02-janhavi-mcp-tools.md` and `03-ayoub-console.md` so you know what they expect from you. Read `docs/handoff/vedant.md` if it exists.

## Step 2 — boundaries

Edit only Vedant's paths (team contract §2). **Contracts:** edit only when Vedant explicitly asks for a contract change; then update fixtures, run `python scripts/validate_contracts.py`, bump `contracts/VERSION` only for breaking changes, and draft the "contract updated" message for the team chat. Never edit `loglad_mcp/tools|reasoning|prompts|resources`, the Janhavi-owned `core/` files, or `console/`, even to fix a bug during a merge — instead write the fix request for the owner (file, line, failing test output).

## Step 3 — milestones

Follow spec §2–§7. At V0 and V1, write down in `docs/handoff/vedant.md` exactly what you learned about SereneDB (DSN, parameter binding, working index/dictionary syntax, function names) — Janhavi's agent reads it.

## Step 4 — merge windows (`Merge window Wn`)

For each open PR, in order Janhavi → Ayoub:

1. Read the author's `docs/handoff/<name>.md`; list deviations and open questions for Vedant.
2. `git diff --stat main...<branch>` — flag any file outside the author's ownership.
3. `python tasks.py check` on the branch; report failures verbatim.
4. Tell Vedant: merge / merge with notes / send back (with the exact reason). Merge only after he says so.
5. After merging all PRs: `python tasks.py smoke` on `main` (SereneDB + console running), then a short status note for the team chat: what's merged, what's broken and whose it is, next window's focus.

## Step 5 — your own handoff

Keep `docs/handoff/vedant.md` current (same template) so a teammate could take over the integration if needed.
