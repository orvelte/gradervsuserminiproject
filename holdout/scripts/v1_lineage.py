#!/usr/bin/env python3
"""Group V1 runs into lineages (an original run and its resumed continuations share their first assistant turn) and
list, for every lineage without a complete run, its furthest checkpoint to resume from.

    python holdout/scripts/v1_lineage.py   -> writes results/holdout/v1_qwen38/to_resume2.txt and prints a summary
"""
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "holdout"))
import v1_analysis as V  # noqa: E402


def key(msgs: list[dict]) -> str | None:
    a = [m for m in msgs if m.get("role") == "assistant" and m.get("_vllm")]
    return hashlib.sha256(json.dumps(a[0].get("_vllm", {}).get("completion_token_ids", [])).encode()).hexdigest() if a else None


def last_step(run: Path) -> Path | None:
    st = sorted(run.glob("step-*"), key=lambda p: int(p.name.split("-")[1]))
    return st[-1] if st else None


def main() -> int:
    lineages = defaultdict(list)
    for root in ("v1_qwen38", "v1_qwen38_resume"):
        for run in sorted((REPO / "results/holdout" / root).glob("*/*/*/*/run-*")):
            st = last_step(run)
            src = run / "final" / "messages.json" if (run / "final" / "messages.json").exists() else (st / "messages.json" if st else None)
            if not src or not src.exists():
                continue
            k = key(json.loads(src.read_text()))
            if k:
                lineages[(run.parts[run.parts.index("holdout") + 2], k)].append(run)
    todo, summary = [], defaultdict(lambda: [0, 0])
    for (cell, _), runs in lineages.items():
        if any(V.complete(r) for r in runs):
            summary[cell][0] += 1; continue
        best = max(runs, key=lambda r: int(last_step(r).name.split("-")[1]) if last_step(r) else -1)
        if last_step(best):
            todo.append(str(last_step(best))); summary[cell][1] += 1
    (REPO / "results/holdout/v1_qwen38/to_resume2.txt").write_text("\n".join(todo) + "\n")
    for c, (done, left) in sorted(summary.items()):
        print(f"{c:14} complete lineages {done:2}  to resume {left:2}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
