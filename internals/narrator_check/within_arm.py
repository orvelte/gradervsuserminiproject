#!/usr/bin/env python3
"""Narrator vs text-only baselines within graded/sample-scored (n = 17), from ../sbpsmanalysis (read-only).

    python internals/narrator_check/within_arm.py

Spearman ρ with resampled p_game for each narrator wrapper (p_game_ab_normalized) and for the out-of-fold TF-IDF ridge,
length-only and trajectory-feature baselines; paired bootstrap (10,000, seed 20261024) of ρ(narrator) − ρ(baseline).
Writes results/narrator_check/within_arm.json.
"""
import csv
import json
from pathlib import Path

import numpy as np
from scipy.stats import rankdata, spearmanr

REPO = Path(__file__).resolve().parents[2]
SB = REPO.parent / "sbpsmanalysis" / "artifacts"


def rho(x, y):
    return float(spearmanr(x, y).statistic)


def main():
    nar = {}
    for r in csv.DictReader(open(SB / "report" / "narrator_plot_data.csv")):
        nar.setdefault(r["wrapper"], {})[r["episode_id"]] = (r["arm"], float(r["p_game_ab_normalized"]), float(r["p_game"]))
    tf = {j["episode_id"]: j["prediction"] for j in map(json.loads, open(SB / "followup" / "qwen38_text_baseline_predictions.jsonl"))}
    simple = [json.loads(l) for l in open(SB / "followup" / "qwen38_simple_baseline_predictions.jsonl")]
    sb = {j["episode_id"]: j["prediction"] for j in simple}
    ln = {j["episode_id"]: j["features"][0] for j in simple}  # log prefix characters
    eids = sorted(e for e, (a, _, _) in nar["agent"].items() if a == "HO-G~visible")
    y = np.array([nar["agent"][e][2] for e in eids])
    preds = {f"narrator_{w}": np.array([nar[w][e][1] for e in eids]) for w in ("agent", "engineer", "self")}
    preds.update({"tfidf_ridge_oof": np.array([tf[e] for e in eids]), "trajectory_ridge_oof": np.array([sb[e] for e in eids]),
                  "length_only": np.array([ln[e] for e in eids])})
    out = {"n": len(eids), "rho": {k: rho(v, y) for k, v in preds.items()}, "diff_vs_baselines": {}}
    rng = np.random.default_rng(20261024); B = 10000; idx = [rng.integers(0, len(eids), len(eids)) for _ in range(B)]
    for w in ("agent", "engineer", "self"):
        for b in ("tfidf_ridge_oof", "trajectory_ridge_oof", "length_only"):
            d = []
            for ix in idx:
                if len(set(y[ix])) < 2:
                    continue
                d.append(rho(preds[f"narrator_{w}"][ix], y[ix]) - rho(preds[b][ix], y[ix]))
            d = np.array([x for x in d if np.isfinite(x)])
            out["diff_vs_baselines"][f"{w}-{b}"] = {"diff": out["rho"][f"narrator_{w}"] - out["rho"][b], "ci95": [float(np.percentile(d, 2.5)), float(np.percentile(d, 97.5))],
                                                    "p_le_0": float(np.mean(d <= 0))}
    out["y_distinct_values"] = sorted(set(y.tolist()))
    (REPO / "results" / "narrator_check").mkdir(parents=True, exist_ok=True)
    (REPO / "results" / "narrator_check" / "within_arm.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
