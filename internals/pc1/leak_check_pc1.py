#!/usr/bin/env python3
"""PC1 word-level leak checker for CHARACTER prompts (PREREG PC1): PP1's checker (internals/personaprompt/leak_check.py,
unchanged) plus the pre-registered finance and generic words, with the same normalisation (inflections at word start,
look-alike characters, split spellings). Short words that are common as other words match only as whole words.

    from leak_check_pc1 import check
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "personaprompt"))
import leak_check as PP1  # noqa: E402

STEMS = ["money", "monet", "invest", "financ", "stock", "saving", "loan", "credit", "debt", "mortgag", "crypto", "bitcoin",
         "bank", "wealth", "profit", "market", "broker", "portfolio", "asset", "income", "salar", "budget", "cash", "dollar",
         "pric", "econom", "retir", "pension", "gambl", "lend", "borrow", "inherit", "payroll", "invoice", "currenc",
         # generic
         "domain", "topic", "question", "advice", "advis", "medic", "health", "doctor", "patient", "symptom", "treatment"]
WHOLE = ["fund", "funds", "share", "shares", "rich", "riches", "tax", "taxes", "bet", "bets", "betting", "trade", "trades",
         "trading", "trader", "traders", "coin", "coins"]


def check(text: str) -> list[str]:
    hits = set(PP1.check(text)); norm = PP1.normalise(text); words = re.findall(r"[a-z]+", norm); squashed = re.sub(r"[^a-z]", "", norm)
    for s in STEMS:
        if any(w.startswith(s) for w in words) or (len(s) >= 6 and s in squashed):
            hits.add(s)
    hits.update(w for w in WHOLE if w in words)
    return sorted(hits)
