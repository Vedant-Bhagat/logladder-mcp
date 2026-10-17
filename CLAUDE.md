# LogLadder — rules for every coding agent in this repo

You are helping one of three people build LogLadder for the SereneDB "Making Sense of Logs" hackathon: an MCP server over SereneDB (BGL + OpenStack logs) used by Claude Code, plus a console that shows the evidence. Three people work on separate branches; **Vedant merges everything and runs the demo on his Windows laptop.** Consistency matters more than cleverness.

## Before you write any code

1. Ask (or read from the prompt) **who you are working for**: Vedant, Janhavi or Ayoub. Then read `instructions/<NAME>.md` and follow it.
2. Read `docs/specs/00-team-contract.md` and that person's spec in `docs/specs/`.
3. Read the files in `contracts/` that your work produces or consumes.

## Hard rules

- **Only edit files owned by your person** (ownership table in `docs/specs/00-team-contract.md` §2). If a change outside them seems necessary, stop and tell your human what and why; do not make it.
- **Never edit `contracts/`** on a feature branch. Contracts change only on `main`, by Vedant.
- Every JSON you produce for another person's code must validate: `python scripts/validate_contracts.py envelope|panel <file>`.
- Names are exact: datasets `bgl`/`openstack`; roles `engineer`/`team_lead`/`manager`/`unknown`; tool, prompt, resource, index and table names as in the contract. No synonyms, no camelCase variants.
- Don't add dependencies. Python deps are in `pyproject.toml` (Vedant's); console deps in `console/package.json` (Ayoub's). If you need one, tell your human.
- Cross-platform: `pathlib`/`path.join`, UTF-8, LF; no bash-only or PowerShell-only scripts in the run path; use `python tasks.py …`.
- The MCP server must **never write to stdout** (it's the MCP channel). Log to stderr.
- Never invent data. Fixture numbers in `contracts/fixtures/` are fake; never present them as findings. Any summary or label you generate from query results must only contain values that are in the results.
- Never commit `data/` (except `data/samples/`), `.env`, `.venv/`, `node_modules/`, build output or files over 1 MB.
- Use the SereneDB docs MCP for SQL syntax you're not sure of (`claude mcp add --transport http serenedb-docs https://api.serenedb.com/mcp`), and note any surprise in the handoff under "SereneDB notes".

## Definition of done for any task

1. Matches the person's spec and the contracts.
2. Tests listed in the spec pass; `pytest tests/contract` passes.
3. Fails gracefully (bad input, DB down, console down) — no crash, no hang.
4. `docs/handoff/<name>.md` updated from `docs/handoff/TEMPLATE.md` with real command output, deviations and known issues.
5. Commits are small with prefixes `data: tools: reasoning: console: docs: test: chore:`; branch `<name>/<topic>`; rebased on `main`.

## When unsure

Prefer the contract over the spec, the spec over this file's general advice, and asking your human over guessing. Write the question into the handoff's "Open questions" if your human isn't around.
