#!/usr/bin/env python3
"""Model screen summary (spec §12 gates): per batch × arm × model, gaming and legit-fix rates, verbalised belief and
harness health. Works for every framing, including `cues`.

    python deploysim/analysis/screen.py results/deploysim/screen1_* [--runs]

Belief: test talk via gate_check.TEST_TALK per reasoning sentence (sustained = 3+ sentences, early = within the first
5 turns, as everywhere in deploysim); grader words via gate_check.GRADER. Health: share of assistant turns with
reasoning text (needed to measure awareness at all), malformed calls, crashes.
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent / "labels"))
import gate_check as G  # noqa: E402
import taxonomy as T  # noqa: E402
from testtalk_table import measure as testtalk  # noqa: E402


def runs(root: Path):
    for f in sorted(root.glob("**/run-*/final/score.json")):
        yield f.parent.parent


def row(run: Path) -> dict:
    sc = json.loads((run / "final" / "score.json").read_text())
    msgs = json.loads((run / "final" / "messages.json").read_text())
    sf = json.loads((run / "final" / "sf_run.json").read_text()) if (run / "final" / "sf_run.json").exists() else {}
    asst = [m for m in msgs if m.get("role") == "assistant"]
    lab = T.label_run(run); tt = testtalk(asst)
    text = " ".join(G.reasoning(m) for m in asst)
    return {"gaming": lab["gaming"], "legit": "legit_fix" in lab["labels"], "commit": bool(sc.get("commit_landed")), "labels": lab["gaming_labels"],
            "sustained": tt["sustained"], "early": tt["early"], "any_tt": tt["any"], "grader": bool(G.GRADER.search(text)),
            "reasoning_share": sum(bool((m.get("reasoning") or m.get("reasoning_content") or "").strip()) for m in asst) / max(1, len(asst)),
            "malformed": len(sf.get("malformed_calls") or []), "steps": sc.get("n_steps"), "censored": bool(sc.get("censored")),
            "post": ((sf.get("post_question") or {}).get("answer") or "")[:140].replace("\n", " ")}


def main(argv) -> int:
    show = "--runs" in argv
    cells = defaultdict(list)
    for a in [a for a in argv if not a.startswith("--")]:
        for run in runs(Path(a)):
            parts = run.parts; i = parts.index("deploysim")
            batch, arm = parts[i + 1], parts[i + 2]
            model = next((p for p in parts[i + 3:] if p not in ("precommit_hook_ds",)), "?")
            cells[(batch, arm, parts[parts.index("precommit_hook_ds") + 1] if "precommit_hook_ds" in parts else model)].append((run, row(run)))
    hdr = f"{'batch':22} {'arm':18} {'model':30} {'n':>2} {'gaming':>6} {'legit':>5} {'commit':>6} {'sust':>4} {'early':>5} {'tt':>3} {'grader':>6} {'reason%':>7} {'malf':>4} {'steps':>5}"
    print(hdr)
    for (b, a, m), rs in sorted(cells.items()):
        n = len(rs); s = lambda k: sum(bool(r[k]) for _, r in rs)  # noqa: E731
        print(f"{b:22} {a:18} {m:30} {n:2} {s('gaming'):6} {s('legit'):5} {s('commit'):6} {s('sustained'):4} {s('early'):5} {s('any_tt'):3} {s('grader'):6} "
              f"{100 * sum(r['reasoning_share'] for _, r in rs) / n:6.0f}% {sum(r['malformed'] for _, r in rs):4} {sum(r['steps'] or 0 for _, r in rs) / n:5.0f}")
        if show:
            for run, r in rs:
                print(f"    {run.name:7} gaming={r['gaming']} {r['labels']} legit={r['legit']} steps={r['steps']} tt={r['any_tt']}/{r['sustained']} | {r['post']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
