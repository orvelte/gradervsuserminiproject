#!/usr/bin/env python3
"""Emotion profiles per run and over the course of each run (exploratory; decision #96).

    python internals/persona/emotions_runs.py [--root results/persona_min] [--layer 32] [--tag min]

For every V1 replay and every assistant turn, the mean reasoning activation is projected onto the 12 emotion
directions with the Assistant-Axis component removed (`<emotion>⊥axis`), in z units of the default-Assistant spread.
Per run: the mean over turns, reported (a) against the default Assistant and (b) centred on the mean of all runs
("relative"), since every agentic run shares a common offset; the run's dominant emotion is the largest relative z.
Over the run: group means in 10 bins of normalised run time.
Writes <root>/analysis/emotions_runs.json and fig_persona_emotions_by_run_<tag>.png, fig_persona_emotion_trajectories_<tag>.png.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent)); sys.path.insert(0, str(REPO / "deploysim" / "figures_splitbrain"))
import analyze as A  # noqa: E402

GROUPS = ["G-cheat", "G-honest", "D-visible", "G-holdout"]
LABEL = {"G-cheat": "Graded, cheated", "G-honest": "Graded, honest", "D-visible": "Deployment", "G-holdout": "Graded, held-out scoring"}
BINS = 10


def main(argv) -> int:
    root = REPO / (argv[argv.index("--root") + 1] if "--root" in argv else "results/persona_min")
    layer = int(argv[argv.index("--layer") + 1]) if "--layer" in argv else 32
    tag = argv[argv.index("--tag") + 1] if "--tag" in argv else "min"
    ps = A.persona_space(root, layer)
    ax = A.unit(ps["axis"][layer])
    names = list(ps["emo_dirs"])
    dirs = {n: A.unit(v - (v @ ax) * ax) for n, v in ps["emo_dirs"].items()}
    sc = {n: A.scale(ps, layer, d) for n, d in dirs.items()}
    rows = A.v1_positions(root)
    runs = []
    for r in rows:
        T = [t for t in r["traj"] if t is not None]
        if not T:
            continue
        Z = np.array([[(t[layer] @ dirs[n] - sc[n][0]) / sc[n][1] for n in names] for t in T])   # turns x emotions
        runs.append({"run": r["run"], "group": r["group"], "Z": Z, "mean": Z.mean(0)})
    grand = np.mean([x["mean"] for x in runs], 0)
    for x in runs:
        x["rel"] = x["mean"] - grand; x["top"] = names[int(np.argmax(x["rel"]))]
    out = {"layer": layer, "emotions": names, "grand_mean_vs_default": dict(zip(names, grand.round(3).tolist())),
           "groups": {}, "runs": [{"run": x["run"], "group": x["group"], "top_relative": x["top"],
                                    "vs_default": dict(zip(names, x["mean"].round(3).tolist())), "relative": dict(zip(names, x["rel"].round(3).tolist()))} for x in runs]}
    for g in GROUPS:
        xs = [x for x in runs if x["group"] == g]
        if xs:
            tops = {}
            for x in xs:
                tops[x["top"]] = tops.get(x["top"], 0) + 1
            out["groups"][g] = {"n": len(xs), "mean_relative": dict(zip(names, np.mean([x["rel"] for x in xs], 0).round(3).tolist())), "top_counts": tops}
    (root / "analysis").mkdir(parents=True, exist_ok=True)
    (root / "analysis" / "emotions_runs.json").write_text(json.dumps(out, indent=1))

    import matplotlib.pyplot as plt
    import style
    style.setup()
    # 1. per-run heatmap (relative), grouped
    order = [x for g in GROUPS for x in runs if x["group"] == g]
    M = np.array([x["rel"] for x in order]); lim = np.abs(M).max()
    fig, a = plt.subplots(figsize=(6.6, 0.16 * len(order) + 1.4))
    im = a.imshow(M, cmap="RdBu_r", vmin=-lim, vmax=lim, aspect="auto", interpolation="nearest")
    a.set_xticks(range(len(names))); a.set_xticklabels(names, rotation=45, ha="right")
    a.set_yticks([]); a.tick_params(top=False, right=False)
    y = 0
    for g in GROUPS:
        k = sum(x["group"] == g for x in order)
        if k:
            a.text(-0.7, y + k / 2 - 0.5, f"{LABEL[g]} ({k})", ha="right", va="center", fontsize=8.5)
            if y:
                a.axhline(y - 0.5, color="black", lw=0.8)
            y += k
    for i, x in enumerate(order):
        j = names.index(x["top"]); a.add_patch(plt.Rectangle((j - 0.5, i - 0.5), 1, 1, fill=False, ec="black", lw=0.8))
    cb = fig.colorbar(im, ax=a, fraction=0.04, pad=0.02); cb.set_label("z, relative to the average run", fontsize=8.5); cb.ax.tick_params(direction="in")
    a.set_title("Emotion profile of each run (boxed: the run's dominant emotion)")
    fig.savefig(REPO / "deploysim" / "figures_splitbrain" / f"fig_persona_emotions_by_run_{tag}.png", bbox_inches="tight"); plt.close(fig)
    # 2. trajectories: group means over normalised run time
    fig, axs = plt.subplots(3, 4, figsize=(9, 6), sharex=True)
    edges = np.linspace(0, 1, BINS + 1)
    for e, a in zip(range(len(names)), axs.flat):
        for gi, g in enumerate(GROUPS):
            xs = [x for x in runs if x["group"] == g]
            if not xs:
                continue
            B = np.full((len(xs), BINS), np.nan)
            for i, x in enumerate(xs):
                t = np.linspace(0, 1, len(x["Z"]), endpoint=False) + 0.5 / len(x["Z"])
                for b in range(BINS):
                    m = (t >= edges[b]) & (t < edges[b + 1])
                    if m.any():
                        B[i, b] = x["Z"][m, e].mean() - grand[e]
            mu = np.nanmean(B, 0); se = np.nanstd(B, 0) / np.sqrt(np.maximum(1, np.sum(~np.isnan(B), 0)))
            c = (edges[:-1] + edges[1:]) / 2
            a.plot(c, mu, color=style.PALETTE[gi], ls="--" if g == "D-visible" else "-", label=LABEL[g])
            a.fill_between(c, mu - se, mu + se, color=style.PALETTE[gi], alpha=0.15, lw=0)
        a.axhline(0, color="black", lw=0.5, ls=":"); a.set_title(names[e])
    for a in axs[-1]:
        a.set_xlabel("fraction of run")
    for a in axs[:, 0]:
        a.set_ylabel("z (rel. average run)")
    h, l = axs.flat[0].get_legend_handles_labels()
    fig.tight_layout(rect=(0, 0.06, 1, 1))
    fig.legend(h, l, loc="lower center", ncol=4, frameon=False, bbox_to_anchor=(0.5, 0.0))
    style.titles(fig, "Emotion projections over the course of a run", "mean ± s.e. per group · axis component removed · relative to the average run")
    fig.savefig(REPO / "deploysim" / "figures_splitbrain" / f"fig_persona_emotion_trajectories_{tag}.png", bbox_inches="tight"); plt.close(fig)
    print("grand mean vs default:", {k: round(v, 2) for k, v in out["grand_mean_vs_default"].items()})
    for g, d in out["groups"].items():
        top3 = sorted(d["mean_relative"].items(), key=lambda kv: -kv[1])[:3]
        print(f"{g:10} n={d['n']:2} top (relative): {[(k, round(v, 2)) for k, v in top3]}  dominant counts: {d['top_counts']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
