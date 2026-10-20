#!/usr/bin/env python3
"""GPU step 2: replay exact token sequences through Qwen3.8-27B (HF transformers) and average the residual stream over
named spans at every layer (assistantaxis.md guardrails 1 and 3).

    python pod_acts.py seqs.jsonl out_dir [--chunk 16384] [--check]

Input rows: {"id", "ids": [...], "spans": {name: [start, end] | [[start, end], ...]}} (half-open token ranges).
Output per row: out_dir/<sha1(id)>.npz with `names` and `means` [n_spans, n_layers + 1, hidden] (fp16; index 0 is the
embedding output = the layer-0 leak check, index l is the output of decoder layer l, i.e. the post-MLP residual), and
`counts`. Sequences longer than --chunk run in chunks with the KV/recurrent cache.
--check first compares a chunked and an unchunked pass on one short sequence (cosine of span means must be > 0.999).
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np
import torch
from transformers import AutoConfig, AutoModelForCausalLM

MODEL = "Qwen/Qwen3.8-27B"


def load():
    cfg = AutoConfig.from_pretrained(MODEL)
    model = AutoModelForCausalLM.from_pretrained(MODEL, torch_dtype=torch.bfloat16, device_map="cuda", attn_implementation="sdpa")
    model.eval()
    n = getattr(getattr(cfg, "text_config", cfg), "num_hidden_layers")
    layers = max((m for m in model.modules() if isinstance(m, torch.nn.ModuleList) and len(m) == n), key=lambda m: sum(p.numel() for p in m.parameters()))
    print(f"loaded {type(model).__name__}; {n} decoder layers ({type(layers[0]).__name__}); hidden {layers[0].mlp.down_proj.out_features if hasattr(layers[0], 'mlp') else '?'}")
    return model, layers, model.get_input_embeddings()


def _ranges(v):
    return [v] if v and isinstance(v[0], int) else v


@torch.no_grad()
def replay(model, layers, emb, ids: list[int], spans: dict, chunk: int):
    names = list(spans); rngs = [_ranges(spans[n]) for n in names]
    hidden = emb.weight.shape[1]; L = len(layers) + 1
    sums = torch.zeros(len(names), L, hidden, dtype=torch.float32, device="cuda"); counts = torch.zeros(len(names), dtype=torch.float32)
    for i, rs in enumerate(rngs):
        counts[i] = sum(max(0, e - s) for s, e in rs)
    state = {"c0": 0}

    def hook(idx):
        def f(_m, _inp, out):
            h = out[0] if isinstance(out, tuple) else out
            c0 = state["c0"]; c1 = c0 + h.shape[1]
            for i, rs in enumerate(rngs):
                for s, e in rs:
                    a, b = max(s, c0), min(e, c1)
                    if a < b:
                        sums[i, idx] += h[0, a - c0: b - c0].float().sum(0)
        return f
    hs = [emb.register_forward_hook(hook(0))] + [l.register_forward_hook(hook(j + 1)) for j, l in enumerate(layers)]
    try:
        x = torch.tensor([ids], device="cuda")
        if len(ids) <= chunk:
            model(input_ids=x, use_cache=False)
        else:
            from transformers import DynamicCache
            cache = DynamicCache(config=model.config) if "config" in DynamicCache.__init__.__code__.co_varnames else DynamicCache()
            for c0 in range(0, len(ids), chunk):
                state["c0"] = c0; c1 = min(len(ids), c0 + chunk)
                out = model(input_ids=x[:, c0:c1], past_key_values=cache, use_cache=True, cache_position=torch.arange(c0, c1, device="cuda"))
                cache = out.past_key_values
    finally:
        for h in hs:
            h.remove()
    means = (sums / counts.clamp(min=1).view(-1, 1, 1).to(sums.device)).half().cpu().numpy()
    return names, means, counts.numpy()


def main(argv) -> int:
    src, out = Path(argv[0]), Path(argv[1]); out.mkdir(parents=True, exist_ok=True)
    chunk = int(argv[argv.index("--chunk") + 1]) if "--chunk" in argv else 16384
    rows = [json.loads(l) for l in src.read_text().splitlines() if l.strip()]
    model, layers, emb = load()
    if "--check" in argv:
        r = min(rows, key=lambda r: abs(len(r["ids"]) - 6000))
        _, a, _ = replay(model, layers, emb, r["ids"], r["spans"], chunk=10 ** 9)
        _, b, _ = replay(model, layers, emb, r["ids"], r["spans"], chunk=max(512, len(r["ids"]) // 3))
        a, b = a.astype(np.float32).reshape(-1, a.shape[-1]), b.astype(np.float32).reshape(-1, b.shape[-1])
        cos = (a * b).sum(1) / (np.linalg.norm(a, axis=1) * np.linalg.norm(b, axis=1) + 1e-6)
        print(f"chunk check on {len(r['ids'])} tokens: min cos {cos.min():.5f}, mean {cos.mean():.5f}")
        if cos.min() < 0.999:
            print("CHUNK CHECK FAILED"); return 1
    t0 = time.time(); ntok = 0
    for i, r in enumerate(rows):
        f = out / (hashlib.sha1(r["id"].encode()).hexdigest() + ".npz")
        if f.exists():
            continue
        names, means, counts = replay(model, layers, emb, r["ids"], r["spans"], chunk)
        np.savez_compressed(f, id=r["id"], names=np.array(names), means=means, counts=counts)
        ntok += len(r["ids"])
        if i % 20 == 0 or len(r["ids"]) > 20000:
            print(f"{i + 1}/{len(rows)} {len(r['ids'])} tok; {ntok / max(1e-6, time.time() - t0):.0f} tok/s", flush=True)
    print(f"done: {len(rows)} sequences, {ntok} tokens in {(time.time() - t0) / 60:.1f} min")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
