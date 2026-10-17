# LogLadder

Evidence-first log investigation for engineers, team leads and managers — an MCP server over SereneDB, used by Claude Code, with a console that shows the evidence behind every answer.

> **Status: starter.** Vedant replaces this README at V4 with setup, workflow, tools, the worked investigation and known limitations.

## For the team — start here

1. `docs/specs/00-team-contract.md` — ownership, interfaces, git rules, timeline.
2. Your spec: `docs/specs/01-vedant-…`, `02-janhavi-…`, `03-ayoub-…`.
3. Your coding agent's prompt: `instructions/<NAME>.md` (start `claude` in the repo root and tell it to read that file).
4. `contracts/` — frozen interfaces and fixtures.

```bash
python tasks.py setup            # .venv + pinned deps
python tasks.py check            # contract + unit tests + ruff; must pass on every branch
python tasks.py db               # SereneDB in Docker (needs Docker Desktop)
python tasks.py data --sample    # load the 2k samples (full data: tasks.py fetch, then tasks.py data)
claude                           # in the repo root; .mcp.json starts the `loglad` MCP server
```
