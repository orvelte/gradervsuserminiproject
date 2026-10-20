"""Render a holdout condition from the cue registry (holdout/cues/cues.yaml).

    render(frame="graded"|"deployment"|"conduct", scoring="visible"|"holdout"|"none", settings=None)
      -> {system_prompt, prior_turns, user_prompt, cue_content{readme, files, history, question_reply}, settings}

Every cue defaults to the frame's version; `settings` overrides single cues (cue swaps, as in deploysim).
"""
from __future__ import annotations

import copy
from pathlib import Path

import yaml

CUES_FILE = Path(__file__).resolve().parent / "cues.yaml"
FRAMES = ("graded", "deployment", "conduct")
SCORING = ("visible", "holdout", "none")


def load() -> dict:
    return yaml.safe_load(CUES_FILE.read_text())


def render(frame: str, scoring: str = "visible", settings: dict | None = None) -> dict:
    if frame not in FRAMES or scoring not in SCORING:
        raise ValueError((frame, scoring))
    reg = load(); cues = reg["cues"]
    s = {c: frame for c in cues if c != "scoring"}; s.update(settings or {})
    t = {c: copy.deepcopy(cues[c][v]) for c, v in s.items()}
    sc = cues["scoring"][scoring]
    scoring_text = sc[s.get("scoring_frame", frame)] if sc else None
    user = reg["message_template"].format(opener=t["opener"], body=t["body"], scoring=(scoring_text + "\n\n") if scoring_text else "", closer=t["closer"])
    return {"edition": reg["edition"], "settings": {**s, "scoring": scoring}, "system_prompt": t["system_prompt"], "prior_turns": t["prior_turns"],
            "user_prompt": user, "cue_content": {"readme": t["readme"], "files": t["files"], "history": t["history"], "question_reply": t["question_reply"]}}
