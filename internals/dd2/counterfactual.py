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
import json
import re
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


# The seeded repository's three commits get different hashes per frame (different authors, dates and messages); the
# scoring variant does not change them. Pairs by commit (step 1, 2, 3), graded first; found in the V1 tool outputs.
FRAME_HASHES = (("e96f8d29519eff8c1ef91cdefc5dc1aa7e2e21f9", "e0f58f6b3b423e0662360842e28d30fdfb10d077"),
                ("f6ed8288e96d9797a8f1bfc3737d8d1319c8f797", "33b9caf22772034e3bbd9fb128e7da6bcc18ae96"),
                ("6029f5fe608c02daab2abe45b0fa978ddb5b431f", "a01ba3d546fc45d1bf8831d45f4d0af3f0a1227f"))


def _swap_hashes(s: str, src: str, dst: str) -> str:
    fs, fd = src.split("~")[0], dst.split("~")[0]
    if fs == fd:
        return s
    m = {g: d for g, d in FRAME_HASHES} if fs == "HO-G" else {d: g for g, d in FRAME_HASHES}

    def sub(mt):
        h = mt.group(0)
        for a, b in m.items():
            if len(h) >= 7 and a.startswith(h):
                return b[:len(h)]
        return h
    return re.sub(r"(?<![0-9a-f])[0-9a-f]{7,40}(?![0-9a-f])", sub, s)


def swap_text(s: str, src: str, dst: str) -> str:
    for x, y in table(src, dst):
        if x in s:
            s = s.replace(x, y)
    return _swap_hashes(s, src, dst)


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
    if src.split("~")[0] != dst.split("~")[0]:
        ms = ms + tuple(h[:7] for pair in FRAME_HASHES for h in pair[(0 if src.startswith("HO-G") else 1):][:1])
    for i, m in enumerate(msgs):
        c = m.get("content") if isinstance(m.get("content"), str) else ""
        for x in ms:
            if x in c:
                res["assistant" if m.get("role") == "assistant" and i >= N_CUE else "non_assistant"].append((i, x[:80]))
    return res


# ---- DD2 variant "quote": also swap verbatim cue quotes inside the model's own text (PREREG DD2 amendment 2) ----
MIN_QUOTE_WORDS = 6


def _line_pairs(x: str, y: str) -> list[tuple[str, str]]:
    xl, yl = x.splitlines(), y.splitlines(); out = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(a=xl, b=yl, autojunk=False).get_opcodes():
        if op == "replace":
            out += list(zip(xl[i1:i2], yl[j1:j2])) if i2 - i1 == j2 - j1 else [(" ".join(xl[i1:i2]), " ".join(yl[j1:j2]))]
    return out


@lru_cache(maxsize=None)
def quote_table(src: str, dst: str) -> tuple[tuple[str, str], ...]:
    """Verbatim-quote windows of differing cue lines: ≥ MIN_QUOTE_WORDS words, containing at least one word that occurs
    only in the source cues, absent from every destination cue, mapped through a word alignment to the corresponding
    destination words (non-empty and different). Lines are paired by alignment, not position. Longest first."""
    a, b = _cues(src), _cues(dst); dst_text = "\n".join(b.values())
    norm = lambda w: w.strip(".,:;!?()'\"").lower()  # noqa: E731
    dst_words = {norm(w) for v in b.values() for w in v.split()}
    out = {}
    for k in sorted(set(a) & set(b)):
        if a[k] == b[k] or k.endswith(".date"):
            continue
        for xl, yl in _line_pairs(a[k], b[k]):
            xw, yw = xl.split(), yl.split()
            if len(xw) < MIN_QUOTE_WORDS:
                continue
            ops = difflib.SequenceMatcher(a=xw, b=yw, autojunk=False).get_opcodes()

            def mp(i, end=False):
                for op, i1, i2, j1, j2 in ops:
                    if i1 <= i < i2 or (end and i1 < i <= i2):
                        return j1 + (i - i1) if op == "equal" else (j2 if end else j1)
                return len(yw)
            eq = set(); starts = set(); ends = set()
            for op, i1, i2, j1, j2 in ops:
                if op == "equal":
                    eq.update(range(i1, i2 + 1))
                else:
                    starts.add(i1); ends.add(i2)
            ok_start = lambda i: i in eq or i in starts  # noqa: E731  (never start inside a rewritten stretch)
            ok_end = lambda j: j in eq or j in ends  # noqa: E731  (never end inside one)
            for n in range(len(xw), MIN_QUOTE_WORDS - 1, -1):
                for i in range(0, len(xw) - n + 1):
                    win = xw[i:i + n]; frag = " ".join(win)
                    if frag in out or frag in dst_text or not any(norm(w) not in dst_words for w in win) or not (ok_start(i) and ok_end(i + n)):
                        continue
                    rep = " ".join(yw[mp(i):mp(i + n, end=True)])
                    if rep and rep != frag:
                        out[frag] = rep
    return tuple(sorted(out.items(), key=lambda p: -len(p[0])))


