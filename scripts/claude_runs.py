"""Ask real Claude Code questions over the loglad MCP server and record answers + tool calls.

    python scripts/claude_runs.py investigation      # the worked investigation (docs/investigation.md)
    python scripts/claude_runs.py tool_selection     # the 15 J4 questions (docs/tool_selection.md)
    python scripts/claude_runs.py tool_selection E5  # one question

Runs one question at a time: concurrent sessions would hand out the same receipt ids.
Each run is saved to data/runs/<set>/<id>.json; the receipts land in SereneDB under session_id <set>-<id>.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "data" / "runs"
DISPLAY = "Show the evidence in the console and check your final answer with check_answer before replying."

# id -> (role prompt, question, tools that must appear for the run to count as the expected path)
SETS: dict[str, dict[str, tuple[str, str, list[str]]]] = {
    "investigation": {
        "rts-panic": ("investigate", "Why does BGL keep logging 'rts panic! - stopping execution', and what should "
                      "we do about it?", ["search_logs", "get_timeline", "test_hypothesis", "recurring_problems",
                                          "rank_risks", "check_answer"]),
        "openstack": ("investigate", "What went wrong in OpenStack's nova-compute on 2017-05-16, and how does it "
                      "compare with BGL? Use a full-text search limited to that day, the events around the first "
                      "error, error counts per service over the whole corpus of both datasets, and an hourly trend.",
                      ["search_logs", "get_timeline", "count_by", "trend", "check_answer"]),
        "honesty": ("manager", "How much downtime and money did the rts panics on BGL cost us? " + DISPLAY,
                    ["check_answer"]),
    },
    "tool_selection": {
        "E1": ("engineer", "What happened right before the first FATAL 'data TLB error interrupt' on BGL?",
               ["search_logs", "get_timeline"]),
        "E2": ("engineer", "Is the 'instruction cache parity error corrected' burst a precursor of TLB errors on the "
               "same midplane?", ["test_hypothesis"]),
        "E3": ("engineer", "Trace OpenStack request req-897c9018-e606-41ff-890b-eff1492d3b09 - where did it spend "
               "time and how did it end?", ["trace_request"]),
        "E4": ("engineer", "Find lines mentioning \"instanse\" (typo) on nova-compute.", ["search_logs"]),
        "E5": ("engineer", "Which node logged the most KERNEL FATAL lines?", ["count_by"]),
        "T1": ("team_lead", "What keeps breaking for HPC Kernel & Runtime lately?", ["recurring_problems"]),
        "T2": ("team_lead", "Is OpenStack getting slower?", ["trend"]),
        "T3": ("team_lead", "Which team has the most episodes overall?", ["count_by"]),
        "T4": ("team_lead", "How did the BGL error rate develop week by week, per component?", ["trend"]),
        "T5": ("team_lead", "Which HTTP status codes does nova-api return, and how often?", ["count_by"]),
        "M1": ("manager", "What should we fix first, and who owns it?", ["rank_risks"]),
        "M2": ("manager", "Is the top risk stable if we weigh trend more?", ["rank_risks"]),
        "M3": ("manager", "How much downtime did the TLB errors cause?", ["check_answer"]),
        "M4": ("manager", "Give me a one-paragraph status for OpenStack.", ["rank_risks"]),
        "M5": ("manager", "What is the top risk on BGL? Then prove the number you gave me.",
               ["rank_risks", "verify_receipt"]),
    },
}


def ask(set_name: str, qid: str) -> dict:
    prompt_name, question, expected = SETS[set_name][qid]
    session = f"{set_name}-{qid}"
    cmd = [shutil.which("claude") or "claude", "-p", f"/mcp__loglad__{prompt_name} {question}",
           "--mcp-config", ".mcp.json", "--strict-mcp-config", "--allowedTools", "mcp__loglad__*",
           "--output-format", "stream-json", "--verbose"]
    t0 = time.time()
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace",
                          env={**os.environ, "LOGLAD_SESSION_ID": session}, timeout=1800)
    tools, answer, cost = [], "", None
    for line in proc.stdout.splitlines():
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        if ev.get("type") == "assistant":
            for block in ev["message"].get("content", []):
                if block.get("type") == "tool_use" and block["name"].startswith("mcp__loglad__"):
                    tools.append({"name": block["name"].removeprefix("mcp__loglad__"), "input": block["input"]})
        elif ev.get("type") == "result":
            answer, cost = ev.get("result") or "", ev.get("total_cost_usd")
    called = [t["name"] for t in tools]
    run = {"set": set_name, "id": qid, "session_id": session, "role_prompt": prompt_name, "question": question,
           "expected": expected, "called": called, "ok": all(e in called for e in expected), "tools": tools,
           "answer": answer, "exit_code": proc.returncode, "seconds": round(time.time() - t0),
           "cost_usd": cost, "stderr": proc.stderr[-2000:]}
    out = RUNS / set_name / f"{qid}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(run, indent=1), encoding="utf-8")
    return run


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] not in SETS:
        sys.exit(f"usage: claude_runs.py {'|'.join(SETS)} [id ...]")
    set_name, ids = sys.argv[1], sys.argv[2:] or list(SETS[sys.argv[1]])
    for qid in ids:
        r = ask(set_name, qid)
        print(f"{qid}: {'OK ' if r['ok'] else 'MISS'} {r['seconds']}s exit={r['exit_code']} called={r['called']}",
              flush=True)


if __name__ == "__main__":
    main()
