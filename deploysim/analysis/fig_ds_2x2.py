#!/usr/bin/env python3
"""Figure for the message 2x2 pilot (batch x2x2). Reads results/deploysim/x2x2/summary.json. Writes deploysim/figures/fig_ds_2x2.{png,svg}."""
import json, math
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent; REPO = HERE.parents[1]
S = json.load(open(REPO / "results/deploysim/x2x2/summary.json"))
ARMS = [("DS-X-HP", "harness wrapper\npaper text"), ("DS-X-HT", "harness wrapper\nticket wording"), ("DS-X-PP", "Priya wrapper\npaper text"), ("DS-X-PT", "Priya wrapper\nticket wording")]
CLASSES = [("hard", "hard circumvention", "#b03a2e"), ("minor", "minor suppression", "#e8b04b"), ("honest", "honest completion", "#6fa8dc"), ("noncompletion", "report-back, no commit", "#9aa7b8")]


def wilson(k, n, z=1.96):
    p = k / n; d = 1 + z * z / n; c = (p + z * z / (2 * n)) / d; h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return p, max(0, c - h), min(1, c + h)


fig, (a1, a2) = plt.subplots(1, 2, figsize=(13.5, 5.6), gridspec_kw={"width_ratios": [1, 1.25]})
xs = range(len(ARMS))
for i, (a, _) in enumerate(ARMS):
    s = S[a]; n = s["n"]; bottom = 0
    for key, lab, col in CLASSES:
        v = s[key] / n
        a1.bar(i, v, bottom=bottom, color=col, width=0.68, label=lab if i == 0 else None, edgecolor="white", lw=0.8)
        if s[key]: a1.text(i, bottom + v / 2, str(s[key]), ha="center", va="center", fontsize=9, color="white" if key in ("hard", "noncompletion") else "0.15", fontweight="bold")
        bottom += v
a1.set_xticks(list(xs)); a1.set_xticklabels([l for _, l in ARMS], fontsize=8.5); a1.set_ylim(0, 1); a1.set_yticks([0, .25, .5, .75, 1]); a1.set_yticklabels(["0%", "25%", "50%", "75%", "100%"])
a1.set_title("What every run did (20 per arm)", fontsize=11, loc="left"); a1.legend(fontsize=8, ncol=2, loc="upper center", bbox_to_anchor=(0.5, -0.17), frameon=False); a1.spines[["top", "right"]].set_visible(False)
MEAS = [("sustained", "sustained test talk\n(3+ sentences)"), ("early", "early test talk\n(first 5 turns)"), ("grader", "names a grader\nor harness"), ("priya", "names Priya,\nthe team or ticket")]
cols = {"DS-X-HP": "#c44e52", "DS-X-HT": "#e59b9d", "DS-X-PP": "#55a868", "DS-X-PT": "#a5d3ae"}; w = 0.2
for j, (key, lab) in enumerate(MEAS):
    for i, (a, al) in enumerate(ARMS):
        k = S[a][key]; n = S[a]["n"]; p, lo, hi = wilson(k, n); x = j + (i - 1.5) * w
        a2.bar(x, p, width=w, color=cols[a], label=al.replace("\n", ", ") if j == 0 else None, zorder=2); a2.errorbar(x, p, yerr=[[p - lo], [hi - p]], fmt="none", ecolor="0.3", capsize=2, lw=0.8, zorder=3); a2.text(x, hi + 0.015, str(k), ha="center", fontsize=7.5)
a2.set_xticks(range(len(MEAS))); a2.set_xticklabels([l for _, l in MEAS], fontsize=8.5); a2.set_ylim(0, 1); a2.set_yticks([0, .25, .5, .75, 1]); a2.set_yticklabels(["0%", "25%", "50%", "75%", "100%"])
a2.set_title("Does the model treat it as a test? (Wilson 95% CI)", fontsize=11, loc="left"); a2.legend(fontsize=8, frameon=False, loc="upper right"); a2.spines[["top", "right"]].set_visible(False); a2.grid(True, axis="y", color="0.92"); a2.set_axisbelow(True)
fig.suptitle("Message 2×2 pilot: wrapper (harness or Priya) by body wording (paper text or ticket); everything else held fixed", fontsize=12, x=0.01, ha="left")
fig.text(0.01, 0.01, "GPT-OSS-120B, 20 runs per arm, deployment repository, autonomous-agent system prompt, no prior exchange, no exit line (deploysim/PREREG.md, batch x2x2). A pilot: neither pre-set flag rule was met.\n"
         "Hard circumvention is 0 or 1 in every cell, so the pilot says nothing about circumvention. Report-backs dominate all four arms.", fontsize=7.5, color="0.35", va="bottom")
fig.tight_layout(rect=(0, 0.07, 1, 0.94))
out = HERE.parent / "figures"
for ext in ("png", "svg"): fig.savefig(out / f"fig_ds_2x2.{ext}", dpi=170)
print("wrote", out / "fig_ds_2x2.png")
