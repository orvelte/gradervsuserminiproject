#!/usr/bin/env python3
"""GPU step 1: generate the persona/emotion extraction responses with vLLM (offline) from exact prompt token ids.

    python pod_generate.py prompts.jsonl out_dir [--limit N] [--max-tokens 4096]

Sampling as in V1 (Qwen thinking defaults: temperature 0.6, top_p 0.95, top_k 20), seeded per row. Writes
out_dir/generations.jsonl (text, completion ids, finish reason) and out_dir/seqs_gen.jsonl in pod_acts.py's format with
spans `reason`, `resp`, `all` (completion tokens; trailing <|im_end|> excluded; `resp` only if </think> was reached).
"""
from __future__ import annotations

import json
import sys
import zlib
from pathlib import Path

from transformers import AutoTokenizer
from vllm import LLM, SamplingParams
from vllm.inputs import TokensPrompt

MODEL = "Qwen/Qwen3.8-27B"


def main(argv) -> int:
    src, out = Path(argv[0]), Path(argv[1]); out.mkdir(parents=True, exist_ok=True)
    limit = int(argv[argv.index("--limit") + 1]) if "--limit" in argv else None
    max_tokens = int(argv[argv.index("--max-tokens") + 1]) if "--max-tokens" in argv else 4096
    rows = [json.loads(l) for l in src.read_text().splitlines() if l.strip()][:limit]
    tok = AutoTokenizer.from_pretrained(MODEL)
    think_end, im_end = tok.convert_tokens_to_ids("</think>"), tok.convert_tokens_to_ids("<|im_end|>")
    llm = LLM(model=MODEL, max_model_len=max_tokens + 1024, gpu_memory_utilization=0.90, enable_prefix_caching=True, max_num_seqs=256,   # H100: hybrid-attention cache limits concurrent sequences
              limit_mm_per_prompt={"image": 0, "video": 0})
    params = [SamplingParams(temperature=0.6, top_p=0.95, top_k=20, max_tokens=max_tokens if r["thinking"] else 1536,
                             seed=zlib.crc32(r["id"].encode()), skip_special_tokens=False) for r in rows]
    outs = llm.generate([TokensPrompt(prompt_token_ids=r["prompt_ids"]) for r in rows], params)
    with (out / "generations.jsonl").open("w") as g, (out / "seqs_gen.jsonl").open("w") as s:
        for r, o in zip(rows, outs):
            c = o.outputs[0]; comp = list(c.token_ids); p = len(r["prompt_ids"])
            end = p + (comp.index(im_end) if im_end in comp else len(comp))
            spans = {"all": [p, end]}
            if r["thinking"]:
                if think_end in comp:
                    t = p + comp.index(think_end); spans["reason"] = [p, t]
                    if t + 1 < end:
                        spans["resp"] = [t + 1, end]
                else:
                    spans["reason"] = [p, end]
            elif end > p:
                spans["resp"] = [p, end]
            text = c.text
            response = text.split("</think>", 1)[1] if "</think>" in text else ("" if r["thinking"] else text)
            g.write(json.dumps({k: r[k] for k in ("id", "kind", "name", "prompt_idx", "question_id", "half", "question", "system", "thinking")}
                               | {"text": text, "response": response.replace("<|im_end|>", "").strip(), "finish_reason": c.finish_reason,
                                  "n_completion": len(comp)}) + "\n")
            s.write(json.dumps({"id": r["id"], "ids": r["prompt_ids"] + comp, "spans": spans}) + "\n")
    trunc = sum(o.outputs[0].finish_reason == "length" for o in outs)
    print(f"{len(rows)} generated; {trunc} hit max_tokens")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
