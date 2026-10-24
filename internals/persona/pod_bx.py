#!/usr/bin/env python3
"""On the pod: BX (PREREG BX). One model per invocation (frees the GPU between models).

    VLLM_ENABLE_V1_MULTIPROCESSING=0 python pod_bx.py inputs.json vector.npy MODEL_KEY out/ [--smoke]

vLLM offline, eager, prefix caching off. A forward hook on the block whose output is layer 36's input (0-based block
35) adds s · (a / ‖v‖) · v to the full residual stream (hidden + residual, as their patch does), every position; one
strength per pass. a = mean final-token ‖h‖ there over the 540 verifier/human prompts, rendered with this model's
template (calibration for Qwen3.6: within 5% of their 82.36, else abort).
Writes out/MODEL_KEY.{calib.json, m1.jsonl, m2.jsonl}.
"""
from __future__ import annotations

import json
import math
import os
import sys
from pathlib import Path

import numpy as np
import torch

os.environ.setdefault("VLLM_ENABLE_V1_MULTIPROCESSING", "0")
from vllm import LLM, SamplingParams  # noqa: E402

STATE = {"delta": None, "capture": False, "store": None}


def hook(_m, _inp, out):
    if isinstance(out, tuple) and len(out) == 2:
        hidden, residual = out
        full = hidden if residual is None else hidden + residual
        if STATE["capture"]:
            STATE["store"] = full[-1].detach().float().cpu()
        if STATE["delta"] is None:
            return out
        d = STATE["delta"].to(full.dtype)
        return (full + d, None) if residual is None else (torch.zeros_like(hidden), full + d)
    h = out[0] if isinstance(out, tuple) else out
    if STATE["capture"]:
        STATE["store"] = h[-1].detach().float().cpu()
    if STATE["delta"] is None:
        return out
    h = h + STATE["delta"].to(h.dtype)
    return (h,) + tuple(out[1:]) if isinstance(out, tuple) else h


def install(model, layer: int, n_layers: int):
    mods = [m for m in model.modules() if isinstance(m, torch.nn.ModuleList) and len(m) == n_layers]
    layers = max(mods, key=lambda m: sum(p.numel() for p in m.parameters()))
    layers[layer - 1].register_forward_hook(hook)  # output of 0-based block L-1 = input of block L = row L of their format = our 1-based "layer L" (DD1)
    return True


