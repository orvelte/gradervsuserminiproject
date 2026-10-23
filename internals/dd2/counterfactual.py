#!/usr/bin/env python3
"""DD2 teacher-forced counterfactual prefixes: take a real V1 trajectory and swap one cue factor, keeping every model
message identical.

    from counterfactual import swap_messages, residual_markers

swap_messages(msgs, src_cell, dst_cell) replaces the source cell's cue texts with the destination cell's in every
non-model message: the system prompt, the scripted prior turns (including their assistant turn), the task message, and tool results that show the README,
CHANGELOG, git history or the ask_question reply. Assistant messages (the model's own reasoning, text and tool calls)
are never edited. The cue texts come from holdout/configs/<cell>.yaml, the same files the runs were launched from.
Replacements are whole strings first, then line-level pieces of multi-line cues (for partial `cat`/`head` output),
then git-formatted history dates; longest first.

residual_markers(msgs, src_cell, dst_cell) lists source-only cue fragments still present after the swap, split into
non-assistant messages (must be empty) and assistant messages (expected: the model's own words are held fixed).
"""
from __future__ import annotations

import difflib
from datetime import datetime
from functools import lru_cache
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
CFG = REPO / "holdout" / "configs"


def _flat(d, p=""):
    out = {}
    if isinstance(d, dict):
        for k, v in d.items():
            out.update(_flat(v, f"{p}.{k}" if p else k))
    elif isinstance(d, list):
        for i, v in enumerate(d):
            out.update(_flat(v, f"{p}[{i}]"))
    else:
        out[p] = d
    return out


def _cues(cell: str) -> dict:
    c = yaml.safe_load((CFG / f"{cell}.yaml").read_text())
    return {k: v for k, v in _flat({"prompts": c["prompts"], "cue": c["task"].get("cue_content") or {}}).items() if isinstance(v, str)}


def _git_dates(iso: str) -> list[str]:
    t = datetime.fromisoformat(iso)
    return [t.strftime("%a %b %-d %H:%M:%S %Y %z"), t.strftime("%a %b %d %H:%M:%S %Y %z"), t.strftime("%Y-%m-%d %H:%M:%S %z"),
            t.strftime("%Y-%m-%d"), iso]


@lru_cache(maxsize=None)
def table(src: str, dst: str) -> tuple[tuple[str, str], ...]:
    a, b = _cues(src), _cues(dst); pairs = []
    for k in sorted(set(a) & set(b)):
        x, y = a[k], b[k]
        if x == y:
            continue
        if k.endswith(".date"):
            pairs += list(zip(_git_dates(x), _git_dates(y)))
            continue
        pairs.append((x, y)); pairs.append((x.strip(), y.strip()))
        xl, yl = x.splitlines(), y.splitlines()
        for op, i1, i2, j1, j2 in difflib.SequenceMatcher(a=xl, b=yl, autojunk=False).get_opcodes():
            if op == "replace" and i2 - i1 == j2 - j1:
                pairs += [(xl[i], yl[j]) for i, j in zip(range(i1, i2), range(j1, j2)) if xl[i].strip()]
            elif op == "replace":
                pairs.append(("\n".join(xl[i1:i2]), "\n".join(yl[j1:j2])))
    seen, out = set(), []
    for x, y in sorted(pairs, key=lambda p: -len(p[0])):
        if x and x != y and x not in seen:
            seen.add(x); out.append((x, y))
    return tuple(out)


def swap_text(s: str, src: str, dst: str) -> str:
    for x, y in table(src, dst):
        if x in s:
            s = s.replace(x, y)
    return s


N_CUE = 4  # system prompt, scripted prior user + assistant turns, task message: all cue text, never model output


def swap_messages(msgs: list[dict], src: str, dst: str) -> list[dict]:
    out = []
    for i, m in enumerate(msgs):
        if (m.get("role") == "assistant" and i >= N_CUE) or not isinstance(m.get("content"), str):
            out.append(dict(m))
        else:
            out.append({**m, "content": swap_text(m["content"], src, dst)})
    return out


@lru_cache(maxsize=None)
def markers(src: str, dst: str) -> tuple[str, ...]:
    """Source-only fragments: lines (≥ 12 chars) of source cues that occur in no destination cue."""
    a, b = _cues(src), _cues(dst); dst_text = "\n".join(b.values())
    ms = set()
    for k, v in a.items():
        if b.get(k) == v:
            continue
        for line in v.splitlines():
            line = line.strip()
            if len(line) >= 12 and line not in dst_text:
                ms.add(line)
    return tuple(sorted(ms))


def residual_markers(msgs: list[dict], src: str, dst: str) -> dict:
    ms = markers(src, dst); res = {"non_assistant": [], "assistant": []}
    for i, m in enumerate(msgs):
        c = m.get("content") if isinstance(m.get("content"), str) else ""
        for x in ms:
            if x in c:
                res["assistant" if m.get("role") == "assistant" and i >= N_CUE else "non_assistant"].append((i, x[:80]))
    return res
