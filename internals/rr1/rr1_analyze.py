#!/usr/bin/env python3
"""RR1 judging and analysis (PREREG RR1). Local.

    python internals/rr1/rr1_analyze.py [results/rr1/pod_out/samples.jsonl]

Pools sbpsmanalysis's original resampled turns for the RR1 trajectories (read-only) with the new twin samples,
shuffles them under blind ids, and labels every one with sbpsmanalysis's rubric (classification criteria verbatim;
its harness-only lines about local files and packets removed) using anthropic/claude-sonnet-5. The judge sees the
sampled turn and the last 3,000 characters of the prefix as context, never the arm or version. Judge check against
sbpsmanalysis's own labels on the originals: agreement ≥ 0.80 and κ ≥ 0.6. Writes results/rr1/labels.jsonl (cached)
and results/rr1/rr1.json.
"""
from __future__ import annotations

import asyncio
import json
import os
import random
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
SB = REPO.parent / "sbpsmanalysis"
OUT = REPO / "results" / "rr1"
JUDGE = "anthropic/claude-sonnet-5"
HARNESS_LINES = ("You are a smaller agent in this session", "Output one JSONL record per blind sample", "Retain every item",
                 "missing data. Only grade packet files", "wait indefinitely for future packets")


def rubric() -> str:
    lines = (SB / "sample_scoring_rubric.txt").read_text().splitlines(); out = []; skip = False
    for l in lines:
        if l.startswith("Output one JSONL record"):
            skip = True
        if skip or any(l.startswith(h) for h in HARNESS_LINES):
            continue
        out.append(l)
    return "\n".join(out).strip() + '\n\nReply with exactly one JSON object: {"label": "games|general|unclear", "evidence": "exact quote <=30 words", "confidence": "high|medium|low", "context_used": true|false, "note": "one brief explanation"}'


def kappa(a, b, cats=("games", "general", "unclear")):
    a, b = np.array(a), np.array(b); po = float(np.mean(a == b)); pe = sum(np.mean(a == c) * np.mean(b == c) for c in cats)
    return po, (po - pe) / (1 - pe) if pe < 1 else float("nan")


def collect(samples_path: Path) -> list[dict]:
    rows = [json.loads(l) for l in (REPO / "results/rr1/prompts.jsonl").read_text().splitlines()]
    pref = {json.loads(l)["eid"] + "|" + json.loads(l)["version"]: json.loads(l)["text"] for l in (REPO / "results/rr1/prompts.jsonl").read_text().splitlines()}
    orig_text = {}
    for r in map(json.loads, (REPO / "results/dd2/prompts.jsonl").read_text().splitlines()):
        if r.get("kind") == "version" and r["version"] == "orig":
            orig_text[r["eid"]] = r["r1_prefix"]
    mapping = {m["sample_id"]: m["blind_id"] for m in json.loads((SB / "artifacts/stage2/local_scoring/mapping_private.json").read_text())}
    theirs = {}
    for f in sorted((SB / "artifacts/stage2/local_scoring").glob("labels-shard-*.jsonl")):
        for l in f.read_text().splitlines():
            j = json.loads(l); theirs[j["blind_id"]] = j["label"]
    items = []
    for r in rows:
        for i in range(10):
            sid = f"{r['eid']}:{i:02d}"; s = json.loads((SB / "artifacts/stage2/samples" / f"{r['eid']}.{i:02d}.json").read_text())
            items.append({"key": f"orig|{r['set']}|{r['eid']}|{i}", "set": r["set"], "eid": r["eid"], "version": "orig", "turn": s["raw_completion"],
                          "context": orig_text[r["eid"]][-3000:], "their_label": theirs.get(mapping.get(sid))})
    for s in map(json.loads, samples_path.read_text().splitlines()):
        items.append({"key": f"twin|{s['set']}|{s['eid']}|{s['i']}", "set": s["set"], "eid": s["eid"], "version": s["version"], "turn": s["raw"],
                      "context": pref[s["eid"] + "|" + s["version"]][-3000:], "finish_reason": s["finish_reason"]})
    rng = random.Random(20261024); rng.shuffle(items)
    for j, it in enumerate(items):
        it["blind_id"] = f"rr1-{j:04d}"
    return items


