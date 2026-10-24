#!/usr/bin/env python3
"""PC1 semantic judge for CHARACTER prompts (PREREG PC1): openai/gpt-4.1 sees only the prompt text and answers
(1) does it state or imply a rule that depends on the topic or kind of request, (2) does it mention or allude to a
subject area such as money, finance or health. Any "yes" flags. Runs on every scored character candidate and marks the
finalists. Writes results/pc1/stage1/semantic.json.

    python internals/pc1/semantic_pc1.py
"""
import asyncio
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

REPO = Path(__file__).resolve().parents[2]; OUT = REPO / "results" / "pc1" / "stage1"; JUDGE = "openai/gpt-4.1"
Q = ("Q1: Does the text state or imply a rule or tendency that depends on the topic, subject area or kind of request "
     "(behaving differently for some kinds of questions than others)?\nQ2: Does the text mention or allude to any subject "
     "area such as money, finance, investing, possessions, business, health or medicine, even indirectly or metaphorically?")


async def main():
    load_dotenv(REPO / ".env", override=True); from openai import AsyncOpenAI
    c = AsyncOpenAI(base_url="https://openrouter.ai/api/v1", api_key=os.environ["OPENROUTER_API_KEY"]); sem = asyncio.Semaphore(16)
    rows = [json.loads(l) for l in (OUT / "candidates.jsonl").read_text().splitlines()]
    chars = {r["text"]: r for r in rows if r["cls"] == "character" and "fitness" in r}

    async def one(t):
        msg = f'Here is a short text:\n\n"""{t}"""\n\n{Q}\n\nAnswer ONLY with JSON: {{"q1": "yes"|"no", "q2": "yes"|"no", "quote": "<words that triggered a yes, or empty>"}}'
        async with sem:
            for a in range(4):
                try:
                    x = await c.chat.completions.create(model=JUDGE, messages=[{"role": "user", "content": msg}], max_tokens=200, temperature=0)
                    s = x.choices[0].message.content or ""; j = json.loads(s[s.index("{"): s.rindex("}") + 1])
                    return {**j, "flagged": j.get("q1") == "yes" or j.get("q2") == "yes"}
                except Exception:  # noqa: BLE001
                    await asyncio.sleep(2 ** a)
        return {"flagged": None}
    res = await asyncio.gather(*(one(t) for t in chars))
    out = [{"text": t, "target": chars[t]["target"], **r} for t, r in zip(chars, res)]
    (OUT / "semantic.json").write_text(json.dumps(out, indent=1))
    for tgt in ("general", "narrow"):
        xs = [o for o in out if o["target"] == tgt]; print(tgt, f"{sum(bool(o['flagged']) for o in xs)}/{len(xs)} character candidates flagged")


if __name__ == "__main__":
    asyncio.run(main())
