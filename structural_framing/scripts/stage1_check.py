#!/usr/bin/env python3
"""Stage 1 transcript checklist (sfbuildtask.md) for SF1 runs, plus per-run cost from the provider-usage log lines.

    python structural_framing/scripts/stage1_check.py results/structural_framing/SF1-G-LAX results/structural_framing/SF1-C-LAX

Per run: injections and question-tool replies appear exactly as specified; reasoning is present; no tool calls
leaked into reasoning (recovered leaks in rollout.log and raw JSON tool calls in reasoning text); the run reached a
natural end before the step cap; whether the model ran `git log` and what it saw; outcome/labels; billed cost.
Pass/fail is printed per run and summarised. Reading the transcripts in full is still done by hand (the script
also writes a plain-text rendering of each transcript next to it: final/transcript.txt).
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "analysis"))
sys.path.insert(0, str(REPO_ROOT / "structural_framing" / "env" / "precommit_hook_sf"))
from common import find_run_dirs  # noqa: E402
from cost import parse_usage  # noqa: E402
import sf_framing as SF  # noqa: E402

LEAK_TEXT_RE = re.compile(r'\{\s*"(command|input|patch|question)"\s*:', re.I)


def render(messages: list[dict]) -> str:
    out = []
    for i, m in enumerate(messages):
        role = m.get("role")
        if role == "assistant":
            out.append(f"\n--- [{i}] ASSISTANT")
            if m.get("reasoning_content") or m.get("reasoning"):
                out.append("REASONING:\n" + (m.get("reasoning_content") or m.get("reasoning")))
            if m.get("content"):
                out.append("TEXT:\n" + m["content"])
            for tc in m.get("tool_calls") or []:
                fn = tc.get("function") or {}
                out.append(f"TOOL CALL {fn.get('name')}: {fn.get('arguments')}")
        else:
            out.append(f"\n--- [{i}] {str(role).upper()}\n{m.get('content')}")
    return "\n".join(out)


def check_run(run_dir: Path) -> dict:
    final = run_dir / "final"
    score = json.loads((final / "score.json").read_text())
    sf = json.loads((final / "sf_run.json").read_text())
    cond = json.loads((final / "run_condition.json").read_text())
    msgs = json.loads((final / "messages.json").read_text())
    (final / "transcript.txt").write_text(render(msgs))
    framing = sf["sf_framing"]
    problems = []
    # injections: present verbatim, right after the 8th and 18th tool results
    user_turns, tools = [], 0
    for i, m in enumerate(msgs):
        if m["role"] == "tool":
            tools += 1
        elif m["role"] == "user" and i > 1:
            user_turns.append((tools, m["content"]))
    expected = [(k, SF.INJECTIONS[framing][k]) for k in SF.INJECTION_STEPS if k <= score["n_steps"] and k < cond["config"]["agent"]["max_steps"]]
    expected = [(k, t) for k, t in expected if k in (sf.get("injections_fired") or [])] if sf.get("injections_fired") is not None else expected
    if user_turns != expected or sf.get("injections_fired") != [k for k, _ in expected]:
        problems.append(f"injections: got {[(t, c[:30]) for t, c in user_turns]}, expected {[(k, t[:30]) for k, t in expected]}")
    # question tool
    tool_results = [m for m in msgs if m["role"] == "tool"]
    q_replies = [m["content"] for m in tool_results if m["content"] == SF.QUESTION_REPLY[framing]]
    if len(q_replies) != sf.get("n_questions", 0) or any(q["reply"] != SF.QUESTION_REPLY[framing] for q in sf.get("questions") or []):
        problems.append(f"question replies: {len(q_replies)} in transcript vs {sf.get('n_questions')} logged")
    # reasoning present
    assistant = [m for m in msgs if m["role"] == "assistant"]
    with_reasoning = [m for m in assistant if (m.get("reasoning_content") or "").strip()]
    if not assistant or len(with_reasoning) < 0.5 * len(assistant):
        problems.append(f"reasoning present on only {len(with_reasoning)}/{len(assistant)} assistant turns")
    # leaks
    leaks_in_text = sum(1 for m in assistant if LEAK_TEXT_RE.search(m.get("reasoning_content") or "") or LEAK_TEXT_RE.search(m.get("content") or ""))
    log = (run_dir / "rollout.log").read_text(errors="replace") if (run_dir / "rollout.log").exists() else ""
    # run_step recovers a leaked call into a tool call whose id is "recovered_<step>"
    recovered = sum(1 for m in assistant for tc in (m.get("tool_calls") or []) if str(tc.get("id", "")).startswith("recovered_"))
    if leaks_in_text or recovered:
        problems.append(f"tool-call leakage: {recovered} recovered leaked calls, {leaks_in_text} raw JSON calls left in reasoning/text")
    # natural end
    if score.get("hit_max_steps") or not score.get("task_completed"):
        problems.append(f"did not reach a natural end: hit_max_steps={score.get('hit_max_steps')} task_completed={score.get('task_completed')} n_steps={score['n_steps']}")
    # git log visibility
    git_log_calls = []
    for i, m in enumerate(msgs):
        for tc in m.get("tool_calls") or []:
            args = (tc.get("function") or {}).get("arguments") or ""
            if re.search(r"git\s+(log|show|shortlog|blame)", args):
                git_log_calls.append(i)
    saw = []
    for i in git_log_calls:
        nxt = next((m for m in msgs[i + 1:] if m["role"] == "tool"), None)
        if nxt:
            txt = nxt["content"]
            saw.append("harness" in txt or "Priya" in txt or "ingestd" in txt or "task setup" in txt)
    usage = parse_usage(log)
    cost = sum(u.get("cost") or 0 for u in usage)
    return {
        "run": str(run_dir.relative_to(REPO_ROOT)), "arm": cond.get("condition_id"), "framing": framing,
        "outcome": score["primary_outcome"], "labels": score.get("workaround_labels"), "n_steps": score["n_steps"],
        "injections_fired": sf.get("injections_fired"), "questions": sf.get("n_questions"),
        "reasoning_turns": f"{len(with_reasoning)}/{len(assistant)}", "git_log_calls": len(git_log_calls),
        "git_history_visible": (all(saw) if saw else None), "recovered_leaks": recovered, "cost_usd": round(cost, 4), "turns": len(usage),
        "problems": problems, "pass": not problems,
    }


def main(argv=None) -> int:
    paths = (argv or sys.argv[1:]) or [str(REPO_ROOT / "results" / "structural_framing")]
    runs = [d for d in find_run_dirs(paths) if "/smoke/" not in str(d)]
    if not runs:
        print("no runs"); return 1
    rows = [check_run(d) for d in runs]
    for r in rows:
        print(f"{r['run']}\n  arm={r['arm']} outcome={r['outcome']} labels={r['labels']} steps={r['n_steps']} injections={r['injections_fired']} "
              f"questions={r['questions']} reasoning={r['reasoning_turns']} git_log_calls={r['git_log_calls']} history_visible={r['git_history_visible']} "
              f"cost=${r['cost_usd']:.3f} -> {'PASS' if r['pass'] else 'FAIL: ' + '; '.join(r['problems'])}")
    costs = [r["cost_usd"] for r in rows]
    print(f"\nruns: {len(rows)}, pass: {sum(r['pass'] for r in rows)}, total cost ${sum(costs):.2f}, mean ${sum(costs)/len(costs):.3f}, max ${max(costs):.3f}")
    print(f"Stage 2 projection (40 runs): mean x 40 = ${40*sum(costs)/len(costs):.2f}; max x 40 = ${40*max(costs):.2f}")
    (REPO_ROOT / "structural_framing" / "analysis" / "out").mkdir(parents=True, exist_ok=True)
    (REPO_ROOT / "structural_framing" / "analysis" / "out" / "stage1_check.json").write_text(json.dumps(rows, indent=2))
    return 0 if all(r["pass"] for r in rows) else 1


if __name__ == "__main__":
    sys.exit(main())
