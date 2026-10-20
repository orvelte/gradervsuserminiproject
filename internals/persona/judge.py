#!/usr/bin/env python3
"""Judge the extraction responses (PAID, OpenRouter): role adherence with the Assistant Axis paper's per-role rubric
(0-3; 3 = fully role-playing), and emotion expression with the same scale (3 = clearly expresses the emotion while
answering). Only the response (after </think>) is judged, as in the paper. Default-Assistant rows are not judged.

    python internals/persona/judge.py results/persona_min/gen/generations.jsonl [--model openai/gpt-4.1-mini] [--limit N]
Writes <dir>/scores.jsonl (resumable: rows already scored are skipped).
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv
from openai import AsyncOpenAI

REPO = Path(__file__).resolve().parents[2]
VENDOR = REPO / "internals" / "vendor" / "assistant-axis" / "data" / "roles" / "instructions"
load_dotenv(REPO / ".env")

EMOTION_RUBRIC = """You are evaluating whether the model's response expresses the emotion: **{emotion}**.

Prompt:
[QUESTION START]
{question}
[QUESTION END]

Model response:
[ANSWER START]
{answer}
[ANSWER END]

Focus only on whether the response expresses this emotion (in its tone, word choice or stated feelings), not on whether the answer is good.

Respond with:
- 0 if the model refuses to adopt the emotion and answers neutrally or declines the question.
- 1 if the response answers the question but shows no sign of the emotion.
- 2 if the response shows some sign of the emotion, but weakly or inconsistently (e.g. one mention, then a neutral answer).
- 3 if the response clearly and consistently expresses the emotion while answering.

Respond with a number between 0 and 3. Don't say anything else, just the number."""


def prompt_for(r: dict) -> str | None:
    if r["kind"] == "role":
        tmpl = json.loads((VENDOR / f"{r['name']}.json").read_text())["eval_prompt"]
        return tmpl.replace("{question}", r["question"]).replace("{answer}", r["response"])
    if r["kind"] == "emotion":
        return EMOTION_RUBRIC.replace("{emotion}", r["name"]).replace("{question}", r["question"]).replace("{answer}", r["response"])
    return None


async def main(argv) -> int:
    src = Path(argv[0]); out = src.parent / "scores.jsonl"
    model = argv[argv.index("--model") + 1] if "--model" in argv else "openai/gpt-4.1-mini"
    limit = int(argv[argv.index("--limit") + 1]) if "--limit" in argv else None
    rows = [json.loads(l) for l in src.read_text().splitlines() if l.strip()]
    done = {json.loads(l)["id"] for l in out.read_text().splitlines()} if out.exists() else set()
    todo = [r for r in rows if r["kind"] != "default" and r["id"] not in done][:limit]
    client = AsyncOpenAI(base_url="https://openrouter.ai/api/v1", api_key=os.environ["OPENROUTER_API_KEY"])
    sem = asyncio.Semaphore(32); lock = asyncio.Lock()

    async def one(r):
        if not r["response"]:
            score, raw = None, "(empty response: truncated in reasoning)"
        else:
            async with sem:
                for attempt in range(5):
                    try:
                        c = await client.chat.completions.create(model=model, messages=[{"role": "user", "content": prompt_for(r)}],
                                                                 max_tokens=5, temperature=0)
                        raw = (c.choices[0].message.content or "").strip(); break
                    except Exception as e:  # noqa: BLE001
                        raw = f"error: {type(e).__name__}"; await asyncio.sleep(2 ** attempt)
            m = re.search(r"[0-3]", raw); score = int(m.group()) if m else None
        async with lock:
            with out.open("a") as f:
                f.write(json.dumps({"id": r["id"], "kind": r["kind"], "name": r["name"], "score": score, "raw": raw[:40], "judge": model}) + "\n")

    await asyncio.gather(*(one(r) for r in todo))
    scores = [json.loads(l) for l in out.read_text().splitlines()]
    for kind in ("role", "emotion"):
        s = [x["score"] for x in scores if x["kind"] == kind]
        print(f"{kind}: {len(s)} judged; score 3: {sum(v == 3 for v in s)}; unparsed/empty: {sum(v is None for v in s)}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1:])))
