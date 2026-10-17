# 03 — Ayoub: the LogLadder console

**You build the screen the judges watch: the real `claude` CLI running in PowerShell on the left, and two panels on the right that Claude fills through MCP display tools.** You need no database and no Python knowledge: everything you render arrives as JSON events defined in `contracts/panel_event.schema.json`, and you can generate those events yourself with `scripts/replay_panel_events.py`. Read `00-team-contract.md` first.

## 1. What you own

`console/**` (including its own `package.json`, `tsconfig.json`, `vite.config.ts`), `docs/slides/**`, `docs/handoff/ayoub.md`. You don't edit anything else; if you need something from the MCP side, ask Janhavi; for repo-level config, ask Vedant.

## 2. The layout (from the team sketch)

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ LogLadder   [Engineer] [Team lead] [Manager]    scope chip · R-count · claims │  header 48 px
├───────────────────────────────────────────┬──────────────────────────────────┤
│                                           │ EVIDENCE  title        [R-0002]  │
│                                           │ colour-highlighted lines /       │
│   Claude Code CLI                         │ table / trend chart / risk cards │  ~60 %
│   (real PowerShell terminal, xterm.js)    │ ◄ ► history · showing 2 of 1,284 │
│                                           ├──────────────────────────────────┤
│                                           │ EXPLAINER  title                 │
│                                           │ markdown with [R-0007] chips;    │  ~40 %
│                                           │ receipt drawer: SQL, scope, counts│
└───────────────────────────────────────────┴──────────────────────────────────┘
              ~58 % width                                ~42 % width
