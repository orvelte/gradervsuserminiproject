#!/usr/bin/env python3
"""On the pod: DD1 steering double dissociation (PREREG DD1). Input: prompts.jsonl from internals/dd1/build.py.

    python pod_dd1.py prompts.jsonl out/ [--smoke]

Layers are 1-based block outputs (layers[L-1], as pod_acts.py and pod_steer.py). Steps:
  1. capture the final-token residual at layers 32 and 36 for the initial, prefix and pair prompts;
  2. directions: mood = G-holdout − D-holdout, scoring = G-visible − G-holdout, fullframe = G-visible − D-visible
     (initial prompts, L32), grader = pos − neg pairs (L36); secondary prefix-mean versions; cosines;
  3. residual covariance over the D-visible eval prefixes' tokens at L32 and L36; 8 random directions per layer from
     N(0, Σ) (seed 20261023);
  4. checks (abort on failure): cached-prefix vs full-recompute probe scores |Δ| < 0.01 on 5 probes; HF α=0
     P(override) per prefix vs Gate 0 (vLLM) Pearson r ≥ 0.95;
  5. every condition on every eval prefix: the probes' common token prefix is run once with the steering hook, then
     each probe's remainder continues from a copy of that cache; P(A), P(B) from the full softmax (all tokens that
     decode to "A" / "B" after strip, as the vLLM read-out);
  6. coherence continuations (greedy, 120 tokens) for the baseline and every targeted condition.
--smoke: steps 1–4 on 3 eval prefixes, then times one condition and prints the projected runtime.
"""
from __future__ import annotations

import copy
import json
import math
import sys
import time
from pathlib import Path

import numpy as np
import torch
from transformers import AutoConfig, AutoModelForCausalLM, AutoTokenizer

MODEL = "Qwen/Qwen3.8-27B"
LAYERS = (32, 36)
ALPHAS = (0.5, 1.0, 2.0, 4.0)
RAND_ALPHAS = (1.0, 2.0)
N_RAND = 8
SEED = 20261023
BATCHED = None  # set by the first check: batched remainders match sequential ones


class Steer:
    """Forward hooks: add `vec` at layer `layer` (all positions); capture outputs at the capture layers."""

    def __init__(self, layers):
        self.layers, self.vec, self.layer, self.capture, self.store = layers, None, None, set(), {}
        for L in LAYERS:
            layers[L - 1].register_forward_hook(self._hook(L))

    def _hook(self, L):
        def f(_m, _inp, output):
            h = output[0] if isinstance(output, tuple) else output
            if self.vec is not None and self.layer == L:
                h = h + self.vec
            if L in self.capture:
                self.store[L] = h.detach()
            return (h,) + tuple(output[1:]) if isinstance(output, tuple) else h
        return f


def letter_ids(tok) -> tuple[list[int], list[int]]:
    a, b = [], []
    for i in range(len(tok)):
        s = tok.decode([i]).strip()
        if s == "A":
            a.append(i)
        elif s == "B":
            b.append(i)
    return a, b


def common_prefix(seqs: list[list[int]]) -> int:
    n = min(len(s) for s in seqs)
    for i in range(n):
        if any(s[i] != seqs[0][i] for s in seqs[1:]):
            return i
    return n


@torch.no_grad()
def final_states(model, st, tok, texts, layers=LAYERS) -> dict:
    st.capture = set(layers); out = {L: [] for L in layers}
    for t in texts:
        ids = torch.tensor([tok(t, add_special_tokens=False).input_ids], device="cuda")
        model(input_ids=ids, use_cache=False)
        for L in layers:
            out[L].append(st.store[L][0, -1].float().cpu().numpy())
    st.capture = set()
    return {L: np.stack(v) for L, v in out.items()}


