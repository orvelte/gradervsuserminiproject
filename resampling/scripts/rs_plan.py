#!/usr/bin/env python3
"""Build a continuation plan (JSON for rs_run.py continue) for one or more source runs.

    python resampling/scripts/rs_plan.py <stage> <out.json> --sources U0/run-27[,N0/run-4,...] --conditions C0,C1 --resamples 3
    python resampling/scripts/rs_plan.py <stage> <out.json> --sources U0/run-27 --conditions C2 --resamples 3 --replacements replacements.json

Prefill rules (PREREG.md): C0-natural = P's reasoning (trailing spaces stripped, newlines kept); C1-keep = reasoning
up to and including S verbatim; C2-replace = P's reasoning + S' from replacements.json {source_run_id: [S', ...]}, one
per resample index (without replacement). Stage 1 uses the source run's own data only."""
from __future__ import annotations

import glob
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
from rs_prefix import build  # noqa: E402

COND = {"C0": "C0-natural", "C1": "C1-keep", "C2": "C2-replace"}


def run_dir(source_id: str) -> Path:
    arm, run = source_id.split("/")
    hits = glob.glob(str(REPO_ROOT / "results" / "openai-gpt-oss-120b" / arm / "*" / "*" / "*" / run))
    assert len(hits) == 1, (source_id, hits)
    return Path(hits[0])


def prefills(p: dict, cond: str, idx: int, replacements: dict | None) -> tuple[str, str | None, str]:
    base = p["prefix_reasoning"].rstrip(" ")
    if cond == "C0":
        return base, None, "none"
    if cond == "C1":
        full = p["full_turn_reasoning"]; i = full.find(p["sentence_S"]); assert i >= 0
        return full[: i + len(p["sentence_S"])], p["sentence_S"], "S"
    if cond == "C2":
        cands = (replacements or {}).get(p["source_run_id"]) or []
        assert idx < len(cands), f"no replacement sentence #{idx} for {p['source_run_id']}"
        sp = cands[idx]
        joiner = "" if base.endswith("\n") or not base else " "
        return base + joiner + sp, sp, "S'"
    raise ValueError(cond)


def main(argv):
    stage, out = argv[0], Path(argv[1])
    sources = argv[argv.index("--sources") + 1].split(",")
    conds = argv[argv.index("--conditions") + 1].split(",")
    n = int(argv[argv.index("--resamples") + 1])
    reps = json.loads(Path(argv[argv.index("--replacements") + 1]).read_text()) if "--replacements" in argv else None
    jobs = []
    for sid in sources:
        d = run_dir(sid); p = build(d)
        for cond in conds:
            for i in range(n):
                text, sent, kind = prefills(p, cond, i, reps)
                jobs.append({"job_id": f"{sid.replace('/', '_')}_t{p['prefix_turn']}_{cond}_{i}", "source_run_dir": str(d), "prefix_turn": p["prefix_turn"],
                             "condition": COND[cond], "resample_idx": i, "prefill": text, "prefill_sentence": sent, "sentence_kind": kind})
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"stage": stage, "jobs": jobs}, indent=1))
    print(f"wrote {len(jobs)} jobs to {out}")
    for j in jobs:
        print(f"  {j['job_id']}: prefill ends {j['prefill'][-90:]!r}")


if __name__ == "__main__":
    main(sys.argv[1:])
