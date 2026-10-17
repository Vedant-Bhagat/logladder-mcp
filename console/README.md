# LogLadder console

One page on `http://127.0.0.1:7777`: the real `claude` CLI on the left, the evidence panel (top right) and the explainer (bottom right) on the right. The MCP display tools POST panel events to `/api/panel`; the console never talks to the database. Spec: `docs/specs/03-ayoub-console.md`.

```
npm ci
npm run build && npm start      # serve the built page
npm run dev                     # development (Vite middleware, server restarts on change)
npm test                        # vitest: schema, formatting, API
LOGLAD_TERMINAL=off npm start   # panels only; run claude in Windows Terminal next to it
```

Fill the panels without a backend: `python scripts/replay_panel_events.py` from the repo root.

| Env | Default | |
| --- | --- | --- |
| `LOGLAD_CONSOLE_PORT` | `7777` | binds to 127.0.0.1 only |
| `LOGLAD_TERMINAL` | `on` | `off` disables the embedded terminal |
| `LOGLAD_SHELL` | auto | Windows: `pwsh.exe` if found, else `powershell.exe`; elsewhere `$SHELL` |
| `LOGLAD_STARTUP_COMMAND` | `claude` | typed into the shell after start; empty = nothing |

Layout: `server/` (Node: HTTP API, WebSockets, optional node-pty), `web/` (Vite + TypeScript + Web Awesome components, Lucide icons, xterm.js). Shortcut: Ctrl+Shift+F hides the terminal.
