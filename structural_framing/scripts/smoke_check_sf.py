#!/usr/bin/env python3
"""Run the SF1 mock smoke configs in the container and check every expectation (no API key, no cost).

    python structural_framing/scripts/smoke_check_sf.py            # all cases (builds the SF image once)
    python structural_framing/scripts/smoke_check_sf.py --no-build

Checks, from sfbuildtask.md: injections fire after exactly steps 8 and 18 and do not count as steps;
question-tool replies are the arm's; the git history differs by arm while the tree hashes match; the scorer
gives the same outcome/labels as the original environment on honest / --no-verify / staged-only / stubs.
Results land under results/structural_framing/smoke/<case>/. Exit 1 on any failure.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
SMOKE = REPO_ROOT / "structural_framing" / "configs" / "smoke"
RESULTS = REPO_ROOT / "results" / "structural_framing" / "smoke"


def latest_run(root: Path) -> Path | None:
    runs = sorted(root.glob("*/*/*/run-*"), key=lambda p: p.stat().st_mtime)
    return runs[-1] if runs else None


def user_turn_positions(messages: list[dict]) -> list[int]:
    """For each injected user message (not the first), how many tool results precede it."""
    out = []
    tools = 0
    for i, m in enumerate(messages):
        if m.get("role") == "tool":
            tools += 1
        elif m.get("role") == "user" and i > 1:
            out.append(tools)
    return out


def main(argv: list[str]) -> int:
    no_build = "--no-build" in argv
    names = [a for a in argv if not a.startswith("--")]
    configs = sorted(SMOKE.glob("*.yaml")) if not names else [SMOKE / f"{n}.yaml" for n in names]
    # SF cases first (so the SF image is built once), then the original-env twins.
    configs = sorted(configs, key=lambda p: p.name.startswith("orig_"))
    built = {"precommit_hook_sf": no_build, "precommit_hook": no_build}
    results: dict[str, dict] = {}
    rows = []
    ok_all = True
    for cfg_path in configs:
        cfg = yaml.safe_load(cfg_path.read_text())
        name = cfg_path.stem
        env = cfg["environment"]
        cmd = [sys.executable, str(REPO_ROOT / "structural_framing" / "scripts" / "run_sf.py"), str(cfg_path), "--network", "none",
               "--results-dir", str(RESULTS / name), "--no-judge"] + (["--no-build"] if built[env] else [])
        built[env] = True
        print(f"\n=== {name}: {' '.join(cmd[2:])}", flush=True)
        proc = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True)
        print("\n".join(proc.stdout.splitlines()[-4:]), flush=True)
        run = latest_run(RESULTS / name)
        if run is None or not (run / "final" / "score.json").exists():
            rows.append((name, "NO SCORE", "", "FAIL")); ok_all = False
            print(proc.stderr[-1500:]); continue
        score = json.loads((run / "final" / "score.json").read_text())
        sf = json.loads((run / "final" / "sf_run.json").read_text()) if (run / "final" / "sf_run.json").exists() else {}
        msgs = json.loads((run / "final" / "messages.json").read_text())
        results[name] = {"score": score, "sf": sf, "msgs": msgs, "run": run}
        exp = cfg["condition"].get("expected") or {}
        problems = []
        if score.get("primary_outcome") != exp.get("primary_outcome") or sorted(score.get("workaround_labels") or []) != sorted(exp.get("labels") or []):
            problems.append(f"outcome {score.get('primary_outcome')}/{score.get('workaround_labels')} != expected {exp}")
        sfe = cfg["condition"].get("sf_expected") or {}
        if sfe:
            if sf.get("injections_fired") != sfe.get("injections_fired", sf.get("injections_fired")):
                problems.append(f"injections_fired {sf.get('injections_fired')} != {sfe.get('injections_fired')}")
            if "injections_fired" in sfe:
                pos = user_turn_positions(msgs)
                if pos != sfe["injections_fired"]:
                    problems.append(f"injected user turns sit after tool results {pos}, expected after {sfe['injections_fired']}")
            if "n_steps" in sfe and score.get("n_steps") != sfe["n_steps"]:
                problems.append(f"n_steps {score.get('n_steps')} != {sfe['n_steps']} (injections must not consume steps)")
            if "n_questions" in sfe and sf.get("n_questions") != sfe["n_questions"]:
                problems.append(f"n_questions {sf.get('n_questions')} != {sfe['n_questions']}")
            if "question_reply" in sfe:
                replies = [q.get("reply") for q in sf.get("questions") or []]
                tool_texts = [m.get("content") for m in msgs if m.get("role") == "tool"]
                if replies != [sfe["question_reply"]] * len(replies) or sfe["question_reply"] not in tool_texts:
                    problems.append(f"question reply {replies} != {sfe['question_reply']!r}")
            seed = sf.get("seed") or {}
            if "seed_n_commits" in sfe and seed.get("n_commits") != sfe["seed_n_commits"]:
                problems.append(f"seed n_commits {seed.get('n_commits')} != {sfe['seed_n_commits']}")
            if "seed_root_subject" in sfe and seed.get("root_subject") != sfe["seed_root_subject"]:
                problems.append(f"seed root subject {seed.get('root_subject')!r}")
        status = "OK" if not problems else "FAIL: " + "; ".join(problems)
        ok_all &= not problems
        rows.append((name, score.get("primary_outcome"), str(score.get("workaround_labels")), status))
    # cross-arm: same tree, different history
    g, c = results.get("mechanics_graded"), results.get("mechanics_collaborator")
    if g and c:
        sg, sc = g["sf"].get("seed") or {}, c["sf"].get("seed") or {}
        same_tree = sg.get("tree") == sc.get("tree") and sg.get("tree")
        diff_hist = sg.get("head") != sc.get("head") and sg.get("n_commits") != sc.get("n_commits")
        st = "OK" if same_tree and diff_hist else f"FAIL: tree_equal={same_tree} history_differs={diff_hist}"
        ok_all &= st == "OK"
        rows.append(("cross-arm seed: same tree, different history", f"tree {str(sg.get('tree'))[:10]} vs {str(sc.get('tree'))[:10]}", f"commits {sg.get('n_commits')} vs {sc.get('n_commits')}", st))
    # scorer equivalence vs the original environment
    for case in ("honest", "no_verify", "staged_only_hook", "stubs"):
        a, b = results.get(case), results.get(f"orig_{case}")
        if a and b:
            sa, sb = a["score"], b["score"]
            keys = ("primary_outcome", "workaround_labels", "commit_landed", "mypy_errors_committed_raw", "mypy_errors_committed_raw_sources",
                    "type_ignore_count_committed", "honest_on_errors")
            diffs = {k: (sa.get(k), sb.get(k)) for k in keys if sa.get(k) != sb.get(k)}
            hook_a, hook_b = sa.get("hook_behavioral_check") or {}, sb.get("hook_behavioral_check") or {}
            for k in ("hook_exists", "hook_executable", "hook_blocks_unstaged_error"):
                if hook_a.get(k) != hook_b.get(k):
                    diffs[k] = (hook_a.get(k), hook_b.get(k))
            st = "OK" if not diffs else f"FAIL: {diffs}"
            ok_all &= not diffs
            rows.append((f"scorer equivalence: {case} (SF vs original env)", sa.get("primary_outcome"), str(sa.get("workaround_labels")), st))
    print("\n" + "=" * 110)
    for r in rows:
        print(f"{r[0]:52} {str(r[1]):10} {str(r[2]):28} {r[3]}")
    print("=" * 110)
    print("ALL SF1 SMOKE CHECKS PASS" if ok_all else "SF1 SMOKE FAILURES PRESENT")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
