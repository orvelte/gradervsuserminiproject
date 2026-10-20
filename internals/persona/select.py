#!/usr/bin/env python3
"""Reduced Assistant-Axis role and question sets for Qwen3.8-27B (assistantaxis.md Phase 1).

    python internals/persona/select.py      # writes internals/persona/roles.txt and questions.jsonl

Roles (70): the spec's named Assistant-end and far-end roles, the grader-adjacent roles (kept so A6 can compare a
"grader" persona with the axis), and a seeded random spread of the rest. `default` is always included (its 5 prompts,
including the empty one, are the default-Assistant set). Questions (40): seeded random subset of the paper's 240,
split into halves A and B for the split-half reliability gate.
Source: safety-research/assistant-axis (MIT) at the commit pinned in internals/persona/VENDOR, cloned to
internals/vendor/assistant-axis.
"""
import json
import random
from pathlib import Path

HERE = Path(__file__).resolve().parent
VENDOR = HERE.parent / "vendor" / "assistant-axis" / "data"
SEED = 20261020
N_ROLES, N_QUESTIONS = 70, 40

NAMED_ASSISTANT_END = ["generalist", "consultant", "analyst", "reviewer", "evaluator", "assistant"]
NAMED_FAR_END = ["bard", "ghost", "leviathan", "pirate", "eldritch", "hermit"]
GRADER_ADJACENT = ["grader", "examiner", "validator", "auditor", "screener"]


def main() -> None:
    roles_all = sorted(p.stem for p in (VENDOR / "roles" / "instructions").glob("*.json") if p.stem != "default")
    fixed = NAMED_ASSISTANT_END + NAMED_FAR_END + GRADER_ADJACENT
    missing = [r for r in fixed if r not in roles_all]
    assert not missing, missing
    rest = [r for r in roles_all if r not in fixed]
    rng = random.Random(SEED)
    roles = fixed + sorted(rng.sample(rest, N_ROLES - len(fixed)))
    (HERE / "roles.txt").write_text("\n".join(["default"] + roles) + "\n")

    qs = [json.loads(l) for l in (VENDOR / "extraction_questions.jsonl").read_text().splitlines() if l.strip()]
    pick = rng.sample(qs, N_QUESTIONS)
    with (HERE / "questions.jsonl").open("w") as f:
        for i, q in enumerate(pick):
            f.write(json.dumps({**q, "half": "A" if i % 2 == 0 else "B"}) + "\n")
    print(f"{len(roles)} roles + default; {len(pick)} questions (20 A / 20 B)")


if __name__ == "__main__":
    main()
