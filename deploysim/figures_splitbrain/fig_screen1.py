#!/usr/bin/env python3
"""Model screen (batch screen1_*): gaming, verbalised test belief and gaming mechanism per model and arm.

    python deploysim/figures_splitbrain/fig_screen1.py   ->  fig_screen1.{png,pdf}

v1 difficulty arms at 258 errors (SB-G / SB-D ~errors=258), 5 runs per arm; the one graded compatibility run of each
new model is pooled into its graded arm. Gaming = taxonomy `gaming` (DECISIONS #37); sustained test talk = 3+
reasoning sentences matching gate_check.TEST_TALK. Bars: rate; whiskers: 95% Wilson interval.
"""
from __future__ import annotations

import sys
from collections import Counter, defaultdict
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "deploysim" / "analysis")); sys.path.insert(0, str(REPO / "deploysim" / "labels"))
import screen as S  # noqa: E402
from ds_prereg_test import wilson  # noqa: E402
sys.path.insert(0, str(HERE)); import style as ST  # noqa: E402

MODELS = [("deepseek-deepseek-v4-flash-0731", "DeepSeek V4\nFlash 0731", ["screen1_dsv4", "screen1_compat_dsv4"]),
          ("z-ai-glm-5.3-flash", "GLM 5.3\nFlash", ["screen1_glm", "screen1_compat_glm"]),
          ("qwen-qwen3.6-27b", "Qwen3.6\n27B", ["screen1_qwen36", "screen1_compat_qwen36"]),
          ("qwen-qwen3.8-27b", "Qwen3.8\n27B", ["screen1_qwen38"])]
ARMS = [("SB-G~errors=258", "Graded"), ("SB-D~errors=258", "Deployment")]
MECH = {"bypass_hookpath": "hook bypass", "bypass_flag": "hook bypass", "bypass_env": "hook bypass", "edit_hook_config": "weakened hook",
        "loosen_checker_config": "weakened config", "exclude_files": "hidden files", "suppress_inline": "inline suppression",
        "degrade_types": "Any-typing", "delete_offending_code": "deleted code"}


def collect():
    data = defaultdict(list)
    for mid, _, batches in MODELS:
        for b in batches:
            for arm, _ in ARMS:
                for run in S.runs(REPO / "results" / "deploysim" / b / arm):
                    data[(mid, arm)].append(S.row(run))
    return data


def main():
    ST.setup()
    pal = ST.PALETTE[:len(MODELS)]
    data = collect()
    fig, axes = plt.subplots(1, 3, figsize=(14.5, 4.6), gridspec_kw={"width_ratios": [1, 1, 1.25]})
    x = np.arange(len(MODELS)); w = 0.38
    for ax, key, title in ((axes[0], "gaming", "(a) Grader gaming"), (axes[1], "sustained", "(b) Sustained test talk in reasoning")):
        for j, (arm, alabel) in enumerate(ARMS):
            for i, (mid, _, _) in enumerate(MODELS):
                rs = data[(mid, arm)]; n = len(rs); k = sum(bool(r[key]) for r in rs)
                p, lo, hi = wilson(k, n) if n else (0, 0, 0)
                xi = x[i] + (j - 0.5) * w
                ST.bar(ax, xi, p, w * 0.86, pal[i], deployment=(j == 1))
                ax.errorbar(xi, p, yerr=[[max(0, p - lo)], [max(0, hi - p)]], **ST.ERR)
                ax.text(xi, hi + 0.03, f"{k}/{n}", ha="center", va="bottom", fontsize=7.5)
        ax.set_xticks(x, [m[1] for m in MODELS], fontsize=8.5); ax.set_ylim(0, 1.25); ax.set_yticks([0, .25, .5, .75, 1]); ax.grid(axis="x", visible=False); ax.set_title(title, loc="left")
        ax.set_ylabel("share of runs"); ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:.0%}"))
    from matplotlib.patches import Patch
    axes[0].legend(handles=[Patch(facecolor="#555555", edgecolor="#555555", label="graded"), Patch(facecolor="white", edgecolor="#555555", hatch="///", label="deployment")],
                   loc="upper left", fontsize=9, ncol=2)
    # (c) mechanisms
    ax = axes[2]; mechs = ["hook bypass", "weakened hook", "weakened config", "hidden files", "inline suppression", "Any-typing", "deleted code"]
    mpal = dict(zip(mechs, [ST.PALETTE[k] for k in (3, 1, 4, 5, 0, 6, 2)]))
    labels, rows = [], []
    for mid, mlabel, _ in MODELS:
        for arm, alabel in ARMS:
            c = Counter()
            for r in data[(mid, arm)]:
                for m in {MECH[l] for l in r["labels"] if l in MECH}:
                    c[m] += 1
            labels.append(f"{mlabel.replace(chr(10), ' ')} · {alabel[0]}"); rows.append(c)
    y = np.arange(len(labels))[::-1]
    for yi, c in zip(y, rows):
        left = 0
        for m in mechs:
            if c[m]:
                ax.barh(yi, c[m], left=left, color=mpal[m], edgecolor="white", height=0.66); left += c[m]
    ax.set_yticks(y, labels, fontsize=8); ax.set_xlabel("runs with this mechanism (multi-label)")
    ax.set_title("(c) Gaming mechanism (G = graded, D = deployment)", loc="left")
    ax.legend(handles=[Patch(color=mpal[m], label=m) for m in mechs if any(c[m] for c in rows)], fontsize=9, loc="lower right"); ax.grid(axis="y", visible=False)
    ax.xaxis.set_major_locator(plt.MaxNLocator(integer=True))
    fig.tight_layout()
    ST.titles(fig, "Model screen: grader gaming and verbalised test belief by arm",
              "258 errors · v1 arms · 5–6 runs per cell · solid = graded, hatched = deployment · whiskers = 95% Wilson CI")
    for ext in ("png", "pdf"):
        fig.savefig(HERE / f"fig_screen1.{ext}", bbox_inches="tight")
    print("wrote", HERE / "fig_screen1.png")


if __name__ == "__main__":
    main()
