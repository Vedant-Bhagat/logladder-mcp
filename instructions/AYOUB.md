# Instructions for Ayoub's coding agent

> **Ayoub — how to use this file.** Open a terminal in the repo root on your branch (`git checkout -b ayoub/<milestone>` from latest `main`), start `claude`, and send:
> `Read instructions/AYOUB.md and follow it. Current milestone: A1.` (change to A2/A3/A4 later).
> Review the agent's plan before it codes, look at the UI yourself, and read `docs/handoff/ayoub.md` before you open a PR.

---

You are working for **Ayoub**. He owns the LogLadder console: a Node + TypeScript app on `127.0.0.1:7777` whose main window is a real PowerShell terminal running `claude`, with an evidence panel and an explainer panel that the MCP server fills by POSTing panel events. Vedant integrates and runs the demo on his **Windows** laptop.

## Step 1 — load context (do not skip)

Read in this order, fully:

1. `CLAUDE.md`
2. `docs/specs/00-team-contract.md`
3. `docs/specs/03-ayoub-console.md` — **your spec; it is the source of truth for behaviour and the server API**
4. `contracts/panel_event.schema.json` and every file in `contracts/fixtures/panel_events/`
5. `scripts/replay_panel_events.py`
6. `docs/handoff/ayoub.md` if it exists (where the last session stopped)

Then tell Ayoub, in five lines or fewer: the milestone, the files you'll create, the libraries you plan to use (from the suggested stack), and anything unclear. Wait for his OK.

## Step 2 — your boundaries

You may create/edit only `console/**`, `docs/slides/**`, `docs/handoff/ayoub.md` and `docs/handoff/img/**`. Do not touch Python code, `contracts/`, `scripts/`, the root `package.json`/`pyproject.toml`, or other people's handoffs. The console **never** connects to SereneDB or imports Python code; everything it shows comes from panel events.

## Step 3 — build rules

- Implement the server API in spec §3.1 exactly (paths, status codes, message shapes). Janhavi's display tools and Vedant's smoke test depend on it.
- Validate incoming events with the schema file read from `contracts/` at startup (resolve the path from the repo root; don't copy the schema).
- Bind to `127.0.0.1` only. Port from env `LOGLAD_CONSOLE_PORT`, default 7777.
- `node-pty` is loaded optionally (dynamic import in try/catch). With it missing or `LOGLAD_TERMINAL=off`, everything except the terminal must still work.
- Escape all text before inserting highlight `<mark>`s; highlights are **character** offsets. Sanitise explainer markdown with DOMPurify.
- Role pills type `/mcp__loglad__<role>` into the terminal without pressing Enter.
- Paths with `path.join`, no shell-specific npm scripts (use `node`/`tsx`/`vite` commands that work on Windows; no `rm -rf`, `&&` chains that break in PowerShell — use `rimraf`/`npm-run-all` style or plain Node scripts if needed).
- Commit `console/package-lock.json`. Keep the dependency list short.

## Step 4 — prove it

Run and paste real output into the handoff:

```bash
cd console && npm ci && npm test && npm run build
npm start                                        # then, from repo root in another terminal:
python scripts/replay_panel_events.py            # every line must say [202]
LOGLAD_TERMINAL=off npm start                    # fallback mode still serves the panels
```

Take screenshots of each panel kind (lines, table, trend, risks, explainer, status) at 1366×768 and 1920×1080 into `docs/handoff/img/`. If you're on macOS/Linux, say so in the handoff and list what still needs testing on Vedant's Windows laptop.

## Step 5 — hand off

Update `docs/handoff/ayoub.md` from `docs/handoff/TEMPLATE.md` (replace the previous milestone's content, keep a one-line history at the bottom). Include: what works, commands + output, screenshots, deviations from the spec and why, Windows status of node-pty, open questions. Commit with the `console:` prefix, rebase on `main`, and tell Ayoub it's ready for his review. Do not open or merge the PR yourself unless he asks.
