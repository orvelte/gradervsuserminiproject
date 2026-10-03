"""Harmony rendering/parsing for GPT-OSS resampling: harness chat messages <-> raw Harmony prompt.

Conventions reproduced (evidence in resampling/BUILD_REPORT.md, S2):
- System message: openai-harmony default (identity, knowledge cutoff 2024-06, `Reasoning: <effort>`, `Current date: <run date>`,
  channel list); the harness's system prompt goes into the developer message's `# Instructions`; tools into `functions`.
- Assistant turns that ended in a tool call keep their analysis (reasoning) message; a turn that ended with a final
  message drops earlier analysis (Harmony convention; verified on AkashML with a nonce test).
- Tool results are `functions.<name>` messages to the assistant on the commentary channel.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass

from openai_harmony import (Author, Conversation, DeveloperContent, HarmonyEncodingName, Message, ReasoningEffort, Role,
                            SystemContent, TextContent, ToolDescription, load_harmony_encoding)

ENC = load_harmony_encoding(HarmonyEncodingName.HARMONY_GPT_OSS)
EFFORT = {"low": ReasoningEffort.LOW, "medium": ReasoningEffort.MEDIUM, "high": ReasoningEffort.HIGH}

# History-rendering convention of the source endpoint (AkashML via OpenRouter), fixed by matching its reported
# prompt_tokens at two checkpoints of a source run (BUILD_REPORT.md, S2): tool-call arguments are re-serialised
# compactly (json.dumps) and past tool calls carry `<|constrain|>json`, tool results carry no `to=assistant`
# recipient... OR past calls carry no constrain marker and results carry the recipient. Both give identical token
# counts; HISTORY_CONVENTION selects one and is recorded in every run's resample.json.
HISTORY_CONVENTION = {"constrain_on_past_calls": True, "recipient_on_tool_results": False, "compact_args": True}


def compact_args(args: str) -> str:
    try:
        return json.dumps(json.loads(args))
    except Exception:
        return args


@dataclass
class Rendered:
    tokens: list[int]
    text: str


def _system(effort: str, date: str | None) -> SystemContent:
    s = SystemContent.new().with_reasoning_effort(EFFORT[effort])
    if date:
        s = s.with_conversation_start_date(date)
    return s


def _developer(instructions: str, tools: list[dict]) -> DeveloperContent:
    d = DeveloperContent.new().with_instructions(instructions)
    if tools:
        d = d.with_function_tools([ToolDescription.new(t["function"]["name"], t["function"]["description"], parameters=t["function"]["parameters"]) for t in tools])
    return d


def to_conversation(messages: list[dict], tools: list[dict], effort: str, date: str | None) -> list[Message]:
    """Harness chat messages (system, user, assistant{reasoning,content,tool_calls}, tool) -> Harmony messages."""
    out: list[Message] = []
    sys_text = ""
    id_to_name: dict[str, str] = {}
    for i, m in enumerate(messages):
        role = m["role"]
        if role == "system":
            sys_text = m.get("content") or ""
            out.append(Message.from_role_and_content(Role.SYSTEM, _system(effort, date)))
            out.append(Message.from_role_and_content(Role.DEVELOPER, _developer(sys_text, tools)))
        elif role == "user":
            out.append(Message.from_role_and_content(Role.USER, m.get("content") or ""))
        elif role == "assistant":
            reasoning = m.get("reasoning") or m.get("reasoning_content") or ""
            tcs = m.get("tool_calls") or []
            if reasoning:
                out.append(Message.from_role_and_content(Role.ASSISTANT, reasoning).with_channel("analysis"))
            if tcs:
                for tc in tcs:
                    fn = tc["function"]; id_to_name[tc["id"]] = fn["name"]
                    args = compact_args(fn["arguments"]) if HISTORY_CONVENTION["compact_args"] else fn["arguments"]
                    mm = Message.from_role_and_content(Role.ASSISTANT, args).with_channel("commentary").with_recipient(f"functions.{fn['name']}")
                    if HISTORY_CONVENTION["constrain_on_past_calls"]:
                        mm = mm.with_content_type("<|constrain|>json")
                    out.append(mm)
            if m.get("content"):
                out.append(Message.from_role_and_content(Role.ASSISTANT, m["content"]).with_channel("final"))
        elif role == "tool":
            name = id_to_name.get(m.get("tool_call_id"), "bash")
            mm = Message.from_author_and_content(Author.new(Role.TOOL, f"functions.{name}"), m.get("content") or "").with_channel("commentary")
            if HISTORY_CONVENTION["recipient_on_tool_results"]:
                mm = mm.with_recipient("assistant")
            out.append(mm)
        else:
            raise ValueError(f"unknown role {role}")
    return out


def render_prompt(messages: list[dict], tools: list[dict], effort: str, date: str | None, prefill: str | None = None) -> Rendered:
    """Prompt for the next assistant turn. `prefill` = partial analysis text appended after
    `<|start|>assistant<|channel|>analysis<|message|>` (mid-reasoning continuation)."""
    conv = Conversation.from_messages(to_conversation(messages, tools, effort, date))
    toks = list(ENC.render_conversation_for_completion(conv, Role.ASSISTANT))
    if prefill is not None:
        toks += ENC.encode("<|channel|>analysis<|message|>", allowed_special="all") + ENC.encode(prefill, allowed_special=set())
    return Rendered(toks, ENC.decode(toks))


class _Seg:
    def __init__(self, channel, recipient, text):
        self.channel, self.recipient, self.text = channel, recipient, text


def _parse_completion_text(ids: list[int]) -> list[_Seg]:
    """Tolerant text-level parse of a completion: segments `<|channel|>X [to=functions.Y] [anything]<|message|>body<|end|/|call|/|return|>`.
    gpt-oss emits header variants the strict parser rejects (e.g. `analysis to=functions.bash code<|message|>`)."""
    import re
    text = ENC.decode(ids)
    pat = re.compile(r"(?:<\|start\|>assistant)?\s*(?P<header>(?:<\|channel\|>|to=)[^<]*?)<\|message\|>(?P<body>.*?)(?:<\|end\|>|<\|call\|>|<\|return\|>|$)", re.S)
    out = []
    for m in pat.finditer(text):
        h = m.group("header")
        ch = re.search(r"<\|channel\|>(analysis|commentary|final)", h); rc = re.search(r"to=(functions\.[A-Za-z0-9_]+)", h)
        out.append(_Seg(ch.group(1) if ch else "analysis", rc.group(1) if rc else None, m.group("body")))
    return out


def parse_completion(token_ids: list[int], prefill: str | None = None) -> dict:
    """Completion tokens -> harness assistant message {role, reasoning, reasoning_content, content, tool_calls}.
    With a prefill, the analysis text is `prefill + continuation` (the parser is fed the channel header + prefill).
    The strict openai-harmony parser is tried first; on HarmonyError the text-level parser is used and the message
    is marked `rs_parse_fallback`."""
    from openai_harmony import HarmonyError
    ids = list(token_ids)
    if prefill is not None:
        ids = ENC.encode("<|channel|>analysis<|message|>", allowed_special="all") + ENC.encode(prefill, allowed_special=set()) + ids
    fallback = False
    try:
        parsed = ENC.parse_messages_from_completion_tokens(ids, Role.ASSISTANT)
        msgs = [_Seg(m.channel, m.recipient, "".join(c.text for c in m.content if isinstance(c, TextContent))) for m in parsed]
    except HarmonyError:
        msgs = _parse_completion_text(ids); fallback = True
    reasoning, content, tool_calls = [], None, []
    for m in msgs:
        text = m.text
        # gpt-oss emits function calls on the analysis channel as well as on commentary
        # (`<|channel|>analysis to=functions.bash <|constrain|>json`); any functions.* recipient is a tool call.
        if m.recipient and m.recipient.startswith("functions."):
            tool_calls.append({"id": f"call_{uuid.uuid4().hex[:24]}", "type": "function", "function": {"name": m.recipient.split(".", 1)[1], "arguments": text}})
        elif m.channel == "analysis":
            reasoning.append(text)
        elif m.channel == "final":
            content = (content or "") + text
        else:  # commentary without recipient: treat as content preamble
            content = (content or "") + text
    r = "\n".join(reasoning) if reasoning else None
    out = {"role": "assistant", "content": content, "reasoning": r, "reasoning_content": r,
           "reasoning_details": ([{"type": "reasoning.text", "text": r, "format": "unknown", "index": 0}] if r else None),
           "tool_calls": tool_calls or None, "refusal": None, "annotations": None, "audio": None, "function_call": None}
    if fallback:
        out["rs_parse_fallback"] = True
    return out


def render_history(messages: list[dict], tools: list[dict], effort: str, date: str | None) -> list[int]:
    """The conversation without the trailing `<|start|>assistant` header (what parse_prompt consumes)."""
    return list(ENC.render_conversation(Conversation.from_messages(to_conversation(messages, tools, effort, date))))


def parse_prompt(token_ids: list[int]) -> list[dict]:
    """Rendered history (render_history) -> harness-shaped messages, for the S3 round-trip check. Text-level parse of
    the decoded prompt (openai-harmony's parser rejects tool roles). Tool-call ids are regenerated; arguments come
    back compact (see HISTORY_CONVENTION)."""
    import re
    text = ENC.decode(list(token_ids))
    pat = re.compile(r"<\|start\|>(?P<header>.*?)<\|message\|>(?P<body>.*?)(?P<stop><\|end\|>|<\|call\|>|<\|return\|>)", re.S)
    out: list[dict] = []
    pending: dict | None = None
    last_call_id = None
    for m in pat.finditer(text):
        header, body = m.group("header"), m.group("body")
        if header == "system":
            continue
        if header == "developer":
            instr = body.split("# Instructions\n\n", 1)[1].split("\n\n# Tools", 1)[0] if "# Instructions" in body else body
            out.append({"role": "system", "content": instr}); continue
        if header == "user":
            pending = None; out.append({"role": "user", "content": body}); continue
        if header.startswith("assistant"):
            if pending is None or pending.get("_closed"):
                pending = {"role": "assistant", "content": None, "reasoning": None, "tool_calls": None}; out.append(pending)
            if "<|channel|>analysis" in header:
                pending["reasoning"] = (pending["reasoning"] + "\n" if pending["reasoning"] else "") + body
            elif "<|channel|>commentary" in header and "to=functions." in header:
                name = re.search(r"to=functions\.([A-Za-z0-9_]+)", header).group(1)
                last_call_id = f"call_{len(out)}"
                pending["tool_calls"] = (pending["tool_calls"] or []) + [{"id": last_call_id, "type": "function", "function": {"name": name, "arguments": body}}]
                pending["_closed"] = True
            elif "<|channel|>final" in header:
                pending["content"] = body; pending["_closed"] = True
            continue
        if header.startswith("functions."):
            out.append({"role": "tool", "tool_call_id": last_call_id, "content": body}); continue
        raise ValueError(f"unknown header {header!r}")
    for m in out:
        m.pop("_closed", None)
    return out
