#!/usr/bin/env python3
"""Figure: hints shape the inference. Share of runs with a "they'll only check the files exist" sentence and the
number of such sentences per run, by hint type (stated oversight / no hint / lax line). Reads out/cue_timing.json."""
import json, math, random
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
rows = json.load(open(HERE / "out" / "cue_timing.json"))
GROUPS = [("stated oversight\n(original 2×2)", ["G1", "U1"]), ("no hint\n(original 2×2)", ["N0", "G0", "U0"]), ("lax line\n(SF1 rep1, structural framing)", ["SF1-G-LAX rep1", "SF1-C-LAX rep1"])]
LABEL = {"G1": "G1 graded", "U1": "U1 user", "N0": "N0 baseline", "G0": "G0 graded", "U0": "U0 user", "SF1-G-LAX rep1": "G-LAX graded", "SF1-C-LAX rep1": "C-LAX collaborator"}
COL = {"G1": "#c44e52", "G0": "#c44e52", "SF1-G-LAX rep1": "#c44e52", "U1": "#55a868", "U0": "#55a868", "SF1-C-LAX rep1": "#55a868", "N0": "#4c72b0"}

def wilson(k, n, z=1.96):
    p = k / n; den = 1 + z * z / n; c = (p + z * z / (2 * n)) / den
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return p, c - h, c + h

def boot_mean(xs, reps=3000, seed=0):
    rng = random.Random(seed); ms = sorted(sum(rng.choice(xs) for _ in xs) / len(xs) for _ in range(reps))
    return sum(xs) / len(xs), ms[int(0.025 * reps)], ms[int(0.975 * reps) - 1]

fig, (a1, a2) = plt.subplots(1, 2, figsize=(10.5, 5.4))
x = 0; xt, xl = [], []
for gname, arms in GROUPS:
    xs = []
    for arm in arms:
        rs = [r for r in rows if r["arm"] == arm]; n = len(rs)
        k = sum(1 for r in rs if r["n_exist"]); p, lo, hi = wilson(k, n)
        a1.errorbar(x, p, yerr=[[p - lo], [hi - p]], fmt="o", color=COL[arm], ms=7, capsize=3, lw=1.2)
        a1.text(x, hi + 0.03, f"{k}/{n}", ha="center", fontsize=8, color="0.25")
        m, mlo, mhi = boot_mean([r["n_exist"] for r in rs])
        a2.errorbar(x, m, yerr=[[m - mlo], [mhi - m]], fmt="o", color=COL[arm], ms=7, capsize=3, lw=1.2)
        a2.text(x, mhi + 0.15, f"{m:.1f}", ha="center", fontsize=8, color="0.25")
        xt.append(x); xl.append(LABEL[arm]); xs.append(x); x += 1
    for a in (a1, a2):
        a.text(sum(xs) / len(xs), -0.36, gname, ha="center", va="top", fontsize=9, transform=a.get_xaxis_transform())
    x += 0.8
for a in (a1, a2):
    a.set_xticks(xt); a.set_xticklabels(xl, rotation=35, ha="right", fontsize=8)
    for gx in (xt[1] + 0.9, xt[4] + 0.9):
        a.axvline(gx, color="0.85", lw=1)
    a.spines[["top", "right"]].set_visible(False); a.grid(True, axis="y", color="0.92"); a.set_axisbelow(True)
a1.set_ylim(0, 1.08); a1.set_yticks([0, .25, .5, .75, 1]); a1.set_yticklabels(["0%", "25%", "50%", "75%", "100%"])
a1.set_ylabel("runs with ≥1 \"they'll only check\nthe files exist\" sentence")
a1.set_title("prevalence (Wilson 95% CI)", fontsize=10.5, loc="left")
a2.set_ylabel("such sentences per run\n(mean, bootstrap 95% CI)")
a2.set_title("density", fontsize=10.5, loc="left")
a2.set_ylim(0, None)
fig.suptitle("Hints shape the inference: stated oversight suppresses it, a lax line amplifies it", fontsize=12, x=0.01, ha="left")
fig.text(0.01, 0.012, "Red: graded wrapper.  Green: user / collaborator wrapper.  Blue: paper baseline.\nSF1 arms also carry structural cues and a question tool: the lax-line group is lax line + structural framing, not the line alone.", fontsize=7.5, color="0.35", va="bottom")
fig.tight_layout(rect=(0, 0.07, 1, 0.93))
for ext in ("png", "svg"):
    fig.savefig(HERE / "out" / f"fig_hints.{ext}", dpi=170)
print("wrote", HERE / "out" / "fig_hints.png")
