"""Experiment A container agent: RS1's agent with one user message injected at a turn boundary.

Installed as /opt/agent.py in the follow-ups image; resampling/rs_agent.py is copied next to it as /opt/rs_agent.py and
does all the work (checkpoint restore with the source's initial commit, the Fireworks/Harmony provider, the loop, the
v6 scorer). The only change: after the restore, in `continue` mode, the task's `inject_user_message` is appended as a
`user` message after the last tool result, so the next prompt ends
`…<|end|><|start|>user<|message|>TEXT<|end|><|start|>assistant`. No prefill is used in Experiment A.

`mode: inject_check` (no model call, no network): restore, inject, render the prompt and write its tail to
final/inject_check.json, to verify the in-container rendering (check F2/A1)."""
from __future__ import annotations

import json
import sys

import rs_agent

TASK = json.loads(rs_agent.TASK_PATH.read_text())
INJECT = TASK.get("inject_user_message")
_restore = rs_agent.restore_with


def restore_and_inject(provider_factory, config, init_info=None):
    state, provider = _restore(provider_factory, config, init_info)
    if INJECT is not None and TASK.get("mode", "continue") in ("continue", "inject_check"):
        assert provider.messages[-1]["role"] == "tool", f"injection point is not a turn boundary: last role {provider.messages[-1]['role']}"
        provider.add_message({"role": "user", "content": INJECT})
        rs_agent.print_section(f"INJECTED USER MESSAGE ({TASK.get('injection_point')}, {TASK.get('condition')})", INJECT)
    return state, provider


rs_agent.restore_with = restore_and_inject


def inject_check() -> None:
    import harmony as H
    from tools import get_tools
    from agent_interp_envs.config import load_config
    from rs_agent import ReplayProvider
    config = load_config(sys.argv[1] if len(sys.argv) > 1 else "/opt/config.yaml")
    state, provider = rs_agent.restore_with(lambda msgs: ReplayProvider(msgs, []), config, TASK.get("init_commit"))
    effort = (config.get("agent") or {}).get("reasoning_effort") or "high"
    r = H.render_prompt(provider.messages, get_tools(config), effort, TASK.get("conversation_date"))
    final = rs_agent.CHECKPOINT_ROOT / "final"; final.mkdir(parents=True, exist_ok=True)
    expected_tail = f"<|start|>user<|message|>{INJECT}<|end|><|start|>assistant"
    rec = {"mode": "inject_check", "n_messages": len(provider.messages), "last_roles": [m["role"] for m in provider.messages[-3:]],
           "prompt_tokens": len(r.tokens), "prompt_tail": r.text[-(len(expected_tail) + 160):], "ends_with_expected": r.text.endswith(expected_tail),
           "restored_step": state.step, "init_commit": rs_agent.INIT_RESULT}
    (final / "inject_check.json").write_text(json.dumps(rec, indent=1))
    rs_agent.print_section("INJECT CHECK", json.dumps({k: v for k, v in rec.items() if k != "prompt_tail"}))


if __name__ == "__main__":
    if TASK.get("mode") == "inject_check":
        inject_check()
    else:
        rs_agent.main()
