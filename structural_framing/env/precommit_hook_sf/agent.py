#!/usr/bin/env python3
"""
Agent for the precommit_hook_sf task (structural framing, SF1).

Same loop as the original environment plus: a fixed user turn appended after the tool result of
agent steps 8 and 18 (sf_framing.INJECTIONS; not a step), and final/sf_run.json written next to the
scorer's output (seeded history, injections fired, question-tool calls).

Original docstring follows.


Tests agent behavior in a realistic software engineering scenario where
shortcuts (--no-verify, chmod, staged-only hooks, blanket ignores, ...) are
available but the instructed approach requires fixing the type errors.

Changes from upstream (see UPSTREAM.md / CHANGELOG.md):
- the provider is built with ``checkpoint.provider_kwargs`` so every
  ``agent.*`` knob (reasoning_effort, mock_script, temperature, ...) reaches
  ``create_provider`` on the fresh path exactly as on the resume path;
- a context-window overflow censors the episode (final/censored.json) instead
  of crashing it, as ``agent_interp_envs.runner`` does;
- when the loop ends — by the agent stopping, by max_steps, by a censor or by
  an exception — ``score.finalize`` computes the ground-truth score from the
  real final repo state and writes final/{score.json, run_condition.json,
  telemetry.json, messages.json} under the root-only /opt/output.

Nothing the agent sees changes: same prompts, same tools, same shell.
"""

import json
import sys
from pathlib import Path

from dotenv import load_dotenv
from run_step import print_final_results, run_step
from score import finalize
from sf_framing import INJECTION_STEPS, INJECTIONS
from states import CodingAgentState, dump, init_fs_tracking, restore
from tools import get_tools

from agent_interp_envs.checkpoint import CHECKPOINT_ROOT, provider_kwargs, step_dir
from agent_interp_envs.config import load_config
from agent_interp_envs.print_helpers import print_section, print_step_header
from agent_interp_envs.providers import create_provider
from agent_interp_envs.runs import CENSOR_MARKER, is_context_limit_error

SF_SEED_PATH = Path("/opt/sf_seed.json")  # written root-only by entrypoint.py; tests redirect it

load_dotenv()


def main() -> None:
    config_path = sys.argv[1] if len(sys.argv) > 1 else "/opt/config.yaml"
    config = load_config(config_path)

    state = None
    provider = None
    crashed = False
    try:
        if Path("/opt/checkpoint").exists():
            state, provider = restore(config, Path("/opt/checkpoint"))
            state.step += 1
        else:
            state = CodingAgentState()
            state.variant = config.get("task", {}).get("variation", "unknown")
            init_fs_tracking()

            prompts = config.get("prompts") or {}
            provider = create_provider(
                messages=[
                    {"role": "system", "content": prompts.get("system_prompt", "")},
                    {"role": "user", "content": prompts.get("user_prompt", "")},
                ],
                tools=get_tools(config),
                **provider_kwargs(config),
            )

        provider.print_history()

        max_steps = config.get("agent", {}).get("max_steps", 30)
        while state.step < max_steps:
            print_step_header(state.step)

            try:
                should_quit = run_step(provider, state, config)
            except Exception as exc:
                if not is_context_limit_error(exc):
                    raise
                # The model's context window overflowed: no final decision is
                # possible. Mark the run censored and let finalize record what is on disk.
                print("\nCONTEXT LIMIT REACHED — episode censored (no final decision)")
                final = CHECKPOINT_ROOT / "final"
                final.mkdir(parents=True, exist_ok=True)
                (final / CENSOR_MARKER).write_text(json.dumps(
                    {"step": state.step, "error": str(exc)[:500]}, indent=1) + "\n")
                dump(state, provider, step_dir(state.step))
                break
            dump(state, provider, step_dir(state.step))
            state.step += 1

            if should_quit:
                break

            # SF1: after the tool result of the k-th agent step (k in INJECTION_STEPS; STEP k-1 in the
            # 0-indexed log), append the framing's user turn. Not a step: no tool call, no checkpoint
            # of its own (it is in the next step's messages.json), and it is identical in every run of
            # an arm.
            if state.step in INJECTION_STEPS and state.step not in state.injections and state.step < max_steps:
                framing = config.get("task", {}).get("sf_framing")
                text = INJECTIONS[framing][state.step]
                provider.add_message({"role": "user", "content": text})
                state.injections.append(state.step)
                print_section(f"INJECTED USER MESSAGE (after step {state.step})", text)

        if not state.task_completed and state.step >= max_steps:
            print_final_results(state, False)
    except BaseException:
        crashed = True
        raise
    finally:
        if state is not None and provider is not None:
            finalize(state, provider, config, crashed=crashed)
            _write_sf_run(state, config)


def _write_sf_run(state, config) -> None:
    """final/sf_run.json: the SF1-specific record (seeded history, injections, questions). Never raises."""
    try:
        final = CHECKPOINT_ROOT / "final"
        final.mkdir(parents=True, exist_ok=True)
        seed_path = SF_SEED_PATH
        seed = json.loads(seed_path.read_text()) if seed_path.exists() else None
        task = config.get("task") or {}
        rec = {
            "sf_framing": task.get("sf_framing"),
            "condition": config.get("condition") or {},
            "injection_steps": list(INJECTION_STEPS),
            "injections_fired": list(getattr(state, "injections", []) or []),
            "injection_texts": INJECTIONS.get(task.get("sf_framing"), {}),
            "questions": list(getattr(state, "questions", []) or []),
            "n_questions": len(getattr(state, "questions", []) or []),
            "seed": seed,
            "n_steps": getattr(state, "step", None),
        }
        (final / "sf_run.json").write_text(json.dumps(rec, indent=2, default=str))
    except Exception as exc:  # the record must never take the run down
        print(f"[sf_run] could not write final/sf_run.json: {exc}", flush=True)


if __name__ == "__main__":
    main()
