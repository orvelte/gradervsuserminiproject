#!/usr/bin/env python3
"""Emotion profile at the moment a run first weighs the shortcut (dp_consider): took vs declined, with 95% bootstrap
intervals. P3-full emotion directions, Assistant-Axis component removed, layer 32, z units of the default-Assistant
spread. Two contrasts per emotion: all runs (took vs declined) and within graded (cheated vs honest).

    python internals/persona/fig_emotion_consider.py      # writes deploysim/figures_splitbrain/fig_persona_emotion_consider.png
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent)); sys.path.insert(0, str(REPO / "deploysim" / "figures_splitbrain"))
import analyze as A  # noqa: E402

LAYER, B = 32, 5000
RNG = np.random.default_rng(20261022)


def diff_ci(a, b):
    a, b = np.asarray(a), np.asarray(b)
    boots = [RNG.choice(a, len(a)).mean() - RNG.choice(b, len(b)).mean() for _ in range(B)]
    return float(a.mean() - b.mean()), float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))


def main() -> int:
    root = REPO / "results" / "persona_full"
    ps = A.persona_space(root, LAYER)
    ax = A.unit(ps["axis"][LAYER])
    dirs = {n: A.unit(v - (v @ ax) * ax) for n, v in ps["emo_dirs"].items()}
    sc = {n: A.scale(ps, LAYER, d) for n, d in dirs.items()}
    rows = [r for r in A.v1_positions(root) if "dp_consider" in r["pos"] and r.get("group_c")]
    z = lambda r, n: (r["pos"]["dp_consider"][LAYER] @ dirs[n] - sc[n][0]) / sc[n][1]  # noqa: E731
    res = {}
    for n in dirs:
        took = [z(r, n) for r in rows if r["group_c"] == "took"]; dec = [z(r, n) for r in rows if r["group_c"] == "declined"]
        gc = [z(r, n) for r in rows if r["group"] == "G-cheat"]; gh = [z(r, n) for r in rows if r["group"] == "G-honest"]
        res[n] = {"all": diff_ci(took, dec), "graded": diff_ci(gc, gh)}
    n_took = sum(r["group_c"] == "took" for r in rows); n_dec = sum(r["group_c"] == "declined" for r in rows)
    n_gc = sum(r["group"] == "G-cheat" for r in rows); n_gh = sum(r["group"] == "G-honest" for r in rows)
    (root / "analysis" / "emotion_consider.json").write_text(json.dumps(res, indent=1))

    import matplotlib.pyplot as plt
    import style
    style.setup()
    order = sorted(res, key=lambda n: res[n]["all"][0])
    fig, axp = plt.subplots(figsize=(6.4, 5.6))
    y = np.arange(len(order))
    for off, key, col, mk, lab in ((-0.14, "all", style.PALETTE[1], "o", f"all runs: took ({n_took}) − declined ({n_dec})"),
                                   (0.14, "graded", style.PALETTE[0], "s", f"graded only: cheated ({n_gc}) − honest ({n_gh})")):
        m = np.array([res[n][key][0] for n in order]); lo = np.array([res[n][key][1] for n in order]); hi = np.array([res[n][key][2] for n in order])
        axp.errorbar(m, y + off, xerr=[m - lo, hi - m], fmt=mk, color=col, ecolor=col, elinewidth=1, capsize=2.5, ms=5, label=lab)
    axp.axvline(0, color="black", lw=0.8)
    axp.set_yticks(y); axp.set_yticklabels(order); axp.set_ylim(-0.6, len(order) - 0.4)
    axp.set_xlabel("difference at the consideration point (z, default-Assistant units)")
    axp.legend(loc="upper center", bbox_to_anchor=(0.5, -0.13), frameon=False)
    style.titles(fig, "Emotion projections when the model weighs the shortcut",
                 "Qwen3.8-27B · layer 32 · 100-role pass · emotions with the Assistant-Axis component removed · 95% bootstrap intervals · none survives FDR")
    out = REPO / "deploysim" / "figures_splitbrain" / "fig_persona_emotion_consider.png"
    fig.savefig(out, bbox_inches="tight"); plt.close(fig)
    print("wrote", out); print({n: [round(v, 2) for v in res[n]["all"]] for n in order})
    return 0


if __name__ == "__main__":
    sys.exit(main())
