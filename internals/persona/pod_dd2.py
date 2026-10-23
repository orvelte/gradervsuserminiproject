#!/usr/bin/env python3
"""On the pod: DD2 teacher-forced counterfactuals and activation patching (PREREG DD2 + amendment).

    python pod_dd2.py prompts.jsonl out/ [--smoke]

Input from internals/dd2/build.py. Layers are 1-based block outputs (layers[L-1]). Gates are applied as pre-registered
and every number is written to out/dd2.json as it is produced:
  gate0   R1 (in-place stub) and R2 (user-turn probe) P(override) on the 72 originals vs resampled p_game; R1 if ρ ≥ .5
          else R2 else stop.
  stage1  paired gaps (cue version − other) per set: scoring/full on P(override), mood on ON (+ P(override), OFF).
  stage2  per passing contrast: layer sweep (2..64 step 2) of full-residual patching at site A and B; L* on the fit half;
          rank-1 subspace patching on the eval half with d_scoring, d_mood and 20 random N(0, Σ) directions; the full
          battery at L*; cross terms.
Patch sites are aligned from the end of the sequence and must lie in the token-identical suffix (asserted per pair).
--smoke: 2 pairs per set, layers {16, 32, 48}, 2 random directions; prints a runtime projection.
"""
from __future__ import annotations

import copy
import json
import sys
import time
from pathlib import Path

import numpy as np
import torch
from scipy.stats import spearmanr
from transformers import AutoConfig, AutoModelForCausalLM, AutoTokenizer

MODEL = "Qwen/Qwen3.8-27B"
SEED = 20261024
N_RAND = 20
ON = ("competitiveness", "ambition")
OFF = ("rule_breaking", "dishonesty", "approval_seeking")
GEN_TAIL = 6  # "<|im_end|>\n<|im_start|>assistant\n<think>\n" tokens at the end of every prefix (checked below)


class Hooks:
    def __init__(self, layers):
        self.layers = layers; self.patch = {}; self.capture = set(); self.store = {}; self.keep = 1
        for i, m in enumerate(layers):
            m.register_forward_hook(self._f(i + 1))

    def _f(self, L):
        def f(_m, _inp, out):
            h = out[0] if isinstance(out, tuple) else out
            if L in self.capture:
                self.store[L] = h[0, -self.keep:].detach().clone()
            if L in self.patch:
                fn = self.patch[L]; h = fn(h)
            return (h,) + tuple(out[1:]) if isinstance(out, tuple) else h
        return f


def letter_ids(tok):
    a, b = [], []
    for i in range(len(tok)):
        s = tok.decode([i]).strip()
        (a if s == "A" else b if s == "B" else []).append(i)
    return a, b


def lcp(seqs):
    n = min(len(s) for s in seqs)
    for i in range(n):
        if any(s[i] != seqs[0][i] for s in seqs[1:]):
            return i
    return n


def csuffix(a, b):
    k = 0
    while k < min(len(a), len(b)) and a[-1 - k] == b[-1 - k]:
        k += 1
    return k


