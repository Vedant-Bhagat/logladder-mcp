# LogLadder console

One page on `http://127.0.0.1:7777`: a real terminal running `claude` on the left, the evidence panel (top right) and the explainer (bottom right). The MCP display tools POST panel events to `/api/panel`; the console never talks to the database. Spec: `docs/specs/03-ayoub-console.md`.

- **Server:** Python, FastAPI (`loglad_console/`). The terminal is a real shell: pywinpty (ConPTY) on Windows, the standard library pty on macOS/Linux. No C++ build tools needed.
- **Page:** Vite + TypeScript + Web Awesome components, Lucide icons, xterm.js (`web/`), built once into `dist/web`.

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
pytest console/tests   # API + terminal tests (from the repo root)
```

Fill the panels without a backend: `python scripts/replay_panel_events.py` from the repo root.

| Env | Default | |
| --- | --- | --- |
| `LOGLAD_CONSOLE_PORT` | `7777` | binds to 127.0.0.1 only |
| `LOGLAD_TERMINAL` | `on` | `off` = panels only (run `claude` in Windows Terminal next to the browser) |
| `LOGLAD_SHELL` | auto | Windows: `pwsh.exe` if found, else `powershell.exe`; elsewhere `$SHELL` |
| `LOGLAD_STARTUP_COMMAND` | `claude` | typed into the shell after it starts; empty = nothing |

Role buttons type `/mcp__loglad__<role>` into the terminal without pressing Enter (if the terminal is off, they copy it to the clipboard). Ctrl+Shift+F hides the terminal so the panels fill the screen.
