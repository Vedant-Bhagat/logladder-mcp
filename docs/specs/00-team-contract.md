# 00 — Team contract: how three branches become one demo

**Read this first, all three of us.** It fixes who owns which files, the interfaces between our work, the git rules and the timeline. If something here and your personal spec disagree, this file wins; if this file and `contracts/` disagree, `contracts/` wins.

Design background (the why): [LogLadder — Design Document](https://claude.ai/code/artifact/4be24739-436f-482a-aef1-33b9d07b3c14). Challenge: SereneDB "Making Sense of Logs", National AI Hackathon 2026.

| Doc | Who reads it |
| --- | --- |
| `docs/specs/00-team-contract.md` (this) | everyone |
| `docs/specs/01-vedant-data-and-integration.md` | Vedant |
| `docs/specs/02-janhavi-mcp-tools.md` | Janhavi (Vedant skims) |
| `docs/specs/03-ayoub-console.md` | Ayoub (Vedant skims) |
| `instructions/<NAME>.md` | the prompt each person gives their own coding agent |
| `CLAUDE.md` | read automatically by every Claude Code session in the repo |
| `contracts/` | the frozen interfaces; read by everyone's agent |

---

## 1. What we are building (one paragraph)

A Python MCP server (`loglad_mcp`) over a local SereneDB loaded with BGL and OpenStack logs. Claude Code connects to it and answers questions for three roles — engineer, team lead, manager — using 12 tools that search, count, trend, rank and test hypotheses **inside SereneDB**, and that store a **receipt** (SQL + scope + result digest) for every call. Two extra display tools push highlighted evidence and explanations to a **console**: a web page whose main window is the real `claude` CLI running in PowerShell, with an evidence panel (top-right) and an explainer panel (bottom-right).

```
Ayoub ─ console/ (Node + TS)          ◄── POST /api/panel ──┐
                                                            │ panel events (contracts/panel_event.schema.json)
Janhavi ─ loglad_mcp/core, tools, reasoning, prompts ───────┘
              │  envelopes (contracts/envelope.schema.json)     ▲ Db / Settings (contracts/interfaces.py)
              ▼                                                 │
Vedant ─ server.py, config.py, core/db.py, ingest/, sql/  ──► SereneDB :7890 (contracts/db_schema.sql)
```

## 2. Ownership — who may edit what

**Rule: you only edit files you own.** Anything else → ask the owner. This is what makes Vedant's merges conflict-free.

| Path | Owner | Notes |
| --- | --- | --- |
| `contracts/**` | Vedant (frozen) | change process in §6 |
| `CLAUDE.md`, `README.md`, `tasks.py`, `pyproject.toml`, `.mcp.json`, `.env.example`, `.gitignore`, `.gitattributes`, `.github/**` | Vedant | ask him to add a Python dependency |
| `infra/**`, `ingest/**`, `sql/**`, `data/samples/**` | Vedant | |
| `loglad_mcp/__init__.py`, `__main__.py`, `server.py`, `config.py`, `core/db.py` | Vedant | |
| `loglad_mcp/core/{context,envelope,receipts,limits,console,timeparse}.py` | Janhavi | |
| `loglad_mcp/tools/**`, `loglad_mcp/reasoning/**`, `loglad_mcp/prompts/**`, `loglad_mcp/resources/**` | Janhavi | |
| `tests/tools/**`, `tests/reasoning/**`, `docs/tools.md`, `docs/tool_selection.md` | Janhavi | `docs/tools.md` is generated |
| `tests/ingest/**`, `tests/integration/**`, `docs/investigation.md`, `docs/validation.md` | Vedant | |
| `console/**` (incl. its own `package.json`) | Ayoub | |
| `docs/slides/**` | Ayoub | |
| `scripts/validate_contracts.py`, `scripts/replay_panel_events.py`, `tests/contract/**` | Vedant | shared tooling, already written |
| `docs/handoff/<name>.md` | each person their own | required with every merge request (§8) |

## 3. Repository layout (final shape)

```
loglad/
├── CLAUDE.md  README.md  pyproject.toml  tasks.py  .mcp.json  .env.example
├── contracts/            # FROZEN: schemas, DDL, interfaces, fixtures
├── infra/                # docker-compose.yml for SereneDB
├── data/                 # gitignored, except data/samples/*_2k.log
├── ingest/               # fetch.py parse_bgl.py parse_openstack.py templates.py load.py
├── sql/                  # 01_schema.sql … 07_checks.sql, ownership.sql
├── loglad_mcp/
│   ├── __main__.py server.py config.py
│   ├── core/             # db.py | context.py envelope.py receipts.py limits.py console.py timeparse.py
│   ├── tools/            # registry.py orient.py retrieve.py aggregate.py analyse.py reason.py display.py
│   ├── reasoning/        # claims.py hypothesis.py risk.py
│   ├── prompts/          # registry.py engineer.md team_lead.md manager.md investigate.md
│   └── resources/        # registry.py answer_contract.md glossary.md
├── console/              # server/ (Node: node-pty + WebSocket + POST /api/panel)  web/ (TypeScript UI)
├── scripts/              # validate_contracts.py replay_panel_events.py
├── tests/                # contract/ tools/ reasoning/ ingest/ integration/
└── docs/                 # specs/ handoff/ tools.md investigation.md validation.md slides/
```

## 4. Platform and runtime (Vedant's laptop hosts the demo)

The final demo runs on **Vedant's machine (Windows, PowerShell)**. Your code must run there even if you develop on macOS or Linux.

| Item | Value |
| --- | --- |
| Python | 3.11+ ; virtual env in `.venv/` ; install with `pip install -e ".[dev]"` |
| Node | 20 LTS ; console uses its own `console/package.json` |
| Docker | Docker Desktop ; SereneDB image `serenedb/serenedb` |
| SereneDB | `localhost:7890`, Postgres wire protocol, no credentials by default |
| Console | `http://127.0.0.1:7777` (HTTP + WebSockets on the same port) |
| MCP transport | stdio (Claude Code launches `python -m loglad_mcp`) |
| Task runner | `python tasks.py <cmd>` — **not `make`** (Windows has no make) |

Environment variables (defaults in `.env.example`): `SERENEDB_DSN`, `LOGLAD_CONSOLE_URL=http://127.0.0.1:7777`, `LOGLAD_SESSION_ID` (optional), `LOGLAD_QUERY_TIMEOUT_S=10`, `LOGLAD_LOG_LEVEL=INFO`, console-only: `LOGLAD_CONSOLE_PORT=7777`, `LOGLAD_SHELL` (auto-detected if empty), `LOGLAD_STARTUP_COMMAND=claude`, `LOGLAD_TERMINAL=on|off`. Tests only: `LOGLAD_VALIDATE=1` (tools validate their own envelopes).

Cross-platform rules (everyone):

- Paths via `pathlib` / `path.join`, never hard-coded `/` or `\`.
- No shell-specific scripts in the run path; use Python (`tasks.py`) or Node.
- Text files UTF-8 with LF endings (`.gitattributes` enforces it). Open files with `encoding="utf-8"`.
- **MCP server: never print to stdout** — stdout is the MCP channel. Log to stderr.
- No absolute paths, usernames or machine names in committed files.

## 5. Interfaces (summary — the files in `contracts/` are authoritative)

### 5.1 Names that must match everywhere

| Thing | Exact values |
| --- | --- |
| Datasets | `bgl`, `openstack` (lower-case); scope may also be `both` or `none` |
| Roles | `engineer`, `team_lead`, `manager`, `unknown` |
| Tools | `describe_corpus`, `search_logs`, `get_timeline`, `trace_request`, `count_by`, `trend`, `recurring_problems`, `rank_risks`, `test_hypothesis`, `check_answer`, `verify_receipt`, `get_receipt`, `show_evidence`, `show_explainer` (+ optional `create_workspace_index`, `drop_workspace_index`) |
| MCP server name | `loglad` (so prompts appear in Claude Code as `/mcp__loglad__engineer` etc. — Vedant confirms the exact form at M2) |
| Prompts | `engineer`, `team_lead`, `manager`, `investigate` |
| Resources | `loglad://schema`, `loglad://ownership`, `loglad://answer-contract`, `loglad://glossary` |
| Receipt IDs | `R-0001`, `R-0002`, … |
| Index names | `bgl_idx`, `os_idx` |
| Episode gaps | BGL `10m` per (template, midplane); OpenStack `60s` per (template, service) |

### 5.2 The three seams

1. **SereneDB ↔ tools** — `contracts/db_schema.sql`. Vedant's loader produces exactly these tables; Janhavi's SQL reads exactly these columns.
2. **Python ↔ Python** — `contracts/interfaces.py`. Vedant provides `Settings`, `load_settings()`, `SereneDb` (implements `Db`). Janhavi provides `init_context()`, `ctx()`, and the `TOOLS`, `PROMPTS`, `RESOURCES` registries. `server.py` (Vedant) only wires registries into FastMCP.
3. **MCP ↔ console** — `contracts/panel_event.schema.json`. Janhavi's display tools POST events to `{LOGLAD_CONSOLE_URL}/api/panel`; Ayoub's console renders them. **The console never queries the database**; everything it shows comes in an event.

### 5.3 The display flow (the key trick)

Claude never sends log lines to the console itself. It calls `show_evidence(receipt_id=..., kind=...)`; the tool loads that receipt's stored `data` from the `receipts` table and builds the panel event from it. So **the evidence panel can only show data a real query returned** — the demo cannot display fabricated evidence.

## 6. Contract-change process

1. You find you need a change in `contracts/` (a new field, a renamed column, a new tool).
2. Message Vedant with: what, why, which files, and whether it breaks anyone.
3. Vedant decides, edits `contracts/` **on `main`**, bumps `contracts/VERSION` only if the change breaks existing producers/consumers, updates fixtures, runs `python scripts/validate_contracts.py`, and posts "contract updated" in the chat.
4. Everyone rebases on `main` at the next convenient point.

Additive, optional fields can be agreed in minutes. Renames and removals after Saturday 21:00 are refused unless something is broken.

## 7. Git workflow

| Rule | Detail |
| --- | --- |
| Branches | `vedant/<topic>`, `janhavi/<topic>`, `ayoub/<topic>`. Never commit to `main` (except Vedant). |
| Base | Branch from the latest `main`; `git pull --rebase origin main` before every merge request. |
| Commits | Small, present tense, prefixed: `data:`, `tools:`, `reasoning:`, `console:`, `docs:`, `test:`, `chore:` |
| Never commit | `data/` (except `data/samples/`), `.env`, `.venv/`, `node_modules/`, `console/dist/`, large files (> 1 MB), secrets, personal paths |
| Merge requests | A GitHub PR into `main` with the checklist below; Vedant merges |
| Merge windows | **W1 Sat 16:00 · W2 Sat 21:00 · W3 Sun 09:30 · W4 Sun 13:00 · freeze = submission − 2 h** |

PR checklist (paste into the PR description):

- [ ] Only files I own are changed (§2)
- [ ] Rebased on latest `main`
- [ ] `pytest tests/contract` passes
- [ ] My own tests pass (command in my spec)
- [ ] `docs/handoff/<me>.md` updated for this merge
- [ ] No new dependency added without Vedant's OK

## 8. Handoffs — how work comes back to Vedant

Every merge request updates **`docs/handoff/<your-name>.md`** using `docs/handoff/TEMPLATE.md`: what's done, how to run it, test output, deviations from the spec, known issues, what's next. Your coding agent writes it; you read it before opening the PR. Vedant reads it before merging. No handoff → no merge.

## 9. Milestones and dependencies

| When | Vedant | Janhavi | Ayoub |
| --- | --- | --- | --- |
| Sat 14:00 | **V0** repo created from this starter; SereneDB running; `SERENEDB_DSN` in `.env.example`; everyone invited | start from contracts + fixtures (no DB needed) | start from fixtures + replay (no DB needed) |
| Sat 15:30 | **V1** `python tasks.py data --sample` loads the 2k samples end-to-end → Janhavi can test SQL locally | | |
| **W1 Sat 16:00** | merge J1, A1 | **J1** core: envelope, receipts, limits, context, console client; `describe_corpus` + `search_logs` on sample DB | **A1** console server + three panels rendering all 7 fixtures via replay |
| Sat 20:00 | **V2** full data + templates + episodes + indexes; `server.py` wired; Claude Code connects | | |
| **W2 Sat 21:00** | merge J2, A2; Ayoub tests terminal on Vedant's laptop | **J2** tools 3–7 + display tools | **A2** embedded PowerShell terminal running `claude`; live panels; role switcher |
| **W3 Sun 09:30** | **V3** one answer per role works end to end | **J3** `rank_risks`, `test_hypothesis`, `check_answer`, receipts tools, prompts, resources | **A3** receipt drawer, status header, colour language, empty/error states |
| **W4 Sun 13:00** | investigation chosen + exported; README; validation | **J4** descriptions tuned from tool-selection log; `docs/tools.md` | **A4** demo polish, slides, backup recording setup |
| freeze | clean-checkout test, rehearsal | bug fixes only | bug fixes only |

If you're blocked for more than 30 minutes, say so in the team chat with what you tried. Working around a blocker by editing someone else's files is not allowed — stub it on your side instead.

## 10. Definition of done (everyone)

1. Works on Vedant's Windows machine (or at least nothing platform-specific was used).
2. Matches the contracts — validated by `scripts/validate_contracts.py`, not by eye.
3. Has tests or a reproducible manual check listed in the handoff.
4. Fails gracefully: no crash on bad input, no hang when SereneDB or the console is down.
5. Handoff file updated.
