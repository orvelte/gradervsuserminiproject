#!/usr/bin/env python3
"""OLMo smoke check against a served checkpoint: does the model emit a parseable tool call on the holdout first prompt?

    VLLM_ENV_FILE=.env.poddpo python internals/olmo_smoke.py olmo3-7b-instruct-dpo [--n 3]

Sends the graded and deployment first prompts (as run in V1) through the real `vllm_completions` provider, n samples
each, and prints the first characters of each completion and whether a tool call was parsed.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

REPO = Path(__file__).resolve().parents[1]
load_dotenv(os.environ.get("VLLM_ENV_FILE") or (REPO / ".env"), override=True)
sys.path.insert(0, str(REPO / "src")); sys.path.insert(0, str(REPO / "internals"))
import yaml  # noqa: E402

import replay_check as R  # noqa: E402
from agent_interp_envs.providers.vllm_completions_provider import VLLMCompletionsProvider  # noqa: E402


def main(argv) -> int:
    model = argv[0]; n = int(argv[argv.index("--n") + 1]) if "--n" in argv else 3
    prompts = json.loads((REPO / "results/gate1/prompts.json").read_text())
    runs = [json.loads(l) for l in (REPO / "results/persona_min/v1/runs.jsonl").read_text().splitlines()]
    run = REPO / next(m["run"] for m in runs if m["cell"] == "HO-G~visible")
    tools = R.T.get_tools(yaml.safe_load((run.parent / "config.yaml").read_text()))
    hint = ("You are provided with function signatures within <functions></functions> XML tags. You may call one or more "
            "functions to assist with the user query. Output any function calls within <function_calls></function_calls> XML "
            "tags. Do not make assumptions about what values to plug into functions.")   # the template's own default text
    ok = tot = 0
    for arm in ("G", "D"):
        for i in range(n):
            msgs = [dict(m) for m in prompts[arm]]
            if "--format-hint" in argv:
                msgs[0]["content"] = msgs[0]["content"] + " " + hint
            p = VLLMCompletionsProvider(model, msgs, tools)
            r = p.invoke(); m = p.messages[-1]
            tot += 1; ok += bool(r.tool_calls)
            calls = [(c.name, c.arguments[:80]) for c in (r.tool_calls or [])]
            print(f"[{arm}{i}] tool_call={bool(r.tool_calls)} {calls} | text: {(m.get('content') or '')[:160]!r}")
    print(f"{ok}/{tot} completions produced a parseable tool call")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
