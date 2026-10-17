# Handoff — Ayoub — A1 (with A2 terminal groundwork) — Sat 17 Oct 16:10

Branch: `ayoub/console-a1` · Rebased on `main` at: `593844b` · Contract version: `1`

## 1. Done

| Item from my spec | Status | Notes |
| --- | --- | --- |
| `POST /api/panel` validated against `contracts/panel_event.schema.json` | done | Schema read from the repo at startup (ajv 2020). 202 / 400 with error list / duplicate `event_id` → 202 ignored. Bad JSON → 400. Body limit 2 MB. |
| `GET /api/state`, `GET /api/health` | done | State = last 20 evidence + latest explainer + latest status (+ `role`). |
| `WS /ws/panels` | done | `snapshot` on connect, then `event` per accepted event. `reset` clears and is broadcast. |
| Three-panel layout rendering all 7 fixtures | done | lines, table, trend, risks, explainer, status, reset — all via `replay_panel_events.py`. |
| Terminal (A2 groundwork) | done on macOS | node-pty loaded optionally; `/ws/terminal`, `/api/terminal/restart`, `LOGLAD_TERMINAL=off` fallback, exit overlay with Restart. **Windows not tested yet.** |
| Role pills + `POST /api/role` (A2) | done | Types `/mcp__loglad__<role>` without Enter. |
| Receipt drawer, evidence history, header scope/claims, empty/reconnect states (A3 items) | done (first pass) | Will polish in A3. |

## 2. How to run it

macOS 15, Node 24 (works on Node 20+). From the repo root:

```
cd console
npm ci
npm test
npm run build
npm start                                   # http://127.0.0.1:7777
# other terminal, repo root:
python scripts/replay_panel_events.py       # every line must say [202]
LOGLAD_TERMINAL=off npm start               # panels only (fallback)
npm run dev                                 # dev: Vite middleware, server restarts on change
```

`python tasks.py console` runs `npm --prefix console start`, unchanged.

## 3. Proof

```
$ npm test
 ✓ test/format.test.ts (14)   highlight escaping, number formatting, labels
 ✓ test/validate.test.ts (10) all 7 fixtures accepted; broken events rejected
 ✓ test/api.test.ts (8)       202/400/duplicate, state, 20-event cap, WS snapshot+reset, health, role
 Test Files  3 passed (3)
      Tests  31 passed (31)

$ python scripts/replay_panel_events.py
[202] 01_evidence_lines
[202] 02_evidence_table
[202] 03_evidence_trend
[202] 04_evidence_risks
[202] 05_explainer
[202] 06_status
[202] 07_reset

$ LOGLAD_TERMINAL=off LOGLAD_CONSOLE_PORT=7778 node dist/server/index.js
LogLadder console on http://127.0.0.1:7778 · terminal: disabled (LOGLAD_TERMINAL=off)
$ curl 127.0.0.1:7778/api/health
{"ok":true,"panel_clients":0,"terminal":"disabled"}
(replay against :7778 → all 7 [202])

$ pytest tests/contract
17 passed
```

Screenshots (fixture data, numbers are fake): `docs/handoff/img/`
- `a1-lines-explainer-1366.jpg`, `a1-lines-explainer-1920.jpg` — lines + explainer + amber claims shield
- `a1-lines-expanded.png` — a line clicked open (full message, time, source, component)
- `a1-table.png`, `a1-trend-hover.png`, `a1-risks-1366.jpg`
- `a1-receipt-drawer.jpg` — receipt chip → drawer with scope, counts and SQL (copy button)
- `a1-empty-role-typed.jpg` — empty states; Engineer pill typed `/mcp__loglad__engineer` into the shell

## 4. Deviations from the spec

- **UI stack: Web Awesome (web components) + plain TypeScript + Vite** instead of Preact — Ayoub's call (no JSX). Uses `wa-split-panel` (draggable terminal/panel split), `wa-drawer` (receipts), `wa-tooltip`, `wa-copy-button`. Icons: Lucide, bundled. Fonts: Inter / Inter Tight / JetBrains Mono, bundled via @fontsource (no network needed at demo time).
- **Less text, more icons** (Ayoub's design feedback): severity is an icon with a distinct shape per level (octagon-x / circle-alert / triangle / dot) plus the stripe colour, with the level name on hover and in the expanded row — still not colour alone. Max-level table cells show the icon only (name on hover). Times show `HH:MM:SS` (full timestamp on hover); BGL node ids shortened `R23-M0-N4-C:J12-U11 → N4·J12` (full id on hover). Evidence footer is `4 / 316` in the header instead of a sentence.
- **Extra WS message** `{"kind":"role","role":…}` on `/ws/panels` when the role changes, and `snapshot` carries `role`. Additive; only the console reads it.
- `/ws/terminal` also sends `{"type":"disabled","reason":…}` and `{"type":"restarted"}` (console-internal).
- `POST /api/terminal/restart` returns 409 when the terminal is disabled.
- The server reads the repo-root `.env` (only keys not already set) so `LOGLAD_*` values there apply to the console too.
- On reconnect the WS `snapshot` replaces the separate `GET /api/state` call (same content).
- Presenter shortcut: **Ctrl+Shift+F** hides/shows the terminal so the panels fill the screen.

## 5. SereneDB notes (backend only)

n/a — the console never talks to SereneDB.

## 6. Known issues

- **Windows untested.** Needs the W2 checkpoint on Vedant's laptop. Dependencies: `node-pty@1.0.0` (needs build tools on Windows) **and** `@homebridge/node-pty-prebuilt-multiarch@0.12.0` (prebuilt binaries) are both optional; the server tries node-pty first, then the prebuilt fork, then falls back to panels-only. Shell = `LOGLAD_SHELL`, else `pwsh.exe` if on PATH, else `powershell.exe`.
- npm 11 warns that install scripts were not approved (`npm install-scripts approve`). On macOS node-pty still works. On Windows, if neither pty package loads, run `npm install-scripts approve node-pty @homebridge/node-pty-prebuilt-multiarch` (or `npm rebuild`) in `console/`.
- Screenshots were taken through a scaled preview, so they're lower resolution than the real screen.
- At 1920×1080 the text is on the small side for a projector — A4 polish (bigger base size / zoom).
- JS bundle is ~520 kB (xterm + Web Awesome + marked + DOMPurify); local only, loads instantly.

## 7. Open questions for Vedant

1. OK to keep both pty packages as optional dependencies, or do you prefer only the prebuilt fork on Windows?
2. Should the console's startup command activate the venv before `claude` on your laptop (e.g. `LOGLAD_STARTUP_COMMAND=.venv\Scripts\Activate.ps1; claude`), or does `.mcp.json` already point at the venv Python?

## 8. Next

A2: Windows checkpoint on Vedant's laptop (npm ci, pty, PowerShell + `claude` in the repo root, resize, replay, one real `show_evidence`). Then A3 polish (receipt drawer details, history, states) and A4 (projector sizing, slides).

---
History (one line per milestone): `A1 – Sat 16:10 – server + 3 panels + all 7 fixtures; terminal groundwork`
