#!/usr/bin/env python3
"""Graded-mode probe, difference-of-means version (replaces analyze.py's PCA-logistic probe, which overfit: 27
features for 29 runs).

    python internals/persona/probe.py [--root results/persona_min]

Train: w = mean(G-visible) - mean(D-visible) on all runs but one; threshold = midpoint of the two class means along w;
classify the held-out run. Leave-one-run-out accuracy, at each read position (P1, the first three turns' reasoning,
the decision points, run means) and layer (0 = embeddings, the prompt-text leak check). Null: 200 label shuffles.
Transfer: a probe trained on all G-visible vs D-visible runs, applied to G-holdout runs (graded frame, nothing scored
that rewards the shortcut): the fraction read as "graded".
Writes <root>/analysis/probe.json and deploysim/figures_splitbrain/fig_persona_probe.png.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import analyze as A  # noqa: E402

RNG = np.random.default_rng(7)
LAYERS = [0, 8, 16, 24, 32, 40, 48, 56, 64]


def loo(X, y):
    n = len(y); ok = 0
    for i in range(n):
        tr = np.arange(n) != i
        m1, m0 = X[tr][y[tr] == 1].mean(0), X[tr][y[tr] == 0].mean(0); w = m1 - m0; t = ((m1 + m0) / 2) @ w
        ok += ((X[i] @ w > t) == bool(y[i]))
    return ok / n


def main(argv) -> int:
    root = REPO / (argv[argv.index("--root") + 1] if "--root" in argv else "results/persona_min")
    rows = A.v1_positions(root)
    for r in rows:                                   # early-turn positions: when does it form?
        for k in range(3):
            if k < len(r["traj"]) and r["traj"][k] is not None:
                r["pos"][f"turn{k}_reason"] = r["traj"][k]
    poss = ["P1", "turn0_reason", "turn1_reason", "turn2_reason", "dp_temptation", "dp_consider", "dp_first_write", "mean_reason", "mean_resp"]
    res = {}
    for p in poss:
        sel = [r for r in rows if r["group"] in ("G-cheat", "G-honest", "D-visible") and p in r["pos"]]
        gh = [r for r in rows if r["group"] == "G-holdout" and p in r["pos"]]
        y = np.array([r["group"] != "D-visible" for r in sel], dtype=int)
        if len(sel) < 8 or y.sum() < 3 or (1 - y).sum() < 3:
            continue
        res[p] = {"n": [int(y.sum()), int((1 - y).sum())]}
        for L in LAYERS:
            X = np.stack([r["pos"][p][L] for r in sel]).astype(np.float64)
            acc = loo(X, y)
            null = [loo(X, RNG.permutation(y)) for _ in range(200)]
            w = X[y == 1].mean(0) - X[y == 0].mean(0); t = ((X[y == 1].mean(0) + X[y == 0].mean(0)) / 2) @ w
            tr = float(np.mean([r["pos"][p][L].astype(np.float64) @ w > t for r in gh])) if gh else None
            res[p][str(L)] = {"loo_acc": acc, "null_mean": float(np.mean(null)), "p": float((np.sum(np.array(null) >= acc) + 1) / 201),
                              "g_holdout_read_as_graded": tr}
    out = root / "analysis"; out.mkdir(parents=True, exist_ok=True)
    (out / "probe.json").write_text(json.dumps(res, indent=1))
    print(f"{'position':15} {'n(G,D)':8} " + " ".join(f"L{L:<5}" for L in LAYERS))
    for p, d in res.items():
        print(f"{p:15} {str(d['n']):8} " + " ".join(f"{d[str(L)]['loo_acc']:.2f}{'*' if d[str(L)]['p'] < 0.05 else ' '} " for L in LAYERS))
    print("(* = above 200 label shuffles, p < 0.05)\nG-holdout read as graded (layer 32):",
          {p: d["32"]["g_holdout_read_as_graded"] for p, d in res.items()})
    sys.path.insert(0, str(REPO / "deploysim" / "figures_splitbrain"))
    import matplotlib.pyplot as plt
    import style
    style.setup()
    fig, ax = plt.subplots(figsize=(8, 4.2))
    for i, p in enumerate(res):
        ax.plot(LAYERS, [res[p][str(L)]["loo_acc"] for L in LAYERS], marker="o", ms=4, color=style.PALETTE[i % len(style.PALETTE)], label=p)
    ax.axhline(0.5, color="black", lw=0.8, ls=":"); ax.set_xlabel("layer (0 = embeddings)"); ax.set_ylabel("leave-one-run-out accuracy")
    ax.set_ylim(0.2, 1.05); ax.legend(fontsize=8, ncol=2, loc="lower right")
    style.titles(fig, "Graded-mode probe: graded vs deployment", "difference-of-means · Qwen3.8-27B · holdout V1 · 17 graded vs 12 deployment runs")
    fig.savefig(REPO / "deploysim" / "figures_splitbrain" / "fig_persona_probe.png", bbox_inches="tight"); plt.close(fig)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
