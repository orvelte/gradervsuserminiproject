"""Leaked-tool-call recovery (gpt-oss / Harmony): the promoted call must be a tool the run offers.

With task.tools: [bash, apply_patch] there is no execute_command, so a call recovered as
execute_command would be rejected as an unknown function.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
ENV_DIR = REPO_ROOT / "environments" / "precommit_hook"
if str(ENV_DIR) not in sys.path:
    sys.path.insert(0, str(ENV_DIR))

import run_step  # noqa: E402
import states  # noqa: E402
from agent_interp_envs.types import LLMResponse  # noqa: E402

LEAKED = 'I will check the errors first.{"command": "mypy src/ | tail -3"}'


class _FakeProvider:
    def __init__(self, text=LEAKED):
        self.messages = [{"role": "assistant", "content": None, "reasoning": text, "reasoning_content": text,
                          "reasoning_details": [{}]}]


def _recover(shell_tool: str, text: str = LEAKED, patch_tool: str | None = None):
    provider = _FakeProvider(text)
    response = LLMResponse(reasoning=text, response=None, tool_calls=[])
    out = run_step._recover_json_tool_call(response, provider, states.CodingAgentState(), shell_tool=shell_tool,
                                           patch_tool=patch_tool)
    return out, provider.messages[-1]


PATCH = "*** Begin Patch\n*** Update File: src/models.py\n@@\n-x = {}\n+x: dict[str, int] = {}\n*** End Patch"
# The two shapes seen from gpt-oss on OpenRouter (DeepInfra): {"patch": ...} and a pretty-printed {"input": ...}
# whose body ends with a doubled "*** End Patch".
LEAKED_PATCH_KEY = "Let's patch src/models.py.\n\n" + json.dumps({"patch": PATCH}) + "\n"
LEAKED_INPUT_KEY = "Let's apply patch.\n\n" + json.dumps({"input": PATCH + "\n*** End Patch"}, indent=2) + "\n"


def test_recovered_call_uses_bash_when_the_run_offers_bash():
    out, last = _recover("bash")
    assert [tc.name for tc in out.tool_calls] == ["bash"]
    assert json.loads(out.tool_calls[0].arguments) == {"command": "mypy src/ | tail -3"}
    assert last["tool_calls"][0]["function"]["name"] == "bash"
    assert '"command"' not in last["reasoning"] and "reasoning_details" not in last


def test_recovered_call_defaults_to_execute_command():
    out, last = _recover("execute_command")
    assert out.tool_calls[0].name == "execute_command"
    assert last["tool_calls"][0]["function"]["name"] == "execute_command"


def test_leaked_patch_is_promoted_to_apply_patch_whatever_the_key():
    for text, body in ((LEAKED_PATCH_KEY, PATCH), (LEAKED_INPUT_KEY, PATCH + "\n*** End Patch")):
        out, last = _recover("bash", text, patch_tool="apply_patch")
        assert [tc.name for tc in out.tool_calls] == ["apply_patch"]
        assert json.loads(out.tool_calls[0].arguments) == {"input": body}
        assert last["tool_calls"][0]["function"]["name"] == "apply_patch"
        # the leaked JSON is gone from both reasoning fields that are replayed
        for k in ("reasoning", "reasoning_content"):
            assert "Begin Patch" not in last[k] and last[k].startswith("Let's")
        assert "reasoning_details" not in last


def test_patch_leak_left_alone_when_the_run_has_no_apply_patch():
    out, _ = _recover("execute_command", LEAKED_PATCH_KEY, patch_tool=None)
    assert out.tool_calls == []


def test_the_later_leaked_call_wins():
    text = 'First look.{"command": "ls src"} then edit: ' + json.dumps({"input": PATCH})
    out, _ = _recover("bash", text, patch_tool="apply_patch")
    assert out.tool_calls[0].name == "apply_patch"
    text = "Edit: " + json.dumps({"input": PATCH}) + ' and check {"command": "mypy src"}'
    out, _ = _recover("bash", text, patch_tool="apply_patch")
    assert out.tool_calls[0].name == "bash"
    assert json.loads(out.tool_calls[0].arguments) == {"command": "mypy src"}


def test_shell_leak_also_cleans_reasoning_content():
    out, last = _recover("bash")
    assert '"command"' not in last["reasoning_content"]

