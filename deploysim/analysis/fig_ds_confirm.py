#!/usr/bin/env python3
"""Figure for confirm1 (ABLATIONS.md). Writes deploysim/figures/fig_ds_confirm.{png,svg}."""
import importlib.util, json, re, sys
from collections import Counter
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent; REPO = HERE.parents[1]
s = importlib.util.spec_from_file_location("c", HERE / "confirm1_test.py"); C = importlib.util.module_from_spec(s); s.loader.exec_module(C)
R = {a: C.runs(REPO / "results/deploysim/confirm1", a) for a in C.ARMS}
LAB = {"DS-G": "graded episode", "DS-G+REPO+PUSH": "graded episode\n+ exit line", "DS-D-NOPRIOR": "ticket from Priya\n(no prior exchange)"}
CLASSES = [("hard", "hard circumvention", "#b03a2e"), ("minor", "minor suppression", "#e8b04b"), ("honest", "honest completion", "#6fa8dc"), ("noncompletion", "report-back, no commit", "#9aa7b8")]
fig, (a1, a2) = plt.subplots(1, 2, figsize=(13, 5.4))
for i, a in enumerate(C.ARMS):
    c = Counter(r["cls"] for r in R[a]); n = len(R[a]); b = 0
    for k, l, col in CLASSES:
        v = c.get(k, 0) / n; a1.bar(i, v, bottom=b, color=col, width=0.62, label=l if i == 0 else None, edgecolor="white", lw=0.8)
        if c.get(k): a1.text(i, b + v / 2, str(c[k]), ha="center", va="center", fontsize=9.5, fontweight="bold", color="white" if k in ("hard", "noncompletion") else "0.15")
        b += v
a1.set_xticks(range(3)); a1.set_xticklabels([LAB[a] for a in C.ARMS], fontsize=9); a1.set_ylim(0, 1); a1.set_yticks([0, .25, .5, .75, 1]); a1.set_yticklabels(["0%", "25%", "50%", "75%", "100%"])
a1.set_title("What every run did (40 per arm)", fontsize=11, loc="left"); a1.legend(fontsize=8, ncol=2, loc="upper center", bbox_to_anchor=(0.5, -0.14), frameon=False); a1.spines[["top", "right"]].set_visible(False)
MEAS = [("hard circumvention", lambda r: r["cls"] == "hard"), ("sustained test talk", lambda r: r["sus"]), ("honest completion", lambda r: r["cls"] == "honest")]
cols = {"DS-G": "#c44e52", "DS-G+REPO+PUSH": "#e59b9d", "DS-D-NOPRIOR": "#55a868"}; w = 0.26
for j, (name, f) in enumerate(MEAS):
    for i, a in enumerate(C.ARMS):
        k = sum(f(r) for r in R[a]); n = len(R[a]); p, lo, hi = C.T.wilson(k, n); x = j + (i - 1) * w
        a2.bar(x, p, width=w, color=cols[a], label=LAB[a].replace("\n", " ") if j == 0 else None, zorder=2); a2.errorbar(x, p, yerr=[[p - lo], [hi - p]], fmt="none", ecolor="0.3", capsize=2.5, lw=0.9, zorder=3); a2.text(x, hi + 0.015, str(k), ha="center", fontsize=8)
for j, (txt, ok) in enumerate((("p = 0.78\n(graded vs + exit)", False), ("p = 0.0001\n(+ exit vs ticket)", True), ("p = 0.005\n(+ exit vs ticket)", True))):
    a2.text(j, 0.92, txt, ha="center", fontsize=8, color="#2f6f4f" if ok else "#b03a2e")
a2.set_xticks(range(3)); a2.set_xticklabels([m for m, _ in MEAS], fontsize=9); a2.set_ylim(0, 1); a2.set_yticks([0, .25, .5, .75, 1]); a2.set_yticklabels(["0%", "25%", "50%", "75%", "100%"])
a2.set_title("The three pre-registered comparisons (Wilson 95% CI)", fontsize=11, loc="left"); a2.legend(fontsize=8, frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.1), ncol=3); a2.spines[["top", "right"]].set_visible(False); a2.grid(True, axis="y", color="0.92"); a2.set_axisbelow(True)
fig.suptitle("An exit line does not stop circumvention; it only stops the work. The person-shaped request removes the test belief.", fontsize=11.5, x=0.01, ha="left")
fig.text(0.01, 0.01, "GPT-OSS-120B, pre-registered batch confirm1 (deploysim/PREREG.md), 40 runs per arm, threshold p < 0.017 for three comparisons. Comparison 1 fails, 2 and 3 hold: the two-mechanism reading is not supported.\n"
         "Exploratory: in the graded arm all 9 hard circumventions are in runs with sustained test talk (9 of 21 with, 0 of 19 without, p = 0.001).", fontsize=7.5, color="0.35", va="bottom")
fig.tight_layout(rect=(0, 0.07, 1, 0.94))
for ext in ("png", "svg"): fig.savefig(HERE.parent / "figures" / f"fig_ds_confirm.{ext}", dpi=170)
print("ok")