class Runner:
    def __init__(self):
        self.tok = AutoTokenizer.from_pretrained(MODEL); cfg = AutoConfig.from_pretrained(MODEL)
        self.model = AutoModelForCausalLM.from_pretrained(MODEL, dtype=torch.bfloat16, device_map="cuda").eval()
        n = getattr(getattr(cfg, "text_config", cfg), "num_hidden_layers")
        layers = max((m for m in self.model.modules() if isinstance(m, torch.nn.ModuleList) and len(m) == n), key=lambda m: sum(p.numel() for p in m.parameters()))
        self.H = Hooks(layers); self.nL = n; self.A, self.B = letter_ids(self.tok)

    def enc(self, t):
        return self.tok(t, add_special_tokens=False).input_ids

    @torch.no_grad()
    def cache(self, ids):
        return self.model(input_ids=torch.tensor([ids], device="cuda"), use_cache=True).past_key_values

    @torch.no_grad()
    def cont(self, base, start, ids):
        """Continue from a copy of `base` (covering [0, start)) with `ids`; returns (pA, pB) at the last position."""
        o = self.model(input_ids=torch.tensor([ids], device="cuda"), past_key_values=copy.deepcopy(base), use_cache=True,
                       cache_position=torch.arange(start, start + len(ids), device="cuda"))
        p = torch.softmax(o.logits[0, -1].float(), -1)
        return float(p[self.A].sum()), float(p[self.B].sum())

    def readouts(self, seqs):
        """seqs: full token sequences sharing a long prefix. One cache over the common prefix, then each remainder."""
        c = lcp(seqs) - 1; base = self.cache(seqs[0][:c])
        return [self.cont(base, c, s[c:]) for s in seqs]


def p_worse(pa, pb, worse):
    t = pa + pb
    return (pa if worse == "A" else pb) / t if t > 0 else float("nan"), t


