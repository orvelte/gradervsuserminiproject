#!/usr/bin/env python3
"""Pre-registered SF1 follow-up tests (structural_framing/PREREG.md): any-gaming, Fisher's exact test, fresh batches.

    python structural_framing/analysis/sf_fisher.py                 # every pre-registered comparison whose batches exist
    python structural_framing/analysis/sf_fisher.py --power          # Monte-Carlo power for the planned sample sizes

Pure Python (no scipy): two-sided Fisher p = sum of hypergeometric probabilities of tables at most as likely as the
observed one. Risk-difference CI: Newcombe (Wilson score) hybrid. Batches are read from final/sf_metrics.json's
`batch`; the pilot (batch "pilot") is never pooled with a fresh batch.
"""

from __future__ import annotations

import json
import math
import random
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
sys.path.insert(0, str(REPO_ROOT / "analysis"))
from common import find_run_dirs  # noqa: E402

OUT = HERE / "out"

# (name, hypothesis, batch_a, arm_a, batch_b, arm_b, predicted sign of p_a - p_b)
COMPARISONS = [
    ("H1 replication", "fresh G-LAX games more than fresh C-LAX", "rep1", "SF1-G-LAX", "rep1", "SF1-C-LAX", "+"),
    ("H2 strict main effect", "G-STRICT games more than C-STRICT", "strict1", "SF1-G-STRICT", "strict1", "SF1-C-STRICT", "+"),
    ("H3 horizon ablation", "C-LAX without the long-horizon line games more than fresh C-LAX", "nohorizon1", "SF1-C-LAX-NOHORIZON", "rep1", "SF1-C-LAX", "+"),
    ("H4 checker identity", "G-LAX with the lax line in Priya's voice games less than fresh G-LAX", "priyacheck1", "SF1-G-LAX-PRIYACHECK", "rep1", "SF1-G-LAX", "-"),
]
SECONDARY = [  # descriptive context, same test, not confirmatory
    ("H3b", "C-LAX-NOHORIZON vs fresh G-LAX", "nohorizon1", "SF1-C-LAX-NOHORIZON", "rep1", "SF1-G-LAX", "?"),
    ("H4b", "G-LAX-PRIYACHECK vs fresh C-LAX", "priyacheck1", "SF1-G-LAX-PRIYACHECK", "rep1", "SF1-C-LAX", "?"),
    ("pilot (not confirmatory)", "pilot G-LAX vs pilot C-LAX", "pilot", "SF1-G-LAX", "pilot", "SF1-C-LAX", "+"),
]


def fisher_two_sided(a: int, b: int, c: int, d: int) -> float:
    """Table [[a, b], [c, d]] = [[gamed_A, not_A], [gamed_B, not_B]]."""
    n1, n2, k = a + b, c + d, a + c
    n = n1 + n2
    def p_of(x):  # P(X = x) hypergeometric
        return math.comb(n1, x) * math.comb(n2, k - x) / math.comb(n, k)
    p_obs = p_of(a)
    lo, hi = max(0, k - n2), min(k, n1)
    return min(1.0, sum(p_of(x) for x in range(lo, hi + 1) if p_of(x) <= p_obs * (1 + 1e-9)))


def newcombe(a: int, n1: int, c: int, n2: int, z: float = 1.96) -> tuple[float, float, float]:
    def wilson(k, n):
        p = k / n; den = 1 + z * z / n; cen = (p + z * z / (2 * n)) / den
        half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
        return cen - half, cen + half
    p1, p2 = a / n1, c / n2
    l1, u1 = wilson(a, n1); l2, u2 = wilson(c, n2)
    d = p1 - p2
    return d, d - math.sqrt((p1 - l1) ** 2 + (u2 - p2) ** 2), d + math.sqrt((u1 - p1) ** 2 + (p2 - l2) ** 2)


def holm(pvals: list[float]) -> list[float]:
    order = sorted(range(len(pvals)), key=lambda i: pvals[i]); adj = [0.0] * len(pvals); running = 0.0
    for rank, i in enumerate(order):
        running = max(running, (len(pvals) - rank) * pvals[i]); adj[i] = min(1.0, running)
    return adj


