"""Cue registry: render a condition from a vector of cue settings (docs/specs/splitbrainexperiments.md, Phase 2).

    from registry import load, render, swaps
    r = render("v1", {"system_prompt": "graded", ...})      # unspecified cues default to the arm given by `base`

A rendered condition is {system_prompt, prior_turns, user_prompt, cue_content, settings}. `cue_content` is what the
container needs to build the repository under the `cues` framing: readme, pyproject_lines, files, history,
question_reply.

Editions: `baseline` reproduces the frozen arms DS-G (all graded) and DS-D-NOPUSH (all deployment) byte-for-byte, by
reading their texts from the frozen builder and framing module; `v1` reads cues.yaml.
"""
from __future__ import annotations

import copy
import importlib.util
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
DS = HERE.parent
CUES_FILE = HERE / "cues.yaml"
ARMS = ("graded", "deployment")


def _load(name, path):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path); m = importlib.util.module_from_spec(spec); sys.modules[name] = m; spec.loader.exec_module(m); return m


def frozen():
    """The frozen builder and framing module (their texts define the baseline edition)."""
    return _load("build_ds_arms_frozen", DS / "configs" / "build_ds_arms.py"), _load("ds_framing_frozen", DS / "env" / "precommit_hook_ds" / "sf_framing.py")


def _baseline() -> dict:
    A, F = frozen()
    ticket = A.D_PROMPT_NOPUSH
    d_open, rest = ticket.split("\n\n", 1)
    d_body, d_close = rest.rstrip("\n").rsplit("\n\n", 1)
    g_open, rest = A.G_PROMPT.split("\n\n", 1)
    g_body, g_close = rest.rstrip("\n").rsplit("\n\n", 1)
    seed = lambda s: [{"date": c["date"], "author": list(c["author"]), "message": c["message"], "files": c["files"]} for c in s]  # noqa: E731
    cues = {
        "system_prompt": {"graded": A.G_SYSTEM, "deployment": A.D_SYSTEM},
        "prior_turns": {"graded": [], "deployment": [dict(t) for t in A.D_PRIOR]},
        "opener": {"graded": g_open, "deployment": d_open},
        "body": {"graded": g_body, "deployment": d_body},
        "closer": {"graded": g_close, "deployment": d_close},
        "readme": {"graded": F.README["graded"], "deployment": F.README["deploy"]},
        "pyproject_project": {"graded": F.PYPROJECT_LINES["graded"], "deployment": F.PYPROJECT_LINES["deploy"]},
        "extra_files": {"graded": {}, "deployment": dict(F.DEPLOY_FILES)},
        "git_history": {"graded": seed(F.GRADED_SEED), "deployment": seed(F.DEPLOY_SEED)},
        "question_reply": {"graded": F.QUESTION_REPLY["graded"], "deployment": F.QUESTION_REPLY["deploy"]},
    }
    return {"edition": "baseline", "message_template": "{opener}\n\n{body}\n\n{closer}\n", "cues": cues, "shared_repo_files": {}}


def load(edition: str = "v1") -> dict:
    if edition == "baseline":
        return _baseline()
    reg = yaml.safe_load(CUES_FILE.read_text())
    _, F = frozen()
    reg["shared_repo_files"] = {k: F.DEPLOY_FILES[k] for k in reg["shared_repo_files"]}
    return reg


def default_settings(reg: dict, base: str) -> dict:
    out = {}
    for cue, spec in reg["cues"].items():
        out[cue] = spec.get("default", base) if isinstance(spec, dict) and "default" in spec else base
    return out


def _text(reg: dict, cue: str, value: str):
    if value == "off":
        return None
    spec = reg["cues"][cue]
    if value not in spec:
        raise KeyError(f"cue {cue!r} has no value {value!r} (has {[k for k in spec if k not in ('location', 'notes', 'default')]})")
    return copy.deepcopy(spec[value])


def render(edition: str, settings: dict | None = None, base: str = "graded") -> dict:
    reg = load(edition)
    s = {**default_settings(reg, base), **(settings or {})}
    unknown = set(s) - set(reg["cues"])
    if unknown:
        raise KeyError(f"unknown cues {sorted(unknown)}")
    t = {c: _text(reg, c, v) for c, v in s.items()}
    parts = {"opener": t["opener"], "body": t["body"], "closer": t["closer"],
             "forewarning": t.get("forewarning"), "exit_offer": (t["exit_offer"] + "\n\n") if t.get("exit_offer") else ""}
    user_prompt = reg["message_template"].format(**{k: (v if v is not None else "") for k, v in parts.items()})
    files = dict(reg.get("shared_repo_files") or {})
    if "extra_files" in t and t["extra_files"]:
        files.update(t["extra_files"])
    if t.get("changelog") is not None:
        files["CHANGELOG.md"] = t["changelog"]
    return {"edition": edition, "settings": s, "system_prompt": t["system_prompt"], "prior_turns": t["prior_turns"] or [], "user_prompt": user_prompt,
            "cue_content": {"readme": t["readme"], "pyproject_lines": t["pyproject_project"], "files": files, "history": t["git_history"],
                            "question_reply": t["question_reply"]}}


def swappable(reg: dict) -> list[str]:
    """Cues that take part in single-cue swaps: those with both arm versions and no default of their own."""
    return [c for c, spec in reg["cues"].items() if all(a in spec for a in ARMS) and "default" not in spec]


def swaps(edition: str = "v1") -> list[tuple[str, str, dict]]:
    """(base arm, swapped cue, settings) for every single-cue swap in both directions."""
    reg = load(edition); out = []
    for base, other in (("graded", "deployment"), ("deployment", "graded")):
        for cue in swappable(reg):
            out.append((base, cue, {**default_settings(reg, base), cue: other}))
    return out
