#!/usr/bin/env python3
"""BX inputs (PREREG BX). Local, no GPU. Writes results/bx/inputs.json and copies the vectors to results/bx/.

    python internals/bx/build.py

The pod renders every prompt with each model's own chat template (tokenizer.apply_chat_template), so this ships
messages, tools and texts, not rendered prompts. Their open-ended eval data (question bank, judge rubric, trait
definitions) is vendored from github.com/johny-b/public-steering-vectors @ cb71586 (MIT) under internals/bx/vendor/.
"""
from __future__ import annotations

import ast
import json
import random
import shutil
import sys
from pathlib import Path

import numpy as np
import yaml

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "internals")); sys.path.insert(0, str(REPO / "internals" / "personaprompt")); sys.path.insert(0, str(REPO / "internals" / "personaprompt" / "heldout"))
sys.path.insert(0, str(REPO / "holdout")); sys.path.insert(0, str(REPO / "deploysim" / "analysis"))
from forced_choice import PROBE, OVERRIDE_LETTER, build_prefixes  # noqa: E402
import frame_traits as FT  # noqa: E402
import replay_check as R  # noqa: E402

V = HERE / "vendor"
OUT = REPO / "results" / "bx"
TRAITS5 = ("rule_breaking", "dishonesty", "competitiveness", "ambition", "approval_seeking")


def trait_descriptions() -> dict:
    tree = ast.parse((V / "traits.py").read_text())
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            tgt = node.targets[0] if isinstance(node, ast.Assign) else node.target
            if getattr(tgt, "id", None) == "TRAIT_DESCRIPTIONS":
                return ast.literal_eval(node.value)
    raise SystemExit("TRAIT_DESCRIPTIONS not found")


def cut3(msgs):
    n = 0
    for j, m in enumerate(msgs):
        if m.get("role") == "tool":
            n += 1
            if n == 3:
                return msgs[:j + 1]
    return None


def clean(m):
    keep = {"role", "content", "tool_calls", "tool_call_id", "reasoning_content"}
    return {k: v for k, v in m.items() if k in keep and v is not None}


def q36_prefixes():
    out = []
    for f in sorted((REPO / "results" / "holdout" / "q36" / "HO-D~visible").glob("**/final/messages.json")):
        run = f.parent.parent; msgs = cut3(json.loads(f.read_text()))
        if msgs is None:
            continue
        cfg = yaml.safe_load((run.parent / "config.yaml").read_text())
        out.append({"run": str(run.relative_to(REPO)), "messages": [clean(m) for m in msgs], "tools": R.T.get_tools(cfg)})
    return out


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    qs = [json.loads(l) for l in (V / "openended_questions.jsonl").read_text().splitlines()]
    desc = trait_descriptions(); assert set(desc) >= {q["trait"] for q in qs}
    pairs = []
    for side in ("positive", "negative"):
        pairs += [{"side": side[:3], "messages": json.loads(l)["messages"]} for l in (REPO / "internals/dd1/vendor/verifier_vs_human" / f"{side}.jsonl").read_text().splitlines()]
    q38 = [{"run": p["run"], "messages": p["messages"], "tools": p["tools"]} for p in build_prefixes() if p["cell"] == "HO-D~visible"]
    q36 = q36_prefixes()
    probes = [{"measure": "override", "order": o, "worse": OVERRIDE_LETTER[o], "text": PROBE[o]} for o in ("AB", "BA")]
    probes += [{"measure": m, "worse": w, "text": u} for m, u, w in FT.probes() if m in TRAITS5]
    inp = {"models": {"qwen3.6": {"hf": "Qwen/Qwen3.6-27B", "vector": "vector_qwen36.npy", "their_act_norm": 82.36234608235951, "prefixes": q36},
                      "qwen3.8": {"hf": "Qwen/Qwen3.8-27B", "vector": "vector_qwen38.npy", "their_act_norm": None, "prefixes": q38}},
           "layer": 36, "strengths": [-0.3, 0.0, 0.3], "questions": qs, "pairs": pairs, "probes": probes}
    (OUT / "inputs.json").write_text(json.dumps(inp))
    shutil.copy(V / "vector_0007.npy", OUT / "vector_qwen36.npy")
    g = np.load(REPO / "results" / "dd1" / "pod_out" / "dirs.npz")["grader"].astype(np.float32); np.save(OUT / "vector_qwen38.npy", g)
    (OUT / "judge.json").write_text(json.dumps({"rubric": (V / "judge_rubric.txt").read_text(), "descriptions": desc}))
    print(f"questions {len(qs)}; pairs {len(pairs)}; prefixes q36 {len(q36)}, q38 {len(q38)}; probes {len(probes)}; "
          f"‖v36‖ {np.linalg.norm(np.load(OUT / 'vector_qwen36.npy')):.3f} ‖v38‖ {np.linalg.norm(g):.3f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
