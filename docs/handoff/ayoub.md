# Handoff — Ayoub — A2 (FastAPI server + terminal inside the page) — Sun 18 Oct 02:00

Branch: `ayoub/console-fastapi` · Rebased on `main` at: `c29529d` · Contract version: `1`

## 1. Done

| Item | Status | Notes |
| --- | --- | --- |
| Console server rewritten in Python/FastAPI | done | `console/loglad_console/`. Same API as A1: `POST /api/panel` (validated with `jsonschema` against `contracts/panel_event.schema.json`, read at startup), `GET /api/state`, `GET /api/health`, `POST /api/role`, `WS /ws/panels`. 202 / 400 + error list / duplicate → 202 ignored. |
| Node server removed | done | No more node-pty, ws, ajv, xterm. Node is only used to build the page (`npm run build`). |
| Embedded terminal, now from Python | done (macOS tested) | `loglad_console/terminal.py`: **pywinpty** (ConPTY, ready-built wheels for Windows, no C++ tools) on Windows, standard-library `pty` on macOS/Linux. Same `/ws/terminal` protocol as A1, `/api/terminal/restart`, starts `LOGLAD_STARTUP_COMMAND` (default `claude`) in the repo root, scrollback for new tabs. `LOGLAD_TERMINAL=off` → panels only. This replaces node-pty, so the Windows failure Vedant found (node-pty 1.0.0 needs build tools, prebuilt fork has no Node 24 binary) can't happen. |
| Page | done | Same layout as A1 (terminal left, evidence + explainer right). **Show/hide-terminal button** left of the logo (shortcut Ctrl/Cmd+Shift+F, now works while the terminal has focus). |
| Role switch | done | Role button sends **Ctrl+C** (stops whatever Claude is doing / clears the line), then **`/clear`** (fresh conversation, so roles don't mix), then types `/mcp__loglad__<role>` **and presses Enter**. A second click while a switch is still typing gets 409 (a second Ctrl+C could quit Claude) (Ayoub's call, replaces "no Enter" from the spec). Terminal off → copies the command to the clipboard. |
| One-command run | done | `python tasks.py console` (unchanged `tasks.py`) → `npm start` → `start.mjs` sets up on first run: `.venv` via `tasks.py setup` if missing, `pip install -r console/requirements.txt` if the imports fail, `npm ci` if node_modules is stale, page build if `dist/` is older than `web/`; warns if `claude` isn't on PATH; then starts the server and opens the browser (`LOGLAD_OPEN_BROWSER=off` to skip). |
| `npm start` / `python tasks.py console` | done | `npm start` runs `node start.mjs`, which starts `python -m loglad_console` with the repo `.venv` Python (or `LOGLAD_PYTHON`, else `python`/`python3`). `tasks.py` needs no change. |

## 2. How to run it

macOS 15, Python 3.12, Node 24. Needs Python 3.11+, Node 20+, Claude Code. From the repo root:

```
python tasks.py console                 # first run installs everything, then opens http://127.0.0.1:7777
python scripts/replay_panel_events.py   # other terminal: fill the panels with the sample events
```

## 3. Proof

```
$ pytest console/tests
20 passed            (all 7 fixtures valid, broken events rejected, 202/400/duplicate,
                      state, 20-event cap, WS snapshot → event → role, health, role, SPA fallback,
                      terminal: startup command runs, typed input, role typed without Enter,
                      exit → restart, LOGLAD_TERMINAL=off, other-website Origin rejected)
$ cd console && npm test
Tests  12 passed     (highlight escaping, number formatting, labels)
$ pytest tests/contract
17 passed
$ ruff check console/loglad_console console/tests
All checks passed!
$ python scripts/replay_panel_events.py
[202] 01_evidence_lines … [202] 07_reset   (all 7)
```

Checked in the browser at 1366×768: typed `echo hello from the console` into the page's terminal and got the output (`docs/handoff/img/a2-fastapi-terminal-1366.jpg`); panels update live over `/ws/panels`.

## 3b. Polish and slides (A4, first pass)

- **Projector size:** at 1700 px wide and up (1920×1080 projector) the header, panels, drawer and tooltips are scaled ×1.22 and the terminal font goes from 13 to 16 px.
- **Slides:** `docs/slides/index.html`, one self-contained HTML file (open it in a browser; ← → to move, F for full screen; no network). 8 slides: title, problem, idea (ladder + receipt), architecture, three roles, honesty moment, the console (`docs/slides/img/console-1920.jpg`), results and limits. The **Results** box is a placeholder to fill from `docs/investigation.md` / `docs/validation.md` once Vedant's worked investigation exists; no fixture numbers are presented as findings. The console screenshot should be retaken with real data before the demo.

## 4. Deviations from the spec

- **Server is Python/FastAPI, not Node** (Ayoub's decision). API paths, status codes and message shapes unchanged, so the display tools and the smoke test are unaffected.
- **New Python dependencies: `fastapi==0.128.8`, `websockets==15.0.1`** (uvicorn needs `websockets` for WebSockets) **and `pywinpty==3.1.0` on Windows only** (the terminal). Everything else (`starlette`, `uvicorn`, `httpx`, `jsonschema`) already comes with `mcp==1.30.0`. They are listed in `console/requirements.txt` for now — **Vedant: OK to move them into `pyproject.toml` dependencies?**
- The console's Python tests live in `console/tests/` (my folder). `pytest` from the repo root only collects `tests/` (pyproject `testpaths`), so run `pytest console/tests` explicitly, or add it to `testpaths`.

## 5. SereneDB notes (backend only)

n/a.

## 5b. Security

The terminal is a real shell, so the server rejects requests and WebSockets whose `Origin` is another website (403 / close 1008). Without that, any page open in the presenter's browser could type into the shell or post fake evidence. Scripts (the MCP display tools, `replay_panel_events.py`) send no `Origin` and are unaffected; GETs stay open. Server still binds to 127.0.0.1 only.

## 6. Known issues

- **Windows untested.** On Vedant's laptop: `pip install -r console/requirements.txt` (pulls pywinpty), `npm ci && npm run build && npm start`, check PowerShell opens in the repo root and starts `claude`.
- On this Mac `pip install -e ".[dev]"` failed building `cryptography` from source (x86_64 Python, no wheel picked). `pip install --only-binary=:all: cryptography` first fixed it. Probably local to this machine.
- First start can take a few seconds while Python compiles FastAPI.

## 7. Open questions for Vedant

1. OK to add `fastapi` and `websockets` to `pyproject.toml` (or keep `console/requirements.txt`)?
2. Add `console/tests` to pytest `testpaths`, or keep running it separately?

Answered from A1: the terminal-library question is moot now. The Windows failure Vedant found (node-pty@1.0.0 needs build tools, the prebuilt fork has no Node 24 binary) is gone because this branch has no node-pty at all. No venv activation is needed before `claude`, since `.mcp.json` runs `python tasks.py mcp`. `npm audit fix` updated dompurify to 3.4.17, and `ws` is no longer a dependency.

## 8. Next

Windows checkpoint, then A3/A4: polish with real data (bigger text for the projector), slides.

---
History (one line per milestone): `A1 – Sat 16:10 – Node server + 3 panels + all 7 fixtures; terminal groundwork` · `A2 – Sat 22:00 – server rewritten in FastAPI, panels only` · `A2 – Sun 02:00 – terminal back inside the page (pywinpty / pty)` · `A2 – Sun 03:00 – terminal toggle button, Ctrl+C role switch, one-command run` · `A4 – Sun 03:30 – projector sizing, slide deck (results TBD)`
