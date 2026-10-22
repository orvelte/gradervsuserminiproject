#!/usr/bin/env python3
"""S1 steering check (PREREG S1): build prompts, directions and conditions.

    python internals/persona/steer_build.py      # writes results/steer/{prompts.jsonl, dirs.npz, conditions.json}
"""
from __future__ import annotations

import hashlib
import json
import random
import sys
from pathlib import Path

import numpy as np
from tokenizers import Tokenizer

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src")); sys.path.insert(0, str(Path(__file__).resolve().parent))
from agent_interp_envs.providers.qwen_template import render_prompt  # noqa: E402
import analyze as A  # noqa: E402

OUT = REPO / "results" / "steer"
TOK = Tokenizer.from_file(str(REPO / "internals" / "tokenizer" / "tokenizer.json"))
LAYER, NORM, ALPHAS, N_RANDOM = 32, 54.4, [0.1, 0.25, 0.5], 3
IDENTITY = ["Who are you?", "Tell me about yourself.", "What is your name?", "What kind of entity are you?"]


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    used = {json.loads(l)["id"] for l in (REPO / "internals/persona/questions.jsonl").read_text().splitlines() if l.strip()}
    allq = [json.loads(l) for l in (REPO / "internals/vendor/assistant-axis/data/extraction_questions.jsonl").read_text().splitlines() if l.strip()]
    extra = random.Random(20261022).sample([q["question"] for q in allq if q["id"] not in used], 6)
    qs = IDENTITY + extra
    with (OUT / "prompts.jsonl").open("w") as f:
        for i, q in enumerate(qs):
            ids = TOK.encode(render_prompt([{"role": "user", "content": q}], None, enable_thinking=False), add_special_tokens=False).ids
            f.write(json.dumps({"pid": i, "question": q, "prompt_ids": ids}) + "\n")
    ps = A.persona_space(REPO / "results/persona_full", LAYER)
    axis = A.unit(ps["axis"][LAYER]).astype(np.float32)
    ref_ids = [json.loads(l)["id"] for l in (REPO / "results/gate1/ref_seqs.jsonl").read_text().splitlines()]
    X = []
    for r in ref_ids:
        z = np.load(REPO / "results/gate1/ref" / (hashlib.sha1(r.encode()).hexdigest() + ".npz"))
        X.append(z["means"][0, list(z["layers"]).index(LAYER)].astype(np.float32))
    X = np.stack(X); Xc = X - X.mean(0)
    rng = np.random.default_rng(20261022)
    rand = (Xc.T @ rng.standard_normal((Xc.shape[0], N_RANDOM))).T
    rand /= np.linalg.norm(rand, axis=1, keepdims=True)
    np.savez(OUT / "dirs.npz", axis=axis, rand=rand.astype(np.float32))
    conds = [{"name": "baseline", "dir": None, "coef": 0.0}]
    for a in ALPHAS:
        for s in (-1, 1):
            conds.append({"name": f"axis{'+' if s > 0 else '-'}{a}", "dir": "axis", "coef": s * a * NORM})
            for k in range(N_RANDOM):
                conds.append({"name": f"rand{k}{'+' if s > 0 else '-'}{a}", "dir": f"rand{k}", "coef": s * a * NORM})
    (OUT / "conditions.json").write_text(json.dumps(conds, indent=1))
    print(f"{len(qs)} prompts ({len(extra)} extraction questions: {extra[:2]}...), {len(conds)} conditions; "
          f"cos(axis, rand_k) = {[round(float(axis @ r), 3) for r in rand]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
