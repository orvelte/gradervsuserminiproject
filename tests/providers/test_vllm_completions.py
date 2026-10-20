"""vllm_completions provider and the Qwen3.5-family template helpers (assistantaxis.md guardrail 1)."""
import json

import pytest

from agent_interp_envs.providers import qwen_template as Q
from agent_interp_envs.providers.vllm_completions_provider import VLLMCompletionsProvider

TOOLS = [{"type": "function", "function": {"name": "bash", "description": "Run a shell command.",
                                           "parameters": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}}}]


def test_render_ends_in_generation_prefix_and_lists_tools():
    p = Q.render_prompt([{"role": "system", "content": "sys"}, {"role": "user", "content": "hi"}], TOOLS)
    assert p.endswith(Q.GENERATION_PREFIX) and "<tools>" in p and '"name": "bash"' in p


def test_parse_tool_call_and_reasoning():
    text = "I should look around.\n</think>\n\n<tool_call>\n<function=bash>\n<parameter=command>\nls -la\n</parameter>\n</function>\n</tool_call>"
    m = Q.parse_completion(text, TOOLS)["message"]
    assert m["reasoning_content"] == "I should look around." and m["content"] == ""
    assert m["tool_calls"][0]["function"]["name"] == "bash" and json.loads(m["tool_calls"][0]["function"]["arguments"]) == {"command": "ls -la"}


def test_parse_multiline_parameter_and_text_reply():
    text = "think\n</think>\n\n<tool_call>\n<function=bash>\n<parameter=command>\ncat > a <<'EOF'\nx\nEOF\n</parameter>\n</function>\n</tool_call>"
    assert json.loads(Q.parse_completion(text, TOOLS)["message"]["tool_calls"][0]["function"]["arguments"])["command"] == "cat > a <<'EOF'\nx\nEOF"
    m = Q.parse_completion("done thinking\n</think>\n\nAll done.<|im_end|>", TOOLS)["message"]
    assert m["content"] == "All done." and "tool_calls" not in m


def test_truncated_reasoning():
    r = Q.parse_completion("still thinking about", TOOLS)
    assert r["truncated"] and r["message"]["content"] is None


def test_round_trip_render_of_parsed_message_reproduces_the_completion():
    """The history re-render of a parsed turn equals generation prefix + completion (so replay is consistent)."""
    completion = "Look first.\n</think>\n\n<tool_call>\n<function=bash>\n<parameter=command>\nls\n</parameter>\n</function>\n</tool_call>"
    base = [{"role": "system", "content": "sys"}, {"role": "user", "content": "do it"}]
    msg = Q.parse_completion(completion, TOOLS)["message"]
    full = Q.render_prompt(base + [msg, {"role": "tool", "tool_call_id": "x", "content": "a b"}], TOOLS)
    assert (Q.render_prompt(base, TOOLS) + completion) in full


def test_provider_records_token_ids(monkeypatch):
    monkeypatch.setenv("VLLM_BASE_URL", "http://localhost:9/v1")
    p = VLLMCompletionsProvider("qwen3.8-27b", [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}], TOOLS)
    monkeypatch.setattr(p, "_complete", lambda prompt: ("r\n</think>\n\n<tool_call>\n<function=bash>\n<parameter=command>\npwd\n</parameter>\n</function>\n</tool_call>", [1, 2, 3], [7, 8], "stop"))
    out = p.invoke()
    assert out.tool_calls[0].name == "bash" and p.messages[-1]["_vllm"]["prompt_len"] == 3 and p.messages[-1]["_vllm"]["completion_token_ids"] == [7, 8]


def test_provider_needs_base_url(monkeypatch):
    monkeypatch.delenv("VLLM_BASE_URL", raising=False)
    with pytest.raises(ValueError):
        VLLMCompletionsProvider("m", [], TOOLS)
