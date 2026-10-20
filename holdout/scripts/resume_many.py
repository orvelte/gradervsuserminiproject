#!/usr/bin/env python3
"""Resume many holdout runs in parallel from their last checkpoints (PAID: uses the configured provider).

    python holdout/scripts/resume_many.py results/holdout/v1_qwen38/to_resume.txt --workers 24 [overrides ...]
Each line is a step-N directory. Continuations land in results/holdout/<batch>_resume/<cell>/... so the analysis can
take, per original run, the resumed continuation in place of the partial run.
"""
from __future__ import annotations

import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def main(argv) -> int:
    lst = Path(argv[0]); workers = int(argv[argv.index("--workers") + 1]) if "--workers" in argv else 24
    extra = [a for i, a in enumerate(argv[1:], 1) if a != "--workers" and argv[i - 1] != "--workers"]
    steps = [Path(l.strip()) for l in lst.read_text().splitlines() if l.strip()]

    def one(step: Path) -> tuple[str, int]:
        p = step.parts; i = p.index("holdout"); batch, cell = p[i + 1].removesuffix("_resume"), p[i + 2]   # a resume of a resume stays in <batch>_resume
        out = REPO / "results" / "holdout" / f"{batch}_resume" / cell
        cmd = [sys.executable, str(REPO / "holdout" / "scripts" / "resume_ho.py"), str(step), "--results-dir", str(out), "--no-judge"] + extra
        r = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True)
        return str(step), r.returncode

    with ThreadPoolExecutor(workers) as ex:
        res = list(ex.map(one, steps))
    bad = [s for s, rc in res if rc]
    print(f"{len(res) - len(bad)}/{len(res)} resumed OK" + (f"; failed: {bad[:5]}" if bad else ""))
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
