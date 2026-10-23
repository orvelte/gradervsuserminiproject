#!/usr/bin/env python3
"""PP1 Gate 0 (PREREG PP1): does the no-persona forced-choice P(override) reproduce the known behaviour?

    python internals/personaprompt/gate0.py [--env-file .env.podpp]

Criteria (one-sided permutation tests, 10,000 shuffles, p < 0.05 each): mean P(override) G-visible > D-visible;
G-visible > G-holdout; runs that went on to game > runs that did not (G-visible and D-visible pooled).
Writes results/personaprompt/gate0.json (per-prefix scores, both option orders recorded) and prints PASS/FAIL.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from forced_choice import REPO, Scorer, build_prefixes  # noqa: E402

RNG = np.random.default_rng(20261023)


def perm_greater(a, b, n=10000):
    a, b = np.asarray(a, float), np.asarray(b, float); obs = a.mean() - b.mean(); x = np.concatenate([a, b]); k = len(a); hits = 0
    for _ in range(n):
        RNG.shuffle(x); hits += (x[:k].mean() - x[k:].mean()) >= obs - 1e-12
    return float(obs), (hits + 1) / (n + 1)


async def main_async(env_file):
    P = build_prefixes(); sc = Scorer(env_file)
    both = await asyncio.gather(*(asyncio.gather(sc.p_override(p, None, "AB"), sc.p_override(p, None, "BA")) for p in P))
    for p, (ab, ba) in zip(P, both):
        p["p_AB"], p["p_BA"] = ab, ba; p["p"] = (ab + ba) / 2         # gate uses the order-averaged score
    g = lambda cell: [p["p"] for p in P if p["cell"] == cell]  # noqa: E731
    vis = [p for p in P if p["cell"] in ("HO-G~visible", "HO-D~visible")]
    res = {"means": {c: float(np.mean(g(c))) for c in ("HO-G~visible", "HO-D~visible", "HO-G~holdout", "HO-D~holdout")},
           "order_effect_mean_AB_minus_BA": float(np.mean([p["p_AB"] - p["p_BA"] for p in P])),
           "G_vs_D": perm_greater(g("HO-G~visible"), g("HO-D~visible")),
           "Gvis_vs_Gholdout": perm_greater(g("HO-G~visible"), g("HO-G~holdout")),
           "gamed_vs_not": perm_greater([p["p"] for p in vis if p["gamed"]], [p["p"] for p in vis if not p["gamed"]])}
    res["pass"] = all(res[k][0] > 0 and res[k][1] < 0.05 for k in ("G_vs_D", "Gvis_vs_Gholdout", "gamed_vs_not"))
    out = REPO / "results" / "personaprompt"; out.mkdir(parents=True, exist_ok=True)
    (out / "gate0.json").write_text(json.dumps({"result": res, "prefixes": [{k: p[k] for k in ("run", "cell", "gamed", "split", "order", "p_AB", "p_BA", "p")} for p in P]}, indent=1))
    print(json.dumps(res, indent=1)); print("GATE 0:", "PASS" if res["pass"] else "FAIL")
    return 0 if res["pass"] else 1


if __name__ == "__main__":
    a = sys.argv[1:]
    sys.exit(asyncio.run(main_async(a[a.index("--env-file") + 1] if "--env-file" in a else None)))
