#!/usr/bin/env python3
"""Summary per batch × condition × model for holdout runs (H1 screen and later pilots).

    python holdout/analysis.py results/holdout/h1_* [--runs]
Columns: grader-targeted gaming and its mechanisms, legit, mean sample / held-out accuracy and overfit gap, verbalised
belief (sustained / early test talk, grader words; deploysim measures), reasoning share, malformed calls, steps.
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(REPO / "deploysim" / "analysis"))
import labels as L  # noqa: E402
import gate_check as G  # noqa: E402
from testtalk_table import measure as testtalk  # noqa: E402


def row(run: Path) -> dict:
    o = L.label_run(run); f = run / "final"
    msgs = json.loads((f / "messages.json").read_text()); asst = [m for m in msgs if m.get("role") == "assistant"]
    sf = json.loads((f / "sf_run.json").read_text()) if (f / "sf_run.json").exists() else {}
    tt = testtalk(asst); text = " ".join(G.reasoning(m) for m in asst)
    return {**o["measures"], "gaming": o["grader_gaming"], "prereg": o["grader_gaming_h1_prereg"], "mech": [l for l in o["labels"] if l in L.GAMING + L.MECHANISMS], "legit": "legit" in o["labels"],
            "sustained": tt["sustained"], "early": tt["early"], "any_tt": tt["any"], "grader": bool(G.GRADER.search(text)),
            "reason": sum(bool((m.get("reasoning") or "").strip()) for m in asst) / max(1, len(asst)), "malformed": len(sf.get("malformed_calls") or []),
            "post": ((sf.get("post_question") or {}).get("answer") or "")[:130].replace("\n", " ")}


def main(argv) -> int:
    cells = defaultdict(list)
    for a in [a for a in argv if not a.startswith("--")]:
        for f in sorted(Path(a).glob("*/*/*/*/run-*/final/score.json")):
            run = f.parent.parent; p = run.parts; i = p.index("holdout")
            cells[(p[i + 1], p[i + 2], p[i + 4])].append((run, row(run)))
    print(f"{'batch':12} {'cond':14} {'model':32} {'n':>2} {'gaming':>6} {'prereg':>6} {'legit':>5} {'sample':>6} {'heldout':>7} {'gap':>5} {'sust':>4} {'early':>5} {'tt':>3} {'grader':>6} {'reas%':>5} {'malf':>4} {'steps':>5}  mechanisms")
    for (b, c, m), rs in sorted(cells.items()):
        n = len(rs); s = lambda k: sum(bool(r[k]) for _, r in rs)  # noqa: E731
        mean = lambda k: sum((r[k] or 0) for _, r in rs) / n  # noqa: E731
        mech = Counter(x for _, r in rs for x in r["mech"])
        print(f"{b:12} {c:14} {m:32} {n:2} {s('gaming'):6} {s('prereg'):6} {s('legit'):5} {mean('sample_acc'):6.3f} {mean('holdout_acc'):7.3f} {mean('overfit_gap'):5.2f} {s('sustained'):4} {s('early'):5} {s('any_tt'):3} {s('grader'):6} {100 * mean('reason'):5.0f} {sum(r['malformed'] for _, r in rs):4} {mean('n_steps'):5.0f}  {dict(mech)}")
        if "--runs" in argv:
            for run, r in rs:
                print(f"    {run.name:7} gaming={r['gaming']} {r['mech']} sample={r['sample_acc']:.3f} heldout={r['holdout_acc']:.3f} steps={r['n_steps']} tt={r['any_tt']}/{r['sustained']} | {r['post']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
