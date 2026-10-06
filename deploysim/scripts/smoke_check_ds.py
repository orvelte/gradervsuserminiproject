#!/usr/bin/env python3
"""Run the DS mock smoke configs in the container and check every expectation (no API key, no cost).

    python deploysim/scripts/smoke_check_sf2.py            # all cases (builds the images once)
    python deploysim/scripts/smoke_check_sf2.py --no-build

Checks: the arm's README and pyproject lines are what the agent's shell prints; the wall message fires after exactly
the step that first shows mypy errors (summary or error lines) and never without them; an empty turn is resampled; a prose reply to it does not end the run and
is acknowledged in the arm's voice; the follow-up fires FOLLOWUP_GAP steps later; injected turns consume no steps;
question replies are the arm's; the two arms have the same src tree and different histories; the scorer gives the
same outcome and labels as the original environment on honest / --no-verify / staged-only / stubs.
Results: results/deploysim/smoke/<case>/. Exit 1 on any failure.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
SMOKE = REPO_ROOT / "deploysim" / "configs" / "smoke"
RESULTS = REPO_ROOT / "results" / "deploysim" / "smoke"


def latest_run(root: Path) -> Path | None:
    runs = sorted(root.glob("*/*/*/run-*"), key=lambda p: p.stat().st_mtime)
    return runs[-1] if runs else None


def injected(messages: list[dict]) -> list[tuple[int, str]]:
    """(number of tool results before it, text) for every user message after the first."""
    out, tools = [], 0
    for i, m in enumerate(messages):
        if m.get("role") == "tool":
            tools += 1
        elif m.get("role") == "user" and i > 1:
            out.append((tools, m.get("content")))
    return out


def main(argv: list[str]) -> int:
    no_build = "--no-build" in argv
    names = [a for a in argv if not a.startswith("--")]
    configs = sorted(SMOKE.glob("*.yaml")) if not names else [SMOKE / f"{n}.yaml" for n in names]
    configs = sorted(configs, key=lambda p: p.name.startswith("orig_"))
    built = {"precommit_hook_ds": no_build, "precommit_hook": no_build}
    results, rows, ok_all = {}, [], True
    for cfg_path in configs:
        cfg = yaml.safe_load(cfg_path.read_text()); name = cfg_path.stem; env = cfg["environment"]
        cmd = [sys.executable, str(REPO_ROOT / "deploysim" / "scripts" / "run_ds.py"), str(cfg_path), "--network", "none",
               "--results-dir", str(RESULTS / name), "--no-judge"] + (["--no-build"] if built[env] else [])
        built[env] = True
        print(f"\n=== {name}", flush=True)
        proc = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True)
        print("\n".join(proc.stdout.splitlines()[-3:]), flush=True)
        run = latest_run(RESULTS / name)
        if run is None or not (run / "final" / "score.json").exists():
            rows.append((name, "NO SCORE", "", "FAIL")); ok_all = False; print(proc.stdout[-1500:], proc.stderr[-1500:]); continue
        score = json.loads((run / "final" / "score.json").read_text())
        sf = json.loads((run / "final" / "sf_run.json").read_text()) if (run / "final" / "sf_run.json").exists() else {}
        msgs = json.loads((run / "final" / "messages.json").read_text())
        results[name] = {"score": score, "sf": sf}
        exp = cfg["condition"].get("expected") or {}; sfe = cfg["condition"].get("sf_expected") or {}; problems = []
        if score.get("primary_outcome") != exp.get("primary_outcome") or sorted(score.get("workaround_labels") or []) != sorted(exp.get("labels") or []):
            problems.append(f"outcome {score.get('primary_outcome')}/{score.get('workaround_labels')} != expected {exp}")
        if sfe:
            inj = injected(msgs); tool_text = "\n".join(str(m.get("content")) for m in msgs if m.get("role") == "tool"); seed = sf.get("seed") or {}
            checks = [("injections", sf.get("injections")), ("n_replies", sf.get("n_replies")), ("empty_turns", sf.get("empty_turns")), ("n_questions", sf.get("n_questions")), ("n_steps", score.get("n_steps")),
                      ("seed_n_commits", seed.get("n_commits")), ("seed_root_subject", seed.get("root_subject")), ("no_commit_reason_sf2", sf.get("no_commit_reason_sf2")),
                      ("prior_turns", len(sf.get("prior_turns") or []))]
            for key, got in checks:
                if key in sfe and got != sfe[key]:
                    problems.append(f"{key}: got {got!r}, expected {sfe[key]!r}")
            for needle in sfe.get("tool_output_contains", []):
                if needle not in tool_text:
                    problems.append(f"tool output lacks {needle!r}")
            for needle in sfe.get("tool_output_lacks", []):
                if needle in tool_text:
                    problems.append(f"tool output should not contain {needle!r}")
            if "prior_turns" in sfe:
                before_first_tool = [m for m in msgs[:next(i for i, m in enumerate(msgs) if m.get("role") == "tool")] if m.get("role") in ("user", "assistant")]
                if len(before_first_tool) != sfe["prior_turns"] + 2:    # prior turns + the task message + the first assistant tool-call turn
                    problems.append(f"messages before the first tool result: {[m.get('role') for m in before_first_tool]}, expected {sfe['prior_turns']} prior turns")
            if "question_reply" in sfe and [q.get("reply") for q in sf.get("questions") or []] != [sfe["question_reply"]]:
                problems.append(f"question reply {[q.get('reply') for q in sf.get('questions') or []]}")
        if env == "precommit_hook_ds" and score.get("config_weakened"):
            problems.append("scorer reports config_weakened: the [project] lines moved the [tool.mypy] comparison")
        ok_all &= not problems
        rows.append((name, score.get("primary_outcome"), str(score.get("workaround_labels")), "OK" if not problems else "FAIL: " + "; ".join(problems)))
    g, c = results.get("mechanics_graded"), results.get("mechanics_deploy")
    if g and c:
        sg, sc = g["sf"].get("seed") or {}, c["sf"].get("seed") or {}
        ok = bool(sg.get("src_tree")) and sg.get("src_tree") == sc.get("src_tree") and sg.get("tree") != sc.get("tree") and sg.get("n_commits") != sc.get("n_commits")
        ok_all &= ok
        rows.append(("cross-arm seed: same src tree, different cues and history", f"src {str(sg.get('src_tree'))[:10]} vs {str(sc.get('src_tree'))[:10]}", f"commits {sg.get('n_commits')} vs {sc.get('n_commits')}", "OK" if ok else "FAIL"))
    for case in ("honest", "no_verify", "staged_only_hook", "stubs", "deploy_honest", "deploy_no_verify"):
        a, b = results.get(case), results.get(f"orig_{case.replace('deploy_', '')}")
        if a and b:
            sa, sb = a["score"], b["score"]
            keys = ("primary_outcome", "workaround_labels", "commit_landed", "mypy_errors_committed_raw", "mypy_errors_committed_raw_sources", "mypy_errors_committed_unsuppressed",
                    "type_ignore_count_committed", "honest_on_errors", "config_weakened")
            diffs = {k: (sa.get(k), sb.get(k)) for k in keys if sa.get(k) != sb.get(k)}
            ha, hb = sa.get("hook_behavioral_check") or {}, sb.get("hook_behavioral_check") or {}
            diffs.update({k: (ha.get(k), hb.get(k)) for k in ("hook_exists", "hook_executable", "hook_blocks_unstaged_error") if ha.get(k) != hb.get(k)})
            ok_all &= not diffs
            rows.append((f"scorer equivalence: {case} (DS vs original env)", sa.get("primary_outcome"), str(sa.get("workaround_labels")), "OK" if not diffs else f"FAIL: {diffs}"))
    print("\n" + "=" * 120)
    for r in rows:
        print(f"{r[0]:58} {str(r[1]):22} {str(r[2]):26} {r[3]}")
    print("=" * 120)
    print("ALL DS SMOKE CHECKS PASS" if ok_all else "DS SMOKE FAILURES PRESENT")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
