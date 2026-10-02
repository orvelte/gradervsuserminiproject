#!/usr/bin/env python3
"""Which OpenRouter endpoint serves GPT-OSS-120B tool calls cleanly? A cheap multi-turn probe.

    python scripts/probe_gptoss_providers.py                         # default candidates, 2 repeats x 8 turns
    python scripts/probe_gptoss_providers.py deepinfra/bf16 groq --repeats 3 --turns 10

THIS MAKES PAID API CALLS (OPENROUTER_API_KEY from .env). Expected total: well under $1 for the defaults.

Some providers return gpt-oss (Harmony) tool calls as raw JSON inside the reasoning text instead of as
structured tool_calls ("leaks"). The harness recovers those (environments/precommit_hook/run_step.py), but
every leak is a chance for a run to end early, and leaked history may encourage more leaks. This probe replays
the experiment's opening on each endpoint with the arm configs' system prompt, tools ([bash, apply_patch]),
reasoning effort and the N0 user prompt, answers tool calls with canned outputs, recovers leaks exactly as the
harness does, and reports per endpoint: structured calls, leaked calls, unrecoverable turns, and cost.
No container, no workspace: it measures tool-call formatting only, not task behaviour.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "environments" / "precommit_hook"))

import run_step  # noqa: E402
import states  # noqa: E402
from tools import get_tools  # noqa: E402

from agent_interp_envs.providers.openrouter_provider import OpenRouterProvider  # noqa: E402
from agent_interp_envs.types import ToolResult  # noqa: E402

CANDIDATES = ["deepinfra/bf16", "akashml/bf16", "crusoe/bf16", "dekallm/bf16", "coreweave/fp4", "baseten/fp4",
              "parasail/fp4", "novita/fp4", "groq", "together", "cerebras/fp16"]

LISTING = "pyproject.toml\nsrc/__init__.py\nsrc/api_source.py\nsrc/cache.py\nsrc/cli.py\nsrc/config.py\nsrc/models.py\n"
MYPY = ("src/models.py:10: error: Missing type arguments for generic type \"dict\"  [type-arg]\n"
        "src/cache.py:8: error: Function is missing a type annotation  [no-untyped-def]\n"
        "Found 258 errors in 14 files (checked 15 source files)\n")
SOURCE = '"""Simple TTL cache for expensive lookups."""\n\nimport time\n\n\nclass TTLCache:\n    def __init__(self, ttl_seconds=300):\n        self.ttl = ttl_seconds\n        self._data = {}\n'


def canned_result(name: str, args: dict) -> str:
    if name == "apply_patch":
        return "Exit code: 0\nOutput:\nDone!"
    cmd = str(args.get("command", ""))
    if "mypy" in cmd:
        return f"Exit code: 1\nOutput:\n{MYPY}"
    if cmd.startswith(("ls", "find", "tree")):
        return f"Exit code: 0\nOutput:\n{LISTING}"
    if cmd.startswith(("cat", "sed", "head", "nl")):
        return f"Exit code: 0\nOutput:\n{SOURCE}"
    return "Exit code: 0\nOutput:\n"


def probe(endpoint: str, cfg: dict, turns: int) -> dict:
    agent = cfg["agent"]
    tools = get_tools(cfg)
    allowed = {t["function"]["name"] for t in tools}
    shell = "bash" if "bash" in allowed else "execute_command"
    patch = "apply_patch" if "apply_patch" in allowed else None
    prompts = cfg["prompts"]
    provider = OpenRouterProvider(
        model=agent["model"],
        messages=[{"role": "system", "content": prompts["system_prompt"]},
                  {"role": "user", "content": prompts["user_prompt"]}],
        tools=tools, reasoning_effort=agent.get("reasoning_effort"),
        provider_preferences={"only": [endpoint], "allow_fallbacks": False},
    )
    costs: list[float] = []
    original_log = provider._log_usage

    def log_usage(response):
        cost = getattr(response.usage, "cost", None)
        if cost is not None:
            costs.append(float(cost))
        with contextlib.redirect_stdout(io.StringIO()):
            original_log(response)

    provider._log_usage = log_usage
    out = {"turns": 0, "structured": 0, "leaked": 0, "unrecovered": 0, "ended": None, "error": None}
    state = states.CodingAgentState()
    try:
        for t in range(turns):
            state.step = t
            response = provider.invoke()
            out["turns"] += 1
            if response.tool_calls:
                out["structured"] += 1
            else:
                recovered = run_step._recover_json_tool_call(response, provider, state, shell_tool=shell, patch_tool=patch)
                if recovered.tool_calls:
                    out["leaked"] += 1
                    response = recovered
                else:
                    text = (response.reasoning or "") + (response.response or "")
                    if '"command"' in text or "Begin Patch" in text:
                        out["unrecovered"] += 1
                        out["ended"] = "unrecovered leak"
                    else:
                        out["ended"] = "text reply (no tool call)"
                    break
            tc = response.tool_calls[0]
            try:
                args = json.loads(tc.arguments) if isinstance(tc.arguments, str) else dict(tc.arguments)
            except json.JSONDecodeError:
                args = {}
            provider.add_tool_result(ToolResult(id=tc.id, name=tc.name, content=canned_result(tc.name, args)))
    except Exception as e:  # e.g. 404 (privacy setting / unknown endpoint tag), tools unsupported, rate limit
        out["error"] = f"{type(e).__name__}: {str(e)[:160]}"
    out["cost"] = sum(costs)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("endpoints", nargs="*", default=CANDIDATES, help="OpenRouter endpoint tags (provider[/quant])")
    ap.add_argument("--config", default=str(REPO_ROOT / "configs" / "precommit_hook" / "N0_replication.yaml"))
    ap.add_argument("--repeats", type=int, default=2)
    ap.add_argument("--turns", type=int, default=8)
    args = ap.parse_args(argv)
    cfg = yaml.safe_load(Path(args.config).read_text())
    print(f"model={cfg['agent']['model']} effort={cfg['agent'].get('reasoning_effort')} "
          f"tools={[t['function']['name'] for t in get_tools(cfg)]} repeats={args.repeats} turns={args.turns}\n")
    print(f"{'endpoint':<16} {'turns':>5} {'structured':>10} {'leaked':>6} {'unrecov':>7} {'leak %':>6} {'cost $':>8}  notes")
    total = 0.0
    for ep in args.endpoints:
        agg = {"turns": 0, "structured": 0, "leaked": 0, "unrecovered": 0, "cost": 0.0}
        notes = []
        for _ in range(args.repeats):
            r = probe(ep, cfg, args.turns)
            for k in agg:
                agg[k] += r[k]
            if r["error"]:
                notes.append(r["error"])
                break
            if r["ended"]:
                notes.append(f"ended: {r['ended']}")
        calls = agg["structured"] + agg["leaked"] + agg["unrecovered"]
        pct = f"{100 * (agg['leaked'] + agg['unrecovered']) / calls:.0f}%" if calls else "-"
        total += agg["cost"]
        print(f"{ep:<16} {agg['turns']:>5} {agg['structured']:>10} {agg['leaked']:>6} {agg['unrecovered']:>7} {pct:>6} "
              f"{agg['cost']:>8.4f}  {'; '.join(dict.fromkeys(notes))}")
    print(f"\ntotal cost: ${total:.4f}. Prefer an endpoint with 0 unrecovered, the lowest leak %, and no errors;")
    print("then set it in configs/precommit_hook/build_arms.py (AGENT.provider_preferences.only) and regenerate.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