```

- Must look right at **1366×768** and **1920×1080** (laptop and projector). Dark theme by default (the terminal is dark); light theme optional.
- The panel split can be draggable; not required.

## 3. Architecture

One Node process (TypeScript) on **`127.0.0.1:7777`** serves the page, the panel API and the terminal. Bind to 127.0.0.1 only.

```
display tools (Python) ──POST /api/panel──► console server ──WS /ws/panels──► browser panels
browser terminal (xterm.js) ◄──WS /ws/terminal──► console server ◄──node-pty──► PowerShell ► claude
```

Suggested stack (you may choose differently if you keep the API below and the bundle light): Node 20, `ws`, `node-pty`, `ajv` (2020-12 draft support via `ajv/dist/2020`), Vite + vanilla TypeScript or Preact, `@xterm/xterm` + `@xterm/addon-fit`, `marked` + `dompurify`, hand-written SVG for the trend chart, `vitest` for tests.

### 3.1 Server API (freeze this — Janhavi and Vedant rely on it)

| Method + path | Request | Response |
| --- | --- | --- |
| `POST /api/panel` | a panel event (schema) | `202 {"ok":true}`; `400 {"ok":false,"errors":[…]}` if it fails schema validation; duplicate `event_id` → `202` and ignored |
| `GET /api/state` | — | `{"events":[…]}` latest evidence history (≤ 20), latest explainer, latest status, current role |
| `GET /api/health` | — | `{"ok":true,"panel_clients":n,"terminal":"running"\|"exited"\|"disabled"}` |
| `POST /api/terminal/restart` | — | restarts the shell (and startup command) |
| `POST /api/role` | `{"role":"engineer"\|"team_lead"\|"manager"}` | types `/mcp__loglad__<role>` into the terminal **without pressing Enter**, sets current role |
| `WS /ws/panels` | — | server → client: `{"kind":"snapshot","events":[…]}` on connect, then `{"kind":"event","event":{…}}` for each accepted event |
| `WS /ws/terminal` | client → server: `{"type":"input","data":"…"}`, `{"type":"resize","cols":n,"rows":n}` | server → client: `{"type":"output","data":"…"}`, `{"type":"exit","code":n}` |

Rules:

- Validate every POSTed event against `contracts/panel_event.schema.json` read from the repo at startup (path relative to the repo root, not copied). Invalid → 400 with the error list, nothing broadcast.
- `type: "reset"` clears all panel state and is broadcast.
- Several browser tabs may connect; all mirror the same terminal and panels.
- Never log full event payloads at info level (they can be large); log type, kind, receipt id.

### 3.2 The terminal

- Spawn with `node-pty`: shell = env `LOGLAD_SHELL`, else on Windows `pwsh.exe` if found, else `powershell.exe`; elsewhere `$SHELL` or `/bin/bash`. Working directory = **repo root** (so Claude Code finds `.mcp.json`).
- After spawn, write env `LOGLAD_STARTUP_COMMAND` (default `claude`) + Enter, unless it's empty.
- Resize the pty when xterm.js fits (`@xterm/addon-fit`) and on window resize.
- **node-pty must be optional.** Load it with a dynamic import inside try/catch. If it fails (native build problems on Windows are common) or `LOGLAD_TERMINAL=off`, the server still runs, `/api/health` reports `"terminal":"disabled"`, and the left pane shows: "Terminal disabled — run `claude` in Windows Terminal next to this window." This is our **version 1** fallback: Windows Terminal snapped left, browser snapped right. If `node-pty` won't build on Windows, try a prebuilt fork (e.g. `@homebridge/node-pty-prebuilt-multiarch`) before giving up — record what worked in your handoff.
- The role pills call `POST /api/role`; the command appears in the terminal input and the presenter presses Enter. Never auto-press Enter (Claude may be mid-answer).

## 4. What each panel renders

Shapes are in `contracts/panel_event.schema.json`; one example of each is in `contracts/fixtures/panel_events/`.

### 4.1 Evidence panel (`type: "evidence"`)

Common header: `payload.title`, a receipt chip (`payload.receipt.receipt_id`), and a footer from the receipt: "showing *returned* of *total_matches*" plus a "truncated" tag when true. Keep the last 20 evidence events; ◄ ► to browse, a "live" badge to jump back to the newest.

| `kind` | Rendering |
| --- | --- |
| `lines` | Monospace rows grouped by `groups[].label` with small group headers (before / anchor / after / matches / trace). Each row: 3 px colour stripe by `tone`, short time, `source`, level badge (text, not colour alone), message with `highlights` wrapped in `<mark>` (**character** offsets; escape the text first, then insert marks), `× N` badge when `repeat_count > 1`, an outline when `is_anchor`. `annotations` appear as small labels at the right edge of the row with that `line_id`. |
| `table` | Header from `columns[]`, formatted by `type`: `int` with thousands separators, `float` 1–2 decimals, `percent` as %, `change` as ▲/▼ with green/red and the % value, `team` as a coloured badge (colour from a stable hash of the team name), `level` as a level badge, `text` truncated with a tooltip. Optional `total_row` in bold. |
| `trend` | SVG line chart: one line per series (max 8), legend, x labels from `t` (day or week), y axis with `unit_label`, hover tooltip with exact values, `null` values = gaps. |
| `risks` | Up to 5 cards in rank order: rank, title, team badge, score as a bar 0–100, five mini bars **F S T V L** with the weights in a tooltip, stability text "top 3 in *round(stability × 10)* of 10 weightings", and the action text (or "No action given" in muted text). |

### 4.2 Explainer panel (`type: "explainer"`)

Render `markdown` as CommonMark, **sanitised** (DOMPurify). Every `[R-0042]` token becomes a clickable receipt chip. Clicking any receipt chip (here or in the evidence header) opens a **receipt drawer** in the explainer area: tool, scope (dataset, from → to, filters, unit, episode gap), total / returned / truncated, runtime, and each SQL statement in a monospace block with a copy button. Receipts come from `payload.receipts` (explainer) or `payload.receipt` (evidence) — the console never asks the backend for them.

### 4.3 Header (`type: "status"` and state)

Role pills (current role highlighted; the role of the latest event also updates it), a scope chip from the latest evidence receipt (`bgl · 2005-06-01 → 2005-06-30 · episodes · gap 10m`), receipt counter from `status.receipt_count`, and a claim indicator from `status.claims`: grey "not checked" (null), green "all claims backed", amber "N flagged / M unbacked".

### 4.4 Colour language (CSS variables, used everywhere)

| Token | Use |
| --- | --- |
| `--tone-critical` (red) | FATAL / FAILURE / CRITICAL, top risks |
| `--tone-error` (orange) | ERROR / SEVERE |
| `--tone-warning` (amber) | WARNING, flagged / unbacked claims |
| `--tone-info` (grey) | INFO, context lines |
| `--tone-accent` (blue) | search highlights, anchor outline, receipt chips |
| `--tone-good` (green) | backed claims, healthy status |

Use the `frontend-design` skill (or your own taste) to make it look deliberate, not templated — this screen is 20 % of the score through "presentation". Calm, dense, readable from the back of a room.

### 4.5 Empty, error and disconnected states

- No events yet: "Waiting for Claude to show evidence…" / "Explanations appear here."
- Panel WebSocket lost: a thin banner "Reconnecting…", exponential backoff to 5 s, re-request `/api/state` on reconnect.
- Terminal exited: overlay with "Restart" (calls `/api/terminal/restart`).
- A malformed event never reaches the browser (server rejects it), but the renderer must still not crash on unexpected optional fields.

## 5. How you develop without the backend

```bash
cd console && npm install
npm run dev                                   # server on :7777 (+ Vite dev server if you use one)
python scripts/replay_panel_events.py         # posts all 7 fixtures, 1.5 s apart
python scripts/replay_panel_events.py 04_evidence_risks --delay 0
```

The replay script is plain Python 3 (no packages). It must get `202` for every fixture; a `400` means your server's validation disagrees with the schema — the schema wins.

## 6. Commands that must work (Vedant runs these)

| Command | Result |
| --- | --- |
| `cd console && npm ci` | installs from your lockfile |
| `npm run build` | production build into `console/dist` |
| `npm start` | serves everything on `127.0.0.1:7777` from `dist` |
| `npm test` | vitest: schema validation accepts all fixtures and rejects a broken one; highlight rendering escapes HTML; number formatting |
| `LOGLAD_TERMINAL=off npm start` | panels only (version 1 fallback) |

Vedant's `python tasks.py console` will just call `npm --prefix console start`.

## 7. Windows checkpoint (W2, Sat 21:00)

On Vedant's laptop, together: `npm ci` succeeds; terminal opens PowerShell in the repo root and starts `claude`; typing works; resizing works; `replay_panel_events.py` fills all panels; a real `show_evidence` call from Claude Code appears. Anything that fails goes into your handoff with the workaround.

## 8. Milestones

| Milestone | Due | Done when |
| --- | --- | --- |
| **A1** | W1 Sat 16:00 | server with `POST /api/panel` (validated), `/ws/panels`, `/api/state`, `/api/health`; three-panel layout renders all 7 fixtures via replay (lines, table, trend, risks, explainer, status, reset) |
| **A2** | W2 Sat 21:00 | embedded terminal via node-pty running `claude` in the repo root; resize; restart; `LOGLAD_TERMINAL=off` fallback; role pills; Windows checkpoint passed |
| **A3** | W3 Sun 09:30 | receipt drawer, evidence history, header scope/claims, empty/error/reconnect states, colour language final |
| **A4** | W4 Sun 13:00 | visual polish at both resolutions; `docs/slides/` deck (6–8 slides: problem, idea, architecture, three roles, honesty moment, results, limits) using screenshots of the real console |

Each milestone is one PR with an updated `docs/handoff/ayoub.md` including screenshots (`docs/handoff/img/`) of every panel kind.
