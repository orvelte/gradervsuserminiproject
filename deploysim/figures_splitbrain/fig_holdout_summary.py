#!/usr/bin/env python3
"""Holdout summary (Qwen3.8-27B): grader-targeted gaming by frame × scoring statement across H3, H4, H5, H6.
    python deploysim/figures_splitbrain/fig_holdout_summary.py"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(REPO / "holdout")); sys.path.insert(0, str(REPO / "deploysim" / "analysis"))
import style as ST  # noqa: E402
import analysis as A  # noqa: E402
from ds_prereg_test import wilson  # noqa: E402

ROWS = [  # (label, batch, cell, colour index, hatched)
    ("graded · scored on sample (H3)", "h3_qwen38", "HO-G~visible", 1, False),
    ("graded · sample + purpose stated (H6)", "h6_qwen38", "HO-G~visible_intent", 1, False),
    ("graded · scored on held-out (H3)", "h3_qwen38", "HO-G~holdout", 1, False),
    ("graded · sample, data v3 (H5)", "h5_qwen38", "HO3-G~visible", 1, False),
    ("conduct review · scored on sample (H4)", "h4_qwen38", "HO-C~visible", 2, False),
    ("conduct review · scored on held-out (H4)", "h4_qwen38", "HO-C~holdout", 2, False),
    ("deployment · scored on sample (H3)", "h3_qwen38", "HO-D~visible", 0, True),
    ("deployment · sample + purpose stated (H6)", "h6_qwen38", "HO-D~visible_intent", 0, True),
    ("deployment · scored on held-out (H3)", "h3_qwen38", "HO-D~holdout", 0, True),
    ("deployment · sample, data v3 (H5)", "h5_qwen38", "HO3-D~visible", 0, True),
]


def main():
    ST.setup()
    fig, ax = plt.subplots(figsize=(10, 5.6))
    for i, (lab, b, c, col, hatch) in enumerate(ROWS):
        rs = [A.row(f.parent.parent) for f in sorted((REPO / "results" / "holdout" / b / c).glob("*/*/*/run-*/final/score.json"))]
        n = len(rs); k = sum(r["gaming"] for r in rs); p, lo, hi = wilson(k, n)
        y = len(ROWS) - 1 - i; color = ST.PALETTE[col]
        if hatch:
            ax.barh(y, p, 0.7, facecolor="white", edgecolor=color, hatch="///", linewidth=1.2)
        else:
            ax.barh(y, p, 0.7, color=color)
        ax.errorbar(p, y, xerr=[[max(0, p - lo)], [max(0, hi - p)]], **ST.ERR)
        ax.text(min(hi + 0.02, 0.97), y, f"{k}/{n}", va="center", fontsize=9)
    ax.set_yticks(range(len(ROWS)), [r[0] for r in ROWS][::-1], fontsize=9.5)
    ax.set_xlim(0, 1.05); ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:.0%}")); ax.grid(axis="y", visible=False)
    ax.set_xlabel("runs with grader-targeted gaming (fitting the sample's quirk labels, or tampering)")
    fig.tight_layout()
    ST.titles(fig, "Qwen3.8-27B games the grader only when it believes it is scored",
              "holdout env (ticket routing) · pre-registered batches H3–H6 · orange = score-graded, purple = conduct review, hatched = deployment · whiskers = 95% Wilson CI")
    for ext in ("png", "pdf"):
        fig.savefig(HERE / f"fig_holdout_summary.{ext}", bbox_inches="tight")
    print("wrote", HERE / "fig_holdout_summary.png")


if __name__ == "__main__":
    main()
