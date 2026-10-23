#!/usr/bin/env python3
"""On the pod: DD2 teacher-forced counterfactuals and activation patching (PREREG DD2 + amendments 1–2).

    python pod_dd2.py prompts.jsonl out/ [--smoke] [--stage1-only]

Input from internals/dd2/build.py. Layers are 1-based block outputs (layers[L-1]). Every number goes to out/dd2.json
as it is produced. Gates, as pre-registered:
  gate0   R1 (in-place stub) and R2 (user-turn probe) P(override) on the 72 originals vs resampled p_game:
          R1 if ρ ≥ .5, else R2, else stop.
  stage1  cue gaps on P(override) per (set, variant); full-residual layer sweep (4..64 step 4, sites A/B) for scoring
          and full; norm-matched random-perturbation band at the 3 best layers; pass = ΔP_real − band95 ≥ 0.10.
  stage2  only if full passes in some variant (quote preferred): mood ON sweep, mood trait gaps, cross-fitted rank-1
          subspace patching (d_scoring, d_mood) and rank-2 span patching against 20 projection-matched random
          directions, full battery for real directions, ON items for random ones.
Patch sites are aligned from the end and asserted to lie in the token-identical suffix.
--smoke: 2 pairs per (set, variant), layers {16, 32, 48}, 2 random draws/directions; ignores gates.
"""
from __future__ import annotations

import copy
import hashlib
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
ON = ("competitiveness", "ambition")
OFF = ("rule_breaking", "dishonesty", "approval_seeking")
GEN_TAIL = 6
GATE1 = 0.10
SETS1 = ("scoring", "full")


class Hooks:
    def __init__(self, layers):
        self.patch = {}; self.capture = set(); self.store = {}; self.keep = 1
        for i, m in enumerate(layers):
            m.register_forward_hook(self._f(i + 1))

    def _f(self, L):
        def f(_m, _inp, out):
            h = out[0] if isinstance(out, tuple) else out
            if L in self.capture:
                self.store[L] = h[0, -self.keep:].detach().clone()
            if L in self.patch:
                h = self.patch[L](h)
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


def p_worse(pa, pb, worse):
    t = pa + pb
    return ((pa if worse == "A" else pb) / t if t > 0 else float("nan")), t


class Model:
    def __init__(self):
        self.tok = AutoTokenizer.from_pretrained(MODEL); cfg = AutoConfig.from_pretrained(MODEL)
        self.m = AutoModelForCausalLM.from_pretrained(MODEL, dtype=torch.bfloat16, device_map="cuda").eval()
        n = getattr(getattr(cfg, "text_config", cfg), "num_hidden_layers")
        layers = max((x for x in self.m.modules() if isinstance(x, torch.nn.ModuleList) and len(x) == n), key=lambda x: sum(p.numel() for p in x.parameters()))
        self.H = Hooks(layers); self.nL = n; self.A, self.B = letter_ids(self.tok); self._enc = {}

    def enc(self, t):
        k = hashlib.sha1(t.encode()).hexdigest()
        if k not in self._enc:
            self._enc[k] = self.tok(t, add_special_tokens=False).input_ids
        return self._enc[k]

    @torch.no_grad()
    def prep(self, seqs, ns):
        c = min(lcp(seqs), min(len(q) - n for q, n in zip(seqs, ns))); assert c > 0
        return self.m(input_ids=torch.tensor([seqs[0][:c]], device="cuda"), use_cache=True).past_key_values, c

    @torch.no_grad()
    def cont(self, pre, ids):
        base, c = pre
        o = self.m(input_ids=torch.tensor([ids[c:]], device="cuda"), past_key_values=copy.deepcopy(base), use_cache=True,
                   cache_position=torch.arange(c, len(ids), device="cuda"))
        p = torch.softmax(o.logits[0, -1].float(), -1)
        return float(p[self.A].sum()), float(p[self.B].sum())

    def readouts(self, seqs):
        pre = self.prep(seqs, [1] * len(seqs))
        return [self.cont(pre, q) for q in seqs]

    @torch.no_grad()
    def capture(self, seqs, ns, Ls, pre=None):
        pre = pre or self.prep(seqs, ns); out = []
        for q, n in zip(seqs, ns):
            self.H.capture, self.H.keep = set(Ls), n
            self.cont(pre, q)
            out.append({L: self.H.store[L].clone() for L in Ls})
        self.H.capture, self.H.keep = set(), 1
        return out

    def patched(self, seqs, ns, pre, fns):
        """fns[i]: {L: hook fn} for sequence i."""
        res = []
        for q, n, f in zip(seqs, ns, fns):
            self.H.patch = f; res.append(self.cont(pre, q)); self.H.patch = {}
        return res


