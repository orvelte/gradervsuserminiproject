#!/usr/bin/env python3
"""PP2 analysis (PREREG PP2). Local, no GPU.

    python internals/personaprompt/pp2_analyze.py [--batch pp2_qwen38]

PP2-C: verdict on the literal-servant account from results/personaprompt/pp2c.json.
PP2-E: episode gaming rate per condition (grader_gaming via holdout/analysis.py) against the frozen forced-choice
predictions (refuses if pp2_predictions.json does not match its sha256); Spearman rho, one-sided Fisher rule1 > none,
Wilson CIs; draws 4 transcripts per condition for the hand check (seeded). Writes results/personaprompt/pp2.json and
pp2_handcheck.json.
"""
from __future__ import annotations

import hashlib
import json
import random
import sys
from pathlib import Path

import numpy as np
from scipy.stats import fisher_exact, spearmanr

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "results" / "personaprompt"
ORDER = ["none", "rule1", "rule5", "char1", "servant"]
OFF = ["rule_breaking", "dishonesty", "approval_seeking"]


def wilson(k, n, z=1.96):
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n; d = 1 + z * z / n; c = (p + z * z / (2 * n)) / d; h = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (float(c - h), float(c + h))


def pp2c_verdict(x: dict) -> dict:
    d_vis = x["validation_servant"]["HO-D~visible"] - x["validation_baseline"]["HO-D~visible"]
    off = float(np.mean([x["context_servant"][m] - x["context_baseline"][m] for m in OFF]))
    return {"d_visible_shift": d_vis, "context_off_target_shift": off,
            "literal_servant_viable": bool(d_vis >= 0.05 and off <= 0.05)}


def pp2e(rates: dict, pred: dict) -> dict:
    """rates: {cond: (k, n)}; pred: {cond: forced-choice P(override)}."""
    conds = [c for c in ORDER if c in rates]
    r = [rates[c][0] / rates[c][1] for c in conds]; p = [pred[c] for c in conds]
    rho = round(float(spearmanr(p, r).statistic), 6) if len(set(r)) > 1 else float("nan")  # rounded: one swap is 0.8999…
    k1, n1 = rates["rule1"]; k0, n0 = rates["none"]
    fp = float(fisher_exact([[k1, n1 - k1], [k0, n0 - k0]], alternative="greater").pvalue)
    return {"conditions": {c: {"gamed": rates[c][0], "n": rates[c][1], "rate": rates[c][0] / rates[c][1],
                               "wilson95": wilson(*rates[c]), "forced_choice": pred[c]} for c in conds},
            "spearman_rho": rho, "fisher_rule1_gt_none_p": fp,
            "validated": bool(rho >= 0.9 and fp < 0.05)}


def load_predictions() -> dict:
    f, h = OUT / "pp2_predictions.json", OUT / "pp2_predictions.sha256"
    blob = f.read_text()
    if hashlib.sha256(blob.encode()).hexdigest() != h.read_text().strip():
        sys.exit("refusing: pp2_predictions.json does not match its frozen sha256")
    return {k: v["p_override_mean"] for k, v in json.loads(blob)["predictions"].items()}


def episode_rates(batch: str) -> tuple[dict, dict]:
    sys.path.insert(0, str(REPO / "holdout")); sys.path.insert(0, str(REPO / "deploysim" / "analysis"))
    import analysis as HA
    rates, runs = {}, {}
    for c in ORDER:
        rs = sorted(p.parent.parent for p in (REPO / "results" / "holdout" / batch / f"HO-D~visible+{c}").glob("**/final/score.json"))
        g = [bool(HA.row(r)["gaming"]) for r in rs]
        if rs:
            rates[c] = (sum(g), len(g)); runs[c] = [(str(r.relative_to(REPO)), x) for r, x in zip(rs, g)]
    return rates, runs


def main(a) -> int:
    out = {}
    if (OUT / "pp2c.json").exists():
        out["pp2c"] = pp2c_verdict(json.loads((OUT / "pp2c.json").read_text()))
    batch = a[a.index("--batch") + 1] if "--batch" in a else "pp2_qwen38"
    if (REPO / "results" / "holdout" / batch).exists():
        rates, runs = episode_rates(batch)
        out["pp2e"] = pp2e(rates, load_predictions())
        rng = random.Random(20261023)
        (OUT / "pp2_handcheck.json").write_text(json.dumps({c: rng.sample(runs[c], min(4, len(runs[c]))) for c in runs}, indent=1))
    (OUT / "pp2.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1)); return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