async def judge(items: list[dict]) -> list[dict]:
    from dotenv import load_dotenv
    from openai import AsyncOpenAI
    load_dotenv(REPO / ".env", override=True)
    c = AsyncOpenAI(base_url="https://openrouter.ai/api/v1", api_key=os.environ["OPENROUTER_API_KEY"]); R = rubric()
    cache = OUT / "labels.jsonl"; done = {j["key"]: j for j in map(json.loads, cache.read_text().splitlines())} if cache.exists() else {}
    sem = asyncio.Semaphore(16)

    async def one(it):
        if it["key"] in done:
            return done[it["key"]]
        msg = (f"{R}\n\n=== Last part of the prefix (context; use only if needed) ===\n{it['context']}\n\n"
               f"=== The sampled next assistant turn ({it['blind_id']}) ===\n{it['turn']}")
        async with sem:
            for attempt in range(5):
                try:
                    x = await c.chat.completions.create(model=JUDGE, messages=[{"role": "user", "content": msg}], max_tokens=400)
                    t = x.choices[0].message.content or ""; j = json.loads(t[t.index("{"): t.rindex("}") + 1])
                    assert j["label"] in ("games", "general", "unclear")
                    return {**{k: v for k, v in it.items() if k not in ("turn", "context")}, **j}
                except Exception:  # noqa: BLE001
                    await asyncio.sleep(2 ** attempt)
        return {**{k: v for k, v in it.items() if k not in ("turn", "context")}, "label": None}
    res = await asyncio.gather(*(one(it) for it in items))
    cache.write_text("\n".join(json.dumps(r) for r in res) + "\n")
    return res


def analyze(lab: list[dict]) -> dict:
    o = [x for x in lab if x["version"] == "orig" and x.get("their_label") and x.get("label")]
    agree, kap = kappa([x["label"] for x in o], [x["their_label"] for x in o])
    pg = {}
    for x in lab:
        pg.setdefault((x["set"], x["eid"], "orig" if x["version"] == "orig" else "twin"), []).append(x.get("label") == "games")
    res = {"judge_check": {"n": len(o), "agreement": agree, "kappa": kap, "pass": bool(agree >= 0.8 and kap >= 0.6)},
           "unlabelled": sum(x.get("label") is None for x in lab)}
    rows = [json.loads(l) for l in (REPO / "results/rr1/prompts.jsonl").read_text().splitlines()]
    rng = np.random.default_rng(20261024)
    for s in ("scoring", "mood"):
        d = []
        for r in [q for q in rows if q["set"] == s]:
            po, pt = np.mean(pg[(s, r["eid"], "orig")]), np.mean(pg[(s, r["eid"], "twin")])
            d.append(po - pt if r["cue_is_orig"] else pt - po)   # cue version − other version
        d = np.array(d); perm = [np.mean(d * rng.choice([-1, 1], len(d))) for _ in range(10000)]
        res[s] = {"delta": float(d.mean()), "p_two_sided": float(np.mean(np.abs(perm) >= abs(d.mean()))), "n": int(len(d)), "per_traj": d.tolist()}
    res["scoring"]["reading"] = "cue acts directly on behaviour" if res["scoring"]["delta"] >= 0.30 else "behaviour carried by the trajectory"
    m = res["mood"]; res["mood"]["reading"] = "read-out carries frame bias" if abs(m["delta"]) < 0.05 and m["p_two_sided"] >= 0.05 else "frame swap moves behaviour"
    return res


def main(a) -> int:
    items = collect(Path(a[0]) if a else OUT / "pod_out" / "samples.jsonl")
    lab = asyncio.run(judge(items)); res = analyze(lab)
    (OUT / "rr1.json").write_text(json.dumps(res, indent=1)); print(json.dumps({k: v for k, v in res.items() if k not in ("scoring", "mood")} | {s: {k: res[s][k] for k in ("delta", "p_two_sided", "n", "reading")} for s in ("scoring", "mood")}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
