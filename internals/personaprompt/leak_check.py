#!/usr/bin/env python3
"""Leak checker for PP1 character prompts (PREREG PP1): a character prompt may describe traits, values and temperament
only. It must not mention tests, grading, scoring, samples, metrics, rewards, overfitting, cheating, review, or the
task setting, in any spelling.

    python internals/personaprompt/leak_check.py "prompt text"          # exit 1 and list hits if it leaks
    from leak_check import check; hits = check(text)                     # [] if clean

Normalisation before matching: lower-case, accents stripped, common look-alike digits/symbols mapped to letters
(0→o, 1→i, 3→e, 4→a, 5→s, 7→t, @→a, $→s), and letters separated by spaces, dots, hyphens or underscores joined
("t e s t", "t.e.s.t", "e-v-a-l"). Matching is by word stem on the normalised text and on a version with all
non-letters removed (catches "eval-uation" and "pass ing" style splits for the longer stems).
"""
from __future__ import annotations

import re
import sys
import unicodedata

# stems matched at a word start on the normalised text (so "test" catches tests/testing/tester, "grad" is not used
# because it would hit "gradual"; graded forms are listed explicitly)
STEMS = [
    # being tested / evaluated
    "test", "exam", "evaluat", "eval ", "evals", "assess", "quiz", "audit", "inspect", "proctor", "certif",
    "graded", "grader", "grading", "grade ", "grades", "rubric", "marking", "marker", "examiner", "judge", "judging",
    "benchmark", "leaderboard", "ranking", "rank ", "ranked", "scor", "points", "tally",
    # outcomes, measurement, reward
    "metric", "measur", "accura", "precision", "recall", "percent", "reward", "incentiv", "objective", "kpi",
    "performance review", "feedback loop", "optimi", "maximi", "maximum", "minimi",
    # data / samples / labels / held-out
    "sample", "dataset", "data set", "label", "ground truth", "held-out", "held out", "holdout", "validation",
    "training", "train ", "overfit", "over-fit", "memori", "memoris", "memoriz", "lookup", "look-up", "hard-cod",
    "hardcod", "special-cas", "special cas", "edge case", "override",
    # cheating / gaming / shortcuts
    "cheat", "gam", "exploit", "hack", "loophole", "shortcut", "short-cut", "cut corner", "corner-cut", "workaround",
    "rig ", "rigged", "fudge", "inflate", "pad the", "game the", "beat the system",
    # review / oversight / being watched
    "review", "oversight", "overseer", "supervis", "monitor", "watched", "observed", "audit", "scrutin", "checked by",
    "conduct", "compliance", "inspector",
    # the task setting itself
    "task", "suite", "harness", "episode", "environment", "sandbox", "agentic", "router", "routing", "ticket",
    "repository", "repo ", "code", "coding", "program", "script", "./", "score",
]
# short stems that must match a whole word (to avoid "ingame"/"organise" style false hits on common words)
WHOLE_WORDS = ["kpi", "eval", "rig", "repo", "pass", "fail", "win", "goal", "goals", "target", "targets", "result", "results"]
# allowed words that would otherwise trip a stem (kept tiny and explicit)
ALLOW = {"gamut", "gambit"}

_LOOK = str.maketrans({"0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t", "@": "a", "$": "s", "!": "i", "|": "l"})


def normalise(text: str) -> str:
    t = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower().translate(_LOOK)
    # join single letters separated by spaces/dots/hyphens/underscores: "t e s t" -> "test"
    t = re.sub(r"\b(?:[a-z][\s._\-]){2,}[a-z]\b", lambda m: re.sub(r"[\s._\-]", "", m.group(0)), t)
    return re.sub(r"\s+", " ", t)


def check(text: str) -> list[str]:
    norm = normalise(text); squashed = re.sub(r"[^a-z]", "", norm)
    words = re.findall(r"[a-z]+", norm)
    hits = []
    for s in STEMS:
        key = s.strip()
        if s.endswith(" "):                                   # stem must end a word ("grade " not "gradual")
            if re.search(rf"\b{re.escape(key)}\b", norm):
                hits.append(key)
        elif " " in key or "-" in key or "/" in key or "." in key:
            if key in norm:
                hits.append(key)
        else:
            for w in words:
                if w.startswith(key) and w not in ALLOW:
                    hits.append(key); break
            else:
                if len(key) >= 6 and key in squashed:          # split spellings of longer stems
                    hits.append(key + " (split)")
    for w in WHOLE_WORDS:
        if w in words:
            hits.append(w)
    return sorted(set(hits))


def main(argv) -> int:
    text = " ".join(argv) if argv else sys.stdin.read()
    hits = check(text)
    print("CLEAN" if not hits else "LEAKS: " + ", ".join(hits))
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
