#!/usr/bin/env python3
"""Emotion projections by frame (decision #104). Two panels, P3-full answer-token emotion directions with the
Assistant-Axis component removed, layer 32.

  A. Final prompt token (G1 forward passes): graded, conduct review and the five graded paraphrases (mean, with their
     range), each minus deployment, in units of the across-prompt spread at that position (3,000 reference prompts, as
     in G1). Grey band: 95% of |Δz| over 1,000 covariance-matched random directions for graded − deployment.
  B. Consideration point, choice held fixed: graded runs that declined − deployment runs that declined (z units of the
     default-Assistant spread), 95% bootstrap intervals.

    python internals/persona/fig_emotion_frames.py
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent)); sys.path.insert(0, str(REPO / "deploysim" / "figures_splitbrain"))
import analyze as A  # noqa: E402
from fig_emotion_consider import diff_ci  # noqa: E402

LAYER = 32
RNG = np.random.default_rng(20261023)


def final(d: Path, rid: str) -> np.ndarray:
    z = np.load(d / (hashlib.sha1(rid.encode()).hexdigest() + ".npz"), allow_pickle=False)
    li = list(z["layers"]).index(LAYER) if "layers" in z.files else LAYER
    return z["means"][list(z["names"]).index("final"), li].astype(np.float64)


def main() -> int:
    root = REPO / "results" / "persona_full"; g1 = REPO / "results" / "gate1"
    ps = A.persona_space(root, LAYER)
    ax = A.unit(ps["axis"][LAYER])
    dirs = {n: A.unit(v - (v @ ax) * ax).astype(np.float64) for n, v in ps["emo_dirs"].items()}
    names = list(dirs)

    # panel A: final prompt token
    ref_ids = [json.loads(l)["id"] for l in (g1 / "ref_seqs.jsonl").read_text().splitlines()]
    X = np.stack([final(g1 / "ref", r) for r in ref_ids]); Xc = X - X.mean(0)
    acts = {c: final(g1 / "acts", f"gate1:{c}") for c in ["D", "G", "C"] + [f"G_para{i}" for i in range(1, 6)]}
    sd = {n: float((Xc @ dirs[n]).std()) for n in names}
    dz = lambda c, n: float((acts[c] - acts["D"]) @ dirs[n] / sd[n])  # noqa: E731
    U = Xc.T @ RNG.standard_normal((Xc.shape[0], 1000)); U /= np.linalg.norm(U, axis=0, keepdims=True)
    p95 = float(np.percentile(np.abs((acts["G"] - acts["D"]) @ U / (Xc @ U).std(0)), 95))
    A_res = {n: {"G": dz("G", n), "C": dz("C", n), "para": [dz(f"G_para{i}", n) for i in range(1, 6)]} for n in names}

    # panel B: consideration point, decliners only
    sc = {n: A.scale(ps, LAYER, d) for n, d in dirs.items()}
    rows = [r for r in A.v1_positions(root) if "dp_consider" in r["pos"] and r.get("group_c") == "declined"]
    gd = [r for r in rows if r["cell"] == "HO-G~visible"]; dd = [r for r in rows if r["cell"] == "HO-D~visible"]
    z = lambda r, n: (r["pos"]["dp_consider"][LAYER] @ dirs[n] - sc[n][0]) / sc[n][1]  # noqa: E731
    B_res = {n: diff_ci([z(r, n) for r in gd], [z(r, n) for r in dd]) for n in names}
    out = {"final_token": A_res, "random_p95_abs_dz": p95, "consider_decliners_G_minus_D": B_res, "n_G_declined": len(gd), "n_D_declined": len(dd)}
    (root / "analysis" / "emotion_frames.json").write_text(json.dumps(out, indent=1))

    import matplotlib.pyplot as plt
    import style
    style.setup()
    order = sorted(names, key=lambda n: A_res[n]["G"])
    y = np.arange(len(order))
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(11, 5.6), sharey=True)
    a1.axvspan(-p95, p95, color="#e3e3e3", zorder=0, label="95% of random directions (graded − deployment)")
    pm = np.array([np.mean(A_res[n]["para"]) for n in order]); plo = np.array([min(A_res[n]["para"]) for n in order]); phi = np.array([max(A_res[n]["para"]) for n in order])
    a1.errorbar(pm, y + 0.18, xerr=[pm - plo, phi - pm], fmt="D", color=style.PALETTE[4], ecolor=style.PALETTE[4], capsize=2.5, ms=4.5, elinewidth=1, label="graded paraphrases (mean, range of 5)")
    a1.plot([A_res[n]["G"] for n in order], y, "o", color=style.PALETTE[1], ms=6, label="graded (as run)")
    a1.plot([A_res[n]["C"] for n in order], y - 0.18, "s", color=style.PALETTE[2], ms=5.5, label="conduct review")
    a1.axvline(0, color="black", lw=0.8)
    a1.set_yticks(y); a1.set_yticklabels(order); a1.set_ylim(-0.6, len(order) - 0.4)
    a1.set_xlabel("difference from deployment (z, across-prompt spread)")
    a1.set_title("(a) Frame alone: final prompt token", loc="left")
    a1.legend(loc="upper center", bbox_to_anchor=(0.5, -0.12), frameon=False)
    m = np.array([B_res[n][0] for n in order]); lo = np.array([B_res[n][1] for n in order]); hi = np.array([B_res[n][2] for n in order])
    a2.errorbar(m, y, xerr=[m - lo, hi - m], fmt="o", color=style.PALETTE[0], ecolor=style.PALETTE[0], capsize=2.5, ms=5, elinewidth=1,
                label=f"graded declined ({len(gd)}) − deployment declined ({len(dd)})")
    a2.axvline(0, color="black", lw=0.8)
    a2.set_xlabel("difference (z, default-Assistant units)")
    a2.set_title("(b) Frame with the choice fixed: when weighing the shortcut", loc="left")
    a2.legend(loc="upper center", bbox_to_anchor=(0.5, -0.12), frameon=False)
    fig.tight_layout()
    style.titles(fig, "Does the evaluation frame change emotion projections?",
                 "Qwen3.8-27B · layer 32 · 100-role pass emotion directions (answer tokens, Assistant-Axis component removed) · (b) 95% bootstrap intervals")
    out_png = REPO / "deploysim" / "figures_splitbrain" / "fig_persona_emotion_frames.png"
    fig.savefig(out_png, bbox_inches="tight"); plt.close(fig)
    print("wrote", out_png, "| random p95 |Δz| =", round(p95, 3))
    for n in order:
        print(f"{n:11} A: G {A_res[n]['G']:+.2f}  C {A_res[n]['C']:+.2f}  para {np.mean(A_res[n]['para']):+.2f} [{min(A_res[n]['para']):+.2f},{max(A_res[n]['para']):+.2f}]   "
              f"B: {B_res[n][0]:+.2f} [{B_res[n][1]:+.2f},{B_res[n][2]:+.2f}]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
