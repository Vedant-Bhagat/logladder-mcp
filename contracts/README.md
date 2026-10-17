# contracts/ — the frozen seams between our three branches

Everything in this folder is **frozen at contract version 1** (see `VERSION`).
Feature branches never edit it. If you need a change, follow the contract-change
process in `docs/specs/00-team-contract.md` §6 — Vedant edits it on `main`, bumps
`VERSION`, and everyone rebases.

| File | What it freezes | Producer | Consumer |
| --- | --- | --- | --- |
| `db_schema.sql` | Table names, column names, types, index names | Vedant (`sql/`, `ingest/`) | Janhavi (tool SQL) |
| `interfaces.py` | Python seams: `Settings`, `Db`, `QueryResult`, `ToolContext`, `ToolSpec`, `PromptSpec`, `ResourceSpec`, server wiring | Vedant + Janhavi | Vedant + Janhavi |
| `envelope.schema.json` | The JSON every MCP tool returns, per-tool `data` shapes | Janhavi (tools) | Claude, receipts, Vedant (investigation export) |
| `panel_event.schema.json` | The JSON the display tools POST to the console | Janhavi (display tools) | Ayoub (console) |
| `fixtures/envelopes/*.json` | One valid example per tool (fake numbers, `"fixture": true`) | — | Janhavi's tests, Vedant's docs |
| `fixtures/panel_events/*.json` | One valid example per panel event kind (fake numbers) | — | Ayoub builds and tests the UI against these |

Check anything against the contracts:

```bash
python scripts/validate_contracts.py                    # all fixtures
python scripts/validate_contracts.py envelope out.json  # one tool output
python scripts/validate_contracts.py panel event.json   # one panel event
pytest tests/contract                                   # same, as tests
```

Fixture numbers are invented. Never quote them as findings.
