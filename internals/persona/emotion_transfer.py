#!/usr/bin/env python3
"""Do the emotion directions (built from answer tokens) transfer to reasoning tokens? (decision #103)

    python internals/persona/emotion_transfer.py [--root results/persona_full] [--layer 32]

Directions are built from question half A (answer tokens, judged-expressive emotion rows minus default Assistant, with
the Assistant-Axis component removed) and tested on half B, on answer tokens and on reasoning tokens:
  vs default   AUC of emotion-e rows vs default-Assistant rows along direction e
  specificity  AUC of emotion-e rows vs the other 11 emotions' rows along direction e
Also builds reasoning-derived directions (same recipe on reasoning tokens, half A) and tests them on half B reasoning.
AUC 0.5 = no separation. Writes <root>/analysis/emotion_transfer.json.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import analyze as A  # noqa: E402


def auc(pos, neg):
    pos, neg = np.asarray(pos), np.asarray(neg)
    r = np.argsort(np.argsort(np.concatenate([pos, neg]))) + 1
    return float((r[: len(pos)].sum() - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg)))


def rows(root, layer, span):
    """{(kind, name, half): [vectors]} at `layer` for one span, emotion rows restricted to judged-expressive (3)."""
    gens = [json.loads(l) for l in (root / "gen" / "generations.jsonl").read_text().splitlines()]
    sc = {json.loads(l)["id"]: json.loads(l)["score"] for l in (root / "gen" / "scores.jsonl").read_text().splitlines()}
    need = sorted({0, layer}); li = need.index(layer); out = {}
    for g in gens:
        if not g["thinking"] or g["kind"] not in ("default", "emotion") or (g["kind"] == "emotion" and sc.get(g["id"]) != 3):
            continue
        a = A._load_layers(root / "gen" / "acts", g["id"], need)
        if a and span in a:
            out.setdefault((g["kind"], g["name"], g["half"]), []).append(a[span][li].astype(np.float64))
    return out


def directions(R, emos, axis, half):
    D = np.mean([v for (k, n, h), vs in R.items() if k == "default" and h == half for v in vs], 0)
    out = {}
    for e in emos:
        v = np.mean([x for (k, n, h), vs in R.items() if k == "emotion" and n == e and h == half for x in vs], 0) - D
        v = v - (v @ axis) * axis; out[e] = v / np.linalg.norm(v)
    return out


def evaluate(dirs, R, emos, half):
    res = {}
    dflt = [v for (k, n, h), vs in R.items() if k == "default" and h == half for v in vs]
    for e in emos:
        own = [v for (k, n, h), vs in R.items() if k == "emotion" and n == e and h == half for v in vs]
        oth = [v for (k, n, h), vs in R.items() if k == "emotion" and n != e and h == half for v in vs]
        d = dirs[e]
        res[e] = {"vs_default": auc([v @ d for v in own], [v @ d for v in dflt]), "specificity": auc([v @ d for v in own], [v @ d for v in oth]), "n": len(own)}
    return res


def main(argv) -> int:
    root = REPO / (argv[argv.index("--root") + 1] if "--root" in argv else "results/persona_full")
    layer = int(argv[argv.index("--layer") + 1]) if "--layer" in argv else 32
    axis = A.unit(A.persona_space(root, layer)["axis"][layer]).astype(np.float64)
    Ra, Rr = rows(root, layer, "resp"), rows(root, layer, "reason")
    emos = sorted({n for (k, n, h) in Ra if k == "emotion"})
    ans_dirs = directions(Ra, emos, axis, "A")
    out = {"answer_dirs_on_answers_B": evaluate(ans_dirs, Ra, emos, "B"),
           "answer_dirs_on_reasoning_B": evaluate(ans_dirs, Rr, emos, "B"),
           "reasoning_dirs_on_reasoning_B": evaluate(directions(Rr, emos, axis, "A"), Rr, emos, "B")}
    rd = A.unit(np.random.default_rng(0).standard_normal(axis.shape[0]))
    out["random_dir_vs_default_reasoning"] = evaluate({e: rd for e in emos}, Rr, emos, "B")
    (root / "analysis" / "emotion_transfer.json").write_text(json.dumps(out, indent=1))
    print(f"{'emotion':11} | answer dirs → answers (B) | answer dirs → reasoning (B) | reasoning dirs → reasoning (B)")
    print(f"{'':11} | vs default  specificity   | vs default  specificity     | vs default  specificity")
    for e in emos:
        a, b, c = (out[k][e] for k in ("answer_dirs_on_answers_B", "answer_dirs_on_reasoning_B", "reasoning_dirs_on_reasoning_B"))
        print(f"{e:11} |   {a['vs_default']:.2f}        {a['specificity']:.2f}       |   {b['vs_default']:.2f}        {b['specificity']:.2f}         |   {c['vs_default']:.2f}        {c['specificity']:.2f}")
    for k in ("answer_dirs_on_answers_B", "answer_dirs_on_reasoning_B", "reasoning_dirs_on_reasoning_B"):
        print(k, "mean vs_default %.2f, mean specificity %.2f" % (np.mean([v["vs_default"] for v in out[k].values()]), np.mean([v["specificity"] for v in out[k].values()])))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
