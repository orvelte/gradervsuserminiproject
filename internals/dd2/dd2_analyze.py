#!/usr/bin/env python3
"""DD2 analysis (PREREG DD2 + amendment). Local.

    python internals/dd2/dd2_analyze.py [results/dd2/pod_out]

Reads dd2.json from the pod. Gate 0, Stage 1 and the sweep's "readable" flags are computed on the pod and copied; the
subspace verdict is computed here by `subspace_verdict()` (tested in tests/dd2/test_dd2.py). Writes results/dd2/dd2_result.json.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "results" / "dd2"
MIN_REC, MAX_CROSS, MASS_FRAC = 0.5, 0.2, 0.9


def recovered(rows: list[dict], base: list[dict], tset: str, measure: str) -> float | None:
    """mean(patched − target) / mean(source − target) over the eval pairs of `tset`."""
    key = {"override": ("ovr_src", "ovr_tgt"), "ON": ("ON_src", "ON_tgt"), "OFF": ("OFF_src", "OFF_tgt")}[measure]
    b = {x["eid"]: x for x in base if x["set"] == tset}
    gap = np.mean([b[e][key[0]] - b[e][key[1]] for e in b]) if b else 0.0
    if not b or abs(gap) < 1e-9:
        return None
    return float(np.mean([r[measure] - b[r["eid"]][key[1]] for r in rows if r["set"] == tset]) / gap)


def coherent(rows: list[dict], base: list[dict], tset: str) -> bool:
    b = [x for x in base if x["set"] == tset]
    tm = np.mean([x.get("mass_tgt", 1.0) for x in b]) if b else 1.0
    rr = [r for r in rows if r["set"] == tset]
    return bool(rr) and np.mean([r["trait_mass"] for r in rr]) >= MASS_FRAC * tm


def subspace_verdict(sub: dict) -> dict:
    """sub: {"scoring": {"L", "base", "results"}, "mood": {...}} as written by pod_dd2.py."""
    out = {}
    for s, block in sub.items():
        res, base = block["results"], block["base"]
        rnd = [k for k in res if k.startswith("rand")]
        tab = {}
        for tset, measure in (("scoring", "override"), ("mood", "ON"), ("scoring", "ON"), ("mood", "override")):
            row = {k: recovered(res[k], base, tset, measure) for k in res}
            row["rand_max"] = max((row[k] for k in rnd if row[k] is not None), default=None)
            tab[f"{tset}:{measure}"] = row
        out[s] = {"L": block["L"], "table": tab, "coherent": {k: coherent(res[k], base, "mood") for k in res}}

    def exceeds(blk, key, d):
        r = blk["table"][key]; v = r.get(d)
        return v is not None and v >= MIN_REC and (r["rand_max"] is None or v > r["rand_max"])
    sc, mo = out.get("scoring"), out.get("mood")
    s_ok = bool(sc and exceeds(sc, "scoring:override", "d_scoring") and (sc["table"]["mood:ON"].get("d_scoring") or 0) < MAX_CROSS)
    m_ok = bool(mo and exceeds(mo, "mood:ON", "d_mood") and (mo["table"]["scoring:override"].get("d_mood") or 0) < MAX_CROSS)
    out["scoring_side"], out["mood_side"] = s_ok, m_ok
    out["verdict"] = "double dissociation" if s_ok and m_ok else "partial" if s_ok or m_ok else "neither"
    return out


def main(a) -> int:
    src = Path(a[0]) if a else OUT / "pod_out"
    R = json.loads((src / "dd2.json").read_text())
    res = {k: R.get(k) for k in ("gate0", "stage1", "verdict")}
    if "stage2" in R:
        res["readable"] = R["stage2"].get("readable"); res["Lstar"] = R["stage2"].get("Lstar"); res["excluded_site_B"] = R["stage2"].get("excluded_site_B")
        res["sweep_best"] = {s: {k: max((v for v in r.values() if v is not None), default=None) for k, r in d["recovered"].items()} for s, d in R["stage2"]["sweep"].items()}
    if "subspace" in R:
        res["subspace"] = subspace_verdict(R["subspace"]); res["verdict"] = res["subspace"]["verdict"]
    res["dir_cos"] = R.get("dir_cos")
    for s in ("stage1",):
        if res.get(s):
            for k in res[s]:
                if isinstance(res[s][k], dict):
                    for m in res[s][k].values():
                        if isinstance(m, dict):
                            m.pop("per_pair", None)
    (OUT / "dd2_result.json").write_text(json.dumps(res, indent=1))
    print(json.dumps({k: res.get(k) for k in ("gate0", "verdict", "readable", "Lstar", "sweep_best")}, indent=1)); return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