def main(argv) -> int:
    rows = [json.loads(l) for l in open(argv[0]) if l.strip()]; out = Path(argv[1]); out.mkdir(parents=True, exist_ok=True)
    smoke = "--smoke" in argv; t0 = time.time(); R = {"smoke": smoke}
    hdr = rows[0]; V = {(r["eid"], r["version"]): r for r in rows if r["kind"] == "version"}; pairs = [r for r in rows if r["kind"] == "pair"]
    if smoke:
        pairs = [p for s in ("scoring", "mood", "full") for p in [q for q in pairs if q["set"] == s][:2]]
    run = Runner(); enc = run.enc
    save = lambda: (out / "dd2.json").write_text(json.dumps(R, indent=1))  # noqa: E731
    print(f"loaded {time.time() - t0:.0f}s", flush=True)

    def r1_seqs(v):
        return [enc(v["r1_prefix"] + hdr["stub"][o]) for o in ("AB", "BA")]

    def r2_seqs(v):
        return [enc(v["r2_head"] + hdr["probe"][o] + v["r2_tail"]) for o in ("AB", "BA")]

    def trait_seqs(v, items):
        return [enc(v["r2_head"] + it["text"] + v["r2_tail"]) for it in items]

    def override(ps, letters):
        vals = [p_worse(a, b, w) for (a, b), w in zip(ps, letters)]
        return float(np.mean([x for x, _ in vals])), float(np.mean([m for _, m in vals]))

    traits = hdr["traits"]
    sweep_items = [it for m in ON for it in [x for x in traits if x["measure"] == m][:4]]  # 2 items × 2 orders per ON trait

    def trait_scores(ps, items):
        d = {}
        for (a, b), it in zip(ps, items):
            d.setdefault(it["measure"], []).append(p_worse(a, b, it["worse"]))
        res = {m: float(np.mean([x for x, _ in v])) for m, v in d.items()}
        res["ON"] = float(np.mean([res[m] for m in ON if m in res])); res["mass"] = float(np.mean([t for v in d.values() for _, t in v]))
        if all(m in res for m in OFF):
            res["OFF"] = float(np.mean([res[m] for m in OFF]))
        return res

    # sanity: every prefix ends with the generation tail
    tail = enc("<|im_end|>\n<|im_start|>assistant\n<think>\n")
    assert len(tail) == GEN_TAIL, tail
    # ---- gate 0 + stage 1 read-outs on every version needed
    need = {(p["eid"], p["cue_version"]) for p in pairs} | {(p["eid"], p["other_version"]) for p in pairs}
    need |= {k for k in V if k[1] == "orig"} if not smoke else set()
    mood_need = {(p["eid"], v) for p in pairs if p["set"] == "mood" for v in (p["cue_version"], p["other_version"])}
    RO = {}
    for i, k in enumerate(sorted(need)):
        v = V[k]; s1 = r1_seqs(v); s2 = r2_seqs(v)
        r1 = override(run.readouts(s1), [hdr["stub_override_letter"]["AB"], hdr["stub_override_letter"]["BA"]])
        r2 = override(run.readouts(s2), [hdr["probe_override_letter"]["AB"], hdr["probe_override_letter"]["BA"]])
        RO[k] = {"r1": r1[0], "r1_mass": r1[1], "r2": r2[0], "r2_mass": r2[1]}
        if k in mood_need:
            RO[k]["traits"] = trait_scores(run.readouts(trait_seqs(v, traits)), traits)
        if i % 20 == 0:
            print(f"read-outs {i + 1}/{len(need)} ({(time.time() - t0) / 60:.0f} min)", flush=True)
    R["readouts"] = {f"{e}|{v}": x for (e, v), x in RO.items()}
    if not smoke:
        orig = [k for k in RO if k[1] == "orig"]; pg = [V[k]["p_game"] for k in orig]; gv = [V[k]["cell"] == "HO-G~visible" for k in orig]
        g0 = {}
        for r in ("r1", "r2"):
            x = [RO[k][r] for k in orig]
            g0[r] = {"rho_all": float(spearmanr(x, pg).statistic),
                     "rho_Gvis": float(spearmanr([a for a, g in zip(x, gv) if g], [b for b, g in zip(pg, gv) if g]).statistic),
                     "mass": float(np.mean([RO[k][f"{r}_mass"] for k in orig]))}
        pick = "r1" if g0["r1"]["rho_all"] >= 0.5 else "r2" if g0["r2"]["rho_all"] >= 0.5 else None
        R["gate0"] = {**g0, "readout": pick}; save()
        print("gate0", json.dumps(R["gate0"]), flush=True)
        if pick is None:
            R["verdict"] = "uninformative (gate 0: no read-out tracks resampled p_game)"; save(); return 0
    else:
        pick = "r1"; R["gate0"] = {"readout": "r1 (smoke)"}

    # ---- stage 1
    rng = np.random.default_rng(SEED)

    def gap(ps, f):
        d = np.array([f(p["cue"]) - f(p["other"]) for p in ps])
        perm = [np.mean(d * rng.choice([-1, 1], len(d))) for _ in range(10000)]
        return {"mean": float(d.mean()), "p": float((np.sum(np.array(perm) >= d.mean()) + 1) / 10001), "n": int(len(d)), "per_pair": d.tolist()}
    S1 = {}
    for s in ("scoring", "mood", "full"):
        ps = [{"cue": RO[(p["eid"], p["cue_version"])], "other": RO[(p["eid"], p["other_version"])]} for p in pairs if p["set"] == s]
        S1[s] = {"override": gap(ps, lambda x: x[pick])}
        if s == "mood":
            for m in ("ON", "OFF"):
                S1[s][m] = gap(ps, lambda x: x["traits"][m])
    passes = lambda g: g["mean"] >= 0.05 and g["p"] < 0.05  # noqa: E731
    S1["pass"] = {"scoring": passes(S1["scoring"]["override"]), "mood": passes(S1["mood"]["ON"]), "full": passes(S1["full"]["override"])}
    R["stage1"] = S1; save(); print("stage1", json.dumps({s: {k: round(v["mean"], 3) for k, v in S1[s].items() if isinstance(v, dict) and "mean" in v} for s in ("scoring", "mood", "full")}), S1["pass"], flush=True)
    if not S1["pass"]["full"] and not smoke:
        R["verdict"] = "uninformative (full positive-control gap < 0.05)"; save(); return 0

    # ---- stage 2
    layers = [16, 32, 48] if smoke else list(range(2, run.nL + 1, 2))
    stub_n = max(len(enc(hdr["stub"][o])) for o in ("AB", "BA"))
    split = {}
    for s in ("scoring", "mood", "full"):
        ps = [p for p in pairs if p["set"] == s]
        for c in sorted({p["cell"] for p in ps}):
            for j, p in enumerate(sorted([q for q in ps if q["cell"] == c], key=lambda q: q["eid"])):
                split[(s, p["eid"])] = "fit" if j % 2 == 0 else "eval"

    def site_patch(src, n, mode="full", d=None):
        """Hook fn on the remainder pass: the last n positions take the source activations (full), or the target plus
        the projection of (source − target) on unit vector d (rank-1)."""
        def fn(h):
            h = h.clone(); tgt = h[0, -n:]; sv = src.to(h.dtype)
            if mode == "full":
                h[0, -n:] = sv
            else:
                dd = d.to(h.device).float(); diff = (sv - tgt).float()
                h[0, -n:] = (tgt.float() + (diff @ dd)[:, None] * dd[None, :]).to(h.dtype)
            return h
        return fn

    def prep(seqs, ns):
        c = min(lcp(seqs), min(len(q) - n for q, n in zip(seqs, ns))); assert c > 0
        return run.cache(seqs[0][:c]), c

    @torch.no_grad()
    def capture(seqs, ns, Ls, pre=None):
        base, c = pre or prep(seqs, ns); out = []
        for q, n in zip(seqs, ns):
            run.H.capture, run.H.keep = set(Ls), n
            run.model(input_ids=torch.tensor([q[c:]], device="cuda"), past_key_values=copy.deepcopy(base), use_cache=True,
                      cache_position=torch.arange(c, len(q), device="cuda"))
            out.append({L: run.H.store[L].clone() for L in Ls})
        run.H.capture, run.H.keep = set(), 1
        return out

    def patched(seqs, ns, pre, acts, L, mode="full", d=None):
        base, c = pre; res = []
        for q, n, a in zip(seqs, ns, acts):
            run.H.patch = {L: site_patch(a[L], n, mode, d)}
            res.append(run.cont(base, c, q[c:]))
        run.H.patch = {}
        return res

    def r1_site(cv, ov, wide):
        src, tgt = r1_seqs(cv), r1_seqs(ov); cs = min(csuffix(a, b) for a, b in zip(src, tgt))
        nA = stub_n + GEN_TAIL; assert cs >= nA, cs
        n = nA + 64 if wide else nA
        return src, tgt, (n if cs >= n else None)

    def trait_site(cv, ov, items):
        src, tgt = trait_seqs(cv, items), trait_seqs(ov, items)
        ns = [len(q) - lcp(tgt) for q in tgt]  # the probe span: everything after the shared head
        for a, b, n in zip(src, tgt, ns):
            assert a[-n:] == b[-n:], "probe span differs between versions"
        return src, tgt, ns

    ovr = lambda ps, lets: float(np.mean([p_worse(a, b, w)[0] for (a, b), w in zip(ps, lets)]))  # noqa: E731
    lets_r1 = [hdr["stub_override_letter"][o] for o in ("AB", "BA")]
    S2 = {"layers": layers, "sweep": {}, "excluded_site_B": {}}
    gated = [s for s in ("scoring", "mood", "full") if S1["pass"][s] or smoke]
    for s in gated:
        sw = {"A": {L: [] for L in layers}, "B": {L: [] for L in layers}}; base_d = []; excl = 0
        for p in [q for q in pairs if q["set"] == s]:
            cv, ov = V[(p["eid"], p["cue_version"])], V[(p["eid"], p["other_version"])]; sp = split[(s, p["eid"])]
            if s == "mood":
                src, tgt, ns = trait_site(cv, ov, sweep_items)
                pre_t, pre_s = prep(tgt, ns), prep(src, ns); acts = capture(src, ns, layers, pre_s)
                b_src = trait_scores(run.readouts(src), sweep_items)["ON"]; b_tgt = trait_scores(run.readouts(tgt), sweep_items)["ON"]
                for L in layers:
                    sw["A"][L].append({"eid": p["eid"], "split": sp, "val": trait_scores(patched(tgt, ns, pre_t, acts, L), sweep_items)["ON"]})
                base_d.append({"eid": p["eid"], "split": sp, "src": b_src, "tgt": b_tgt})
            else:
                src, tgt, nB = r1_site(cv, ov, True); nA = stub_n + GEN_TAIL
                if nB is None:
                    excl += 1
                nmax = nB or nA
                acts = capture(src, [nmax] * 2, layers); pre_t = prep(tgt, [nmax] * 2)
                for site, n in (("A", nA), ("B", nB)):
                    if not n:
                        continue
                    sub = [{L: a[L][-n:] for L in layers} for a in acts]
                    for L in layers:
                        sw[site][L].append({"eid": p["eid"], "split": sp, "val": ovr(patched(tgt, [n] * 2, pre_t, sub, L), lets_r1)})
                base_d.append({"eid": p["eid"], "split": sp, "src": RO[(p["eid"], p["cue_version"])][pick], "tgt": RO[(p["eid"], p["other_version"])][pick]})
            print(f"sweep {s} {p['eid'][:8]} done ({(time.time() - t0) / 60:.0f} min)", flush=True)
        rec = {}
        for site in ("A", "B"):
            for half in ("fit", "eval", "all"):
                bd = [b for b in base_d if half == "all" or b["split"] == half]
                gapm = float(np.mean([b["src"] - b["tgt"] for b in bd])) if bd else 0.0; tg = {b["eid"]: b["tgt"] for b in bd}
                rec[f"{site}/{half}"] = {L: (float(np.mean([x["val"] - tg[x["eid"]] for x in sw[site][L] if x["eid"] in tg])) / gapm
                                             if gapm and any(x["eid"] in tg for x in sw[site][L]) else None) for L in layers}
        S2["sweep"][s] = {"recovered": rec, "base": base_d, "raw": {k: {str(L): v for L, v in d.items()} for k, d in sw.items()}}
        S2["excluded_site_B"][s] = excl; R["stage2"] = S2; save()
        print(f"sweep {s}: best recovered", {k: max((v for v in r.values() if v is not None), default=None) for k, r in rec.items()}, flush=True)

    key_all = {"scoring": "B/all", "full": "B/all", "mood": "A/all"}; key_fit = {"scoring": "B/fit", "full": "B/fit", "mood": "A/fit"}
    readable = {s: max((v for v in S2["sweep"][s]["recovered"][key_all[s]].values() if v is not None), default=0) >= 0.5 for s in gated}
    S2["readable"] = readable; save()
    if not any(readable.get(s) for s in ("scoring", "mood")) and not smoke:
        R["verdict"] = f"no subspace test: readable at the decision site = {readable}"; save(); return 0
    Lstar = {}
    for s in ("scoring", "mood"):
        if s in gated:
            rr = S2["sweep"][s]["recovered"][key_fit[s]]; cand = [L for L in layers if rr[L] is not None]
            if cand:
                Lstar[s] = max(cand, key=lambda L: rr[L])
    S2["Lstar"] = Lstar; save()

    def direction(k, L):
        ds = []
        for p in [q for q in pairs if q["set"] == k and split[(k, q["eid"])] == "fit"]:
            cv, ov = V[(p["eid"], p["cue_version"])], V[(p["eid"], p["other_version"])]
            if k == "mood":
                src, tgt, ns = trait_site(cv, ov, sweep_items)
            else:
                src, tgt, nB = r1_site(cv, ov, True); ns = [nB or stub_n + GEN_TAIL] * 2
            a, b = capture(src, ns, [L]), capture(tgt, ns, [L])
            ds += [(x[L].float().mean(0) - y[L].float().mean(0)).cpu().numpy() for x, y in zip(a, b)]
        v = np.mean(ds, 0); return v / np.linalg.norm(v)

    def randoms(L, k):
        acts = []
        for p in pairs[:: max(1, len(pairs) // 30)]:
            ov = V[(p["eid"], p["other_version"])]; q = r1_seqs(ov)[:1]
            acts.append(capture(q, [stub_n + GEN_TAIL + 64], [L])[0][L].float())
        X = torch.cat(acts); X = X - X.mean(0); cov = (X.T @ X / len(X)).double()
        w, U = torch.linalg.eigh(cov); g = torch.Generator(device="cuda").manual_seed(SEED + L)
        z = torch.randn(k, cov.shape[0], generator=g, dtype=torch.float64, device="cuda"); x = (z * w.clamp(min=0).sqrt()) @ U.T
        return (x / x.norm(dim=1, keepdim=True)).float().cpu().numpy()

    nr = 2 if smoke else N_RAND; SUB = {}; dirs = {}
    for s, L in Lstar.items():
        for k in ("scoring", "mood"):
            if k in Lstar or smoke:
                dirs[(k, L)] = direction(k, L)
        rnd = randoms(L, nr)
        conds = {"full": None, **{f"d_{k}": dirs[(k, L)] for k in ("scoring", "mood") if (k, L) in dirs}, **{f"rand{j}": rnd[j] for j in range(nr)}}
        res = {k: [] for k in conds}; base = []
        for tset in ("scoring", "mood"):
            for p in [q for q in pairs if q["set"] == tset and split[(tset, q["eid"])] == "eval"]:
                cv, ov = V[(p["eid"], p["cue_version"])], V[(p["eid"], p["other_version"])]
                src, tgt, nB = r1_site(cv, ov, True); n = nB or stub_n + GEN_TAIL
                acts = capture(src, [n] * 2, [L]); pre_t = prep(tgt, [n] * 2)
                tsrc, ttgt, tns = trait_site(cv, ov, traits); tacts = capture(tsrc, tns, [L]); tpre = prep(ttgt, tns)
                bs, bt = trait_scores(run.readouts(tsrc), traits), trait_scores(run.readouts(ttgt), traits)
                base.append({"set": tset, "eid": p["eid"], "ovr_src": RO[(p["eid"], p["cue_version"])][pick], "ovr_tgt": RO[(p["eid"], p["other_version"])][pick],
                             "ON_src": bs["ON"], "ON_tgt": bt["ON"], "OFF_src": bs["OFF"], "OFF_tgt": bt["OFF"], "mass_tgt": bt["mass"]})
                for k, d in conds.items():
                    mode, dt = ("full", None) if d is None else ("rank1", torch.tensor(d))
                    po = patched(tgt, [n] * 2, pre_t, acts, L, mode, dt); pt = trait_scores(patched(ttgt, tns, tpre, tacts, L, mode, dt), traits)
                    res[k].append({"set": tset, "eid": p["eid"], "override": ovr(po, lets_r1), "override_mass": float(np.mean([a + b for a, b in po])),
                                   "ON": pt["ON"], "OFF": pt["OFF"], "trait_mass": pt["mass"]})
                print(f"subspace L{L} {tset} {p['eid'][:8]} ({(time.time() - t0) / 60:.0f} min)", flush=True)
        SUB[s] = {"L": L, "base": base, "results": res}; R["subspace"] = SUB; save()
    np.savez(out / "dd2_dirs.npz", **{f"{k}@{L}": v for (k, L), v in dirs.items()})
    R["dir_cos"] = {f"L{L}": float(dirs[("scoring", L)] @ dirs[("mood", L)]) for (k, L) in dirs if k == "scoring" and ("mood", L) in dirs}
    R["minutes"] = (time.time() - t0) / 60
    if smoke:
        R["note"] = "smoke: projection = scale the per-pair times in the log to 100 pairs, 32 layers, 20 randoms"
    save(); print(f"DONE in {R['minutes']:.0f} min", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
