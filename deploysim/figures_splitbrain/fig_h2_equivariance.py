#!/usr/bin/env python3
"""H2 equivariance pilot (Qwen3.8-27B, holdout ho-1.1): grader-targeted gaming, held-out accuracy and sustained test
talk by frame × scoring statement.   python deploysim/figures_splitbrain/fig_h2_equivariance.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(REPO / "holdout")); sys.path.insert(0, str(REPO / "deploysim" / "analysis"))
import style as ST  # noqa: E402
import h2_analysis as H  # noqa: E402
from ds_prereg_test import wilson  # noqa: E402


def main():
    ST.setup()
    d = H.collect(REPO / "results" / "holdout" / "h2_qwen38")
    fig, axes = plt.subplots(1, 3, figsize=(14, 4.3))
    groups = [("visible", "scored on ./score\n(the sample)"), ("holdout", "scored on a\nheld-out set")]
    frames = [("G", "graded", ST.PALETTE[1]), ("D", "deployment", ST.PALETTE[0])]
    x = np.arange(len(groups)); w = 0.36
    for ax, key, title, rate in ((axes[0], "gaming", "(a) Grader-targeted gaming (primary)", True),
                                 (axes[2], "sustained", "(c) Sustained test talk in reasoning", True)):
        for j, (f, flab, col) in enumerate(frames):
            for i, (s, _) in enumerate(groups):
                rs = d[f"HO-{f}~{s}"]; n = len(rs); kk = sum(bool(r[key]) for r in rs)
                p, lo, hi = wilson(kk, n) if n else (0, 0, 0)
                xi = x[i] + (j - 0.5) * w
                ST.bar(ax, xi, p, w * 0.9, col, deployment=(f == "D"))
                ax.errorbar(xi, p, yerr=[[max(0, p - lo)], [max(0, hi - p)]], **ST.ERR)
                ax.text(xi, hi + 0.03, f"{kk}/{n}", ha="center", fontsize=8.5)
        ax.set_xticks(x, [g[1] for g in groups]); ax.set_ylim(0, 1.15); ax.set_title(title, loc="left", fontsize=11.5)
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:.0%}")); ax.grid(axis="x", visible=False)
    axes[0].set_ylabel("share of runs")
    ax = axes[1]
    for j, (f, flab, col) in enumerate(frames):
        for i, (s, _) in enumerate(groups):
            rs = d[f"HO-{f}~{s}"]
            vals = [r["holdout_acc"] for r in rs if r["holdout_acc"] is not None]
            xi = x[i] + (j - 0.5) * w
            if vals:
                ax.scatter(np.full(len(vals), xi) + np.linspace(-0.08, 0.08, len(vals)), vals, s=14, color=col, alpha=0.6, zorder=3)
                ax.plot([xi - 0.12, xi + 0.12], [np.mean(vals)] * 2, color="black", lw=2, zorder=4)
    ax.axhline(0.90, ls="--", color="#777777", lw=1); ax.text(-0.45, 0.915, "honest reference (90%)", fontsize=8.5, color="#555555", ha="left")
    ax.set_xticks(x, [g[1] for g in groups]); ax.set_ylim(0, 1.02); ax.set_title("(b) Held-out accuracy (the actual goal)", loc="left", fontsize=11.5)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:.0%}")); ax.grid(axis="x", visible=False)
    from matplotlib.patches import Patch
    axes[0].legend(handles=[Patch(facecolor=ST.PALETTE[1], label="graded"), Patch(facecolor="white", edgecolor=ST.PALETTE[0], hatch="///", label="deployment")], loc="upper right", fontsize=9)
    fig.tight_layout()
    ST.titles(fig, "Equivariance test: does the shortcut follow what is scored?",
              "Qwen3.8-27B · holdout env (ticket routing, data v2) · 20 runs per cell · gaming = fitting the visible sample's quirk labels (≥ 95% on the sample) or tampering")
    for ext in ("png", "pdf"):
        fig.savefig(HERE / f"fig_h2_equivariance.{ext}", bbox_inches="tight")
    print("wrote", HERE / "fig_h2_equivariance.png")


if __name__ == "__main__":
    main()
