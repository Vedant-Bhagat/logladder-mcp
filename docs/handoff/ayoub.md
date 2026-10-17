# Handoff — Ayoub — A2 (server rewritten in FastAPI, panels only) — Sat 17 Oct 22:00

Branch: `ayoub/console-fastapi` · Rebased on `main` at: `c29529d` · Contract version: `1`

## 1. Done

| Item | Status | Notes |
| --- | --- | --- |
| Console server rewritten in Python/FastAPI | done | `console/loglad_console/`. Same API as A1: `POST /api/panel` (validated with `jsonschema` against `contracts/panel_event.schema.json`, read at startup), `GET /api/state`, `GET /api/health`, `POST /api/role`, `WS /ws/panels`. 202 / 400 + error list / duplicate → 202 ignored. |
| Node server removed | done | No more node-pty, ws, ajv, xterm. Node is only used to build the page (`npm run build`). |
| Embedded terminal | **removed (by decision)** | Ayoub chose panels only: Claude Code runs in the presenter's own terminal (Windows Terminal snapped left, browser snapped right) — the spec's "version 1". `GET /api/health` reports `"terminal":"disabled"`; `POST /api/terminal/restart` → 409. |
| Page | done | Same panels as A1, laid out as evidence (top) / explainer (bottom), draggable split. Role buttons copy `/mcp__loglad__<role>` to the clipboard and show a toast (no terminal to type into). JS bundle 520 kB → 224 kB. |
| `npm start` / `python tasks.py console` | done | `npm start` runs `node start.mjs`, which starts `python -m loglad_console` with the repo `.venv` Python (or `LOGLAD_PYTHON`, else `python`/`python3`). `tasks.py` needs no change. |

## 2. How to run it

macOS 15, Python 3.12, Node 24. From the repo root:

```
python -m venv .venv && . .venv/bin/activate        # Windows: .venv\Scripts\Activate.ps1
pip install -e ".[dev]"
pip install -r console/requirements.txt             # fastapi + websockets (see §4)
cd console && npm ci && npm run build && npm start  # http://127.0.0.1:7777
python scripts/replay_panel_events.py               # other terminal, repo root
```

## 3. Proof

```
$ pytest console/tests
17 passed            (all 7 fixtures valid, broken events rejected, 202/400/duplicate,
                      state, 20-event cap, WS snapshot → event → role, health, role, SPA fallback)
$ cd console && npm test
Tests  12 passed     (highlight escaping, number formatting, labels)
$ pytest tests/contract
17 passed
$ ruff check console/loglad_console console/tests
All checks passed!
$ python scripts/replay_panel_events.py
[202] 01_evidence_lines … [202] 07_reset   (all 7)
```

Checked in the browser at 960×1040 (half of a 1920 screen): all panels render, live updates arrive over `/ws/panels`, role button → toast + role shown in the header.

## 4. Deviations from the spec

- **Server is Python/FastAPI, not Node** (Ayoub's decision). API paths, status codes and message shapes unchanged, so the display tools and the smoke test are unaffected.
- **No embedded terminal** (version 1 layout). Role buttons copy the slash command instead of typing it.
- **New Python dependencies: `fastapi==0.128.8` and `websockets==15.0.1`** (uvicorn needs `websockets` for WebSockets). Everything else (`starlette`, `uvicorn`, `httpx`, `jsonschema`) already comes with `mcp==1.30.0`. They are listed in `console/requirements.txt` for now — **Vedant: OK to move them into `pyproject.toml` dependencies?**
- The console's Python tests live in `console/tests/` (my folder). `pytest` from the repo root only collects `tests/` (pyproject `testpaths`), so run `pytest console/tests` explicitly, or add it to `testpaths`.

## 5. SereneDB notes (backend only)

n/a.

## 6. Known issues

- Windows untested (now much simpler: no native modules).
- On this Mac `pip install -e ".[dev]"` failed building `cryptography` from source (x86_64 Python, no wheel picked). `pip install --only-binary=:all: cryptography` first fixed it. Probably local to this machine.
- First start can take a few seconds while Python compiles FastAPI.

## 7. Open questions for Vedant

1. OK to add `fastapi` and `websockets` to `pyproject.toml` (or keep `console/requirements.txt`)?
2. Add `console/tests` to pytest `testpaths`, or keep running it separately?

## 8. Next

A3/A4: polish with real data (bigger text for the projector), demo layout with Windows Terminal + browser side by side, slides.

---
History (one line per milestone): `A1 – Sat 16:10 – Node server + 3 panels + all 7 fixtures; terminal groundwork` · `A2 – Sat 22:00 – server rewritten in FastAPI, panels only`
