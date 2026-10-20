#!/usr/bin/env python3
"""Render-fidelity check for activation replay (assistantaxis.md guardrail 1): re-render saved API transcripts with
Qwen3.8-27B's own chat template and compare token counts with the provider's billed input tokens for the same call.

    python internals/render_check.py results/holdout/h3_qwen38 [--n 20]
A replay is faithful for a call when the rendered prefix has exactly the provider's `in=` token count.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import jinja2
import yaml
from tokenizers import Tokenizer

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO / "deploysim" / "env" / "precommit_hook_ds"))
import tools as T  # noqa: E402

TOK = Tokenizer.from_file(str(HERE / "tokenizer" / "tokenizer.json"))
ENV = jinja2.Environment(trim_blocks=True, lstrip_blocks=True, loader=jinja2.FileSystemLoader(str(HERE / "tokenizer")))
ENV.globals["raise_exception"] = lambda m: (_ for _ in ()).throw(ValueError(m))
ENV.filters["tojson"] = lambda x, indent=None, ensure_ascii=False: json.dumps(x, indent=indent, ensure_ascii=ensure_ascii)
TEMPLATE = ENV.get_template("chat_template.jinja")


def to_template(m: dict) -> dict:
    out = {"role": m["role"], "content": m.get("content") or ""}
    if m.get("reasoning_content") or m.get("reasoning"):
        out["reasoning_content"] = m.get("reasoning_content") or m.get("reasoning")
    if m.get("tool_calls"):
        out["tool_calls"] = [{"type": "function", "id": tc.get("id"), "function": {"name": tc["function"]["name"],
                              "arguments": json.loads(tc["function"]["arguments"] or "{}")}} for tc in m["tool_calls"]]
    if m.get("tool_call_id"):
        out["tool_call_id"] = m["tool_call_id"]
    return out


def render(messages, tools) -> str:
    return TEMPLATE.render(messages=[to_template(m) for m in messages], tools=tools, add_generation_prompt=True, enable_thinking=True)


def calls(run: Path) -> list[int]:
    return [int(x) for x in re.findall(r"\[provider-usage\][^\n]*? in=(\d+)", (run / "rollout.log").read_text())]


def check(run: Path) -> list[tuple[int, int, int]]:
    cfg = yaml.safe_load((run.parent / "config.yaml").read_text()); tools = T.get_tools(cfg)
    msgs = json.loads((run / "final" / "messages.json").read_text())
    billed = calls(run)
    ends = [i for i, m in enumerate(msgs) if m.get("role") == "assistant"]       # each call's prompt = msgs[:i]
    out = []
    for k, i in enumerate(ends[: len(billed)]):
        n = len(TOK.encode(render(msgs[:i], [t for t in tools]), add_special_tokens=False).ids)
        out.append((k, n, billed[k]))
    return out


def main(argv) -> int:
    root = Path(argv[0]); n = int(argv[argv.index("--n") + 1]) if "--n" in argv else 5
    runs = sorted(root.glob("*/*/*/*/run-*"))[:n]
    tot = exact = 0; offs = []
    for run in runs:
        res = check(run)
        for k, mine, theirs in res:
            tot += 1; exact += mine == theirs; offs.append(mine - theirs)
        print(run.parts[-5], run.name, [(m - t) for _, m, t in res][:12])
    print(f"{exact}/{tot} calls render to exactly the billed token count; offsets seen: {sorted(set(offs))[:15]}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
