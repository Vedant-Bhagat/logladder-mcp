# LogLadder console

A page on `http://127.0.0.1:7777` with the evidence panel (top) and the explainer (bottom). Claude Code runs in your own terminal next to it (Windows Terminal / PowerShell snapped left, browser snapped right). The MCP display tools POST panel events to `/api/panel`; the console never talks to the database. Spec: `docs/specs/03-ayoub-console.md`.

- **Server:** Python, FastAPI (`loglad_console/`), started with `npm start` or `python tasks.py console`.
- **Page:** Vite + TypeScript + Web Awesome components, Lucide icons (`web/`), built once into `dist/web`.

```
# once, from the repo root (inside the venv)
pip install -e ".[dev]"
pip install -r console/requirements.txt

# once, in console/
npm ci
npm run build

npm start        # serve on 127.0.0.1:7777 (uses the repo .venv if it exists; LOGLAD_PYTHON overrides)
npm run dev      # same, and rebuilds the page on every change (reload the browser)
npm test         # vitest: formatting + highlight escaping
pytest console/tests   # API tests (from the repo root)
```

Fill the panels without a backend: `python scripts/replay_panel_events.py` from the repo root.

| Env | Default | |
| --- | --- | --- |
| `LOGLAD_CONSOLE_PORT` | `7777` | binds to 127.0.0.1 only |

The role buttons copy `/mcp__loglad__<role>` to the clipboard so you can paste it into Claude.
