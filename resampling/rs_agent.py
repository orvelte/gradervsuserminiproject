"""RS1 container agent: restore a source-run checkpoint, continue from a mid-reasoning prefill, score at the end.

Installed as /opt/agent.py in the resampling image (resampling/env/Dockerfile) and started by the UNMODIFIED
entrypoint with the resolved config. Reads /opt/rs_task.json:
  mode: "continue" | "verify" | "score"
  prefill: str            (continue) analysis text to prefill at the next turn (P's reasoning part [+ S or S'])
  conversation_date: str  the source run's date, for the Harmony system message
  turn_tool_calls / turn_tool_result   (verify) the source run's own turn-t call and stored result to re-execute
The loop below is the original environments/precommit_hook/agent.py loop with the provider swapped; dumps,
finalize (scorer v6) and the step counter (inherited from the checkpoint, so max_steps is counted from the
original step index) are unchanged.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import traceback
from pathlib import Path

from dotenv import load_dotenv
from run_step import print_final_results, run_step
from score import finalize
from states import CodingAgentState, dump
import states as states_mod
from tools import get_tools

from agent_interp_envs.checkpoint import CHECKPOINT_ROOT, step_dir
from agent_interp_envs.config import load_config
from agent_interp_envs.print_helpers import print_section, print_step_header
from agent_interp_envs.providers.base import BaseProvider
from agent_interp_envs.runs import CENSOR_MARKER, is_context_limit_error
from agent_interp_envs.types import LLMResponse, ToolCall


TASK_PATH = Path("/opt/rs_task.json")
INIT_RESULT: dict = {}
CHECKPOINT = Path("/opt/checkpoint")
WORKSPACE = Path("/agent")


class ReplayProvider(BaseProvider):
    """Returns the source run's own turn-t tool call once (S5 re-execution through the real run_step path)."""
    def __init__(self, messages, tool_calls):
        self.messages = messages; self.tool_calls = tool_calls; self.used = False
    def invoke(self) -> LLMResponse:
        assert not self.used; self.used = True
        self.messages.append({"role": "assistant", "content": None, "reasoning": "[replay]", "tool_calls": self.tool_calls})
        return LLMResponse(reasoning="[replay]", response=None, tool_calls=[ToolCall(id=tc["id"], name=tc["function"]["name"], arguments=tc["function"]["arguments"]) for tc in self.tool_calls])
    def add_tool_result(self, tr): self.messages.append({"role": "tool", "tool_call_id": tr.id, "content": tr.content})
    def add_message(self, m): self.messages.append(m)
    def revert_last_turn(self): self.messages = self.messages[:-1]
    def dump_history(self): return json.dumps(self.messages)
    def print_history(self): pass


def tree_hash(root: Path) -> dict:
    """{relative path: sha256(mode+content)} for every file under root (symlinks by target), .git included."""
    out = {}
    for p in sorted(root.rglob("*")):
        if p.is_symlink():
            out[str(p.relative_to(root))] = "symlink:" + os.readlink(p)
        elif p.is_file():
            if any(part in ("__pycache__", ".mypy_cache", ".pytest_cache") for part in p.parts):
                continue
            out[str(p.relative_to(root))] = f"{hashlib.sha256(p.read_bytes()).hexdigest()}:{oct(p.stat().st_mode & 0o7777)}"
    return out


def recreate_initial_commit(info: dict | None) -> dict:
    """Make /agent's initial commit byte-identical to the source container's (same tree, author, dates, message), so
    restored .git objects/refs from the source run form a valid history. Returns what happened."""
    import subprocess
    def git(*args, env=None):
        return subprocess.run(["git", "-C", str(WORKSPACE), *args], capture_output=True, text=True, env={**os.environ, **(env or {})})
    before = git("rev-parse", "HEAD").stdout.strip()
    if not info:
        return {"recreated": False, "reason": "no init commit info in source run", "head_before": before}
    if before == info["sha"]:
        return {"recreated": False, "reason": "already identical", "head": before}
    import shutil
    shutil.rmtree(WORKSPACE / ".git")
    git("init", "-q"); git("config", "user.email", info["email"]); git("config", "user.name", info["name"]); git("add", "-A")
    date = f"{info['epoch']} {info['tz']}"
    r = git("commit", "-q", "--no-verify", "-m", info["message"], env={"GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date,
            "GIT_AUTHOR_NAME": info["name"], "GIT_AUTHOR_EMAIL": info["email"], "GIT_COMMITTER_NAME": info["name"], "GIT_COMMITTER_EMAIL": info["email"]})
    after = git("rev-parse", "HEAD").stdout.strip()
    subprocess.run(["chown", "-R", "dev:dev", str(WORKSPACE / ".git")], capture_output=True)
    return {"recreated": True, "head_before": before, "head_after": after, "source_sha": info["sha"], "sha_match": after == info["sha"], "commit_rc": r.returncode, "stderr": r.stderr[-200:]}


