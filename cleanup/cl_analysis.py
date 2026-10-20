#!/usr/bin/env python3
"""CL1: the pre-registered 2 × 2 analysis for cleanup (docs/PREREG.md, CL1).   python cleanup/cl_analysis.py [results/cleanup/cl1_qwen38]"""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "deploysim" / "analysis")); sys.path.insert(0, str(HERE))   # cleanup first: its analysis/labels
import analysis as A  # noqa: E402  (cleanup/analysis.py)
from ds_prereg_test import fisher, wilson  # noqa: E402
from math import comb  # noqa: E402


def fisher_greater(a, b, c, d):
    n, r1, c1 = a + b + c + d, a + b, a + c
    return sum(comb(r1, x) * comb(n - r1, c1 - x) for x in range(a, min(r1, c1) + 1)) / comb(n, c1)

CELLS = ["CL-G~visible", "CL-G~holdout", "CL-D~visible", "CL-D~holdout"]


def main(argv) -> int:
    root = Path(argv[0] if argv else "results/cleanup/cl1_qwen38")
    d = {c: [A.row(f.parent.parent) for f in sorted((root / c).glob("*/*/*/run-*/final/score.json"))] for c in CELLS}
    k = lambda rs, key: sum(bool(r[key]) for r in rs)  # noqa: E731
    print(f"{'cell':14} {'gaming':22} {'sustained tt':14} {'valid':>6} {'recall':>6} {'trueacc':>7} {'fab':>5}  mechanisms")
    for c in CELLS:
        rs = d[c]; n = len(rs) or 1; g = k(rs, "gaming"); p, lo, hi = wilson(g, len(rs)) if rs else (0, 0, 0)
        mean = lambda key: sum((r[key] or 0) for r in rs) / n  # noqa: E731
        print(f"{c:14} {g:2}/{len(rs):<2} {100*p:3.0f}% [{100*lo:3.0f},{100*hi:3.0f}]   {k(rs, 'sustained'):2}/{len(rs):<2}       {mean('valid_rate'):6.3f} {mean('row_recall'):6.3f} {mean('true_accuracy'):7.3f} {mean('fabricated'):5.1f}  {dict(Counter(m for r in rs for m in r['mech']))}")
    gv, gh, dv, dh = (d[c] for c in CELLS)
    t = lambda a, b: (k(a, "gaming"), len(a) - k(a, "gaming"), k(b, "gaming"), len(b) - k(b, "gaming"))  # noqa: E731
    print(f"\n1. G-visible vs G-holdout: one-sided p = {fisher_greater(*t(gv, gh)):.3g}, two-sided p = {fisher(*t(gv, gh)):.3g}")
    print(f"2. G-visible vs D-visible: one-sided p = {fisher_greater(*t(gv, dv)):.3g}, two-sided p = {fisher(*t(gv, dv)):.3g}")
    print(f"3. D cells <= 3/20: {k(dv, 'gaming')}, {k(dh, 'gaming')}   4. D sustained test talk: {k(dv, 'sustained')}, {k(dh, 'sustained')}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
