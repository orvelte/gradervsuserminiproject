"""Client-side rendering and parsing for Olmo 3 Instruct models (Olmo-3-7B-Instruct and its DPO checkpoint), using the
model's own published chat template (`chat_template.jinja`, copied verbatim from Hugging Face allenai/Olmo-3-7B-Instruct;
the DPO checkpoint's template differs only in treating an empty tool list like no tools).

    render_prompt(messages, tools) -> str      the full prompt, ending in the generation prompt "<|im_start|>assistant\\n"
    parse_completion(text, tools) -> dict      {"message": {...}, "truncated": bool} from the raw completion text

Tool calls are written by the model as Python-style calls, one per line, inside <function_calls>…</function_calls>:
    bash(command="ls -la")
with each argument value JSON-encoded. Tool results go back as `environment` turns. No reasoning channel.
"""
from __future__ import annotations

import ast
import json
import re
import secrets
from pathlib import Path

import jinja2

_DIR = Path(__file__).resolve().parent
_ENV = jinja2.Environment(loader=jinja2.FileSystemLoader(str(_DIR)))
_ENV.filters["tojson"] = lambda x, indent=None, ensure_ascii=False: json.dumps(x, indent=indent, ensure_ascii=ensure_ascii)
_TEMPLATE = _ENV.get_template("chat_template.jinja")
EOS_TOKEN = "<|endoftext|>"
GENERATION_PREFIX = "<|im_start|>assistant\n"
SAMPLING = {"temperature": 0.6, "top_p": 0.95, "top_k": -1}     # generation_config.json of both checkpoints (no top-k)
STOP = ["<|im_end|>", "<|endoftext|>"]


def _template_message(m: dict) -> dict:
    out = {"role": m["role"], "content": m.get("content")}
    if m["role"] == "assistant" and m.get("tool_calls"):
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
    return out


def render_prompt(messages: list[dict], tools: list[dict] | None = None, enable_thinking: bool = True) -> str:
    """`enable_thinking` is accepted for interface parity with qwen_template and ignored (no reasoning channel)."""
    return _TEMPLATE.render(messages=[_template_message(m) for m in messages], tools=tools or None,
                            add_generation_prompt=True, eos_token=EOS_TOKEN)


_CALLS_RE = re.compile(r"<function_calls>(.*?)(?:</function_calls>|$)", re.S)


def _value(node: ast.AST, src: str):
    seg = ast.get_source_segment(src, node)
    try:
        return json.loads(seg)
    except (json.JSONDecodeError, TypeError):
        pass
    try:
        return ast.literal_eval(node)
    except (ValueError, SyntaxError):
        return seg


def _parse_calls(block: str) -> list[dict]:
    calls = []
    src = block.strip()
    try:                                                   # usually one call per line, but a value may span lines
        tree = ast.parse(src, mode="exec")
        exprs = [n.value for n in tree.body if isinstance(n, ast.Expr)]
    except SyntaxError:
        exprs = []
        for line in src.splitlines():
            try:
                exprs += [n.value for n in ast.parse(line.strip(), mode="exec").body if isinstance(n, ast.Expr)]
            except SyntaxError:
                continue
        src = None
    for e in exprs:
        if isinstance(e, ast.Call) and isinstance(e.func, ast.Name):
            seg_src = src if src is not None else ast.unparse(e)
            if src is None:
                e = ast.parse(seg_src, mode="eval").body
            args = {kw.arg: _value(kw.value, seg_src) for kw in e.keywords if kw.arg}
            calls.append({"id": f"call_{secrets.token_hex(8)}", "type": "function",
                          "function": {"name": e.func.id, "arguments": json.dumps(args, ensure_ascii=False)}})
    return calls


def parse_completion(text: str, tools: list[dict] | None = None) -> dict:
    for s in STOP:
        text = text.replace(s, "")
    m = _CALLS_RE.search(text)
    calls = _parse_calls(m.group(1)) if m else []
    content = (text[: m.start()] if m else text).strip()
    msg = {"role": "assistant", "content": content}
    if calls:
        msg["tool_calls"] = calls
    truncated = bool(m) and "</function_calls>" not in text
    return {"message": msg, "truncated": truncated}
