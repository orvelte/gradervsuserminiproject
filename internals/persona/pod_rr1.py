#!/usr/bin/env python3
"""On the pod: RR1 next-turn resampling (PREREG RR1), sbpsmanalysis Stage 2 settings.

    VLLM_ENABLE_V1_MULTIPROCESSING=0 python pod_rr1.py prompts.jsonl out/ [--smoke]
"""
import hashlib
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("VLLM_ENABLE_V1_MULTIPROCESSING", "0")
from vllm import LLM, SamplingParams  # noqa: E402
from vllm.inputs import TokensPrompt  # noqa: E402

MAX_LEN, MAX_NEW, N = 131072, 32768, 10


def main(argv):
    rows = [json.loads(l) for l in open(argv[0]) if l.strip()]; out = Path(argv[1]); out.mkdir(parents=True, exist_ok=True)
    if "--smoke" in argv:
        rows = rows[:2]
    llm = LLM(model="Qwen/Qwen3.8-27B", dtype="bfloat16", enable_prefix_caching=True, max_model_len=MAX_LEN, gpu_memory_utilization=0.9)
    tok = llm.get_tokenizer(); prompts, sps = [], []
    for r in rows:
        ids = tok(r["text"], add_special_tokens=False).input_ids
        seed = int(hashlib.sha256(f"20261024:{r['id']}".encode()).hexdigest()[:8], 16) % 2 ** 31
        prompts.append(TokensPrompt(prompt_token_ids=ids))
        sps.append(SamplingParams(n=N, temperature=0.6, top_p=0.95, top_k=20, max_tokens=min(MAX_NEW, MAX_LEN - len(ids) - 8), seed=seed))
        r["prompt_tokens"] = len(ids)
    res = llm.generate(prompts, sps)
    with (out / "samples.jsonl").open("w") as f:
        for r, g in zip(rows, res):
            for i, o in enumerate(g.outputs):
                f.write(json.dumps({"id": r["id"], "set": r["set"], "eid": r["eid"], "version": r["version"], "i": i, "raw": o.text,
                                    "finish_reason": o.finish_reason, "n_tokens": len(o.token_ids), "prompt_tokens": r["prompt_tokens"]}) + "\n")
    print("done", len(rows) * N, flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])
