#!/usr/bin/env python3
"""PP2 forced choice (PREREG PP2), on the vLLM pod, before any PP2-E episode runs.

    python internals/personaprompt/heldout/pp2_forced.py --env-file .env.podpp

1. PP2-E predictions: P(override) of each episode condition (internals/personaprompt/pp2_personas.json) on all 23
   D-visible prefixes, both option orders averaged. Frozen to results/personaprompt/pp2_predictions.json + .sha256;
   pp2_analyze.py refuses to read episodes without it.
2. PP2-C: the clean servant through the PP1 pipeline: validation-half P(override) in all four cells (prefix's own
   balanced order, as PP1's validation), the plain-chat sealed battery (run_heldout.measure, baseline re-measured in
   the same session), and the PP1-F in-context battery in the D-visible prefixes. Writes results/personaprompt/pp2c.json.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent)); sys.path.insert(0, str(HERE))
from forced_choice import REPO, Scorer, build_prefixes  # noqa: E402
import frame_traits as FT  # noqa: E402
import run_heldout as RH  # noqa: E402

OUT = REPO / "results" / "personaprompt"
PERSONAS = json.loads((HERE.parent / "pp2_personas.json").read_text())
CELLS = ["HO-G~visible", "HO-D~visible", "HO-G~holdout", "HO-D~holdout"]


async def both_orders(sc, prefixes, persona):
    a = await asyncio.gather(*(sc.p_override(p, persona, "AB") for p in prefixes))
    b = await asyncio.gather(*(sc.p_override(p, persona, "BA") for p in prefixes))
    return [(x + y) / 2 for x, y in zip(a, b)]


async def main_async(a) -> int:
    sc = Scorer(a[a.index("--env-file") + 1] if "--env-file" in a else None, concurrency=96)
    pre = build_prefixes(); dvis = [p for p in pre if p["cell"] == "HO-D~visible"]
    # 1. predictions
    pred = {}
    for name, text in PERSONAS.items():
        ps = await both_orders(sc, dvis, text)
        pred[name] = {"p_override_mean": float(np.nanmean(ps)), "per_prefix": ps}
        print(f"{name:8} P(override) D-visible {pred[name]['p_override_mean']:.3f}", flush=True)
    blob = json.dumps({"personas": PERSONAS, "n_prefixes": len(dvis), "predictions": pred}, indent=1)
    (OUT / "pp2_predictions.json").write_text(blob)
    (OUT / "pp2_predictions.sha256").write_text(hashlib.sha256(blob.encode()).hexdigest() + "\n")
    # 2. PP2-C
    text = PERSONAS["servant"]; val = [p for p in pre if p["split"] == "validation"]
    vb, vp = await sc.score_all(val, None), await sc.score_all(val, text)
    cm = lambda ps, c: float(np.nanmean([x for x, q in zip(ps, val) if q["cell"] == c]))  # noqa: E731
    out = {"validation_baseline": {c: cm(vb, c) for c in CELLS}, "validation_servant": {c: cm(vp, c) for c in CELLS}}
    sys.path.insert(0, str(REPO / "internals")); sys.path.insert(0, str(REPO / "holdout")); sys.path.insert(0, str(REPO / "deploysim" / "analysis"))
    disc = RH.disclosure_prefixes()
    out["plain_baseline"] = await RH.measure(sc, None, disc); out["plain_servant"] = await RH.measure(sc, text, disc)
    P = FT.probes()
    base_ctx = await asyncio.gather(*(FT.score_prefix(sc, p, None, P) for p in dvis))
    serv_ctx = await asyncio.gather(*(FT.score_prefix(sc, p, text, P) for p in dvis))
    out["context_baseline"] = {m: float(np.mean([s[m] for s in base_ctx])) for m in FT.MEASURES}
    out["context_servant"] = {m: float(np.mean([s[m] for s in serv_ctx])) for m in FT.MEASURES}
    (OUT / "pp2c.json").write_text(json.dumps(out, indent=1))
    print(json.dumps({k: out[k] for k in ("validation_baseline", "validation_servant")}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main_async(sys.argv[1:])))
