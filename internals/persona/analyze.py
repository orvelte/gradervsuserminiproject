#!/usr/bin/env python3
"""Minimal persona-space / emotion analysis (internals_plan "Minimal design", decisions #90-91). numpy only.

    python internals/persona/analyze.py [--root results/persona_min] [--layer 32]

Inputs (from the pod and the judge):
  <root>/gen/generations.jsonl, <root>/gen/scores.jsonl, <root>/gen/acts/*.npz        extraction responses
  <root>/v1/runs.jsonl, <root>/v1/acts/*.npz                                          V1 replays (prep_v1.py spans)
  <root>/v1/considered.json (optional)    {run: "considered" | "never"}: blind coding of deployment reasoning
Outputs: <root>/analysis/{report.md, results.json}; figures in deploysim/figures_splitbrain/fig_persona_*.

Directions (unit vectors at the analysis layer; index l = output of decoder layer l, 0 = embeddings):
  axis       contrast vector: mean(default Assistant) - mean(fully role-playing role vectors) (paper definition)
  PC1..PC5   PCA of mean-centred role vectors (sign: + toward the default Assistant)
  emotions   mean(emotion responses judged 3) - mean(default Assistant), per emotion
Units: projections are reported as z-scores against the default-Assistant response distribution, and for the axis also
as position 0 (role-play mean) .. 1 (default-Assistant mean).
Groups: G-cheat / G-honest (HO-G~visible by grader_gaming), D-visible, G-holdout.
Nulls: arm-label permutation (10k), 100 random unit directions, the same contrast at layer 0.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
RNG = np.random.default_rng(20261020)
SPAN = "resp"   # extraction vectors over response tokens, as in the paper (reason / all reported as checks)


def _load_npz(d: Path, rid: str):
    f = d / (hashlib.sha1(rid.encode()).hexdigest() + ".npz")
    if not f.exists():
        return None
    z = np.load(f, allow_pickle=False)
    return {str(n): z["means"][i] for i, n in enumerate(z["names"])}, {str(n): float(z["counts"][i]) for i, n in enumerate(z["names"])}


def unit(v):
    return v / (np.linalg.norm(v) + 1e-8)


# ---------------------------------------------------------------- persona space
def persona_space(root: Path, layer: int, span: str = SPAN, thinking: bool = True, half: str | None = None):
    gens = [json.loads(l) for l in (root / "gen" / "generations.jsonl").read_text().splitlines()]
    scores = {json.loads(l)["id"]: json.loads(l)["score"] for l in (root / "gen" / "scores.jsonl").read_text().splitlines()} \
        if (root / "gen" / "scores.jsonl").exists() else {}
    by = {}
    for g in gens:
        if g["thinking"] != thinking or (half and g["half"] != half):
            continue
        a = _load_npz(root / "gen" / "acts", g["id"])
        if a is None or span not in a[0]:
            continue
        by.setdefault((g["kind"], g["name"]), []).append((a[0][span].astype(np.float32), scores.get(g["id"]), g["id"]))
    default = [v[:, :] for v, _, _ in by.get(("default", "default"), [])]
    if not default:
        raise SystemExit("no default-Assistant activations")
    D = np.stack(default)                                         # [n, L, H]
    roles = {n: np.stack([v for v, s, _ in rows if s == 3]) for (k, n), rows in by.items() if k == "role" and sum(s == 3 for _, s, _ in rows) >= 3}
    emos = {}
    for (k, n), rows in by.items():
        if k == "emotion":
            keep = [v for v, s, _ in rows if s == 3]
            if len(keep) >= 5:
                emos[n] = np.stack(keep)
    R = np.stack([r.mean(0) for r in roles.values()])             # [n_roles, L, H]
    axis = D.mean(0) - R.mean(0)                                  # [L, H]
    Rl = R[:, layer] - R[:, layer].mean(0)
    U, S, Vt = np.linalg.svd(Rl, full_matrices=False)
    pcs = Vt[:5].copy()
    for i in range(len(pcs)):                                     # sign: + toward the default Assistant
        if (D[:, layer].mean(0) - R[:, layer].mean(0)) @ pcs[i] < 0:
            pcs[i] *= -1
    emo_dirs = {n: unit(e[:, layer].mean(0) - D[:, layer].mean(0)) for n, e in emos.items()}
    return {"D": D, "roles": roles, "role_names": list(roles), "R": R, "axis": axis, "pcs": pcs, "S": S,
            "emotions": emos, "emo_dirs": emo_dirs, "n_rows": {f"{k}:{n}": len(v) for (k, n), v in by.items()}}


def gates(ps, ps_a, ps_b, ps_nothink, layer):
    ax = unit(ps["axis"][layer]); pc1 = ps["pcs"][0]
    proj_roles = (ps["R"][:, layer] - ps["R"][:, layer].mean(0)) @ pc1
    proj_def = (ps["D"][:, layer].mean(0) - ps["R"][:, layer].mean(0)) @ pc1
    order = np.argsort(proj_roles)
    pct = float((proj_roles < proj_def).mean())
    g = {"cos_axis_pc1": float(abs(ax @ pc1)),
         "default_pc1_percentile_among_roles": pct,
         "pc1_assistant_end": [ps["role_names"][i] for i in order[::-1][:5]],
         "pc1_far_end": [ps["role_names"][i] for i in order[:5]],
         "split_half_cos": float(unit(ps_a["axis"][layer]) @ unit(ps_b["axis"][layer])) if ps_a and ps_b else None,
         "thinking_vs_nonthinking_axis_cos": float(unit(ps_nothink["axis"][layer]) @ ax) if ps_nothink else None,
         "pc_var_explained": (ps["S"][:5] ** 2 / (ps["S"] ** 2).sum()).round(3).tolist(),
         "n_roles_used": len(ps["role_names"]), "emotions_used": list(ps["emo_dirs"]),
         "cos_emotion_axis": {n: round(float(v @ ax), 3) for n, v in ps["emo_dirs"].items()}}
    g["pass"] = {"cos_axis_pc1>0.6": g["cos_axis_pc1"] > 0.6, "default_at_pc1_extreme": pct >= 0.9 or pct <= 0.1,
                 "split_half>0.9": (g["split_half_cos"] or 0) > 0.9}
    return g


# ---------------------------------------------------------------- V1 projections
def v1_positions(root: Path):
    runs = [json.loads(l) for l in (root / "v1" / "runs.jsonl").read_text().splitlines()]
    out = []
    for m in runs:
        a = _load_npz(root / "v1" / "acts", m["run"])
        if a is None:
            continue
        means, counts = a
        pos = {k: means[k].astype(np.float32) for k in ("P0", "P1", "shared", "dp_cheat", "dp_first_write", "dp_temptation", "dp_consider") if k in means}
        for kind in ("reason", "resp"):
            ks = [k for k in means if k.startswith("turn") and k.endswith("_" + kind)]
            w = np.array([counts[k] for k in ks])
            if ks and w.sum():
                pos[f"mean_{kind}"] = (np.stack([means[k].astype(np.float32) for k in ks]) * w[:, None, None]).sum(0) / w.sum()
        nt = m["n_turns"]
        traj = [means.get(f"turn{k}_reason") for k in range(nt)]
        group = ("G-cheat" if m["gaming"] else "G-honest") if m["cell"] == "HO-G~visible" else ("D-visible" if m["cell"] == "HO-D~visible" else "G-holdout")
        cons = (m.get("decision_points") or {}).get("consider") or {}
        if cons.get("found"):     # the choice made at the moment the shortcut is first weighed
            group_c = "took" if (m["gaming"] or cons.get("did_it")) else "declined"
        else:
            group_c = None
        out.append({"run": m["run"], "cell": m["cell"], "group": group, "group_c": group_c, "gaming": m["gaming"], "pos": pos,
                    "traj": [t.astype(np.float32) if t is not None else None for t in traj]})
    return out


def scale(ps, layer, direction):
    """z-score units against the default-Assistant response distribution along `direction`."""
    d = ps["D"][:, layer] @ direction
    return float(d.mean()), float(d.std() + 1e-8)


def effect(a, b):
    a, b = np.asarray(a), np.asarray(b)
    if len(a) < 2 or len(b) < 2:
        return None
    sp = np.sqrt(((len(a) - 1) * a.var(ddof=1) + (len(b) - 1) * b.var(ddof=1)) / (len(a) + len(b) - 2)) + 1e-8
    return float((a.mean() - b.mean()) / sp)


def perm_p(a, b, n=10000):
    a, b = np.asarray(a), np.asarray(b); x = np.concatenate([a, b]); k = len(a); obs = abs(a.mean() - b.mean())
    if len(a) < 2 or len(b) < 2:
        return None
    hits = 0
    for _ in range(n):
        RNG.shuffle(x); hits += abs(x[:k].mean() - x[k:].mean()) >= obs - 1e-12
    return (hits + 1) / (n + 1)


def _in(r, g):
    """Group membership: plain names match r["group"]; "took:<arm>" / "declined:<arm>" match the consider-point choice."""
    if ":" in g:
        c, arm = g.split(":"); return r.get("group_c") == c and (arm == "any" or r["cell"].startswith(arm))
    return r["group"] == g


def contrast(rows, pos, ga, gb, layer, direction, mu, sd):
    va = [(r["pos"][pos][layer] @ direction - mu) / sd for r in rows if any(_in(r, g) for g in ga) and pos in r["pos"]]
    vb = [(r["pos"][pos][layer] @ direction - mu) / sd for r in rows if any(_in(r, g) for g in gb) and pos in r["pos"]]
    if len(va) < 2 or len(vb) < 2:
        return {"n": [len(va), len(vb)]}
    return {"n": [len(va), len(vb)], "mean_a": float(np.mean(va)), "mean_b": float(np.mean(vb)), "diff_z": float(np.mean(va) - np.mean(vb)),
            "d": effect(va, vb), "perm_p": perm_p(va, vb)}


def random_null(rows, pos, ga, gb, layer, d_obs, n=100):
    H = next(r["pos"][pos] for r in rows if pos in r["pos"]).shape[-1]; ds = []
    for _ in range(n):
        v = unit(RNG.standard_normal(H).astype(np.float32))
        va = [r["pos"][pos][layer] @ v for r in rows if any(_in(r, g) for g in ga) and pos in r["pos"]]
        vb = [r["pos"][pos][layer] @ v for r in rows if any(_in(r, g) for g in gb) and pos in r["pos"]]
        e = effect(va, vb)
        if e is not None:
            ds.append(abs(e))
    return float((np.array(ds) >= abs(d_obs)).mean()) if ds and d_obs is not None else None


def bh(ps):
    """Benjamini-Hochberg q-values."""
    ps = np.asarray(ps, dtype=float); n = len(ps); o = np.argsort(ps); q = np.empty(n)
    q[o] = np.minimum.accumulate((ps[o] * n / np.arange(1, n + 1))[::-1])[::-1]
    return np.minimum(q, 1)


def logistic_loo(X, y, l2=1.0, iters=300):
    """Leave-one-out accuracy of an L2 logistic probe (standardised features, gradient descent)."""
    n = len(y); correct = 0; scores = []
    for i in range(n):
        tr = np.arange(n) != i
        mu, sd = X[tr].mean(0), X[tr].std(0) + 1e-6
        Xt = (X[tr] - mu) / sd; w = np.zeros(X.shape[1]); b = 0.0
        for _ in range(iters):
            p = 1 / (1 + np.exp(-(Xt @ w + b)))
            w -= 0.1 * (Xt.T @ (p - y[tr]) / tr.sum() + l2 * w / tr.sum()); b -= 0.1 * (p - y[tr]).mean()
        s = float(((X[i] - mu) / sd) @ w + b); scores.append(s); correct += (s > 0) == bool(y[i])
    return correct / n, scores


def probe(rows, pos, layer, k=64):
    """G-visible (1) vs D-visible (0) at `pos`, on the top-k principal components of the pooled activations (so the
    probe has fewer features than runs)."""
    sel = [r for r in rows if r["group"] in ("G-cheat", "G-honest", "D-visible") and pos in r["pos"]]
    if len(sel) < 6:
        return None
    X = np.stack([r["pos"][pos][layer] for r in sel]); y = np.array([r["group"] != "D-visible" for r in sel], dtype=float)
    Xc = X - X.mean(0); U, S, Vt = np.linalg.svd(Xc, full_matrices=False); Z = Xc @ Vt[: min(k, len(sel) - 2)].T
    acc, _ = logistic_loo(Z, y)
    yp = y.copy(); accs = []
    for _ in range(50):
        RNG.shuffle(yp); accs.append(logistic_loo(Z, yp)[0])
    return {"n": len(sel), "loo_acc": acc, "shuffle_mean": float(np.mean(accs)), "shuffle_p": float((np.array(accs) >= acc).mean())}


# ---------------------------------------------------------------- figures
def figures(ps, rows, dirs, scales, layer, figdir: Path, tag: str = ""):
    sys.path.insert(0, str(REPO / "deploysim" / "figures_splitbrain"))
    import matplotlib.pyplot as plt
    import style
    style.setup(); figdir.mkdir(parents=True, exist_ok=True)
    groups = ["G-cheat", "G-honest", "D-visible", "G-holdout"]; col = dict(zip(groups, style.PALETTE))
    # 1. axis at each read position, by group
    poss = [p for p in ("P0", "shared", "P1", "dp_temptation", "dp_consider", "dp_first_write", "dp_cheat", "mean_reason", "mean_resp") if any(p in r["pos"] for r in rows)]
    fig, ax = plt.subplots(figsize=(11, 4))
    mu, sd = scales["axis"]
    for gi, g in enumerate(groups):
        for pi, p in enumerate(poss):
            v = [(r["pos"][p][layer] @ dirs["axis"] - mu) / sd for r in rows if r["group"] == g and p in r["pos"]]
            if v:
                x = pi + (gi - 1.5) * 0.18
                ax.scatter(np.full(len(v), x) + RNG.uniform(-0.03, 0.03, len(v)), v, s=14, color=col[g], alpha=0.7, label=g if pi == 0 else None,
                           marker="o" if not g.startswith("D") else "s", facecolors=col[g] if not g.startswith("D") else "white")
                ax.errorbar(x, np.mean(v), yerr=1.96 * np.std(v) / max(1, np.sqrt(len(v) - 1)), **style.ERR)
    ax.set_xticks(range(len(poss))); ax.set_xticklabels(poss, rotation=20); ax.set_ylabel("Assistant Axis (z vs default Assistant)")
    ax.legend(ncol=4, loc="upper center", bbox_to_anchor=(0.5, -0.3), frameon=False)
    style.titles(fig, "Assistant Axis by read position", f"Qwen3.8-27B · layer {layer} · holdout V1 · minimal design (exploratory)")
    fig.savefig(figdir / f"fig_persona_axis_positions{tag}.png", bbox_inches="tight"); plt.close(fig)
    # 2. emotion + PC profile at the first-write decision point, by group
    names = [n for n in dirs if n.startswith("PC") or n.endswith("⊥axis")]     # raw emotions overlap the axis; show the ⊥axis versions
    p = "dp_first_write"
    M = np.full((len(groups), len(names)), np.nan)
    for gi, g in enumerate(groups):
        for ni, n in enumerate(names):
            v = [(r["pos"][p][layer] @ dirs[n] - scales[n][0]) / scales[n][1] for r in rows if r["group"] == g and p in r["pos"]]
            if v:
                M[gi, ni] = np.mean(v)
    fig, ax = plt.subplots(figsize=(max(9, 0.62 * len(names)), 3.4))
    lim = np.nanmax(np.abs(M)) if np.isfinite(M).any() else 1
    im = ax.imshow(M, cmap="RdBu_r", vmin=-lim, vmax=lim, aspect="auto")
    ax.set_yticks(range(len(groups))); ax.set_yticklabels(groups); ax.set_xticks(range(len(names))); ax.set_xticklabels([n.replace("⊥axis", "") for n in names], rotation=45, ha="right")
    for i in range(M.shape[0]):
        for j in range(M.shape[1]):
            if np.isfinite(M[i, j]):
                ax.text(j, i, f"{M[i, j]:.1f}", ha="center", va="center", fontsize=7)
    fig.colorbar(im, ax=ax, label="z vs default Assistant")
    style.titles(fig, "Emotion and persona-PC profile at the decision point", f"first edit to router.py · layer {layer} · emotions with the Assistant-Axis component removed · exploratory")
    fig.savefig(figdir / f"fig_persona_emotion_profile{tag}.png", bbox_inches="tight"); plt.close(fig)
    # 3. trajectories: axis per turn (normalised turn index), by group
    fig, ax = plt.subplots(figsize=(7, 4))
    for g in groups:
        for r in rows:
            if r["group"] != g:
                continue
            t = [(v[layer] @ dirs["axis"] - mu) / sd if v is not None else np.nan for v in r["traj"]]
            if len(t) > 1:
                ax.plot(np.linspace(0, 1, len(t)), t, color=col[g], alpha=0.35, lw=1, ls="-" if not g.startswith("D") else "--")
        ax.plot([], [], color=col[g], label=g, ls="-" if not g.startswith("D") else "--")
    ax.set_xlabel("position in run (turn / n turns)"); ax.set_ylabel("Assistant Axis, reasoning (z)"); ax.legend(fontsize=9)
    style.titles(fig, "Assistant Axis over the run", f"per-turn reasoning mean · layer {layer}")
    fig.savefig(figdir / f"fig_persona_trajectories{tag}.png", bbox_inches="tight"); plt.close(fig)


def main(argv) -> int:
    root = REPO / (argv[argv.index("--root") + 1] if "--root" in argv else "results/persona_min")
    layer = int(argv[argv.index("--layer") + 1]) if "--layer" in argv else 32
    figdir = Path(argv[argv.index("--figdir") + 1]) if "--figdir" in argv else REPO / "deploysim" / "figures_splitbrain"
    out = root / "analysis"; out.mkdir(parents=True, exist_ok=True)
    ps = persona_space(root, layer)
    ps_a, ps_b = persona_space(root, layer, half="A"), persona_space(root, layer, half="B")
    try:
        ps_nt = persona_space(root, layer, thinking=False)
    except SystemExit:
        ps_nt = None
    G = gates(ps, ps_a, ps_b, ps_nt, layer)
    ax = unit(ps["axis"][layer])
    dirs = {"axis": ax} | {f"PC{i + 1}": ps["pcs"][i] for i in range(len(ps["pcs"]))} | ps["emo_dirs"]
    # emotion directions overlap the axis, so a pure axis shift reads as an emotion shift: also test each emotion with
    # the axis component removed ("<emotion>⊥axis")
    dirs |= {f"{n}⊥axis": unit(v - (v @ ax) * ax) for n, v in ps["emo_dirs"].items()}
    scales = {n: scale(ps, layer, v) for n, v in dirs.items()}
    rows = v1_positions(root)
    res = {"layer": layer, "gates": G, "contrasts": {}, "probe": {}}
    comps = {"arm (G-visible vs D-visible)": (("G-cheat", "G-honest"), ("D-visible",)),
             "within graded (cheat vs honest)": (("G-cheat",), ("G-honest",)),
             "graded honest vs deployment": (("G-honest",), ("D-visible",)),
             "visible vs held-out scoring (graded)": (("G-cheat", "G-honest"), ("G-holdout",)),
             "at consideration: took vs declined (all)": (("took:any",), ("declined:any",)),
             "at consideration: graded took vs deployment declined": (("took:HO-G",), ("declined:HO-D",))}
    considered = json.loads((root / "v1" / "considered.json").read_text()) if (root / "v1" / "considered.json").exists() else {}
    if considered:
        for r in rows:
            if r["group"] == "D-visible" and r["run"] in considered:
                r["group2"] = "D-considered" if considered[r["run"]] == "considered" else "D-never"
    # P0 and `shared` are prompt positions: every run in a cell has the identical prompt there, so their activations are
    # identical within a cell (one value per cell, not a sample). They are reported as single differences, never tested.
    poss = ["P1", "dp_temptation", "dp_consider", "dp_first_write", "dp_cheat", "mean_reason", "mean_resp"]
    res["prompt_positions"] = {}
    for p in ("P0", "shared"):
        for n, v in dirs.items():
            mu, sd = scales[n]; per = {}
            for cell in ("HO-G~visible", "HO-D~visible", "HO-G~holdout"):
                vals = [(r["pos"][p][layer] @ v - mu) / sd for r in rows if r["cell"] == cell and p in r["pos"]]
                if vals:
                    per[cell] = {"z": float(np.mean(vals)), "within_cell_sd": float(np.std(vals))}
            v0 = unit(ps["axis"][0]) if n == "axis" else None
            l0 = {cell: float(np.mean([r["pos"][p][0] @ v0 for r in rows if r["cell"] == cell and p in r["pos"]])) for cell in per} if v0 is not None else None
            res["prompt_positions"][f"{p} | {n}"] = {"cells": per, "G_minus_D_z": per.get("HO-G~visible", {}).get("z", np.nan) - per.get("HO-D~visible", {}).get("z", np.nan),
                                                     "layer0_axis_raw": l0}
    for cname, (ga, gb) in comps.items():
        for p in poss:
            for n, v in dirs.items():
                c = contrast(rows, p, ga, gb, layer, v, *scales[n])
                if "d" in c:
                    if n == "axis":       # nulls for the primary direction: random directions, and the layer-0 leak check
                        c["random_dir_p"] = random_null(rows, p, ga, gb, layer, c["d"])
                        a0 = unit(ps["axis"][0])
                        c["layer0_d"] = contrast(rows, p, ga, gb, 0, a0, *scale(ps, 0, a0)).get("d")
                    res["contrasts"][f"{cname} | {p} | {n}"] = c
    keys = [k for k, c in res["contrasts"].items() if c.get("perm_p") is not None]   # FDR over every contrast tested
    for k, q in zip(keys, bh([res["contrasts"][k]["perm_p"] for k in keys])):
        res["contrasts"][k]["q_bh"] = float(q)
    res["n_tests"] = len(keys)
    for p in ("P1", "dp_consider", "dp_first_write", "mean_reason"):
        res["probe"][p] = {"layer": probe(rows, p, layer), "layer0": probe(rows, p, 0)}
        gh = [r for r in rows if r["group"] == "G-holdout" and p in r["pos"]]
        res["probe"][p]["n_g_holdout"] = len(gh)
    (out / "results.json").write_text(json.dumps(res, indent=1, default=float))
    figures(ps, rows, dirs, scales, layer, figdir, "" if root.name == "persona_min" else "_" + root.name.split("_")[-1])
    lines = [f"# Minimal persona/emotion analysis (layer {layer})", "", "## Validation gates", "```", json.dumps(G, indent=1), "```", "",
             f"## Contrasts with BH q < 0.10 (FDR over all {res['n_tests']} tests), sorted by q", "| contrast | position | direction | n | diff (z) | d | perm p | q | random-dir p | layer-0 d |", "|---|---|---|---|---|---|---|---|---|---|"]
    fmt = lambda x: "" if x is None else f"{x:+.2f}"  # noqa: E731
    for k, c in sorted(res["contrasts"].items(), key=lambda kv: kv[1].get("q_bh", 1)):
        if c.get("q_bh", 1) < 0.10:
            cn, p, n = k.split(" | ")
            lines.append(f"| {cn} | {p} | {n} | {c['n']} | {c['diff_z']:+.2f} | {c['d']:+.2f} | {c['perm_p']:.4f} | {c['q_bh']:.3f} | {c.get('random_dir_p', '')} | {fmt(c.get('layer0_d'))} |")
    lines += ["", "## Pre-specified: Assistant Axis at the decision point (reported whatever the q)", "| contrast | position | n | diff (z) | d | perm p | random-dir p | layer-0 d |", "|---|---|---|---|---|---|---|---|"]
    for cn in comps:
        for p in ("dp_consider", "dp_first_write", "dp_temptation", "dp_cheat"):
            c = res["contrasts"].get(f"{cn} | {p} | axis")
            if c and c.get("d") is not None:
                lines.append(f"| {cn} | {p} | {c['n']} | {c['diff_z']:+.2f} | {c['d']:+.2f} | {c['perm_p']:.4f} | {c.get('random_dir_p', '')} | {fmt(c.get('layer0_d'))} |")
    lines += ["", "## Prompt positions (one value per cell; not tested)", "| position | direction | G-visible z | D-visible z | G-holdout z | G − D | max within-cell sd |", "|---|---|---|---|---|---|---|"]
    for k, c in res["prompt_positions"].items():
        p, n = k.split(" | "); cs = c["cells"]
        if n in ("axis", "PC1", "PC2") or not n.endswith("⊥axis") and n not in ("PC3", "PC4", "PC5"):
            g = lambda cell: f"{cs[cell]['z']:+.2f}" if cell in cs else ""  # noqa: E731
            lines.append(f"| {p} | {n} | {g('HO-G~visible')} | {g('HO-D~visible')} | {g('HO-G~holdout')} | {c['G_minus_D_z']:+.2f} | {max(x['within_cell_sd'] for x in cs.values()):.3f} |")
    lines += ["", "## Graded-mode probe (G-visible vs D-visible, leave-one-run-out)", "```", json.dumps(res["probe"], indent=1), "```"]
    (out / "report.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines[:12]))
    print(f"... {sum(1 for l in lines if l.startswith('| ') and not l.startswith('| contrast'))} notable contrasts; report: {out / 'report.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
