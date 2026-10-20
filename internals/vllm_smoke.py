#!/usr/bin/env python3
"""Check the self-hosted vLLM server before any rollout (run right after `modal deploy internals/modal/vllm_server.py`).

    python internals/vllm_smoke.py            # uses VLLM_BASE_URL / VLLM_API_KEY from .env

1. /v1/models lists qwen3.8-27b.
2. A short tool-use prompt rendered with the published template completes, returns prompt_token_ids and token_ids
   (`return_token_ids`), and parses into a tool call.
3. Fidelity: the server's prompt_token_ids equal our local tokenizer's encoding of the same rendered prompt, so a
   replay that renders + tokenizes locally reproduces exactly what the model saw.
"""
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI
from tokenizers import Tokenizer

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
from agent_interp_envs.providers.qwen_template import parse_completion, render_prompt  # noqa: E402

load_dotenv(REPO / ".env")
TOOLS = [{"type": "function", "function": {"name": "bash", "description": "Run a shell command.",
                                           "parameters": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}}}]


def main() -> int:
    client = OpenAI(base_url=os.environ["VLLM_BASE_URL"], api_key=os.environ.get("VLLM_API_KEY", "EMPTY"), timeout=1800)
    models = [m.id for m in client.models.list().data]
    print("models:", models)
    msgs = [{"role": "system", "content": "You are a coding agent with a bash tool."}, {"role": "user", "content": "List the files in the current directory."}]
    prompt = render_prompt(msgs, TOOLS)
    r = client.completions.create(model="qwen3.8-27b", prompt=prompt, max_tokens=2048, temperature=0.6, top_p=0.95,
                                  extra_body={"top_k": 20, "return_token_ids": True, "skip_special_tokens": False})
    c = r.choices[0]
    prompt_ids = list(getattr(c, "prompt_token_ids", None) or [])
    out_ids = list(getattr(c, "token_ids", None) or [])
    local = Tokenizer.from_file(str(REPO / "internals" / "tokenizer" / "tokenizer.json")).encode(prompt, add_special_tokens=False).ids
    parsed = parse_completion(c.text, TOOLS)["message"]
    checks = {"model served": "qwen3.8-27b" in models, "prompt ids returned": bool(prompt_ids), "completion ids returned": bool(out_ids),
              "server ids == local tokenizer": prompt_ids == local, "parsed a tool call": bool(parsed.get("tool_calls"))}
    for k, v in checks.items():
        print(f"{'OK  ' if v else 'FAIL'} {k}")
    print("tool call:", json.dumps(parsed.get("tool_calls"))[:200])
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
