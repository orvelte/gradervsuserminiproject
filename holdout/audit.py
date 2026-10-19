#!/usr/bin/env python3
"""Audit export for holdout runs (spec step 5): N random runs per cell as markdown.

    python holdout/audit.py results/holdout/<batch> [--n 10] [--seed 0] [--blind] [--out audit/holdout]
Each file: the transcript (deploysim's renderer), the final router.py and other agent files. Without --blind it
also shows the labels, evidence and measures; --blind writes R01.md ... and a key file outside the folder.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(REPO / "deploysim" / "labels"))
import labels as L  # noqa: E402
import audit as DA  # noqa: E402  (deploysim/labels/audit.py: transcript renderer)


def render(run: Path, blind: bool, rid: str) -> str:
    msgs = json.loads((run / "final" / "messages.json").read_text())
    head = [f"# Rollout {rid}", ""]
    if not blind:
        o = L.label_run(run)
        head += [f"`{run}`", "", f"**Labels:** {o['labels']}  ", f"**Measures:** {o['measures']}", "", "```json", json.dumps(o["evidence"], indent=1)[:4000], "```", "",
                 "## Auditor checklist", "- [ ] labels correct  - [ ] missing: ____  - [ ] wrong: ____  - [ ] disclosed: yes / no", ""]
    body = DA._transcript(["## Transcript"], msgs, run, blind=False).replace("## Release diff", "## (n/a)")
    ws = run / "final" / "workspace"; files = []
    for p in sorted(ws.rglob("*.py")) if ws.is_dir() else []:
        files += [f"## Final `{p.relative_to(ws)}`", "```python", p.read_text(errors="replace")[:30000], "```"]
    return "\n".join(head) + "\n" + body + "\n" + "\n".join(files) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("batch", type=Path); ap.add_argument("--n", type=int, default=10); ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--blind", action="store_true"); ap.add_argument("--out", type=Path, default=REPO / "audit" / "holdout")
    a = ap.parse_args(argv); rng = random.Random(a.seed)
    cells: dict[str, list[Path]] = {}
    for f in sorted(a.batch.glob("*/*/*/*/run-*/final/score.json")):
        cells.setdefault(f.parent.parent.relative_to(a.batch).parts[0], []).append(f.parent.parent)
    out = a.out / a.batch.name / ("blind" if a.blind else ""); out.mkdir(parents=True, exist_ok=True); key = {}; picked = []
    for cell, runs in cells.items():
        picked += [(cell, r) for r in rng.sample(runs, min(a.n, len(runs)))]
    if a.blind:
        rng.shuffle(picked)
    for i, (cell, run) in enumerate(picked, 1):
        rid = f"R{i:02d}" if a.blind else f"{cell}_{run.name}"; key[rid] = str(run)
        (out / f"{rid}.md").write_text(render(run, a.blind, rid))
    if a.blind:
        (a.out / f"{a.batch.name}_blind_key.json").write_text(json.dumps(key, indent=1))
    print(f"wrote {len(picked)} files to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
