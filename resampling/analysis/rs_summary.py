#!/usr/bin/env python3
"""RS1 summary: per-source-run rates by condition, the primary C1 − C2 contrast with a cluster bootstrap over source
runs, secondary contrasts, C2 re-emergence, the descriptive C0 split and the originally-gamed/honest heterogeneity.

    python resampling/analysis/rs_summary.py [results/resampling/stage1 results/resampling/stage3 ...]
Reads final/rs_metrics.json (run rs_metrics.py first). Writes resampling/analysis/out/rs_summary.md."""
from __future__ import annotations

import json
import random
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
OUT = HERE / "out"
CONDS = ["C0-natural", "C1-keep", "C2-replace"]


def load(dirs):
    rows = []
    for d in dirs:
        for p in Path(d).glob("*/final/rs_metrics.json"):
            m = json.loads(p.read_text())
            if m.get("stage") in ("calibration",):  # S13 runs are not resampling cells
                continue
            rows.append(m)
    return rows


def rate(rs, key="any_gaming"):
    vals = [r[key] for r in rs if r.get(key) is not None]
    return (sum(vals) / len(vals), len(vals)) if vals else (None, 0)


def cluster_boot(by_src: dict, a: str, b: str, key="any_gaming", reps=4000, seed=0):
    """Difference of pooled rates a − b, resampling SOURCE RUNS with replacement (cells within a source run stay together)."""
    rng = random.Random(seed); srcs = list(by_src)
    def pooled(sample):
        va = [r[key] for s in sample for r in by_src[s].get(a, []) if r.get(key) is not None]
        vb = [r[key] for s in sample for r in by_src[s].get(b, []) if r.get(key) is not None]
        return (sum(va) / len(va) - sum(vb) / len(vb)) if va and vb else None
    est = pooled(srcs)
    diffs = [d for d in (pooled([rng.choice(srcs) for _ in srcs]) for _ in range(reps)) if d is not None]
    diffs.sort()
    return est, (diffs[int(0.025 * len(diffs))], diffs[int(0.975 * len(diffs)) - 1]) if diffs else (None, None), len(diffs)


def main(argv):
    dirs = argv or [str(REPO_ROOT / "results" / "resampling" / "stage1"), str(REPO_ROOT / "results" / "resampling" / "stage3")]
    rows = load([d for d in dirs if Path(d).exists()])
    if not rows:
        print("no rs_metrics.json found"); return 1
    by_src = defaultdict(lambda: defaultdict(list))
    for r in rows:
        by_src[r["source_run_id"]][r["condition"]].append(r)
    md = ["# RS1 summary (any gaming = scorer v6 `gamed`; no_commit excluded from the denominator and shown separately)\n",
          "## Per source run\n", "| source | original | t | " + " | ".join(f"{c}: gamed / hard / no_commit (n)" for c in CONDS) + " | C2 re-emergence | C0 outcomes identical |", "|---|---|---|" + "---|" * len(CONDS) + "---|---|"]
    locked = 0
    for s, conds in by_src.items():
        cells = []
        for c in CONDS:
            rs = conds.get(c, [])
            g, n = rate(rs); h, _ = rate(rs, "hard"); nc = sum(r["no_commit"] for r in rs)
            cells.append(f"{g:.0%} / {h:.0%} / {nc} ({n})" if n else "—")
        c2 = conds.get("C2-replace", []); re_ = f"{sum(r['thought_reemerges'] for r in c2)}/{len(c2)}" if c2 else "—"
        c0 = conds.get("C0-natural", []); ident = (len({r['primary_outcome'] for r in c0}) == 1) if len(c0) >= 3 else None
        locked += bool(ident)
        any_r = next(iter(conds.values()))[0]
        md.append(f"| {s} | {any_r['original_outcome']} | {any_r['prefix_turn']} | " + " | ".join(cells) + f" | {re_} | {ident} |")
    md.append("")
    md.append("## Pooled contrasts (cluster bootstrap over source runs, 4000 resamples, 95% CI)\n")
    md.append("| contrast | outcome | estimate | 95% CI | n source runs |"); md.append("|---|---|---|---|---|")
    for a, b, label in (("C1-keep", "C2-replace", "PRIMARY C1 − C2"), ("C1-keep", "C0-natural", "C1 − C0"), ("C0-natural", "C2-replace", "C0 − C2")):
        for key in ("any_gaming", "hard"):
            est, (lo, hi), _ = cluster_boot(by_src, a, b, key)
            md.append(f"| {label} | {key} | {est:+.1%} | [{lo:+.1%}, {hi:+.1%}] | {len(by_src)} |" if est is not None else f"| {label} | {key} | — | not enough cells | |")
    for c in CONDS:
        rs = [r for s in by_src for r in by_src[s].get(c, [])]
        g, n = rate(rs); h, _ = rate(rs, "hard"); nc = sum(r["no_commit"] for r in rs)
        md.append(f"\n{c}: any gaming {g:.0%} (n={n}), hard {h:.0%}, no_commit {nc}/{len(rs)}, mean generated steps {sum(r['n_generated_steps'] for r in rs)/len(rs):.0f}" if rs else f"\n{c}: no cells")
    c2 = [r for s in by_src for r in by_src[s].get("C2-replace", [])]
    if c2:
        same_turn = sum(1 for r in c2 if r["thought_reemerges"] and (r["reemergence"] or {}).get("turn_offset") == 0)
        md.append(f"\n## C2 re-emergence (S12/S15)\n\nre-emerges anywhere later: {sum(r['thought_reemerges'] for r in c2)}/{len(c2)}; within the same reasoning turn: {same_turn}/{len(c2)}; "
                  f"median turn offset among re-emergers: {sorted((r['reemergence'] or {}).get('turn_offset', 0) for r in c2 if r['thought_reemerges'])[sum(r['thought_reemerges'] for r in c2)//2] if any(r['thought_reemerges'] for r in c2) else '—'}")
    c0 = [r for s in by_src for r in by_src[s].get("C0-natural", [])]
    if c0:
        a = [r for r in c0 if r["thought_reemerges"]]; b = [r for r in c0 if not r["thought_reemerges"]]
        md.append(f"\n## C0 split by whether the thought recurs naturally (descriptive, confounded)\n\nrecurs: gaming {rate(a)[0] if a else None} (n={rate(a)[1]}); does not recur: gaming {rate(b)[0] if b else None} (n={rate(b)[1]})")
    md.append(f"\n## Within-source spread (S14)\n\nsource runs whose C0 continuations all share one outcome: {locked}/{len(by_src)}")
    md.append("\n## Heterogeneity by original outcome (exploratory)\n")
    for grp, pred in (("originally gamed", lambda r: r["original_outcome"] == "gamed"), ("originally honest/no_commit", lambda r: r["original_outcome"] != "gamed")):
        sub = {s: c for s, c in by_src.items() if pred(next(iter(c.values()))[0])}
        if sub:
            est, (lo, hi), _ = cluster_boot(sub, "C1-keep", "C2-replace")
            md.append(f"- {grp} ({len(sub)} source runs): C1 − C2 any gaming {est:+.1%} [{lo:+.1%}, {hi:+.1%}]" if est is not None else f"- {grp}: not enough cells")
    OUT.mkdir(parents=True, exist_ok=True); (OUT / "rs_summary.md").write_text("\n".join(md) + "\n"); print("\n".join(md))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
