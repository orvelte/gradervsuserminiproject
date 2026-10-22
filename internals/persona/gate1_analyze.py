#!/usr/bin/env python3
"""Gate 1 analysis (PREREG G1). numpy only.

    python internals/persona/gate1_analyze.py [--root results/gate1] [--axis-root results/persona_full] [--layer 32]

Inputs: <root>/acts/*.npz (the 14 conditions, all layers, span `final`) and <root>/ref/*.npz (3,000 reference
final-token activations, slimmed to a few layers). Direction: the Assistant Axis from --axis-root at --layer.
Writes <root>/report.md, <root>/results.json and deploysim/figures_splitbrain/fig_gate1.png.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import analyze as A  # noqa: E402

RNG = np.random.default_rng(20261021)
N_RANDOM = 1000
CONDS = ["G", "G_para1", "G_para2", "G_para3", "G_para4", "G_para5", "G_scramble", "D_decoy", "C", "G_holdout", "D_holdout", "G_intent", "D_intent"]


def load_final(d: Path, rid: str, layer: int) -> np.ndarray:
    z = np.load(d / (hashlib.sha1(rid.encode()).hexdigest() + ".npz"), allow_pickle=False)
    li = list(z["layers"]).index(layer) if "layers" in z.files else layer
    return z["means"][list(z["names"]).index("final"), li].astype(np.float64)


def gate(acts: dict, ref: np.ndarray, axis: np.ndarray) -> dict:
    Xc = ref - ref.mean(0)
    sd = lambda u: float((Xc @ u).std())  # noqa: E731
    dz = lambda c, u: float((acts[c] - acts["D"]) @ u / sd(u))  # noqa: E731
    U = Xc.T @ RNG.standard_normal((Xc.shape[0], N_RANDOM)); U /= np.linalg.norm(U, axis=0, keepdims=True)
    proj = Xc @ U; sds = proj.std(0)
    rand_G = np.abs((acts["G"] - acts["D"]) @ U / sds)
    out = {"dz_axis": {c: dz(c, axis) for c in CONDS if c in acts}}
    g = out["dz_axis"]["G"]
    out["random_G_abs_dz"] = {"p50": float(np.percentile(rand_G, 50)), "p95": float(np.percentile(rand_G, 95)), "max": float(rand_G.max())}
    out["axis_percentile"] = float((rand_G < abs(g)).mean() * 100)
    out["criteria"] = {
        "1_axis_at_or_above_p95": abs(g) >= np.percentile(rand_G, 95),
        "2_paraphrases_same_sign": all(np.sign(out["dz_axis"][f"G_para{i}"]) == np.sign(g) for i in range(1, 6)),
        "3_scramble_le_half": abs(out["dz_axis"]["G_scramble"]) <= 0.5 * abs(g)}
    out["pass"] = all(out["criteria"].values())
    out["paraphrase_percentiles"] = {f"G_para{i}": float((rand_G < abs(out["dz_axis"][f"G_para{i}"])).mean() * 100) for i in range(1, 6)}
    return out


def main(argv) -> int:
    root = REPO / (argv[argv.index("--root") + 1] if "--root" in argv else "results/gate1")
    axis_root = REPO / (argv[argv.index("--axis-root") + 1] if "--axis-root" in argv else "results/persona_full")
    layer = int(argv[argv.index("--layer") + 1]) if "--layer" in argv else 32
    ref_ids = [json.loads(l)["id"] for l in (root / "ref_seqs.jsonl").read_text().splitlines()]
    acts = {c: load_final(root / "acts", f"gate1:{c}", layer) for c in ["D"] + CONDS}
    ref = np.stack([load_final(root / "ref", r, layer) for r in ref_ids])
    a0 = {c: load_final(root / "acts", f"gate1:{c}", 0) for c in ["D", "G"]}
    ps = A.persona_space(axis_root, layer)
    axis = A.unit(ps["axis"][layer]).astype(np.float64)
    res = {"layer": layer, "n_ref": len(ref), "layer0_final_token_identical": bool(np.allclose(a0["D"], a0["G"])), **gate(acts, ref, axis)}

    # exploratory: other layers, with the minimal persona space's axis (all layers stored) and the ref set's layers
    sweep = {}
    zr = np.load(root / "ref" / (hashlib.sha1(ref_ids[0].encode()).hexdigest() + ".npz"))
    sweep_root = argv[argv.index("--sweep-root") + 1] if "--sweep-root" in argv else "results/persona_min"
    use_sweep = sweep_root != "none" and (REPO / sweep_root).exists()
    for L in [int(x) for x in zr["layers"]]:
        if not use_sweep or L == 0:
            continue
        ps_min = A.persona_space(REPO / sweep_root, L)          # persona_space loads only {0, L}: one call per layer
        acts_L = {c: load_final(root / "acts", f"gate1:{c}", L) for c in ["D"] + CONDS}
        ref_L = np.stack([load_final(root / "ref", r, L) for r in ref_ids])
        g = gate(acts_L, ref_L, A.unit(ps_min["axis"][L]).astype(np.float64))
        sweep[L] = {"dz_G": g["dz_axis"]["G"], "pct": g["axis_percentile"], "pass": g["pass"], "dz_scramble": g["dz_axis"]["G_scramble"]}
    res["exploratory_layer_sweep_min_axis"] = sweep
    (root / "results.json").write_text(json.dumps(res, indent=1, default=float))

    lines = [f"# Gate 1 (PREREG G1): layer {layer}, final prompt token", "",
             f"Layer-0 final token identical across conditions: {res['layer0_final_token_identical']}", "",
             f"Axis shift G vs D: Δz = {res['dz_axis']['G']:+.3f}; percentile among {N_RANDOM} covariance-matched random directions: "
             f"{res['axis_percentile']:.1f} (random |Δz| median {res['random_G_abs_dz']['p50']:.3f}, 95th {res['random_G_abs_dz']['p95']:.3f})", "",
             "| condition | Δz vs D (axis) |", "|---|---|"]
    lines += [f"| {c} | {v:+.3f} |" for c, v in res["dz_axis"].items()]
    lines += ["", "Criteria: " + ", ".join(f"{k} = {v}" for k, v in res["criteria"].items()), f"**{'PASS' if res['pass'] else 'STOP'}**", "",
              "Exploratory layer sweep (minimal-pass axis): " + json.dumps({k: {kk: round(vv, 3) if isinstance(vv, float) else vv for kk, vv in v.items()} for k, v in sweep.items()})]
    (root / "report.md").write_text("\n".join(lines) + "\n"); print("\n".join(lines))

    sys.path.insert(0, str(REPO / "deploysim" / "figures_splitbrain"))
    import matplotlib.pyplot as plt
    import style
    style.setup()
    fig, ax = plt.subplots(figsize=(9, 4.2))
    names = list(res["dz_axis"]); vals = [res["dz_axis"][c] for c in names]
    cols = [style.PALETTE[1] if c.startswith("G") and c not in ("G_scramble",) else style.PALETTE[0] if c.startswith("D") else style.PALETTE[2] if c == "C" else "#888888" for c in names]
    ax.bar(range(len(names)), vals, color=cols, width=0.7)
    p95 = res["random_G_abs_dz"]["p95"]
    ax.axhspan(-p95, p95, color="#dddddd", zorder=0, label="95% of random directions (G vs D)")
    ax.axhline(0, color="black", lw=0.8)
    ax.set_xticks(range(len(names))); ax.set_xticklabels(names, rotation=40, ha="right")
    ax.set_ylabel("Assistant Axis shift vs deployment (Δz)")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.32), frameon=False)
    style.titles(fig, "Does the graded cue move the Assistant Axis at the final prompt token?",
                 f"Qwen3.8-27B · layer {layer} · forward passes only · grey band: 95% of {N_RANDOM} covariance-matched random directions · {'PASS' if res['pass'] else 'STOP'}")
    fig.savefig(REPO / "deploysim" / "figures_splitbrain" / "fig_gate1.png", bbox_inches="tight"); plt.close(fig)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
