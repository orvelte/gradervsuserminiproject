#!/usr/bin/env python3
"""On the pod: PC1 Stage 0 (PREREG PC1). Base Qwen3-14B plus the two cds-jb LoRA organisms on vLLM (offline,
enable_lora). Thinking disabled (the organisms' chat format).

    VLLM_ENABLE_V1_MULTIPROCESSING=0 python pod_pc1.py stage0 pc1_inputs.json out/ [--smoke]

gen  : 16 probe questions × 50 samples per model; temperature 1.0, top_p 1.0, max 600 tokens (cds-jb gen_rollouts.py)
fc   : the forced-choice items, both orders; P(A), P(B) from the top-20 next-token log-probs (max_tokens 1, greedy)
Writes out/stage0_gen.jsonl and out/stage0_fc.jsonl.
"""
import json
import math
import os
import sys
from pathlib import Path

os.environ.setdefault("VLLM_ENABLE_V1_MULTIPROCESSING", "0")
from huggingface_hub import snapshot_download  # noqa: E402
from vllm import LLM, SamplingParams  # noqa: E402
from vllm.lora.request import LoRARequest  # noqa: E402

BASE = "Qwen/Qwen3-14B"
ORGS = {"general": "cds-jb/em-risky_financial-broad", "narrow": "cds-jb/em-risky_financial-narrow"}


def fc_prompts(inp, render, system=None):
    out = []
    for dom, qs in inp["fc"].items():
        for q, pairs in qs.items():
            for k, (al, mis) in enumerate(pairs):
                for order in ("AB", "BA"):
                    a, b = (al, mis) if order == "AB" else (mis, al)
                    text = f"{inp['questions'][q]} (A) {a} (B) {b} Answer with one letter."
                    msgs = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": text}]
                    out.append({"domain": dom, "q": q, "pair": k, "order": order, "mis_letter": "B" if order == "AB" else "A", "prompt": render(msgs)})
    return out


def read_ab(r):
    top = r.outputs[0].logprobs[0]
    pa = sum(math.exp(x.logprob) for x in top.values() if (x.decoded_token or "").strip() == "A")
    pb = sum(math.exp(x.logprob) for x in top.values() if (x.decoded_token or "").strip() == "B")
    return pa, pb


def cl_items(inp, tok, render, system=None):
    """Continuation-likelihood items: each option as the whole assistant reply; returns token ids and the option span."""
    out = []
    for dom, qs in inp["fc"].items():
        for q, pairs in qs.items():
            msgs = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": inp["questions"][q]}]
            pre = render(msgs); pids = tok(pre, add_special_tokens=False).input_ids
            for k, pair in enumerate(pairs):
                for kind, text in zip(("aligned", "misaligned"), pair):
                    ids = tok(pre + text + "<|im_end|>", add_special_tokens=False).input_ids
                    assert ids[:len(pids)] == pids, "prefix tokenisation changed"
                    out.append({"domain": dom, "q": q, "pair": k, "kind": kind, "ids": ids, "start": len(pids)})
    return out


def cl_score(llm, items, lora):
    from vllm.inputs import TokensPrompt
    sp = SamplingParams(max_tokens=1, temperature=0.0, prompt_logprobs=0)
    res = llm.generate([TokensPrompt(prompt_token_ids=it["ids"]) for it in items], sp, lora_request=lora, use_tqdm=False)
    out = []
    for it, r in zip(items, res):
        lps = [r.prompt_logprobs[j][it["ids"][j]].logprob for j in range(it["start"], len(it["ids"]))]
        out.append({k: v for k, v in it.items() if k != "ids"} | {"mean_lp": float(sum(lps) / len(lps)), "n_tok": len(lps)})
    return out


def main(argv):
    mode, inp, out = argv[0], json.load(open(argv[1])), Path(argv[2]); out.mkdir(parents=True, exist_ok=True); smoke = "--smoke" in argv
    paths = {k: snapshot_download(v) for k, v in ORGS.items()}
    llm = LLM(model=BASE, dtype="bfloat16", enable_lora=True, max_lora_rank=32, max_loras=2, max_model_len=4096, gpu_memory_utilization=0.9, seed=0)
    tok = llm.get_tokenizer()
    render = lambda msgs: tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True, enable_thinking=False)  # noqa: E731
    loras = {"base": None, "general": LoRARequest("general", 1, paths["general"]), "narrow": LoRARequest("narrow", 2, paths["narrow"])}
    n = 2 if smoke else 50
    gen = SamplingParams(temperature=1.0, top_p=1.0, max_tokens=600, n=n, seed=20261024)
    fc = SamplingParams(max_tokens=1, temperature=0.0, logprobs=20)
    qs = list(inp["questions"].items())
    if mode == "cl":
        items = cl_items(inp, tok, render)
        with (out / "cl.jsonl").open("w") as f:
            for name, lr in loras.items():
                for row in cl_score(llm, items, lr):
                    f.write(json.dumps({"model": name, **row}) + "\n")
                print(f"{name} cl done", flush=True)
        return
    with (out / "stage0_gen.jsonl").open("w") as g, (out / "stage0_fc.jsonl").open("w") as f:
        for name, lr in loras.items():
            res = llm.generate([render([{"role": "user", "content": t}]) for _, t in qs], gen, lora_request=lr)
            for (q, t), r in zip(qs, res):
                for i, o in enumerate(r.outputs):
                    g.write(json.dumps({"model": name, "q": q, "domain": inp["domain_of"][q], "question": t, "i": i, "answer": o.text,
                                        "finish_reason": o.finish_reason}) + "\n")
            items = fc_prompts(inp, render)
            for it, r in zip(items, llm.generate([x["prompt"] for x in items], fc, lora_request=lr, use_tqdm=False)):
                pa, pb = read_ab(r)
                f.write(json.dumps({"model": name, **{k: v for k, v in it.items() if k != "prompt"}, "pA": pa, "pB": pb}) + "\n")
            g.flush(); f.flush(); print(f"{name} done", flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])
