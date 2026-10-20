"""Client-side rendering and parsing for Qwen3.5-family chat models (Qwen3.6 / Qwen3.8), using the model's own published
chat template (`chat_template.jinja`, copied verbatim from the Hugging Face repo).

    render_prompt(messages, tools) -> str      the full prompt, ending in the generation prompt "<|im_start|>assistant\\n<think>\\n"
    parse_completion(text, tools) -> dict      {"message": {...}, "truncated": bool} from the raw completion text

The completion continues after "<think>\\n": reasoning, "\\n</think>\\n\\n", then content and/or XML tool calls
(`<tool_call>\\n<function=NAME>\\n<parameter=KEY>\\nVALUE\\n</parameter>\\n</function>\\n</tool_call>`).
"""
from __future__ import annotations

import json
import re
import secrets
from pathlib import Path

import jinja2

_DIR = Path(__file__).resolve().parent
_ENV = jinja2.Environment(trim_blocks=True, lstrip_blocks=True, loader=jinja2.FileSystemLoader(str(_DIR)))


def _raise(msg):
    raise ValueError(msg)


_ENV.globals["raise_exception"] = _raise
_ENV.filters["tojson"] = lambda x, indent=None, ensure_ascii=False: json.dumps(x, indent=indent, ensure_ascii=ensure_ascii)
_TEMPLATE = _ENV.get_template("chat_template.jinja")
GENERATION_PREFIX = "<|im_start|>assistant\n<think>\n"


def _template_message(m: dict) -> dict:
    out = {"role": m["role"], "content": m.get("content") or ""}
    rc = m.get("reasoning_content") or m.get("reasoning")
    if rc:
        out["reasoning_content"] = rc
    if m.get("tool_calls"):
        calls = []
        for tc in m["tool_calls"]:
            fn = tc.get("function") or {}
            args = fn.get("arguments")
            if isinstance(args, str):
                try:
                    args = json.loads(args or "{}")
                except json.JSONDecodeError:
                    args = {"raw": args}
            calls.append({"type": "function", "id": tc.get("id"), "function": {"name": fn.get("name"), "arguments": args or {}}})
        out["tool_calls"] = calls
    if m.get("tool_call_id"):
        out["tool_call_id"] = m["tool_call_id"]
    return out


def render_prompt(messages: list[dict], tools: list[dict] | None = None) -> str:
    return _TEMPLATE.render(messages=[_template_message(m) for m in messages], tools=tools or None, add_generation_prompt=True, enable_thinking=True)


_CALL_RE = re.compile(r"<tool_call>\s*<function=([^>\n]+)>\n?(.*?)</function>\s*</tool_call>", re.S)
_PARAM_RE = re.compile(r"<parameter=([^>\n]+)>\n?(.*?)\n?</parameter>", re.S)


def _coerce(value: str, schema: dict | None):
    t = (schema or {}).get("type")
    if t in (None, "string"):
        return value
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return value


def parse_completion(text: str, tools: list[dict] | None = None) -> dict:
    """Split a raw completion into reasoning, content and tool calls. A completion with no "</think>" is a truncated
    reasoning-only turn."""
    schemas = {}
    for t in tools or []:
        fn = t.get("function") or {}
        schemas[fn.get("name")] = ((fn.get("parameters") or {}).get("properties") or {})
    text = text.replace("<|im_end|>", "")
    if "</think>" not in text:
        return {"message": {"role": "assistant", "content": None, "reasoning_content": text.strip()}, "truncated": True}
    reasoning, rest = text.split("</think>", 1)
    calls = []
    for name, body in _CALL_RE.findall(rest):
        name = name.strip()
        args = {k.strip(): _coerce(v, schemas.get(name, {}).get(k.strip())) for k, v in _PARAM_RE.findall(body)}
        calls.append({"id": f"call_{secrets.token_hex(8)}", "type": "function", "function": {"name": name, "arguments": json.dumps(args, ensure_ascii=False)}})
    content = rest.split("<tool_call>", 1)[0].strip()
    msg = {"role": "assistant", "content": content, "reasoning_content": reasoning.strip()}
    if calls:
        msg["tool_calls"] = calls
    return {"message": msg, "truncated": False}
