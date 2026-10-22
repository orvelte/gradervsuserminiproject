#!/usr/bin/env python3
"""On the pod: S1 steering generations (PREREG S1).

    python pod_steer.py prompts.jsonl dirs.npz conditions.json out.jsonl [--max-new 160] [--layer 32]

For each prompt, one batch with every condition as a row (same prompt length, so no padding). A forward hook on the
output of decoder layer `layer` (1-based, matching pod_acts.py's layer indexing) adds coef·v to every position of that
row. Greedy decoding.
"""
from __future__ import annotations

import json
import sys

import numpy as np
import torch
from transformers import AutoConfig, AutoModelForCausalLM

MODEL = "Qwen/Qwen3.8-27B"


def main(argv) -> int:
    prompts = [json.loads(l) for l in open(argv[0]) if l.strip()]
    d = np.load(argv[1]); conds = json.load(open(argv[2])); out = open(argv[3], "w")
    max_new = int(argv[argv.index("--max-new") + 1]) if "--max-new" in argv else 160
    layer = int(argv[argv.index("--layer") + 1]) if "--layer" in argv else 32
    cfg = AutoConfig.from_pretrained(MODEL)
    model = AutoModelForCausalLM.from_pretrained(MODEL, dtype=torch.bfloat16, device_map="cuda"); model.eval()
    n = getattr(getattr(cfg, "text_config", cfg), "num_hidden_layers")
    layers = max((m for m in model.modules() if isinstance(m, torch.nn.ModuleList) and len(m) == n), key=lambda m: sum(p.numel() for p in m.parameters()))
    vecs = {"axis": d["axis"], **{f"rand{k}": d["rand"][k] for k in range(len(d["rand"]))}}
    H = d["axis"].shape[0]
    steer = torch.zeros(len(conds), 1, H, dtype=torch.bfloat16, device="cuda")
    for i, c in enumerate(conds):
        if c["dir"]:
            steer[i, 0] = torch.tensor(vecs[c["dir"]] * c["coef"], dtype=torch.bfloat16)

    def hook(_m, _inp, output):
        if isinstance(output, tuple):
            return (output[0] + steer,) + tuple(output[1:])
        return output + steer
    h = layers[layer - 1].register_forward_hook(hook)
    eos = [model.generation_config.eos_token_id] if isinstance(model.generation_config.eos_token_id, int) else list(model.generation_config.eos_token_id or [])
    try:
        for p in prompts:
            x = torch.tensor([p["prompt_ids"]] * len(conds), device="cuda")
            with torch.no_grad():
                g = model.generate(input_ids=x, attention_mask=torch.ones_like(x), max_new_tokens=max_new, do_sample=False,
                                   eos_token_id=eos, pad_token_id=eos[0] if eos else None)
            for i, c in enumerate(conds):
                comp = g[i, x.shape[1]:].tolist()
                for e in eos:
                    if e in comp:
                        comp = comp[: comp.index(e)]
                out.write(json.dumps({"pid": p["pid"], "question": p["question"], "cond": c["name"], "dir": c["dir"], "coef": c["coef"],
                                      "completion_ids": comp}) + "\n")
            out.flush(); print(f"prompt {p['pid']} done", flush=True)
    finally:
        h.remove()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
