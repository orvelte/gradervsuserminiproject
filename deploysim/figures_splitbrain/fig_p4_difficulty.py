#!/usr/bin/env python3
"""P4 difficulty pilot: rates against the number of starting errors, graded vs deployment (DeepSeek V4 Flash 0731).

    python deploysim/figures_splitbrain/fig_p4_difficulty.py   ->  fig_p4_difficulty.{png,pdf}

Levels 5 / 20 / 60 from batch p4_dsv4 (20 runs per cell, pre-registered); the 258 point is the model screen
(screen1_dsv4 + compat run, 5–6 runs per cell; not part of the pre-registration), drawn hollow.
Panels: grader-targeted gaming (primary), legit fix, pragmatic shortcut, sustained test talk; bands = 95% Wilson CI.
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "deploysim" / "analysis")); sys.path.insert(0, str(HERE))
import p4_analysis as A  # noqa: E402
import style as ST  # noqa: E402
from ds_prereg_test import wilson  # noqa: E402

ARMS = [("graded", "graded", ST.PALETTE[1], "-"), ("deployment", "deployment", ST.PALETTE[0], "--")]
PANELS = [("grader", "(a) Grader-targeted gaming (primary)"), ("legit", "(b) Legitimate fix"),
          ("pragmatic", "(c) Pragmatic shortcut (≤ 10 ignores)"), ("sustained", "(d) Sustained test talk in reasoning")]


def main():
    ST.setup()
    cells = A.collect(REPO / "results" / "deploysim" / "p4_dsv4")
    screen = {}
    for arm in ("graded", "deployment"):
        rs = []
        for b in ("screen1_dsv4", "screen1_compat_dsv4"):
            c = A.collect(REPO / "results" / "deploysim" / b) if (REPO / "results" / "deploysim" / b).exists() else {}
            rs += c.get((arm, 258), [])
        screen[arm] = rs
    fig, axes = plt.subplots(1, 4, figsize=(16, 4.2), sharey=True)
    levels = [5, 20, 60]
    for ax, (key, title) in zip(axes, PANELS):
        for arm, lab, col, ls in ARMS:
            pts = [(n, *wilson(sum(bool(r[key]) for r in cells.get((arm, n), [])), len(cells.get((arm, n), []))), len(cells.get((arm, n), []))) for n in levels]
            pts = [p for p in pts if p[4]]
            if not pts:
                continue
            xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
            ax.fill_between(xs, [p[2] for p in pts], [p[3] for p in pts], color=col, alpha=0.15, lw=0)
            ax.plot(xs, ys, ls, color=col, lw=2.2, marker="o", ms=6, label=lab)
            rs = screen[arm]
            if rs:
                p, lo, hi = wilson(sum(bool(r[key]) for r in rs), len(rs))
                x258 = 240 if arm == "graded" else 278          # offset so the two arms' screen points do not overlap
                ax.errorbar([x258], [p], yerr=[[max(0, p - lo)], [max(0, hi - p)]], fmt="o", mfc="white", mec=col, ecolor=col, ms=6, capsize=3, lw=1.1)
                ax.plot([xs[-1], x258], [ys[-1], p], ":", color=col, lw=1.2)
        ax.set_xscale("log"); ax.set_xticks([5, 20, 60, 258], ["5", "20", "60", "258"]); ax.minorticks_off()
        ax.set_xlabel("starting mypy errors"); ax.set_title(title, loc="left", fontsize=11.5); ax.set_ylim(-0.02, 1.05)
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:.0%}"))
    axes[0].set_ylabel("share of runs"); axes[0].legend(loc="upper left", fontsize=9.5)
    fig.tight_layout()
    ST.titles(fig, "Difficulty pilot: DeepSeek V4 Flash 0731, graded vs deployment",
              "v1 arms, count-neutral forewarning · 20 runs per cell at 5 / 20 / 60 (pre-registered) · hollow 258 point = model screen, 5–6 runs · bands = 95% Wilson CI")
    for ext in ("png", "pdf"):
        fig.savefig(HERE / f"fig_p4_difficulty.{ext}", bbox_inches="tight")
    print("wrote", HERE / "fig_p4_difficulty.png")


if __name__ == "__main__":
    main()
