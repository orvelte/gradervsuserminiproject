#!/usr/bin/env python3
"""S13 distribution check: fresh turn-1 continuations on Fireworks vs the source arm's original runs (AkashML).

    python resampling/analysis/rs_calibration.py
Compares thought rate (detector anywhere), any-gaming, hard circumvention, steps, apply_patch share, and the first
sentence style. Writes resampling/analysis/out/calibration.md."""
from __future__ import annotations

import glob, json, statistics, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(REPO_ROOT / "analysis"))
import detector as D  # noqa: E402


def describe(run_dir: Path) -> dict | None:
    final = run_dir / "final"
    if not (final / "score.json").exists():
        return None
    sc = json.loads((final / "score.json").read_text()); msgs = json.loads((final / "messages.json").read_text())
    calls = [tc["function"]["name"] for m in msgs if m.get("role") == "assistant" for tc in m.get("tool_calls") or []]
    reasoning_lens = [len(m.get("reasoning") or m.get("reasoning_content") or "") for m in msgs if m.get("role") == "assistant"]
    return {"gamed": sc["primary_outcome"] == "gamed", "no_commit": sc["primary_outcome"] == "no_commit", "hard": bool(sc.get("workaround_labels")),
            "thought": D.first_hit(msgs) is not None, "steps": sc["n_steps"], "apply_patch_share": (calls.count("apply_patch") / len(calls)) if calls else 0.0,
            "mean_reasoning_chars": statistics.mean(reasoning_lens) if reasoning_lens else 0, "hit_cap": bool(sc.get("hit_max_steps"))}


def summarise(rows: list[dict]) -> dict:
    n = len(rows)
    return {"n": n, "thought": sum(r["thought"] for r in rows) / n, "gamed": sum(r["gamed"] for r in rows) / n, "hard": sum(r["hard"] for r in rows) / n,
            "no_commit": sum(r["no_commit"] for r in rows), "median_steps": statistics.median(r["steps"] for r in rows), "mean_apply_patch_share": statistics.mean(r["apply_patch_share"] for r in rows),
            "mean_reasoning_chars": statistics.mean(r["mean_reasoning_chars"] for r in rows), "hit_cap": sum(r["hit_cap"] for r in rows)}


def main():
    out = ["# S13 calibration: fresh turn-1 continuations (Fireworks) vs original runs (AkashML)\n",
           "| set | n | thought rate | any gaming | hard | no_commit | median steps | apply_patch share | mean reasoning chars/turn | hit cap |", "|---|---|---|---|---|---|---|---|---|---|"]
    def row(label, s):
        return f"| {label} | {s['n']} | {s['thought']:.0%} | {s['gamed']:.0%} | {s['hard']:.0%} | {s['no_commit']} | {s['median_steps']:.0f} | {s['mean_apply_patch_share']:.2f} | {s['mean_reasoning_chars']:.0f} | {s['hit_cap']} |"
    for arm in ("N0", "U0"):
        orig = [d for d in (describe(Path(p)) for p in glob.glob(f"results/openai-gpt-oss-120b/{arm}/*/*/*/run-*")) if d]
        cal = [d for d in (describe(Path(p)) for p in glob.glob(f"results/resampling/calibration/{arm}_*_t1_CAL_*")) if d]
        out.append(row(f"{arm} original (30 runs, AkashML)", summarise(orig)))
        if cal:
            out.append(row(f"{arm} calibration (Fireworks, turn-1 fresh)", summarise(cal)))
    all_cal = [d for d in (describe(Path(p)) for p in glob.glob("results/resampling/calibration/*_t1_CAL_*")) if d]
    all_orig = [d for d in (describe(Path(p)) for p in glob.glob("results/openai-gpt-oss-120b/N0/*/*/*/run-*") + glob.glob("results/openai-gpt-oss-120b/U0/*/*/*/run-*")) if d]
    if all_cal:
        out.append(row("pooled original (60)", summarise(all_orig))); out.append(row("pooled calibration", summarise(all_cal)))
    (HERE / "out").mkdir(exist_ok=True); (HERE / "out" / "calibration.md").write_text("\n".join(out) + "\n"); print("\n".join(out))


if __name__ == "__main__":
    main()