def restore_with(provider_factory, config, init_info=None):
    global INIT_RESULT
    INIT_RESULT = recreate_initial_commit(init_info)
    print_section("INITIAL COMMIT", json.dumps(INIT_RESULT))
    snapshot = states_mod._new_snapshot()
    messages = json.loads((CHECKPOINT / "messages.json").read_text())
    provider = provider_factory(messages)
    state = CodingAgentState.from_json(CHECKPOINT / "state.json")
    snapshot.restore(CHECKPOINT)
    states_mod._snapshot = snapshot
    return state, provider


NONDET = re.compile(r"\d+(\.\d+)?s\b|\d{2}:\d{2}:\d{2}|/tmp/tmp\w+")


def normalise(s: str) -> str:
    return NONDET.sub("<T>", s or "").rstrip()


def main() -> None:
    load_dotenv()
    config = load_config(sys.argv[1] if len(sys.argv) > 1 else "/opt/config.yaml")
    task = json.loads(TASK_PATH.read_text())
    mode = task.get("mode", "continue")
    final = CHECKPOINT_ROOT / "final"
    final.mkdir(parents=True, exist_ok=True)
    tools = get_tools(config)
    effort = (config.get("agent") or {}).get("reasoning_effort") or "high"

    if mode == "verify":
        # S5: restore the checkpoint, hash the tree, re-execute the source run's own turn-t call through run_step.
        state, provider = restore_with(lambda msgs: ReplayProvider(msgs, task["turn_tool_calls"]), config, task.get("init_commit"))
        state.step += 1
        hashes = tree_hash(WORKSPACE)
        hooks = sorted(p for p in hashes if p.startswith(".git/hooks/") and not p.endswith(".sample"))
        should_quit = run_step(provider, state, config)
        got = provider.messages[-1]["content"] if provider.messages[-1]["role"] == "tool" else None
        expected = task.get("turn_tool_result")
        rec = {"mode": "verify", "init_commit": INIT_RESULT, "restored_step": state.step - 1, "n_files_hashed": len(hashes), "tree_digest": hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest(),
               "custom_hooks_present": hooks, "replayed_call": task["turn_tool_calls"], "tool_output_matches": normalise(got) == normalise(expected),
               "tool_output_exact": got == expected, "got": got, "expected": expected, "tree_hashes": hashes}
        (final / "verify.json").write_text(json.dumps(rec, indent=1))
        print_section("VERIFY", json.dumps({k: v for k, v in rec.items() if k not in ("tree_hashes", "got", "expected")}, indent=1))
        return
    if mode == "score":
        # S6: restore the source run's final checkpoint and score it with the unmodified scorer.
        state, provider = restore_with(lambda msgs: ReplayProvider(msgs, []), config, task.get("init_commit"))
        finalize(state, provider, config, crashed=False)
        (final / "init_commit.json").write_text(json.dumps(INIT_RESULT, indent=1))
        return

    # mode == "continue"
    from rs_provider import FireworksHarmonyProvider  # lazy: verify/score modes run offline
    state = provider = None
    crashed = False
    try:
        state, provider = restore_with(lambda msgs: FireworksHarmonyProvider(
            model=None, messages=msgs, tools=tools, reasoning_effort=effort, conversation_date=task.get("conversation_date"),
            usage_log=final / "usage.jsonl"), config, task.get("init_commit"))
        state.step += 1
        provider.set_prefill(task["prefill"])
        print_section("RS1 PREFILL (inherited text, turn %d)" % task.get("prefix_turn", -1), task["prefill"])
        max_steps = config.get("agent", {}).get("max_steps", 30)
        while state.step < max_steps:
            print_step_header(state.step)
            try:
                should_quit = run_step(provider, state, config)
            except Exception as exc:
                if not is_context_limit_error(exc):
                    raise
                print("\nCONTEXT LIMIT REACHED — episode censored (no final decision)")
                (final / CENSOR_MARKER).write_text(json.dumps({"step": state.step, "error": str(exc)[:500]}, indent=1) + "\n")
                dump(state, provider, step_dir(state.step))
                break
            dump(state, provider, step_dir(state.step))
            state.step += 1
            if should_quit:
                break
        if not state.task_completed and state.step >= max_steps:
            print_final_results(state, False)
    except BaseException:
        crashed = True
        traceback.print_exc()
        raise
    finally:
        if state is not None and provider is not None:
            finalize(state, provider, config, crashed=crashed)
            try:
                rec = {k: v for k, v in task.items()}
                rec.update({"n_steps_total": state.step, "crashed": crashed, "init_commit_result": INIT_RESULT, "history_convention": __import__("harmony").HISTORY_CONVENTION,
                            "provider": "fireworks completions (accounts/fireworks/models/gpt-oss-120b, raw_output)"})
                (final / "resample.json").write_text(json.dumps(rec, indent=1))
            except Exception as exc:
                print(f"[rs] could not write resample.json: {exc}")


if __name__ == "__main__":
    main()
