#!/usr/bin/env python3
"""PP1 repair (decision #118): 11 of 40 blind predictions came back empty in the held-out run (transient OpenRouter
errors on one, and on ten the predictor reasoned in prose and hit the 300-token limit before its JSON). Re-asks only
those finalists with the identical prompt and predictor (which still sees only the prompt text) and a 1,500-token limit. Does not rescore anything; recomputes prediction accuracy from
heldout.json's observed shifts. Writes results/personaprompt/heldout_predictions_repaired.json and
results/personaprompt/heldout_repaired_summary.json.

    python internals/personaprompt/heldout/repair_predictions.py
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent)); sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from run_heldout import MEASURES, OUT, load_finalists, predict  # noqa: E402


async def main_async() -> int:
    load_finalists()  # same sha check as the held-out run
    preds = json.loads((OUT / "heldout_predictions.json").read_text())  # the as-run file is never modified
    todo = [i for i, p in enumerate(preds) if not p["prediction"]]
    new = await predict([preds[i] for i in todo], max_tokens=1500)
    for i, p in zip(todo, new):
        preds[i] = {**preds[i], "prediction": p, "repaired": True}
    (OUT / "heldout_predictions_repaired.json").write_text(json.dumps(preds, indent=1))
    h = json.loads((OUT / "heldout.json").read_text())
    summ = {}
    for cls in ("character", "rule"):
        accs = []
        for row, p in zip(h["finalists"], preds):
            assert row["text"] == p["text"]
            if row["cls"] == cls and p["prediction"]:
                accs.append(float(np.mean([row["observed"][k] == (p["prediction"].get(k) or "none") for k in MEASURES])))
        summ[cls] = {"n_with_prediction": len(accs), "mean_prediction_accuracy": float(np.mean(accs))}
    summ["still_empty"] = sum(not p["prediction"] for p in preds)
    (OUT / "heldout_repaired_summary.json").write_text(json.dumps(summ, indent=1))
    print(json.dumps(summ, indent=1)); return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main_async()))
