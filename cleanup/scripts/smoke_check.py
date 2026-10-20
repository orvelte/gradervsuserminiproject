#!/usr/bin/env python3
"""Run the cleanup mock smoke configs in the container and check every expectation (no key, no cost).

    python cleanup/scripts/smoke_check.py [case ...] [--no-build]
Labels must be exactly the expected ones; mechanics cases check that the frame's README and history reach the agent's
shell, the prior turns precede the task, and an ask_question gets the frame's reply. Exit 1 on any failure."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "cleanup"))
import labels as L  # noqa: E402

SMOKE = REPO / "cleanup" / "configs" / "smoke"
RESULTS = REPO / "results" / "cleanup" / "smoke"


def main(argv) -> int:
    names = [a for a in argv if not a.startswith("--")]
    cfgs = [SMOKE / f"{n}.yaml" for n in names] if names else sorted(SMOKE.glob("*.yaml"))
    built = "--no-build" in argv; ok_all = True; rows = []
    for p in cfgs:
        cfg = yaml.safe_load(p.read_text()); name = p.stem; exp = cfg["condition"]["expected"]
        cmd = [sys.executable, str(REPO / "cleanup/scripts/run_cl.py"), str(p), "--network", "none", "--results-dir", str(RESULTS / name), "--no-judge"] + (["--no-build"] if built else [])
        built = True
        proc = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True)
        runs = sorted((RESULTS / name).glob("*/*/*/run-*"), key=lambda q: q.stat().st_mtime)
        if not runs or not (runs[-1] / "final" / "score.json").exists():
            ok_all = False; rows.append((name, "NO SCORE", "")); print(proc.stdout[-2000:], proc.stderr[-2000:]); continue
        run = runs[-1]; o = L.label_run(run); problems = []
        if sorted(o["labels"]) != sorted(exp["labels"]):
            problems.append(f"labels {o['labels']} != {exp['labels']}")
        msgs = json.loads((run / "final" / "messages.json").read_text())
        tool_text = "\n".join(str(m.get("content")) for m in msgs if m.get("role") == "tool")
        cc = cfg["task"]["cue_content"]
        if cc["readme"].splitlines()[0] not in tool_text:
            problems.append("README not seen in the shell")
        if cc["history"][-1]["message"] not in tool_text:
            problems.append("seeded history not seen")
        n_prior = len(cfg["prompts"]["prior_turns"])
        if [m["role"] for m in msgs[1:1 + n_prior]] != [t["role"] for t in cfg["prompts"]["prior_turns"]]:
            problems.append("prior turns not in place")
        if exp.get("question") and cc["question_reply"] not in tool_text:
            problems.append("question reply missing")
        sc = json.loads((run / "final" / "score.json").read_text())
        if sc.get("scorer_errors"):
            problems.append(f"scorer errors {sc['scorer_errors']}")
        ok_all &= not problems
        rows.append((name, f"{o['labels']} valid={sc.get('valid_rate')} recall={sc.get('row_recall')} fab={sc.get('fabricated')} reported={sc.get('reported_rate')}", "OK" if not problems else "FAIL: " + "; ".join(problems)))
    print("\n" + "=" * 110)
    for r in rows:
        print(f"{r[0]:16} {r[1]:70} {r[2]}")
    print("ALL CLEANUP SMOKE CHECKS PASS" if ok_all else "CLEANUP SMOKE FAILURES PRESENT")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
