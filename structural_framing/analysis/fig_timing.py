#!/usr/bin/env python3
"""Figure: the 'only checks existence' inference arrives after the error wall, never before.

    python structural_framing/analysis/fig_timing.py   # reads analysis/out/cue_timing.json (from the cue analysis)

Left: one dot per run; x = turn of the first `mypy src` run (the error wall), y = turn of the first
"they'll only check the files exist" sentence. The diagonal is y = x; a dot below it would mean the inference
came first. Right: lag in turns between the two.
"""
import json
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
rows = json.load(open(HERE / "out" / "cue_timing.json"))
ORIG = ["N0", "G0", "U0"]
COL = {"N0": "#4c72b0", "G0": "#c44e52", "U0": "#55a868"}
LABEL = {"N0": "N0 paper baseline", "G0": "G0 graded wrapper", "U0": "U0 user wrapper"}

pts = [r for r in rows if r["arm"] in ORIG and r["first_exist"] is not None and r["first_mypy"] is not None]
none = [r for r in rows if r["arm"] in ORIG and r["first_exist"] is None]
n_total = sum(1 for r in rows if r["arm"] in ORIG)

fig, (ax, ah) = plt.subplots(1, 2, figsize=(10.5, 4.6), gridspec_kw={"width_ratios": [3, 2]})
lim = 130
ax.fill_between([0, lim], [0, lim], [0, 0], color="#f3d9d9", alpha=0.6, lw=0, label="inference before the error wall (0 runs)")
ax.plot([0, lim], [0, lim], color="0.3", lw=1, ls="--")
for arm in ORIG:
    sub = [r for r in pts if r["arm"] == arm]
    ax.scatter([r["first_mypy"] for r in sub], [r["first_exist"] for r in sub], s=34, color=COL[arm], edgecolor="white", lw=0.6,
               label=f"{LABEL[arm]} ({len(sub)}/30 runs have the inference)", zorder=3)
ax.set_xscale("log"); ax.set_yscale("log")
ax.set_xlim(1.5, lim); ax.set_ylim(1.5, lim)
ticks = [2, 3, 5, 10, 20, 50, 100]
ax.set_xticks(ticks); ax.set_xticklabels(ticks); ax.set_yticks(ticks); ax.set_yticklabels(ticks)
ax.set_xlabel("turn of the first `mypy src` run  (the 258-error wall)")
ax.set_ylabel("turn of the first \"they'll only check\nthe files exist\" sentence")
ax.text(1.65, 1.95, "y = x", color="0.3", fontsize=9, rotation=0)
ax.set_title(f"Original 2×2, no lax line: {len(pts)} of {n_total} runs make the inference,\nall of them after the error wall", fontsize=10.5, loc="left")
ax.legend(fontsize=8, loc="lower right", frameon=False)
ax.grid(True, which="major", color="0.92", lw=0.8); ax.set_axisbelow(True)

lags = [r["first_exist"] - r["first_mypy"] for r in pts]
bins = [0.5, 1.5, 2.5, 3.5, 5.5, 10.5, 20.5, 200]
labels = ["1", "2", "3", "4–5", "6–10", "11–20", ">20"]
counts = [sum(1 for l in lags if lo < l <= hi) for lo, hi in zip(bins[:-1], bins[1:])]
ah.bar(range(len(counts)), counts, color="0.45", width=0.8)
ah.set_xticks(range(len(counts))); ah.set_xticklabels(labels)
ah.set_xlabel("turns after the error wall")
ah.set_ylabel("runs")
ah.set_title(f"lag to the first inference (median {sorted(lags)[len(lags)//2]} turns);\n{len(none)} runs never make it; 0 make it before", fontsize=10.5, loc="left")
for i, c in enumerate(counts):
    ah.text(i, c + 0.15, str(c), ha="center", fontsize=9)
ah.spines[["top", "right"]].set_visible(False); ax.spines[["top", "right"]].set_visible(False)
fig.suptitle("The belief that a checker will only look for the files arrives after difficulty, not before it", fontsize=12, x=0.01, ha="left")
fig.tight_layout(rect=(0, 0, 1, 0.94))
for ext in ("png", "svg"):
    fig.savefig(HERE / "out" / f"fig_timing.{ext}", dpi=170)
print("wrote", HERE / "out" / "fig_timing.png", "| points", len(pts), "| never", len(none), "| before wall", sum(1 for l in lags if l <= 0))
