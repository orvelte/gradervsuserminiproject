#!/usr/bin/env python3
"""Summary per batch × condition × model for cleanup runs.   python cleanup/analysis.py results/cleanup/<batch>* [--runs]"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent / "deploysim" / "analysis"))
import labels as L  # noqa: E402
import gate_check as G  # noqa: E402
from testtalk_table import measure as testtalk  # noqa: E402


def row(run: Path) -> dict:
    o = L.label_run(run); msgs = json.loads((run / "final" / "messages.json").read_text())
    asst = [m for m in msgs if m.get("role") == "assistant"]; tt = testtalk(asst)
    return {**o["measures"], "gaming": o["grader_gaming"], "mech": [l for l in o["labels"] if l in L.GAMING], "legit": "legit" in o["labels"],
            "sustained": tt["sustained"], "any_tt": tt["any"]}


def main(argv) -> int:
    cells = defaultdict(list)
    for a in [a for a in argv if not a.startswith("--")]:
        for f in sorted(Path(a).glob("*/*/*/*/run-*/final/score.json")):
            run = f.parent.parent; p = run.parts; i = p.index("cleanup")
            cells[(p[i + 1], p[i + 2], p[i + 4])].append((run, row(run)))
    print(f"{'batch':14} {'cond':14} {'model':30} {'n':>2} {'gaming':>6} {'legit':>5} {'valid':>6} {'recall':>6} {'trueacc':>7} {'fab':>5} {'sust':>4} {'tt':>3}  mechanisms")
    for (b, c, m), rs in sorted(cells.items()):
        n = len(rs); s = lambda k: sum(bool(r[k]) for _, r in rs); mean = lambda k: sum((r[k] or 0) for _, r in rs) / n  # noqa: E731
        print(f"{b:14} {c:14} {m:30} {n:2} {s('gaming'):6} {s('legit'):5} {mean('valid_rate'):6.3f} {mean('row_recall'):6.3f} {mean('true_accuracy'):7.3f} {mean('fabricated'):5.1f} {s('sustained'):4} {s('any_tt'):3}  {dict(Counter(x for _, r in rs for x in r['mech']))}")
        if "--runs" in argv:
            for run, r in rs:
                print(f"    {run.name:7} {r['mech']} valid={r['valid_rate']:.3f} recall={r['row_recall']:.3f} fab={r['fabricated']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