@torch.no_grad()
def probe_scores(model, st, ids_list, A, B, check=False) -> list[tuple[float, float]]:
    """ids_list: token ids of each full probe prompt. One cached pass over the common prefix, then each remainder."""
    c = common_prefix(ids_list) - 1  # leave ≥ 1 token for every remainder
    base = model(input_ids=torch.tensor([ids_list[0][:c]], device="cuda"), use_cache=True).past_key_values

    def sequential():
        out = []
        for ids in ids_list:
            rem = torch.tensor([ids[c:]], device="cuda")
            o = model(input_ids=rem, past_key_values=copy.deepcopy(base), use_cache=True,
                      cache_position=torch.arange(c, len(ids), device="cuda"))
            p = torch.softmax(o.logits[0, -1].float(), -1)
            out.append((float(p[A].sum()), float(p[B].sum())))
        return out

    def batched():
        # every remainder continues the same cache; right-padded, each read at its own last real token (causal, so exact)
        cache = copy.deepcopy(base); cache.batch_repeat_interleave(len(ids_list))
        lens = [len(i) - c for i in ids_list]; T = max(lens)
        x = torch.tensor([i[c:] + [0] * (T - (len(i) - c)) for i in ids_list], device="cuda")
        o = model(input_ids=x, past_key_values=cache, use_cache=True, cache_position=torch.arange(c, c + T, device="cuda"))
        p = torch.softmax(o.logits[torch.arange(len(ids_list)), torch.tensor(lens, device="cuda") - 1].float(), -1)
        return [(float(q[A].sum()), float(q[B].sum())) for q in p]

    global BATCHED
    if BATCHED is None or check:
        seq = sequential()
        try:
            bat = batched()
            d = max(abs(a / (a + b) - x / (x + y)) for (a, b), (x, y) in zip(bat, seq))
            BATCHED = d < 0.01
            print(f"batched vs sequential max |Δ| = {d:.4f}; batched {'on' if BATCHED else 'OFF'}", flush=True)
        except Exception as e:  # noqa: BLE001
            BATCHED = False; print(f"batched path unavailable ({type(e).__name__}: {e}); sequential", flush=True)
        res = seq
    else:
        res = batched() if BATCHED else sequential()
    if check:
        for j in range(min(5, len(ids_list))):
            o = model(input_ids=torch.tensor([ids_list[j]], device="cuda"), use_cache=False)
            p = torch.softmax(o.logits[0, -1].float(), -1); pa, pb = float(p[A].sum()), float(p[B].sum())
            fa, fb = res[j]
            d = abs(pa / (pa + pb) - fa / (fa + fb))
            assert d < 0.01, f"cache check failed on probe {j}: |Δ| = {d:.4f}"
    return res


@torch.no_grad()
def covariance(model, st, tok, texts, L) -> tuple[np.ndarray, float]:
    st.capture = {L}; H = None; n = 0; norms = []
    for t in texts:
        ids = torch.tensor([tok(t, add_special_tokens=False).input_ids], device="cuda")
        model(input_ids=ids, use_cache=False)
        h = st.store[L][0].double()
        norms.append(h.norm(dim=-1).mean().item())
        if H is None:
            H = torch.zeros(h.shape[1], h.shape[1], dtype=torch.float64, device="cuda"); mu = torch.zeros(h.shape[1], dtype=torch.float64, device="cuda")
        H += h.T @ h; mu += h.sum(0); n += h.shape[0]
    st.capture = set()
    mu /= n; cov = H / n - torch.outer(mu, mu)
    return cov, float(np.mean(norms))


def random_dirs(cov, k, seed) -> np.ndarray:
    w, V = torch.linalg.eigh(cov); w = w.clamp(min=0)
    g = torch.Generator(device="cuda").manual_seed(seed)
    z = torch.randn(k, cov.shape[0], generator=g, dtype=torch.float64, device="cuda")
    x = (z * w.sqrt()) @ V.T
    x = x / x.norm(dim=1, keepdim=True)
    return x.float().cpu().numpy()


def unit(v):
    return v / np.linalg.norm(v)


