"""The source endpoint's history convention, as an OPT-IN runtime switch for resampling/harmony.py (no file edited).

Found by check F1 on 2026-10-03: AkashML (via OpenRouter) renders the conversation history as
  - tool-call arguments exactly as stored (no re-serialisation),
  - past tool calls with the plain content type `json`:  `<|start|>assistant to=functions.bash<|channel|>commentary json<|message|>…<|call|>`
  - tool results addressed to the assistant:              `<|start|>functions.bash to=assistant<|channel|>commentary<|message|>…<|end|>`
This reproduces the endpoint's reported prompt_tokens at all eight checkpoints tested (three Experiment A source runs
at two points each, and RS1's two reference checkpoints), including turns with malformed or pretty-printed arguments.
RS1's convention (compact json.dumps arguments, `<|constrain|>json`, no recipient) matched only on runs whose stored
arguments are compact, where the token counts coincide.

OFF by default: the follow-up pilots were specified to copy RS1's settings exactly. `apply(H)` switches a loaded
harmony module to this convention; nothing calls it unless the task/CLI asks for `history_convention: source`."""
from __future__ import annotations

NAME = "source_v2 (raw args, content type json, to=assistant on tool results)"


def apply(H) -> None:
    from openai_harmony import Author, Message, Role

    def to_conversation(messages, tools, effort, date):
        out, id_to_name = [], {}
        for m in messages:
            role = m["role"]
            if role == "system":
                out.append(Message.from_role_and_content(Role.SYSTEM, H._system(effort, date)))
                out.append(Message.from_role_and_content(Role.DEVELOPER, H._developer(m.get("content") or "", tools)))
            elif role == "user":
                out.append(Message.from_role_and_content(Role.USER, m.get("content") or ""))
            elif role == "assistant":
                reasoning = m.get("reasoning") or m.get("reasoning_content") or ""
                if reasoning:
                    out.append(Message.from_role_and_content(Role.ASSISTANT, reasoning).with_channel("analysis"))
                for tc in m.get("tool_calls") or []:
                    fn = tc["function"]; id_to_name[tc["id"]] = fn["name"]
                    out.append(Message.from_role_and_content(Role.ASSISTANT, fn["arguments"]).with_channel("commentary")
                               .with_recipient(f"functions.{fn['name']}").with_content_type("json"))
                if m.get("content"):
                    out.append(Message.from_role_and_content(Role.ASSISTANT, m["content"]).with_channel("final"))
            elif role == "tool":
                name = id_to_name.get(m.get("tool_call_id"), "bash")
                out.append(Message.from_author_and_content(Author.new(Role.TOOL, f"functions.{name}"), m.get("content") or "")
                           .with_channel("commentary").with_recipient("assistant"))
            else:
                raise ValueError(f"unknown role {role}")
        return out

    H.to_conversation = to_conversation
    H.compact_args = lambda args: args          # arguments are kept as stored; the round trip compares them raw
    H.HISTORY_CONVENTION.clear()
    H.HISTORY_CONVENTION.update({"name": NAME, "args": "as stored", "content_type_on_past_calls": "json", "recipient_on_tool_results": True})
