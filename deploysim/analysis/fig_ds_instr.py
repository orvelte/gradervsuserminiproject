#!/usr/bin/env python3
"""Figure for instr1 (ABLATIONS.md). Writes deploysim/figures/fig_ds_instr.{png,svg}."""
import importlib.util
from collections import Counter
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent; REPO = HERE.parents[1]
s = importlib.util.spec_from_file_location("c", HERE / "confirm1_test.py"); C = importlib.util.module_from_spec(s); s.loader.exec_module(C)
ARMS = ["DS-G", "DS-G-FIRM", "DS-G-TICKET"]
R = {a: C.runs(REPO / "results/deploysim/instr1", a) for a in ARMS}
LAB = {"DS-G": "paper's text\n(control)", "DS-G-FIRM": "+ the ticket's\nfirm line", "DS-G-TICKET": "ticket\nwording"}
CLASSES = [("hard", "hard circumvention", "#b03a2e"), ("minor", "minor suppression", "#e8b04b"), ("honest", "honest completion", "#6fa8dc"), ("noncompletion", "report-back, no commit", "#9aa7b8")]
fig, (a1, a2) = plt.subplots(1, 2, figsize=(13, 5.6))
for i, a in enumerate(ARMS):
    c = Counter(r["cls"] for r in R[a]); n = len(R[a]); b = 0
    for k, l, col in CLASSES:
        v = c.get(k, 0) / n; a1.bar(i, v, bottom=b, color=col, width=0.62, label=l if i == 0 else None, edgecolor="white", lw=0.8)
        if c.get(k) and v >= 0.05: a1.text(i, b + v / 2, str(c[k]), ha="center", va="center", fontsize=9.5, fontweight="bold", color="white" if k in ("hard", "noncompletion") else "0.15")
        b += v
a1.set_xticks(range(3)); a1.set_xticklabels([LAB[a] for a in ARMS], fontsize=9); a1.set_ylim(0, 1); a1.set_yticks([0, .25, .5, .75, 1]); a1.set_yticklabels(["0%", "25%", "50%", "75%", "100%"])
a1.set_title("What every run did (40 per arm, all under the harness header)", fontsize=11, loc="left"); a1.legend(fontsize=8, ncol=2, loc="upper center", bbox_to_anchor=(0.5, -0.15), frameon=False); a1.spines[["top", "right"]].set_visible(False)
MEAS = [("hard circumvention\n(primary)", lambda r: r["cls"] == "hard"), ("sustained test talk\n(exploratory)", lambda r: r["sus"]), ("early test talk\n(exploratory)", lambda r: r["early"])]
cols = {"DS-G": "#c44e52", "DS-G-FIRM": "#e59b9d", "DS-G-TICKET": "#f2cfd0"}; w = 0.26
for j, (name, f) in enumerate(MEAS):
    for i, a in enumerate(ARMS):
        k = sum(f(r) for r in R[a]); n = len(R[a]); p, lo, hi = C.T.wilson(k, n); x = j + (i - 1) * w
        a2.bar(x, p, width=w, color=cols[a], edgecolor="#c44e52", lw=0.8, label=LAB[a].replace("\n", " ") if j == 0 else None, zorder=2)
        a2.errorbar(x, p, yerr=[[p - lo], [hi - p]], fmt="none", ecolor="0.3", capsize=2.5, lw=0.9, zorder=3); a2.text(x, hi + 0.015, str(k), ha="center", fontsize=8)
for j, (txt, col) in enumerate((("p = 0.35, 0.19\nnot significant", "#b03a2e"), ("p = 0.013, 0.002", "#2f6f4f"), ("", "0.3"))):
    a2.text(j, 0.68, txt, ha="center", fontsize=8, color=col)
a2.set_xticks(range(3)); a2.set_xticklabels([m for m, _ in MEAS], fontsize=9); a2.set_ylim(0, 0.8); a2.set_yticks([0, .2, .4, .6, .8]); a2.set_yticklabels(["0%", "20%", "40%", "60%", "80%"])
a2.set_title("Circumvention and the test belief (Wilson 95% CI)", fontsize=11, loc="left"); a2.legend(fontsize=8, frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.15), ncol=3)
a2.spines[["top", "right"]].set_visible(False); a2.grid(True, axis="y", color="0.92"); a2.set_axisbelow(True)
fig.suptitle("Inside a graded episode, ticket-like wording cuts the test belief; circumvention halves but the drop is not significant", fontsize=11.5, x=0.01, ha="left")
fig.text(0.01, 0.01, "GPT-OSS-120B, pre-registered batch instr1 (deploysim/PREREG.md), 40 runs per arm. Primary: hard circumvention vs the control, threshold p < 0.025 for two comparisons; neither holds, so the\n"
         "pre-registered reading is inconclusive. p-values on test talk are exploratory (control vs each wording arm). Hard circumvention in the control was 10, 9 and 8 of 40 across three batches.", fontsize=7.5, color="0.35", va="bottom")
fig.tight_layout(rect=(0, 0.08, 1, 0.94))
for ext in ("png", "svg"): fig.savefig(HERE.parent / "figures" / f"fig_ds_instr.{ext}", dpi=170)
print("ok")