def main(argv) -> int:
    inp = json.load(open(argv[0])); v = np.load(argv[1]).astype(np.float32); key = argv[2]; out = Path(argv[3]); out.mkdir(parents=True, exist_ok=True)
    smoke = "--smoke" in argv; spec = inp["models"][key]; L = inp["layer"]
    llm = LLM(model=spec["hf"], dtype="bfloat16", enforce_eager=True, enable_prefix_caching=False, max_model_len=32768,
              gpu_memory_utilization=0.88, seed=0)
    tok = llm.get_tokenizer(); cfg = llm.llm_engine.model_config.hf_config; n = getattr(getattr(cfg, "text_config", cfg), "num_hidden_layers")
    llm.apply_model(lambda m: install(m, L, n))
    def fix(m):  # HF templates iterate tool-call arguments as a mapping; transcripts store them as JSON strings
        if not m.get("tool_calls"):
            return m
        calls = []
        for c in m["tool_calls"]:
            fn = dict(c.get("function", {})); a = fn.get("arguments")
            if isinstance(a, str):
                try:
                    fn["arguments"] = json.loads(a)
                except json.JSONDecodeError:
                    fn["arguments"] = {"input": a}
            calls.append({**c, "function": fn})
        return {**m, "tool_calls": calls}
    render = lambda msgs, tools=None, think=True: tok.apply_chat_template([fix(m) for m in msgs], tools=tools, tokenize=False, add_generation_prompt=True, enable_thinking=think)  # noqa: E731

    # ---- calibration: a = mean final-token norm at layer L over the 540 prompts
    one = SamplingParams(max_tokens=1, temperature=0.0)
    norms = []
    pairs = inp["pairs"][:20] + inp["pairs"][-20:] if smoke else inp["pairs"]
    for p in pairs:
        STATE["capture"] = True; STATE["store"] = None
        llm.generate([render(p["messages"])], one, use_tqdm=False)
        STATE["capture"] = False; norms.append(float(STATE["store"].norm()))
    a = float(np.mean(norms)); calib = {"act_norm": a, "their_act_norm": spec["their_act_norm"], "v_norm": float(np.linalg.norm(v)), "n_prompts": len(norms)}
    if spec["their_act_norm"]:
        calib["rel_diff"] = abs(a - spec["their_act_norm"]) / spec["their_act_norm"]
        if calib["rel_diff"] > 0.05 and not smoke:
            (out / f"{key}.calib.json").write_text(json.dumps(calib, indent=1)); sys.exit(f"ABORT: act norm {a:.2f} vs theirs {spec['their_act_norm']:.2f}")
    unit = torch.tensor(v / np.linalg.norm(v)).cuda()
    # hook check: logits must change at s != 0
    probe_p = render([{"role": "user", "content": inp["questions"][0]["question"]}])
    lp = SamplingParams(max_tokens=1, temperature=0.0, logprobs=5)
    STATE["delta"] = None; r0 = llm.generate([probe_p], lp, use_tqdm=False)[0].outputs[0].logprobs[0]
    STATE["delta"] = 0.3 * a * unit; r1 = llm.generate([probe_p], lp, use_tqdm=False)[0].outputs[0].logprobs[0]; STATE["delta"] = None
    calib["hook_changes_logprobs"] = any(abs(r0[t].logprob - r1.get(t, r0[t]).logprob) > 1e-3 for t in r0)
    (out / f"{key}.calib.json").write_text(json.dumps(calib, indent=1)); print("calibration", calib, flush=True)
    assert calib["hook_changes_logprobs"], "steering hook has no effect"

    qs = inp["questions"][:20] if smoke else inp["questions"]
    gen = SamplingParams(temperature=0.6, top_p=0.95, top_k=20, max_tokens=1024 if smoke else 16384, seed=20261024)
    pre = spec["prefixes"][:4] if smoke else spec["prefixes"]
    m1, m2 = (out / f"{key}.m1.jsonl").open("w"), (out / f"{key}.m2.jsonl").open("w")
    fc = SamplingParams(max_tokens=1, temperature=0.0, logprobs=20)
    for s in inp["strengths"]:
        STATE["delta"] = None if s == 0 else s * a * unit
        res = llm.generate([render([{"role": "user", "content": q["question"]}]) for q in qs], gen)
        for q, r in zip(qs, res):
            text = r.outputs[0].text; done = "</think>" in text
            m1.write(json.dumps({"s": s, "trait": q["trait"], "question": q["question"], "answer": text.split("</think>", 1)[1].strip() if done else None,
                                 "finished": done, "finish_reason": r.outputs[0].finish_reason, "n_tokens": len(r.outputs[0].token_ids)}) + "\n")
        m1.flush()
        prompts, meta = [], []
        for p in pre:
            for pr in inp["probes"]:
                prompts.append(render(p["messages"] + [{"role": "user", "content": pr["text"]}], p["tools"], think=False)); meta.append((p["run"], pr))
        res = llm.generate(prompts, fc, use_tqdm=False)
        for (run, pr), r in zip(meta, res):
            top = r.outputs[0].logprobs[0]
            pa = sum(math.exp(x.logprob) for x in top.values() if (x.decoded_token or "").strip() == "A")
            pb = sum(math.exp(x.logprob) for x in top.values() if (x.decoded_token or "").strip() == "B")
            m2.write(json.dumps({"s": s, "run": run, "measure": pr["measure"], "worse": pr["worse"], "pA": pa, "pB": pb}) + "\n")
        m2.flush(); print(f"{key} s={s}: done", flush=True)
    STATE["delta"] = None
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
