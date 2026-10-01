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
    def __init__(self):
        self.messages = [{"role": "assistant", "content": None, "reasoning": LEAKED, "reasoning_details": [{}]}]


def _recover(shell_tool: str):
    provider = _FakeProvider()
    response = LLMResponse(reasoning=LEAKED, response=None, tool_calls=[])
    out = run_step._recover_json_tool_call(response, provider, states.CodingAgentState(), shell_tool=shell_tool)
    return out, provider.messages[-1]


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