def full_fn(src, n):
    def fn(h):
        h = h.clone(); h[0, -n:] = src[-n:].to(h.dtype); return h
    return fn


def rank_fn(src, n, basis, coef_dir=None):
    """Patch the target's projection onto span(basis) with the source's. If coef_dir is given (projection-matched
    random control), use coefficient (src − tgt)·coef_dir along the single random basis vector instead."""
    B = basis.float()

    def fn(h):
        h = h.clone(); tgt = h[0, -n:].float(); diff = src[-n:].float().to(tgt.device) - tgt
        if coef_dir is not None:
            c = diff @ coef_dir.float().to(tgt.device); h[0, -n:] = (tgt + c[:, None] * B[0][None, :].to(tgt.device)).to(h.dtype)
        else:
            Bd = B.to(tgt.device); h[0, -n:] = (tgt + (diff @ Bd.T) @ Bd).to(h.dtype)
        return h
    return fn


def noise_fn(src, n, dirs):
    """Norm-matched random perturbation: per position, a random unit direction scaled to ‖src − tgt‖."""
    def fn(h):
        h = h.clone(); tgt = h[0, -n:].float(); nr = (src[-n:].float().to(tgt.device) - tgt).norm(dim=-1)
        h[0, -n:] = (tgt + nr[:, None] * dirs[:n].to(tgt.device)).to(h.dtype); return h
    return fn


