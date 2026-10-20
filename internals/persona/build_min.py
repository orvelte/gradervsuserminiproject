#!/usr/bin/env python3
"""Minimal persona/emotion extraction set (internals_plan "Minimal design", decisions #90-91).

    python internals/persona/build_min.py        # writes results/persona_min/prompts.jsonl

Rows: default Assistant (its 5 prompts, incl. no system prompt) + 20 roles + 12 emotions, x 5 system prompts x 10
questions (5 from half A, 5 from half B of questions.jsonl), thinking on; plus a thinking-off subset (default + 20
roles, prompts 0-1) for the axis-agreement check. Each row has the exact prompt token ids, rendered with Qwen3.8's
published template and tokenized locally, so generation on the pod starts from the same tokens that are replayed.
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

from tokenizers import Tokenizer

REPO = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO / "src"))
from agent_interp_envs.providers.qwen_template import render_prompt  # noqa: E402

VENDOR = REPO / "internals" / "vendor" / "assistant-axis" / "data" / "roles" / "instructions"
OUT = REPO / "results" / "persona_min"
TOK = Tokenizer.from_file(str(REPO / "internals" / "tokenizer" / "tokenizer.json"))
SEED = 20261020
SHORT_NAME = "Qwen"   # the paper's {model_name} substitution for Qwen models

ASSISTANT_END = ["generalist", "consultant", "analyst", "reviewer", "evaluator", "assistant"]
FAR_END = ["bard", "ghost", "leviathan", "pirate", "eldritch", "hermit"]
GRADER_ADJACENT = ["grader", "examiner", "validator", "auditor", "screener"]
N_MIDDLE = 3


def roles_min() -> list[str]:
    full = [r for r in (HERE / "roles.txt").read_text().split() if r != "default"]
    fixed = ASSISTANT_END + FAR_END + GRADER_ADJACENT
    middle = sorted(random.Random(SEED).sample([r for r in full if r not in fixed], N_MIDDLE))
    return fixed + middle


def questions_min() -> list[dict]:
    qs = [json.loads(l) for l in (HERE / "questions.jsonl").read_text().splitlines() if l.strip()]
    return [q for q in qs if q["half"] == "A"][:5] + [q for q in qs if q["half"] == "B"][:5]


def row(kind, name, pi, instruction, q, thinking):
    msgs = ([{"role": "system", "content": instruction}] if instruction else []) + [{"role": "user", "content": q["question"]}]
    text = render_prompt(msgs, None, enable_thinking=thinking)
    return {"id": f"{kind}:{name}:p{pi}:q{q['id']}:{'think' if thinking else 'nothink'}", "kind": kind, "name": name,
            "prompt_idx": pi, "question_id": q["id"], "half": q["half"], "question": q["question"], "system": instruction,
            "thinking": thinking, "prompt_ids": TOK.encode(text, add_special_tokens=False).ids}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    qs = questions_min(); roles = roles_min()
    emotions = {k: v for k, v in json.loads((HERE / "emotions.json").read_text()).items() if not k.startswith("_")}
    sets = [("default", "default", [i["pos"].replace("{model_name}", SHORT_NAME) for i in json.loads((VENDOR / "default.json").read_text())["instruction"]])]
    sets += [("role", r, [i["pos"].replace("{model_name}", SHORT_NAME) for i in json.loads((VENDOR / f"{r}.json").read_text())["instruction"]][:5]) for r in roles]
    sets += [("emotion", e, ps) for e, ps in emotions.items()]
    rows = [row(k, n, pi, ins, q, True) for k, n, ps in sets for pi, ins in enumerate(ps) for q in qs]
    rows += [row(k, n, pi, ins, q, False) for k, n, ps in sets if k != "emotion" for pi, ins in enumerate(ps[:2]) for q in qs]
    with (OUT / "prompts.jsonl").open("w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    (OUT / "roles_min.txt").write_text("\n".join(roles) + "\n")
    n_think = sum(r["thinking"] for r in rows)
    print(f"{len(rows)} prompts ({n_think} thinking, {len(rows) - n_think} non-thinking); {len(roles)} roles, {len(emotions)} emotions, {len(qs)} questions")
    print("middle roles:", roles[-N_MIDDLE:])


if __name__ == "__main__":
    main()