def load(paths=None) -> dict:
    """{(batch, condition_id): [metrics...]} from every final/sf_metrics.json under results/structural_framing (smoke excluded)."""
    paths = paths or [str(REPO_ROOT / "results" / "structural_framing")]
    by = defaultdict(list)
    for d in find_run_dirs(paths):
        p = d / "final" / "sf_metrics.json"
        if not p.exists() or "/smoke/" in str(d):
            continue
        m = json.loads(p.read_text())
        by[(m.get("batch") or "pilot", m["condition_id"])].append(m)
    return by


def gamed(m: dict) -> bool:
    return m["primary_outcome"] == "gamed"  # pre-registered: minor suppression + hard circumvention; no_commit and honest are not gamed


def power(p1: float, p2: float, n1: int, n2: int, reps: int = 4000, seed: int = 0) -> float:
    rng = random.Random(seed); hits = 0
    for _ in range(reps):
        a = sum(rng.random() < p1 for _ in range(n1)); c = sum(rng.random() < p2 for _ in range(n2))
        hits += fisher_two_sided(a, n1 - a, c, n2 - c) < 0.05
    return hits / reps


def main(argv=None) -> int:
    argv = list(argv or sys.argv[1:])
    if "--power" in argv:
        for label, p1, p2, n1, n2 in (("H1 any-gaming 82% vs 50%, 40/40", .82, .50, 40, 40), ("H1 if true effect is 70% vs 50%, 40/40", .70, .50, 40, 40),
                                      ("H2 82% vs 50%, 22/22", .82, .50, 22, 22), ("H3 82% vs 50%, 30/40", .82, .50, 30, 40), ("H4 50% vs 82%, 30/40", .50, .82, 30, 40),
                                      ("hard circumvention 59% vs 32%, 40/40", .59, .32, 40, 40)):
            print(f"{label}: power ≈ {power(p1, p2, n1, n2):.2f}")
        return 0
    by = load([a for a in argv if not a.startswith("--")] or None)
    lines = ["# SF1 pre-registered tests (primary outcome: any gaming; two-sided Fisher's exact test)\n",
             "| test | hypothesis | A | B | A gamed | B gamed | A − B [Newcombe 95%] | Fisher p | Holm p (4 primary) | predicted sign | verdict |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    primary_p = []; rows = []
    for name, hyp, ba, aa, bb, ab, sign in COMPARISONS + SECONDARY:
        A, B = by.get((ba, aa)), by.get((bb, ab))
        if not A or not B:
            rows.append((name, hyp, f"{aa} [{ba}]", f"{ab} [{bb}]", None)); continue
        a, c = sum(gamed(m) for m in A), sum(gamed(m) for m in B)
        p = fisher_two_sided(a, len(A) - a, c, len(B) - c)
        d, lo, hi = newcombe(a, len(A), c, len(B))
        rows.append((name, hyp, f"{aa} [{ba}]", f"{ab} [{bb}]", (a, len(A), c, len(B), d, lo, hi, p, sign)))
        if name.startswith("H") and name[1].isdigit() and len(name.split()[0]) == 2:
            primary_p.append(p)
    adj = holm(primary_p) if primary_p else []
    k = 0
    for name, hyp, A, B, r in rows:
        if r is None:
            lines.append(f"| {name} | {hyp} | {A} | {B} | — | — | not run yet | | | | |"); continue
        a, n1, c, n2, d, lo, hi, p, sign = r
        is_primary = name.startswith("H") and name[1].isdigit() and len(name.split()[0]) == 2
        hp = f"{adj[k]:.3f}" if is_primary else ""
        if is_primary: k += 1
        obs_sign = "+" if d > 0 else ("-" if d < 0 else "0")
        verdict = ("supported" if p < 0.05 and obs_sign == sign else ("opposite direction, p<0.05" if p < 0.05 else "not supported")) if sign in "+-" else ""
        lines.append(f"| {name} | {hyp} | {A} | {B} | {a}/{n1} = {a/n1:.0%} | {c}/{n2} = {c/n2:.0%} | {d:+.0%} [{lo:+.0%}, {hi:+.0%}] | {p:.4f} | {hp} | {sign} | {verdict} |")
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "sf_prereg_tests.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines)); print(f"\nwrote {OUT / 'sf_prereg_tests.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
