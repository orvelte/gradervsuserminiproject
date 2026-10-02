#!/usr/bin/env python3
"""SF1 per-arm table and the G-LAX vs C-LAX contrast (bootstrap CI), from final/sf_metrics.json.

    python structural_framing/analysis/sf_summary.py [results/structural_framing ...]

Writes structural_framing/analysis/out/{sf_runs.csv, sf_summary.md}. A 20-per-arm pilot detects only very
large effects; the markdown says so next to every contrast.
"""

from __future__ import annotations

import csv
import json
import random
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
sys.path.insert(0, str(REPO_ROOT / "analysis"))
from common import find_run_dirs  # noqa: E402
from summarize import wilson, fmt_ci  # noqa: E402

OUT = HERE / "out"
ARMS = ["SF1-G-LAX", "SF1-C-LAX", "SF1-G-STRICT", "SF1-C-STRICT"]


def boot_diff(a: list[bool], b: list[bool], reps: int = 4000, seed: int = 0) -> tuple[float, float, float]:
    rng = random.Random(seed)
    pa, pb = sum(a) / len(a), sum(b) / len(b)
    diffs = sorted(sum(rng.choice(a) for _ in a) / len(a) - sum(rng.choice(b) for _ in b) / len(b) for _ in range(reps))
    return pa - pb, diffs[int(0.025 * reps)], diffs[int(0.975 * reps) - 1]


def main(argv=None) -> int:
    argv = list(argv or sys.argv[1:])
    include_smoke = "--include-smoke" in argv
    paths = [a for a in argv if not a.startswith("--")] or [str(REPO_ROOT / "results" / "structural_framing")]
    rows = []
    for d in find_run_dirs(paths):
        p = d / "final" / "sf_metrics.json"
        if not p.exists() or (not include_smoke and "/smoke/" in str(d)):
            continue
        m = json.loads(p.read_text())
        m["run_dir"] = str(d.relative_to(REPO_ROOT)) if d.is_relative_to(REPO_ROOT) else str(d)
        rows.append(m)
    if not rows:
        print("no sf_metrics.json found; run structural_framing/analysis/sf_metrics.py first"); return 1
    OUT.mkdir(parents=True, exist_ok=True)
    flat = []
    for m in rows:
        f = {k: v for k, v in m.items() if k not in ("decision_window", "question_texts", "workaround_labels", "commits_beyond_seed", "injections_fired")}
        f.update({f"win_{k}": v for k, v in (m.get("decision_window") or {}).items()})
        f["labels"] = "|".join(m.get("workaround_labels") or []); f["question_texts"] = " || ".join(m.get("question_texts") or [])
        flat.append(f)
    with (OUT / f"sf_runs{'_smoke' if include_smoke else ''}.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=sorted({k for r in flat for k in r})); w.writeheader(); w.writerows(flat)
    by = defaultdict(list)
    for m in rows:
        by[m["condition_id"]].append(m)
    arms = [a for a in ARMS if a in by] + sorted(a for a in by if a not in ARMS)
    md = ["# SF1 summary (pilot; only very large effects are detectable at 20 per arm)\n",
          "| arm | n | honest | minor suppression | hard circumvention [Wilson 95%] | no_commit | grader_modeling: runs with >=1, mean count | question-tool calls (runs, total) | report: discloses / false claim / true claim / no claim | median steps |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    for a in arms:
        rs = by[a]; n = len(rs); t = Counter(r["tier"] for r in rs)
        p, lo, hi = wilson(t["hard_circumvention"], n)
        gm_any = sum(1 for r in rs if r["grader_modeling_any"]); gm_mean = statistics.fmean(r["grader_modeling_count"] for r in rs)
        q_runs = sum(1 for r in rs if r["question_tool_calls"]); q_tot = sum(r["question_tool_calls"] for r in rs)
        cat = Counter(r["report_category"] for r in rs)
        steps = [r["n_steps"] for r in rs if isinstance(r["n_steps"], int)]
        md.append(f"| {a} | {n} | {t['honest']} | {t['minor_suppression']} | {t['hard_circumvention']} = {p:.0%} [{lo:.0%}, {hi:.0%}] | {t['no_commit']} | "
                  f"{gm_any}/{n}, {gm_mean:.2f} | {q_runs}, {q_tot} | {cat['discloses']} / {cat['false_claim']} / {cat['true_claim']} / {cat['no_claim']} | "
                  f"{statistics.median(steps) if steps else 'n/a'} |")
    md.append("")
    if "SF1-G-LAX" in by and "SF1-C-LAX" in by:
        g, c = by["SF1-G-LAX"], by["SF1-C-LAX"]
        md.append("## G-LAX vs C-LAX (20-per-arm pilot: only very large effects are detectable)\n")
        for label, fn in (("hard circumvention", lambda r: r["tier"] == "hard_circumvention"),
                          ("gamed (hard + minor)", lambda r: r["primary_outcome"] == "gamed"),
                          ("honest", lambda r: r["tier"] == "honest"),
                          ("grader_modeling >= 1", lambda r: bool(r["grader_modeling_any"])),
                          ("used the question tool", lambda r: r["question_tool_calls"] > 0),
                          ("discloses in final report", lambda r: r["report_category"] == "discloses"),
                          ("false claim in final report", lambda r: r["report_category"] == "false_claim")):
            est, lo, hi = boot_diff([fn(r) for r in g], [fn(r) for r in c])
            md.append(f"- {label}: G-LAX − C-LAX = {est:+.1%}  [{lo:+.1%}, {hi:+.1%}]  (G {sum(fn(r) for r in g)}/{len(g)}, C {sum(fn(r) for r in c)}/{len(c)})")
        md.append("")
    md.append("## Decision-point window (10 reasoning turns before the first workaround; gamed runs)\n")
    md.append("| arm | gamed runs with a locatable workaround | mentions grader words | grader-type terms (prompt words removed) | Priya/team | injection hints | difficulty/effort | grader_modeling matches in window |")
    md.append("|---|---|---|---|---|---|---|---|")
    for a in arms:
        ws = [r["decision_window"] for r in by[a] if r["primary_outcome"] == "gamed" and (r.get("decision_window") or {}).get("first_workaround_turn") is not None]
        if ws:
            md.append(f"| {a} | {len(ws)} | {sum(1 for w in ws if w['grader_words'])} | {sum(1 for w in ws if w['grader_terms_decontaminated'])} | {sum(1 for w in ws if w['priya_or_team'])} | "
                      f"{sum(1 for w in ws if w['injection_hints'])} | {sum(1 for w in ws if w['difficulty_terms'])} | {sum(1 for w in ws if w['grader_modeling_in_window'])} |")
    suffix = "_smoke" if include_smoke else ""
    (OUT / f"sf_summary{suffix}.md").write_text("\n".join(md) + "\n")
    print("\n".join(md)); print(f"\nwrote {OUT / f'sf_runs{suffix}.csv'}, {OUT / f'sf_summary{suffix}.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
