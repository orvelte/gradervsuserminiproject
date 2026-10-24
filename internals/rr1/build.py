#!/usr/bin/env python3
"""RR1 inputs (PREREG RR1): the as-built swapped twins at the decision site, from results/dd2/prompts.jsonl.

    python internals/rr1/build.py      # writes results/rr1/prompts.jsonl
"""
import json
import random
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
rows = [json.loads(l) for l in (REPO / "results/dd2/prompts.jsonl").read_text().splitlines()]
V = {(r["eid"], r["version"]): r for r in rows if r["kind"] == "version"}
pairs = [r for r in rows if r["kind"] == "pair" and r["variant"] == "as_built"]
sc = [p for p in pairs if p["set"] == "scoring"]
mood = [p for p in pairs if p["set"] == "mood"]; rng = random.Random(20261024)
pick = []
for cell, k in (("HO-G~holdout", 7), ("HO-D~holdout", 13)):  # 20 of 32, stratified (11 / 21 available)
    c = sorted([p for p in mood if p["cell"] == cell], key=lambda p: p["eid"]); pick += rng.sample(c, k)
out = []
for s, ps in (("scoring", sc), ("mood", pick)):
    for p in ps:
        sw = p["other_version"] if p["cue_version"] == "orig" else p["cue_version"]
        out.append({"id": f"{s}|{p['eid']}|{sw}", "set": s, "eid": p["eid"], "cell": p["cell"], "version": sw,
                    "cue_is_orig": p["cue_version"] == "orig", "text": V[(p["eid"], sw)]["r1_prefix"]})
(REPO / "results/rr1/prompts.jsonl").write_text("\n".join(json.dumps(r) for r in out) + "\n")
print(len(out), {s: sum(r["set"] == s for r in out) for s in ("scoring", "mood")})