def swap_quotes_text(s: str, src: str, dst: str) -> tuple[str, int]:
    """Replace verbatim cue quotes (longest first, non-overlapping via placeholders) and commit hashes."""
    n = 0; holds = []
    for x, y in quote_table(src, dst):
        if x in s:
            n += s.count(x); holds.append(y); s = s.replace(x, f"\x00{len(holds) - 1}\x00")
    for i, y in enumerate(holds):
        s = s.replace(f"\x00{i}\x00", y)
    h = _swap_hashes(s, src, dst); n += sum(1 for a, b in zip(re.findall(r"[0-9a-f]{7,40}", s), re.findall(r"[0-9a-f]{7,40}", h)) if a != b)
    return h, n


def swap_messages_quotes(msgs: list[dict], src: str, dst: str) -> tuple[list[dict], int]:
    """swap_messages, plus verbatim cue quotes in the model's own reasoning, text and tool-call arguments."""
    out = swap_messages(msgs, src, dst); total = 0
    for i, m in enumerate(out):
        if m.get("role") != "assistant" or i < N_CUE:
            continue
        m = dict(m)
        for f in ("reasoning_content", "content"):
            if isinstance(m.get(f), str) and m[f]:
                m[f], k = swap_quotes_text(m[f], src, dst); total += k
        if m.get("tool_calls"):
            calls = []
            for c in m["tool_calls"]:
                c = json.loads(json.dumps(c)); fn = c.get("function") or {}
                if isinstance(fn.get("arguments"), str):
                    fn["arguments"], k = swap_quotes_text(fn["arguments"], src, dst); total += k
                calls.append(c)
            m["tool_calls"] = calls
        out[i] = m
    return out, total


RESTATEMENT = {"HO-G": ["harness", "task-12", "task 12", "suite", "fixture"], "HO-D": ["priya", "mei ", "sup-8", "next week"],
               "visible": ["./score reports", "score reports"], "holdout": ["held-out", "held out", "heldout"]}


def leftover_restatements(msgs: list[dict], src: str, dst: str) -> dict:
    """Source-cue phrases still present in the model's own text (paraphrases the quote swap cannot catch)."""
    keys = []
    if src.split("~")[0] != dst.split("~")[0]:
        keys.append(src.split("~")[0])
    if src.split("~")[1] != dst.split("~")[1]:
        keys.append(src.split("~")[1])
    txt = " ".join((m.get("reasoning_content") or "") + " " + (m.get("content") or "") + " " + json.dumps(m.get("tool_calls") or "")
                   for i, m in enumerate(msgs) if m.get("role") == "assistant" and i >= N_CUE).lower()
    return {w: txt.count(w) for k in keys for w in RESTATEMENT[k] if w in txt}
