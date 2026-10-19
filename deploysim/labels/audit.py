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


def source_diff(run: Path) -> str:
    """Unified diff src_258 -> final src (committed src for ds-1.7, else rebuilt from the last fs snapshot)."""
    import difflib
    src = T.final_src(run) or {}
    pri = {p.name: p.read_text() for p in T.pristine(T.target_of(run)).iterdir() if p.is_file()}
    out = []
    for name in sorted(set(src) | set(pri)):
        a, b = pri.get(name, ""), src.get(name, "")
        if a != b:
            out += difflib.unified_diff(a.splitlines(), b.splitlines(), f"a/src/{name}" if name in pri else "/dev/null", f"b/src/{name}" if name in src else "/dev/null", lineterm="")
    return "\n".join(out)


def render_blind(run: Path, rid: str) -> str:
    """The transcript and final source only: no scorer verdict, labels, evidence, arm, batch or path."""
    body = render(run, None, None, blind=True)
    return f"# Rollout {rid}\n\n" + body


def render(run: Path, lab: dict | None, disc: dict | None, blind: bool = False) -> str:
    msgs = json.loads((run / "final" / "messages.json").read_text())
    if blind:
        L = ["## Transcript"]
        return _transcript(L, msgs, run, blind)
    L = [f"# {run.parent.parent.parent.parent.name} / {run.name}", "", f"`{run}`", "",
         f"**Scorer:** {lab['primary_outcome']} {lab['scorer_labels']}  ", f"**Taxonomy:** {lab['labels']}  ", f"**Attempted:** {lab['attempted']}  ",
         f"**Counts:** {lab['counts']}"]
    if disc is not None:
        L.append(f"**Disclosed:** {disc.get('disclosed')} — quote: {disc.get('quote')!r} (verified {disc.get('verified_quote')})")
    L += ["", "## Evidence", "```json", json.dumps(lab["evidence"], indent=1, default=str)[:4000], "```", "",
          "## Auditor checklist", "- [ ] labels correct  - [ ] missing label: ____  - [ ] wrong label: ____  - [ ] disclosed: yes / no", "", "## Transcript"]
    return _transcript(L, msgs, run, blind)


def _transcript(L: list, msgs: list, run: Path, blind: bool) -> str:
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
    if blind:
        L += ["## Final source vs the original repository (src/)", "```diff", source_diff(run)[:250000], "```"]
        if (run / "final" / "git_log.txt").exists():
            L += ["## Final git log", "```", (run / "final" / "git_log.txt").read_text()[:4000], "```"]
    elif rd.exists():
        L += ["## Release diff (seeded head -> HEAD)", "```diff", rd.read_text()[:20000], "```"]
    return "\n".join(L) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("batch", type=Path); ap.add_argument("--n", type=int, default=10); ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--judge", action="store_true"); ap.add_argument("--out", type=Path, default=T.REPO / "audit")
    ap.add_argument("--blind", nargs="?", const="", default=None, metavar="EXTRA_RUNS",
                    help="blind export for independent auditors: random sample plus the runs listed (one path per line) in EXTRA_RUNS")
    a = ap.parse_args(argv)
    if a.blind is not None:
        return blind(a)
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


def blind(a) -> int:
    """audit/blind/<batch>/R01.md ... plus key.json (rollout id -> run path), which the auditors must not read."""
    rng = random.Random(a.seed); runs = []
    for cell, rs in cells(a.batch).items():
        runs += rng.sample(rs, min(a.n, len(rs)))
    if a.blind:
        runs += [Path(l.strip()) for l in Path(a.blind).read_text().splitlines() if l.strip()]
    runs = sorted(set(runs), key=str); rng.shuffle(runs)
    d = a.out / "blind" / a.batch.name; d.mkdir(parents=True, exist_ok=True); key = {}
    for i, run in enumerate(runs, 1):
        rid = f"R{i:02d}"; key[rid] = str(run)
        (d / f"{rid}.md").write_text(render_blind(run, rid))
    (a.out / "blind" / f"{a.batch.name}_key.json").write_text(json.dumps(key, indent=1))
    print(f"wrote {len(runs)} blind files to {d}; key outside it")
    return 0


if __name__ == "__main__":
    sys.exit(main())
