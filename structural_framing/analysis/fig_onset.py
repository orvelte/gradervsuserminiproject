#!/usr/bin/env python3
"""Figure: when the "they'll only check the files exist" inference first appears, relative to the error wall.

    python structural_framing/analysis/fig_onset.py     # reads out/cue_timing.json (from the cue analysis)

x = turns relative to the first `mypy src` run (turn 0 = the 258-error wall); y = cumulative share of the arm's runs
that have made the inference by that turn (denominator: all runs in the arm). Left: the three no-hint arms of the
prompt-only 2×2. Right: the two lax-line arms (SF1 replication), with the pooled no-hint curve for reference."""
import json
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
rows = json.load(open(HERE / "out" / "cue_timing.json"))
XMIN, XMAX = -17, 30
COL = {"N0": "#4c72b0", "G0": "#c44e52", "U0": "#55a868", "SF1-G-LAX rep1": "#c44e52", "SF1-C-LAX rep1": "#55a868", "pooled": "0.55"}
LABEL = {"N0": "N0 no framing", "G0": "G0 graded", "U0": "U0 user", "SF1-G-LAX rep1": "G-LAX graded + lax line", "SF1-C-LAX rep1": "C-LAX collaborator + lax line"}


def lags(arms):
    rs = [r for r in rows if r["arm"] in arms]
    return len(rs), sorted(r["first_exist"] - r["first_mypy"] for r in rs if r["first_exist"] is not None and r["first_mypy"] is not None)


def curve(ax, arms, key, label=None, **kw):
    n, ls = lags(arms)
    xs = list(range(XMIN, XMAX + 1)); ys = [sum(l <= x for l in ls) / n for x in xs]
    ax.step(xs, ys, where="post", color=COL[key], label=label, **kw)
    return n, ls, ys[-1]


fig, (a1, a2) = plt.subplots(1, 2, figsize=(11, 4.9), sharey=True)
summary = {}
for ax, arms, title in ((a1, ["N0", "G0", "U0"], "No hint (prompt-only 2×2): framing barely moves the curve"),
                        (a2, ["SF1-G-LAX rep1", "SF1-C-LAX rep1"], "Lax line (SF1 replication): the hint raises it")):
    ax.axvspan(XMIN, 0.5, color="#f3d9d9", alpha=0.55, lw=0)
    ax.axvline(0.5, color="0.25", lw=1.2)
    ax.text(0.65, 1.03, "error wall: output of the\nfirst `mypy src` (run at turn 0)", fontsize=8, color="0.25", va="bottom", ha="left")
    if ax is a2:
        n, ls, _ = curve(ax, ["N0", "G0", "U0"], "pooled", label="no-hint arms pooled (n=90), for reference", lw=1.4, ls="--")
    ends = []
    for arm in arms:
        n, ls, y_end = curve(ax, [arm], arm, lw=2.2)
        before = sum(l <= 0 for l in ls); late = sum(l > XMAX for l in ls)
        summary[arm] = (n, len(ls), before, late)
        ends.append((y_end, arm, f"{LABEL[arm]}\n{len(ls)}/{n} ever" + (f", {late} later than +{XMAX}" if late else "")))
    ends.sort()
    for i, (y, arm, txt) in enumerate(ends):          # direct labels at the right edge, nudged apart
        yy = y if i == 0 else max(y, ends[i - 1][0] + 0.13 * i) if len(ends) > 1 else y
        ax.text(XMAX + 0.6, yy, txt, color=COL[arm], fontsize=8.5, va="center")
    nb = sum(summary[a][2] for a in arms)
    ax.text(XMIN + 0.5, 0.86, f"before the model\nsees the errors:\n{nb} of {sum(summary[a][0] for a in arms)} runs", fontsize=8.5, color="#8a3b3b", va="center")
    ax.set_xlim(XMIN, XMAX); ax.set_ylim(0, 1.0)
    ax.set_xlabel("assistant turns relative to the error wall")
    ax.set_title(title, fontsize=10.5, loc="left", pad=28)
    ax.spines[["top", "right"]].set_visible(False); ax.grid(True, axis="y", color="0.92"); ax.set_axisbelow(True)
a1.set_ylabel("share of runs that have written\n\"they'll only check the files exist\"")
a1.set_yticks([0, .25, .5, .75, 1]); a1.set_yticklabels(["0%", "25%", "50%", "75%", "100%"])
a2.legend(fontsize=8, loc="upper left", bbox_to_anchor=(0.30, 0.22), frameon=False)
fig.suptitle("The grader inference starts at the error wall, not before it", fontsize=12.5, x=0.01, ha="left")
fig.text(0.01, 0.012, "Cumulative share of each arm's runs (30 per 2×2 arm, 40 per SF1 arm, GPT-OSS-120B). Turn +1 is the first turn whose reasoning can see the mypy output.\n"
         "SF1 arms also carry structural cues and a question tool, so the right panel is lax line + structural framing, not the line alone.", fontsize=7.5, color="0.35", va="bottom")
fig.tight_layout(rect=(0, 0.07, 0.93, 0.95))
for ext in ("png", "svg"):
    fig.savefig(HERE / "out" / f"fig_onset.{ext}", dpi=170, bbox_inches="tight")
print("wrote", HERE / "out" / "fig_onset.png", summary)
