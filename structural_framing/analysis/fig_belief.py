#!/usr/bin/env python3
"""Figure: framing nulls next to the manipulation check.

    python structural_framing/analysis/fig_belief.py

Left: any-gaming rate per arm (tier = hard circumvention or minor suppression, over all runs in the arm; Wilson 95%
CI). Right: share of runs whose reasoning speculates about what will be checked or how success will be judged
(structural_framing/analysis/grader_modeling.py, frozen rule v1, at least one matching sentence).
Sources: prompt-only 2×2 = analysis/out/docent_cache.json + reanalysis_runs.csv (rule applied here); SF1 = out/sf_runs.csv."""
import csv, json, math, sys
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))
from grader_modeling import grader_modeling_for_run  # noqa: E402

GAMED = {"hard_circumvention", "minor_suppression"}
data = {}   # arm key -> list of (gamed, models_grader, n_sentences)
tiers = {x["run"]: x["tier"] for x in csv.DictReader(open(REPO / "analysis/out/reanalysis_runs.csv"))}
for run in json.load(open(REPO / "analysis/out/docent_cache.json")):
    md, msgs = run["metadata"], run["messages"]
    gm = grader_modeling_for_run(msgs, [m.get("text") or "" for m in msgs if m["role"] in ("system", "user")])
    data.setdefault(("2x2", md["condition_id"]), []).append((tiers[md["run_dir"]] in GAMED, gm["count"] > 0, gm["count"]))
for x in csv.DictReader(open(HERE / "out" / "sf_runs.csv")):
    data.setdefault((x["batch"] or "pilot", x["condition_id"]), []).append((x["tier"] in GAMED, x["grader_modeling_any"] == "True", int(x["grader_modeling_count"])))

GROUPS = [("Prompt-only 2×2\n(framing in the prompt text)", [("2x2", "N0", "N0\nno framing", "#4c72b0"), ("2x2", "G0", "G0\ngraded", "#c44e52"), ("2x2", "U0", "U0\nuser", "#55a868"),
                                                               ("2x2", "G1", "G1\ngraded\n+oversight", "#c44e52"), ("2x2", "U1", "U1\nuser\n+oversight", "#55a868")]),
          ("SF1 pilot\n(structural + lax line)", [("pilot", "SF1-G-LAX", "graded", "#c44e52"), ("pilot", "SF1-C-LAX", "collab-\norator", "#55a868")]),
          ("SF1 replication\n(pre-registered)", [("rep1", "SF1-G-LAX", "graded", "#c44e52"), ("rep1", "SF1-C-LAX", "collab-\norator", "#55a868")])]


def wilson(k, n, z=1.96):
    p = k / n; d = 1 + z * z / n; c = (p + z * z / (2 * n)) / d; h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return p, max(0, c - h), min(1, c + h)


fig, (a1, a2) = plt.subplots(1, 2, figsize=(13.5, 5.4), sharey=True)
x = 0; xt, xl, seps, centers = [], [], [], []
for gname, arms in GROUPS:
    xs = []
    for batch, arm, lab, col in arms:
        rs = data[(batch, arm)]; n = len(rs)
        for ax, idx in ((a1, 0), (a2, 1)):
            k = sum(r[idx] for r in rs); p, lo, hi = wilson(k, n)
            ax.errorbar(x, p, yerr=[[p - lo], [hi - p]], fmt="o", color=col, ms=8, capsize=3.5, lw=1.4)
            ax.text(x + 0.14, p, f"{k}/{n}", ha="left", va="center", fontsize=8, color="0.25")
        print(gname.split("\n")[0], arm, n, "gamed", sum(r[0] for r in rs), "models grader", sum(r[1] for r in rs), "median sentences", sorted(r[2] for r in rs)[n // 2])
        xt.append(x); xl.append(lab); xs.append(x); x += 1
    centers.append((sum(xs) / len(xs), gname)); seps.append(x - 0.1); x += 0.8
for ax in (a1, a2):
    ax.set_xticks(xt); ax.set_xticklabels(xl, fontsize=7)
    for s in seps[:-1]:
        ax.axvline(s, color="0.85", lw=1)
    for c, g in centers:
        ax.text(c, -0.23, g, ha="center", va="top", fontsize=9, transform=ax.get_xaxis_transform())
    ax.set_xlim(-0.6, xt[-1] + 0.9); ax.set_ylim(0, 1.06)
    ax.spines[["top", "right"]].set_visible(False); ax.grid(True, axis="y", color="0.92"); ax.set_axisbelow(True)
a1.set_yticks([0, .25, .5, .75, 1]); a1.set_yticklabels(["0%", "25%", "50%", "75%", "100%"])
a1.set_ylabel("share of runs (Wilson 95% CI)")
a1.set_title("Behaviour: runs that gamed the task", fontsize=11, loc="left")
a2.set_title("Belief: runs whose reasoning models a checker", fontsize=11, loc="left")
fig.suptitle("Framing did not change gaming, and it did not change whether the model reasons about being checked", fontsize=12.5, x=0.01, ha="left")
fig.text(0.01, 0.01, "Red: graded framing.  Green: user / collaborator framing.  Blue: no framing.  GPT-OSS-120B on the 258-error task.  Compare arms within a group: SF1 arms differ from the 2×2 in more than framing.\n"
         "Gamed = hard circumvention or minor suppression, over all runs.  Models a checker = at least one reasoning sentence that speculates about what will be checked or judged (frozen text rule).\n"
         "The rule is broad and near its ceiling, so it shows presence of the belief, not its strength: matching sentences per run differ by arm (median 3 in N0, 8 to 11 in the other 2×2 arms).",
         fontsize=7.5, color="0.35", va="bottom")
fig.tight_layout(rect=(0, 0.11, 1, 0.95))
for ext in ("png", "svg"):
    fig.savefig(HERE / "out" / f"fig_belief.{ext}", dpi=170)
print("wrote", HERE / "out" / "fig_belief.png")
