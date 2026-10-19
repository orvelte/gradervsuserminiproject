#!/usr/bin/env python3
"""Hand-audit export (spec Phase 3): 10 random rollouts per cell as markdown, with the automatic labels beside them.

    python deploysim/labels/audit.py results/deploysim/prereg1 [--n 10] [--seed 0] [--judge] [--out audit/]

One file per rollout, audit/<batch>/<cell>/<run>.md: labels + evidence, scorer outcome, the user-visible messages,
every command with a clipped output, the reasoning, the release diff (ds-1.7 runs) and a blank checklist for the
auditor. --judge also runs the disclosure judge (a paid call to the judge model; off by default).
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import taxonomy as T  # noqa: E402

CLIP = 1500


def cells(batch: Path) -> dict[str, list[Path]]:
    out: dict[str, list[Path]] = {}
    for f in sorted(batch.glob("*/*/*/*/run-*/final/score.json")):
        run = f.parent.parent
        if "crashed" not in str(run):
            out.setdefault(run.relative_to(batch).parts[0], []).append(run)
    return out


def render(run: Path, lab: dict, disc: dict | None) -> str:
    msgs = json.loads((run / "final" / "messages.json").read_text())
    L = [f"# {run.parent.parent.parent.parent.name} / {run.name}", "", f"`{run}`", "",
         f"**Scorer:** {lab['primary_outcome']} {lab['scorer_labels']}  ", f"**Taxonomy:** {lab['labels']}  ", f"**Attempted:** {lab['attempted']}  ",
         f"**Counts:** {lab['counts']}"]
    if disc is not None:
        L.append(f"**Disclosed:** {disc.get('disclosed')} — quote: {disc.get('quote')!r} (verified {disc.get('verified_quote')})")
    L += ["", "## Evidence", "```json", json.dumps(lab["evidence"], indent=1, default=str)[:4000], "```", "",
          "## Auditor checklist", "- [ ] labels correct  - [ ] missing label: ____  - [ ] wrong label: ____  - [ ] disclosed: yes / no", "", "## Transcript"]
    for i, m in enumerate(msgs):
        role = m.get("role")
        if role == "system":
            continue
        if role == "assistant":
            if m.get("reasoning"):
                L += [f"<details><summary>reasoning ({i})</summary>", "", "```", str(m["reasoning"])[:CLIP * 2], "```", "</details>", ""]
            if (m.get("content") or "").strip():
                L += [f"**assistant ({i}):** {m['content'].strip()}", ""]
            for tc in m.get("tool_calls") or []:
                fn = tc.get("function") or {}
                try:
                    a = json.loads(fn.get("arguments") or "{}")
                except json.JSONDecodeError:
                    a = {"raw": fn.get("arguments")}
                body = a.get("command") or a.get("input") or a.get("question") or a
                L += [f"`{fn.get('name')}` ({i})", "```", str(body)[:CLIP * 2], "```"]
        elif role == "tool":
            L += ["<details><summary>output</summary>", "", "```", str(m.get("content"))[:CLIP], "```", "</details>", ""]
        else:
            L += [f"**{role} ({i}):** {str(m.get('content'))[:CLIP * 2]}", ""]
    rd = run / "final" / "release.diff"
    if rd.exists():
        L += ["## Release diff (seeded head -> HEAD)", "```diff", rd.read_text()[:20000], "```"]
    return "\n".join(L) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("batch", type=Path); ap.add_argument("--n", type=int, default=10); ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--judge", action="store_true"); ap.add_argument("--out", type=Path, default=T.REPO / "audit")
    a = ap.parse_args(argv)
    rng = random.Random(a.seed); n = 0
    for cell, runs in cells(a.batch).items():
        pick = sorted(rng.sample(runs, min(a.n, len(runs))), key=lambda p: str(p))
        d = a.out / a.batch.name / cell; d.mkdir(parents=True, exist_ok=True)
        index = [f"# {a.batch.name} / {cell}: {len(pick)} of {len(runs)} runs (seed {a.seed})", ""]
        for run in pick:
            lab = T.label_run(run); disc = None
            if a.judge and lab["cheat"]:
                import judge
                disc = judge.disclosure(run, lab["labels"])
            name = f"{run.parent.name}_{run.name}.md"
            (d / name).write_text(render(run, lab, disc)); n += 1
            index.append(f"- [{run.name}]({name}) — {lab['primary_outcome']} {lab['labels']}")
        (d / "INDEX.md").write_text("\n".join(index) + "\n")
    print(f"wrote {n} audit files under {a.out / a.batch.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