def main(argv) -> int:
    rows = [json.loads(l) for l in open(argv[0]) if l.strip()]; out = Path(argv[1]); out.mkdir(parents=True, exist_ok=True)
    smoke = "--smoke" in argv; t0 = time.time(); R = {"smoke": smoke}; rng = np.random.default_rng(SEED)
    hdr = rows[0]; V = {(r["eid"], r["version"]): r for r in rows if r["kind"] == "version"}; pairs = [r for r in rows if r["kind"] == "pair"]
    if smoke:
        pairs = [p for s in ("scoring", "mood", "full") for v in ("as_built", "quote") for p in [q for q in pairs if q["set"] == s and q["variant"] == v][:2]]
    M = Model(); enc = M.enc
    save = lambda: (out / "dd2.json").write_text(json.dumps(R, indent=1))  # noqa: E731
    log = lambda *a: print(f"[{(time.time() - t0) / 60:5.1f} min]", *a, flush=True)  # noqa: E731
    log("model loaded")
    assert len(enc("<|im_end|>\n<|im_start|>assistant\n<think>\n")) == GEN_TAIL
    stub_n = max(len(enc(hdr["stub"][o])) for o in ("AB", "BA")); nA = stub_n + GEN_TAIL; nB = nA + 64
    lets_r1 = [hdr["stub_override_letter"][o] for o in ("AB", "BA")]
    traits = hdr["traits"]; on_items = [x for x in traits if x["measure"] in ON]
    sweep_items = [it for m in ON for it in [x for x in traits if x["measure"] == m][:4]]
    r1 = lambda v: [enc(v["r1_prefix"] + hdr["stub"][o]) for o in ("AB", "BA")]  # noqa: E731
    r2 = lambda v: [enc(v["r2_head"] + hdr["probe"][o] + v["r2_tail"]) for o in ("AB", "BA")]  # noqa: E731
    tseq = lambda v, items: [enc(v["r2_head"] + it["text"] + v["r2_tail"]) for it in items]  # noqa: E731
    ovr = lambda ps: float(np.mean([p_worse(a, b, w)[0] for (a, b), w in zip(ps, lets_r1)]))  # noqa: E731

    def tscores(ps, items):
        d = {}
        for (a, b), it in zip(ps, items):
            d.setdefault(it["measure"], []).append(p_worse(a, b, it["worse"]))
        r = {m: float(np.mean([x for x, _ in v])) for m, v in d.items()}
        r["ON"] = float(np.mean([r[m] for m in ON if m in r])); r["mass"] = float(np.mean([t for v in d.values() for _, t in v]))
        if all(m in r for m in OFF):
            r["OFF"] = float(np.mean([r[m] for m in OFF]))
        return r

    # ---------------- gate 0 + stage 1 read-outs (P(override) only) ----------------
    need = sorted({(p["eid"], p[k]) for p in pairs for k in ("cue_version", "other_version")} | (set() if smoke else {k for k in V if k[1] == "orig"}))
    RO, seen = {}, {}
    for i, k in enumerate(need):
        v = V[k]; h = hashlib.sha1(v["r1_prefix"].encode()).hexdigest()
        if h in seen:  # quote variant identical to as-built (no quote found)
            RO[k] = dict(RO[seen[h]]); continue
        a = M.readouts(r1(v)); b = M.readouts(r2(v))
        RO[k] = {"r1": ovr(a), "r1_mass": float(np.mean([x + y for x, y in a])),
                 "r2": float(np.mean([p_worse(x, y, w)[0] for (x, y), w in zip(b, [hdr["probe_override_letter"][o] for o in ("AB", "BA")])])),
                 "r2_mass": float(np.mean([x + y for x, y in b]))}
        seen[h] = k
        if i % 25 == 0:
            log(f"read-outs {i + 1}/{len(need)}")
    R["readouts"] = {f"{e}|{v}": x for (e, v), x in RO.items()}; save()
    if smoke:
        pick = "r1"; R["gate0"] = {"readout": "r1 (smoke)"}
    else:
        orig = [k for k in RO if k[1] == "orig"]; pg = [V[k]["p_game"] for k in orig]; gv = [V[k]["cell"] == "HO-G~visible" for k in orig]
        g0 = {r: {"rho_all": float(spearmanr([RO[k][r] for k in orig], pg).statistic),
                  "rho_Gvis": float(spearmanr([RO[k][r] for k, g in zip(orig, gv) if g], [x for x, g in zip(pg, gv) if g]).statistic),
                  "mass": float(np.mean([RO[k][f"{r}_mass"] for k in orig]))} for r in ("r1", "r2")}
        pick = "r1" if g0["r1"]["rho_all"] >= 0.5 else "r2" if g0["r2"]["rho_all"] >= 0.5 else None
        R["gate0"] = {**g0, "readout": pick}; save(); log("gate0", json.dumps(R["gate0"]))
        if pick is None:
            R["verdict"] = "uninformative (gate 0)"; save(); return 0

    def gap(ds):
        d = np.array(ds); perm = [np.mean(d * rng.choice([-1, 1], len(d))) for _ in range(10000)]
        return {"mean": float(d.mean()), "p": float((np.sum(np.array(perm) >= d.mean()) + 1) / 10001), "n": int(len(d)), "per_pair": d.tolist()}
    S1 = {"gaps": {}}
    for s in ("scoring", "mood", "full"):
        for var in ("as_built", "quote"):
            ps = [p for p in pairs if p["set"] == s and p["variant"] == var]
            if ps:
                S1["gaps"][f"{s}/{var}"] = gap([RO[(p["eid"], p["cue_version"])][pick] - RO[(p["eid"], p["other_version"])][pick] for p in ps])
        if f"{s}/as_built" in S1["gaps"] and f"{s}/quote" in S1["gaps"]:
            S1["gaps"][f"{s}/quote−as_built"] = gap([q - a for q, a in zip(S1["gaps"][f"{s}/quote"]["per_pair"], S1["gaps"][f"{s}/as_built"]["per_pair"])])
    R["stage1"] = S1; save(); log("stage1 gaps", {k: round(v["mean"], 3) for k, v in S1["gaps"].items()})

    # ---------------- stage 1 sweep (scoring, full; both variants) ----------------
    layers = [16, 32, 48] if smoke else list(range(4, M.nL + 1, 4))
    split = {}
    for s in ("scoring", "mood", "full"):
        base = [p for p in pairs if p["set"] == s and p["variant"] == "as_built"]
        for c in sorted({p["cell"] for p in base}):
            for j, p in enumerate(sorted([q for q in base if q["cell"] == c], key=lambda q: q["eid"])):
                split[(s, p["eid"])] = "A" if j % 2 == 0 else "B"

    def pair_seqs(p):
        cv, ov = V[(p["eid"], p["cue_version"])], V[(p["eid"], p["other_version"])]
        src, tgt = r1(cv), r1(ov); cs = min(csuffix(a, b) for a, b in zip(src, tgt)); assert cs >= nA, (p["eid"], cs)
        return cv, ov, src, tgt, (nB if cs >= nB else None)

    def covariance(L, ps):
        X = []
        for p in ps[:30]:
            ov = V[(p["eid"], p["other_version"])]; X.append(M.capture(r1(ov)[:1], [nB], [L])[0][L].float())
        X = torch.cat(X); X = X - X.mean(0); return (X.T @ X / len(X)).double()

    def gauss_dirs(cov, k, seed):
        w, U = torch.linalg.eigh(cov); g = torch.Generator(device="cuda").manual_seed(seed)
        z = torch.randn(k, cov.shape[0], generator=g, dtype=torch.float64, device="cuda"); x = (z * w.clamp(min=0).sqrt()) @ U.T
        return (x / x.norm(dim=1, keepdim=True)).float()

    SW = {}; sweep_cache = {}
    for s in SETS1:
        for var in ("as_built", "quote"):
            ps = [p for p in pairs if p["set"] == s and p["variant"] == var]
            rec = {"A": {L: [] for L in layers}, "B": {L: [] for L in layers}}; base = []; excl = 0
            for p in ps:
                cv, ov, src, tgt, nb = pair_seqs(p)
                key = (hashlib.sha1(cv["r1_prefix"].encode()).hexdigest(), hashlib.sha1(ov["r1_prefix"].encode()).hexdigest())
                if key in sweep_cache:
                    vals = sweep_cache[key]
                else:
                    nmax = nb or nA; acts = M.capture(src, [nmax] * 2, layers); pre = M.prep(tgt, [nmax] * 2); vals = {}
                    for site, n in (("A", nA), ("B", nb)):
                        if n:
                            vals[site] = {L: ovr(M.patched(tgt, [n] * 2, pre, [{L: full_fn(a[L], n)} for a in acts])) for L in layers}
                    sweep_cache[key] = vals
                excl += nb is None
                for site in vals:
                    for L in layers:
                        rec[site][L].append({"eid": p["eid"], "val": vals[site][L]})
                base.append({"eid": p["eid"], "src": RO[(p["eid"], p["cue_version"])][pick], "tgt": RO[(p["eid"], p["other_version"])][pick], "siteB": nb is not None})
                log(f"sweep {s}/{var} {p['eid'][:8]}")
            tg = {b["eid"]: b["tgt"] for b in base}; gapm = float(np.mean([b["src"] - b["tgt"] for b in base]))
            dP = {site: {L: (float(np.mean([x["val"] - tg[x["eid"]] for x in rec[site][L]])) if rec[site][L] else None) for L in layers} for site in rec}
            SW[f"{s}/{var}"] = {"dP": dP, "recovered": {site: {L: (v / gapm if v is not None and gapm else None) for L, v in d.items()} for site, d in dP.items()},
                                "gap": gapm, "excluded_site_B": excl, "raw": {site: {str(L): v for L, v in d.items()} for site, d in rec.items()}, "base": base}
            R["sweep"] = SW; save()
    # random-perturbation band at the 3 best layers (site B; site A for pairs excluded from B)
    G1 = {}
    for key, sw in SW.items():
        s, var = key.split("/"); ps = [p for p in pairs if p["set"] == s and p["variant"] == var]
        top = sorted([L for L in layers if sw["dP"]["B"][L] is not None], key=lambda L: -sw["dP"]["B"][L])[:3]
        bands = {}
        for L in top:
            cov = covariance(L, ps); draws = []
            for j in range(2 if smoke else 8):
                vals = []
                for p in ps:
                    cv, ov, src, tgt, nb = pair_seqs(p)
                    if nb is None:  # same pairs as the real site-B ΔP
                        continue
                    n = nb
                    acts = M.capture(src, [n] * 2, [L]); pre = M.prep(tgt, [n] * 2)
                    dirs = gauss_dirs(cov, n, SEED + 1000 * L + j)
                    vals.append(ovr(M.patched(tgt, [n] * 2, pre, [{L: noise_fn(a[L], n, dirs)} for a in acts])) - RO[(p["eid"], p["other_version"])][pick])
                draws.append(float(np.mean(vals)))
            bands[L] = {"real_dP": sw["dP"]["B"][L], "band95": float(np.percentile(draws, 95)), "draws": draws}
            log(f"band {key} L{L}: real {sw['dP']['B'][L]:+.3f} band95 {bands[L]['band95']:+.3f}")
        G1[key] = {"layers": bands, "pass": bool(any(b["real_dP"] - b["band95"] >= GATE1 for b in bands.values()))}
        R["gate1"] = G1; save()
    var2 = "quote" if G1.get("full/quote", {}).get("pass") else "as_built" if G1.get("full/as_built", {}).get("pass") else None
    R["stage2_variant"] = var2; save()
    if "--stage1-only" in argv or (var2 is None and not smoke):
        R["verdict"] = None if var2 else "full patching fails at this site in both variants: move the read site"; R["minutes"] = (time.time() - t0) / 60; save()
        log("stage 1 done; stage 2", "skipped" if var2 is None else "not requested"); return 0
    var2 = var2 or "quote"

    # ---------------- stage 2 ----------------
    S2 = {"variant": var2}
    mp = [p for p in pairs if p["set"] == "mood" and p["variant"] == var2]
    # mood trait gaps (full battery) and ON sweep
    tg_map = {}
    for p in mp:
        for k in ("cue_version", "other_version"):
            kk = (p["eid"], p[k])
            if kk not in tg_map:
                tg_map[kk] = tscores(M.readouts(tseq(V[kk], traits)), traits)
    S2["mood_trait_gaps"] = {m: gap([tg_map[(p["eid"], p["cue_version"])][m] - tg_map[(p["eid"], p["other_version"])][m] for p in mp]) for m in ("ON", "OFF") + ON + OFF}
    R["stage2"] = S2; save(); log("mood trait gaps", {m: round(v["mean"], 3) for m, v in S2["mood_trait_gaps"].items()})

    def tsite(p, items):
        cv, ov = V[(p["eid"], p["cue_version"])], V[(p["eid"], p["other_version"])]
        src, tgt = tseq(cv, items), tseq(ov, items); ns = [len(q) - lcp(tgt) for q in tgt]
        for a, b, n in zip(src, tgt, ns):
            assert a[-n:] == b[-n:]
        return src, tgt, ns
    msw = {L: [] for L in layers}; mbase = []
    for p in mp:
        src, tgt, ns = tsite(p, sweep_items); acts = M.capture(src, ns, layers); pre = M.prep(tgt, ns)
        mbase.append({"eid": p["eid"], "src": tscores(M.readouts(src), sweep_items)["ON"], "tgt": tscores(M.readouts(tgt), sweep_items)["ON"]})
        for L in layers:
            msw[L].append({"eid": p["eid"], "val": tscores(M.patched(tgt, ns, pre, [{L: full_fn(a[L], n)} for a, n in zip(acts, ns)]), sweep_items)["ON"]})
        log(f"mood sweep {p['eid'][:8]}")
    S2["mood_sweep"] = {"raw": {str(L): v for L, v in msw.items()}, "base": mbase}; save()

    def rec_half(raw, base, half_set, s):
        b = {x["eid"]: x for x in base if split[(s, x["eid"])] in half_set}
        g = np.mean([x["src"] - x["tgt"] for x in b.values()]) if b else 0
        return {L: (float(np.mean([r["val"] - b[r["eid"]]["tgt"] for r in raw[L] if r["eid"] in b])) / g if g and any(r["eid"] in b for r in raw[L]) else -1e9) for L in raw}
    sc_raw = {L: [x for x in SW[f"scoring/{var2}"]["raw"]["B"][str(L)]] for L in layers} if f"scoring/{var2}" in SW else None
    do_scoring = G1.get(f"scoring/{var2}", {}).get("pass", False) or smoke
    S2["scoring_tested"] = do_scoring

    def direction(k, L, half):
        ds = []
        for p in [q for q in pairs if q["set"] == k and q["variant"] == var2 and split[(k, q["eid"])] == half]:
            if k == "mood":
                src, tgt, ns = tsite(p, sweep_items)
            else:
                _, _, src, tgt, nb = pair_seqs(p); ns = [nb or nA] * 2
            a, b = M.capture(src, ns, [L]), M.capture(tgt, ns, [L])
            ds += [(x[L].float().mean(0) - y[L].float().mean(0)) for x, y in zip(a, b)]
        v = torch.stack(ds).mean(0); return v / v.norm()

    nr = 2 if smoke else 20; folds = {}
    for est, test in (("A", "B"), ("B", "A")):
        Ls = {"mood": max(layers, key=lambda L: rec_half(msw, mbase, {est}, "mood")[L])}
        if sc_raw:
            Ls["scoring"] = max(layers, key=lambda L: rec_half(sc_raw, SW[f"scoring/{var2}"]["base"], {est}, "scoring")[L])
        F = {"Lstar": Ls, "tests": {}}
        for tset, L in Ls.items():
            if tset == "scoring" and not do_scoring:
                continue
            d_s = direction("scoring", L, est) if (sc_raw and do_scoring) else None; d_m = direction("mood", L, est)
            basis = torch.stack([x for x in (d_s, d_m) if x is not None]); Q, _ = torch.linalg.qr(basis.T); span = Q.T
            cov = covariance(L, [p for p in pairs if p["set"] == tset and p["variant"] == var2]); rnd = gauss_dirs(cov, nr, SEED + 7 * L)
            own = d_s if tset == "scoring" else d_m
            conds = {"full": None, "d_mood": ("rank", d_m[None]), "span": ("rank", span), **({"d_scoring": ("rank", d_s[None])} if d_s is not None else {}),
                     **{f"rand{j}": ("rand", rnd[j][None]) for j in range(nr)}}
            res = {c: [] for c in conds}; base = []
            for p in [q for q in pairs if q["set"] == tset and q["variant"] == var2 and split[(tset, q["eid"])] == test]:
                cv, ov, src, tgt, nb = pair_seqs(p); n = nb or nA; acts = M.capture(src, [n] * 2, [L]); pre = M.prep(tgt, [n] * 2)
                tsrc, ttgt, tns = tsite(p, traits); tacts = M.capture(tsrc, tns, [L]); tpre = M.prep(ttgt, tns)
                osrc, otgt, ons = tsite(p, on_items); oacts = M.capture(osrc, ons, [L]); opre = M.prep(otgt, ons)
                bs, bt = tscores(M.readouts(tsrc), traits), tscores(M.readouts(ttgt), traits)
                base.append({"set": tset, "eid": p["eid"], "ovr_src": RO[(p["eid"], p["cue_version"])][pick], "ovr_tgt": RO[(p["eid"], p["other_version"])][pick],
                             "ON_src": bs["ON"], "ON_tgt": bt["ON"], "OFF_src": bs["OFF"], "OFF_tgt": bt["OFF"], "mass_tgt": bt["mass"]})
                for c, spec in conds.items():
                    def fn(a, nn):
                        if spec is None:
                            return full_fn(a[L], nn)
                        kind, B = spec
                        return rank_fn(a[L], nn, B) if kind == "rank" else rank_fn(a[L], nn, B, coef_dir=own)
                    po = M.patched(tgt, [n] * 2, pre, [{L: fn(a, n)} for a in acts])
                    if spec is not None and spec[0] == "rand":
                        pt = tscores(M.patched(otgt, ons, opre, [{L: fn(a, nn)} for a, nn in zip(oacts, ons)]), on_items)
                    else:
                        pt = tscores(M.patched(ttgt, tns, tpre, [{L: fn(a, nn)} for a, nn in zip(tacts, tns)]), traits)
                    res[c].append({"set": tset, "eid": p["eid"], "override": ovr(po), "override_mass": float(np.mean([x + y for x, y in po])),
                                   "ON": pt["ON"], "OFF": pt.get("OFF"), "trait_mass": pt["mass"]})
                log(f"subspace fold {est}->{test} {tset}@L{L} {p['eid'][:8]}")
            F["tests"][tset] = {"L": L, "base": base, "results": res,
                                "cos_s_m": float(d_s @ d_m) if d_s is not None else None}
            folds[f"{est}->{test}"] = F; S2["folds"] = folds; R["stage2"] = S2; save()
    R["minutes"] = (time.time() - t0) / 60; save(); log("DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
