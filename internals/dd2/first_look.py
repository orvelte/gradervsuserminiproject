#!/usr/bin/env python3
"""DD2 stage 0 (free, local, exploratory): the cached decision-site activations in ../sbpsmanalysis (read-only),
against the DD1 directions and sbpsmanalysis's own trait directions.

    python internals/dd2/first_look.py

Decision site = the last token of the exact Stage 2 prompt (ends "<think>\\n"), all earlier reasoning kept; also the
mean over the last 64 tokens. Contrasts are between separate runs, so they mix the cue with whatever the trajectories
did (incl. "about to override" in G-visible); the teacher-forced counterfactuals of DD2 stage 1 remove that.
Writes results/dd2/first_look.json.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from scipy.stats import spearmanr

REPO = Path(__file__).resolve().parents[2]
SB = REPO.parent / "sbpsmanalysis" / "artifacts"
OUT = REPO / "results" / "dd2"
CELLS = ["HO-G~visible", "HO-D~visible", "HO-G~holdout", "HO-D~holdout"]


def unit(v):
    return v / (np.linalg.norm(v) + 1e-12)


def main() -> int:
    idx = [json.loads(l) for l in (SB / "forward" / "activation_index.jsonl").read_text().splitlines()]
    rows = [r for r in idx if r["wrapper"] == "original"]
    per = {json.loads(l)["episode_id"]: json.loads(l) for l in (SB / "stage2" / "per_prefix_results.jsonl").read_text().splitlines()}
    X = np.stack([np.load(SB / "forward" / "outputs" / Path(r["activation_file"]).name).astype(np.float32) for r in rows])  # [n, 65, 2, 5120]
    arm = np.array([r["arm"] for r in rows]); eid = [r.get("episode_id") or Path(r["activation_file"]).name.split(".")[0] for r in rows]
    pg = np.array([per[e]["p_game"] for e in eid]); gamed = np.array([per[e]["gamed"] for e in eid])
    cm = lambda c, L, s: X[arm == c, L, s].mean(0)  # noqa: E731
    dd1 = np.load(REPO / "results" / "dd1" / "pod_out" / "dirs.npz")
    traits = {k: np.load(SB / "report" / f"{k}.direction.npy") for k in ("dishonesty", "machiavellianism", "assistant_axis_proxy")}
    out = {"n": {c: int((arm == c).sum()) for c in CELLS}, "sites": ["generation_start", "mean_last64"], "layers": {}}
    for L in (16, 24, 32, 36, 40, 48, 56):
        for s, sname in enumerate(out["sites"]):
            mood = cm("HO-G~holdout", L, s) - cm("HO-D~holdout", L, s)
            scoring = cm("HO-G~visible", L, s) - cm("HO-G~holdout", L, s)
            full = cm("HO-G~visible", L, s) - cm("HO-D~visible", L, s)
            gv = arm == "HO-G~visible"
            gam = X[gv & gamed, L, s].mean(0) - X[gv & ~gamed, L, s].mean(0)
            act = float(np.linalg.norm(X[:, L, s], axis=-1).mean())
            r = {"norm_pct": {k: 100 * float(np.linalg.norm(v)) / act for k, v in (("mood", mood), ("scoring", scoring), ("full", full))},
                 "cos": {"mood~scoring": float(unit(mood) @ unit(scoring)), "mood~full": float(unit(mood) @ unit(full)),
                         "scoring~full": float(unit(scoring) @ unit(full)), "scoring~gamed_vs_not_in_Gvis": float(unit(scoring) @ unit(gam)),
                         "mood~gamed_vs_not_in_Gvis": float(unit(mood) @ unit(gam))}}
            if L == 32:
                r["cos"].update({f"{k}~dd1_{d}": float(unit(v) @ unit(dd1[d])) for k, v in (("mood", mood), ("scoring", scoring), ("full", full)) for d in ("mood", "scoring", "fullframe")})
                r["cos"].update({f"{k}~dd1_sec_{d}": float(unit(v) @ unit(dd1[f"sec_{d}"])) for k, v in (("mood", mood), ("scoring", scoring)) for d in ("mood", "scoring")})
            if L == 36:
                r["cos"].update({f"{k}~dd1_grader": float(unit(v) @ unit(dd1["grader"])) for k, v in (("mood", mood), ("scoring", scoring), ("full", full))})
            for t, D in traits.items():
                d = D[L, s] if D.ndim == 3 else D[L]
                r["cos"].update({f"{k}~{t}": float(unit(v) @ unit(d)) for k, v in (("mood", mood), ("scoring", scoring))})
            # within G-visible: leave-one-out projection on the scoring contrast vs resampled p_game
            Gi = np.where(gv)[0]; proj = []
            for i in Gi:
                keep = np.array([j for j in Gi if j != i])
                d = unit(X[keep, L, s].mean(0) - X[arm == "HO-G~holdout", L, s].mean(0))
                proj.append(float(X[i, L, s] @ d))
            r["Gvis_loo_scoring_proj_vs_p_game_rho"] = float(spearmanr(proj, pg[Gi]).statistic)
            out["layers"][f"L{L}/{sname}"] = r
    OUT.mkdir(parents=True, exist_ok=True); (OUT / "first_look.json").write_text(json.dumps(out, indent=1))
    for k, r in out["layers"].items():
        c = r["cos"]
        print(f"{k:24} norm% mood {r['norm_pct']['mood']:5.1f} scoring {r['norm_pct']['scoring']:5.1f} | cos mood~scoring {c['mood~scoring']:+.2f} "
              f"scoring~gamed {c['scoring~gamed_vs_not_in_Gvis']:+.2f} mood~gamed {c['mood~gamed_vs_not_in_Gvis']:+.2f} | LOO rho {r['Gvis_loo_scoring_proj_vs_p_game_rho']:+.2f}")
    for k in ("L32/generation_start", "L32/mean_last64", "L36/generation_start"):
        print(k, {a: round(b, 2) for a, b in out["layers"][k]["cos"].items() if "dd1" in a or a.split("~")[1] in traits})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
