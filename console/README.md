# LogLadder console

One page on `http://127.0.0.1:7777`: a real terminal running `claude` on the left, the evidence panel (top right) and the explainer (bottom right). The MCP display tools POST panel events to `/api/panel`; the console never talks to the database. Spec: `docs/specs/03-ayoub-console.md`.

- **Server:** Python, FastAPI (`loglad_console/`). The terminal is a real shell: pywinpty (ConPTY) on Windows, the standard library pty on macOS/Linux. No C++ build tools needed.
- **Page:** Vite + TypeScript + Web Awesome components, Lucide icons, xterm.js (`web/`), built once into `dist/web`.

**Run it (one command, from the repo root):**

```
python tasks.py console
```

Needs Python 3.11+, Node 20+ and Claude Code (`npm install -g @anthropic-ai/claude-code`). The first run sets everything up by itself: the `.venv` (same as `python tasks.py setup`), the console's Python packages (`console/requirements.txt`), `npm ci`, and the page build. Then it starts the server and opens http://127.0.0.1:7777 in your browser. Later runs start in a few seconds. Same thing from `console/`: `npm start`.

Development: `npm run dev` (rebuilds the page on change). Tests: `npm test` (page) and `pytest console/tests` (server + terminal, from the repo root).

Fill the panels without a backend: `python scripts/replay_panel_events.py` from the repo root.

| Env | Default | |
| --- | --- | --- |
| `LOGLAD_CONSOLE_PORT` | `7777` | binds to 127.0.0.1 only |
| `LOGLAD_TERMINAL` | `on` | `off` = panels only (run `claude` in Windows Terminal next to the browser) |
| `LOGLAD_SHELL` | auto | Windows: `pwsh.exe` if found, else `powershell.exe`; elsewhere `$SHELL` |
| `LOGLAD_STARTUP_COMMAND` | `claude` | typed into the shell after it starts; empty = nothing |
| `LOGLAD_OPEN_BROWSER` | `on` | `off` = don't open the browser |
| `LOGLAD_PYTHON` | auto | Python used to create the `.venv` on first run |

Role buttons press Ctrl+C in the terminal (stops whatever Claude is doing), run `/clear` (the new role starts with a fresh conversation, nothing carried over from the previous role), then run `/mcp__loglad__<role>`. If the terminal is off, they copy the command to the clipboard. The button left of the logo (or Ctrl/Cmd+Shift+F) hides the terminal so the panels fill the screen.
