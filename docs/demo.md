# Demo cue card (5 minutes)

Before: Docker Desktop running → `python tasks.py db` → `python tasks.py console` (full data already loaded).
Open `docs/slides/index.html` in a second browser tab. Close other Claude sessions (one session at a time).
Backup: if Claude is slow or the network drops, show `docs/investigation.md` (the same run, recorded).

| Time | Beat | Do / type | Point at |
| --- | --- | --- | --- |
| 0:00–0:30 | Problem + thesis | Slides 1–3: "smart tools, every number has a receipt" | ladder + receipt slide |
| 0:30–1:45 | **Engineer** | Click **Engineer**, then type: `What happened on midplane R20-M0 in the hour before the first FATAL kernel error on 2005-06-05?` | highlighted lines in the evidence panel, quiet gap, explainer with Unknowns |
| 1:45–2:45 | **Team lead** | Click **Team lead**: `Which problems recurred most in the last 4 weeks of BGL, by episodes, per team?` | table by team; "episodes, not lines" |
| 2:45–3:40 | **Manager** | Click **Manager**: `Across both systems, what are the top 3 risks right now and what should we do about each?` | risk cards with inputs, stability, three actions |
| 3:40–4:25 | **Honesty moment** | Same session: `How much downtime did this cause?` | Claude: the logs don't record downtime; amber/green claim shield |
| 4:25–5:00 | Receipts | Click a receipt chip → SQL; type `verify_receipt R-xxxx` (any receipt from the manager answer) | "identical" digest; architecture slide |

Expected answers from our test runs are in `docs/investigation.md`. Claude's wording changes run to run; the numbers don't.
Presenter keys: Ctrl+Shift+F hides the terminal; ← → and F in the slides.
