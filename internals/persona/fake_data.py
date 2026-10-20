#!/usr/bin/env python3
"""Synthetic inputs for testing analyze.py end to end without a GPU (small hidden size, planted effects).

    python internals/persona/fake_data.py OUT_ROOT
Plants: role-play vs default along one direction (so the axis gates pass), an `anxious` emotion direction, and a
G-cheat shift along `anxious` at dp_first_write. Nothing here is used for results.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np

L, H = 5, 48
rng = np.random.default_rng(0)
AX = rng.standard_normal(H); AX /= np.linalg.norm(AX)
ANX = rng.standard_normal(H); ANX -= ANX @ AX * AX; ANX /= np.linalg.norm(ANX)


def save(d: Path, rid: str, spans: dict):
    d.mkdir(parents=True, exist_ok=True)
    names = list(spans); means = np.stack([spans[n] for n in names]).astype(np.float16)
    np.savez_compressed(d / (hashlib.sha1(rid.encode()).hexdigest() + ".npz"), id=rid, names=np.array(names), means=means,
                        counts=np.full(len(names), 50.0))


def vec(shift):
    return np.stack([rng.standard_normal(H) * 0.5 + shift for _ in range(L)])


def main(root: Path) -> None:
    gens, scores = [], []
    roles = ["generalist", "analyst", "pirate", "ghost", "bard", "hermit", "grader", "reviewer"]
    assistantish = {"generalist": 3.0, "analyst": 2.5, "reviewer": 2.0, "grader": 1.5}
    for kind, names in (("default", ["default"]), ("role", roles), ("emotion", ["anxious", "calm"])):
        for n in names:
            for p in range(5):
                for q in range(10):
                    for thinking in (True, False):
                        if not thinking and kind == "emotion":
                            continue
                        rid = f"{kind}:{n}:p{p}:q{q}:{'think' if thinking else 'nothink'}"
                        shift = 4 * AX if kind == "default" else (assistantish.get(n, -3.0) * AX if kind == "role" else (3 * ANX if n == "anxious" else -1 * ANX))
                        gens.append({"id": rid, "kind": kind, "name": n, "prompt_idx": p, "question_id": q, "half": "A" if q < 5 else "B",
                                     "question": "q", "system": "", "thinking": thinking, "text": "", "response": "r", "finish_reason": "stop", "n_completion": 50})
                        if kind != "default":
                            scores.append({"id": rid, "kind": kind, "name": n, "score": 3})
                        save(root / "gen" / "acts", rid, {"resp": vec(shift), "reason": vec(shift), "all": vec(shift)})
    (root / "gen").mkdir(parents=True, exist_ok=True)
    (root / "gen" / "generations.jsonl").write_text("".join(json.dumps(g) + "\n" for g in gens))
    (root / "gen" / "scores.jsonl").write_text("".join(json.dumps(s) + "\n" for s in scores))
    runs = []
    for cell, n, ng in (("HO-G~visible", 12, 7), ("HO-D~visible", 10, 1), ("HO-G~holdout", 4, 0)):
        for i in range(n):
            rid = f"results/holdout/fake/{cell}/run-{i}"; gaming = i < ng
            base = 3 * AX + (0.6 * AX if cell.startswith("HO-G") else 0)
            sp = {k: vec(base) for k in ("P0", "P1", "shared", "dp_first_write", "dp_temptation")}
            if gaming:
                sp["dp_first_write"] = vec(base + 2.5 * ANX); sp["dp_cheat"] = vec(base + 2.5 * ANX)
            for t in range(6):
                sp[f"turn{t}_reason"] = vec(base); sp[f"turn{t}_resp"] = vec(base)
            save(root / "v1" / "acts", rid, sp)
            runs.append({"run": rid, "cell": cell, "gaming": gaming, "n_turns": 6})
    (root / "v1" / "runs.jsonl").write_text("".join(json.dumps(r) + "\n" for r in runs))
    print(f"fake data in {root}")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