def main(argv) -> int:
    rows = [json.loads(l) for l in open(argv[0]) if l.strip()]; out = Path(argv[1]); out.mkdir(parents=True, exist_ok=True)
    smoke = "--smoke" in argv; t0 = time.time(); meta = {"smoke": smoke}
    tok = AutoTokenizer.from_pretrained(MODEL); cfg = AutoConfig.from_pretrained(MODEL)
    model = AutoModelForCausalLM.from_pretrained(MODEL, dtype=torch.bfloat16, device_map="cuda"); model.eval()
    n = getattr(getattr(cfg, "text_config", cfg), "num_hidden_layers")
    layers = max((m for m in model.modules() if isinstance(m, torch.nn.ModuleList) and len(m) == n), key=lambda m: sum(p.numel() for p in m.parameters()))
    st = Steer(layers); A, B = letter_ids(tok); meta["letter_ids"] = {"A": len(A), "B": len(B)}
    print(f"model loaded ({time.time() - t0:.0f}s); {n} layers; letter tokens A {len(A)} B {len(B)}", flush=True)

    # 1–2. directions
    init = {r["cell"]: r["text"] for r in rows if r["kind"] == "initial"}
    cells = ["HO-G~visible", "HO-D~visible", "HO-G~holdout", "HO-D~holdout"]
    fi = final_states(model, st, tok, [init[c] for c in cells]); I = {c: {L: fi[L][i] for L in LAYERS} for i, c in enumerate(cells)}
    pairs = [r for r in rows if r["kind"] == "pair"]
    if smoke:
        pairs = pairs[:20] + [r for r in pairs if r["side"] == "neg"][:20]
    fp = final_states(model, st, tok, [r["text"] for r in pairs]); pos = np.array([r["side"] == "pos" for r in pairs])
    prefs = [r for r in rows if r["kind"] == "prefix"]
    if smoke:
        prefs = prefs[:12]
    fpre = final_states(model, st, tok, [r["text"] for r in prefs])
    cm = lambda L, c: fpre[L][[r["cell"] == c for r in prefs]].mean(0)  # noqa: E731
    D = {"mood": (32, I["HO-G~holdout"][32] - I["HO-D~holdout"][32]),
         "scoring": (32, I["HO-G~visible"][32] - I["HO-G~holdout"][32]),
         "fullframe": (32, I["HO-G~visible"][32] - I["HO-D~visible"][32]),
         "grader": (36, fp[36][pos].mean(0) - fp[36][~pos].mean(0))}
    sec = {}
    if not smoke:
        sec = {"mood": cm(32, "HO-G~holdout") - cm(32, "HO-D~holdout"), "scoring": cm(32, "HO-G~visible") - cm(32, "HO-G~holdout"),
               "fullframe": cm(32, "HO-G~visible") - cm(32, "HO-D~visible")}
    grader32 = fp[32][pos].mean(0) - fp[32][~pos].mean(0)
    names = ["mood", "scoring", "fullframe"]
    cos = {f"{a}~{b}@32": float(unit(D[a][1]) @ unit(D[b][1])) for i, a in enumerate(names) for b in names[i + 1:]}
    cos.update({f"grader~{a}@32": float(unit(grader32) @ unit(D[a][1])) for a in names})
    cos.update({f"{a}~secondary": float(unit(D[a][1]) @ unit(sec[a])) for a in sec})
    i36 = {c: I[c][36] for c in cells}
    cos.update({"grader~mood@36": float(unit(D["grader"][1]) @ unit(i36["HO-G~holdout"] - i36["HO-D~holdout"])),
                "grader~scoring@36": float(unit(D["grader"][1]) @ unit(i36["HO-G~visible"] - i36["HO-G~holdout"])),
                "grader~fullframe@36": float(unit(D["grader"][1]) @ unit(i36["HO-G~visible"] - i36["HO-D~visible"]))})
    meta["cosines"] = cos; meta["norms"] = {k: float(np.linalg.norm(v)) for k, (_, v) in D.items()}
    np.savez(out / "dirs.npz", **{k: v for k, (_, v) in D.items()}, grader32=grader32, **{f"sec_{k}": v for k, v in sec.items()})
    print("directions", json.dumps(meta["norms"]), json.dumps(cos), flush=True)

    # 3. covariance and random directions
    evals = [r for r in rows if r["kind"] == "eval"]
    if smoke:
        evals = evals[:3]
    ctx = [r["probes"][0]["text"] for r in evals]
    R, act = {}, {}
    for L in LAYERS:
        cov, act[L] = covariance(model, st, tok, ctx, L); R[L] = random_dirs(cov, N_RAND, SEED + L); del cov
    meta["act_norm"] = act; np.savez(out / "random.npz", **{f"L{L}": R[L] for L in LAYERS})
    meta["pct_of_act_norm_at_alpha1"] = {k: 100 * meta["norms"][k] / act[D[k][0]] for k in D}
    print("activation norms", act, "pct", meta["pct_of_act_norm_at_alpha1"], flush=True)

    # conditions
    conds = [{"id": "base", "dir": None, "layer": None, "alpha": 0.0}]
    for k in ("mood", "scoring", "grader"):
        conds += [{"id": f"{k}@{a}", "dir": k, "layer": D[k][0], "alpha": a} for a in ALPHAS]
    conds += [{"id": f"fullframe@{a}", "dir": "fullframe", "layer": 32, "alpha": a} for a in (1.0, 2.0)]
    for k in ("mood", "scoring", "grader"):
        conds += [{"id": f"rand{j}~{k}@{a}", "dir": f"rand{j}", "match": k, "layer": D[k][0], "alpha": a} for j in range(N_RAND) for a in RAND_ALPHAS]
    meta["conditions"] = conds

    def vec(c):
        if c["dir"] is None:
            return None, None
        if c["dir"].startswith("rand"):
            v = R[c["layer"]][int(c["dir"][4:])] * meta["norms"][c["match"]] * c["alpha"]
        else:
            v = D[c["dir"]][1] * c["alpha"]
        return torch.tensor(v, dtype=torch.bfloat16, device="cuda"), c["layer"]

    ids = [[tok(p["text"], add_special_tokens=False).input_ids for p in r["probes"]] for r in evals]
    f = (out / "dd1_eval.jsonl").open("w")

    def run_cond(c, check=False):
        st.vec, st.layer = vec(c); t = time.time()
        for i, r in enumerate(evals):
            for (pa, pb), p in zip(probe_scores(model, st, ids[i], A, B, check=check and i == 0), r["probes"]):
                f.write(json.dumps({"run": r["run"], "cond": c["id"], "measure": p["measure"], "worse": p["worse"], "pA": pa, "pB": pb}) + "\n")
        st.vec = None; f.flush()
        return time.time() - t

    # 4. checks on the baseline
    tb = run_cond(conds[0], check=True); meta["check_cache"] = "pass"
    base = [json.loads(l) for l in open(out / "dd1_eval.jsonl")]
    hf = []
    for r in evals:
        o = [x for x in base if x["run"] == r["run"] and x["measure"] == "override"]
        hf.append(np.mean([(x["pA"] if x["worse"] == "A" else x["pB"]) / (x["pA"] + x["pB"]) for x in o]))
    g0 = [r["gate0_p"] for r in evals]
    rr = float(np.corrcoef(hf, g0)[0, 1]) if len(evals) > 2 else float("nan")
    meta["check_hf_vs_vllm"] = {"pearson_r": rr, "hf_mean": float(np.mean(hf)), "vllm_mean": float(np.mean(g0))}
    print(f"baseline {tb:.0f}s for {len(evals)} prefixes; HF vs vLLM r = {rr:.3f} (means {np.mean(hf):.4f} vs {np.mean(g0):.4f})", flush=True)
    if smoke:
        t1 = run_cond(conds[1]); meta["batched"] = BATCHED
        meta["projected_hours"] = t1 / len(evals) * 23 * len(conds) / 3600
        print(f"SMOKE OK. projected eval time: {meta['projected_hours']:.2f} h for {len(conds)} conditions", flush=True)
        (out / "dd1_meta.json").write_text(json.dumps(meta, indent=1)); return 0
    if not rr >= 0.95:
        (out / "dd1_meta.json").write_text(json.dumps(meta, indent=1))
        sys.exit(f"ABORT: HF α=0 vs vLLM Gate 0 r = {rr:.3f} < 0.95")

    # 5. all conditions
    for k, c in enumerate(conds[1:], 2):
        dt = run_cond(c)
        print(f"[{k}/{len(conds)}] {c['id']} {dt:.0f}s; elapsed {(time.time() - t0) / 60:.0f} min", flush=True)
    f.close()

    # 6. coherence continuations
    gens = [r for r in rows if r["kind"] == "gen"]; g = (out / "dd1_gen.jsonl").open("w")
    eos = model.generation_config.eos_token_id; eos = [eos] if isinstance(eos, int) else list(eos or [])
    for c in [x for x in conds if not (x["dir"] or "").startswith("rand")]:
        st.vec, st.layer = vec(c)
        for r in gens:
            x = torch.tensor([tok(r["text"], add_special_tokens=False).input_ids], device="cuda")
            y = model.generate(input_ids=x, attention_mask=torch.ones_like(x), max_new_tokens=120, do_sample=False, eos_token_id=eos, pad_token_id=eos[0] if eos else None)
            g.write(json.dumps({"cond": c["id"], "run": r["run"], "text": tok.decode(y[0, x.shape[1]:], skip_special_tokens=False)}) + "\n")
        st.vec = None
    g.close()
    meta["minutes"] = (time.time() - t0) / 60
    (out / "dd1_meta.json").write_text(json.dumps(meta, indent=1))
    print(f"DONE in {meta['minutes']:.0f} min", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
