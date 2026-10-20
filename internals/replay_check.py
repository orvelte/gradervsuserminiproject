#!/usr/bin/env python3
"""V1 gate 4: replay fidelity for vllm_completions rollouts. For each assistant turn, re-render the prefix with the
published template, tokenize locally, and compare with the server's stored prompt length and hash (`_vllm`).

    python internals/replay_check.py results/holdout/v1_qwen38 [--n 5]
Passing means an activation replay (render prefix -> tokenize -> append stored completion ids) reproduces exactly the
token sequence the model saw at every call.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import yaml
from tokenizers import Tokenizer

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src")); sys.path.insert(0, str(REPO / "deploysim" / "env" / "precommit_hook_ds"))
from agent_interp_envs.providers.qwen_template import render_prompt  # noqa: E402
import tools as T  # noqa: E402

TOK = Tokenizer.from_file(str(REPO / "internals" / "tokenizer" / "tokenizer.json"))


def check(run: Path) -> tuple[int, int, int]:
    cfg = yaml.safe_load((run.parent / "config.yaml").read_text()); tools = T.get_tools(cfg)
    msgs = json.loads((run / "final" / "messages.json").read_text())
    ok = tot = missing = 0
    for i, m in enumerate(msgs):
        if m.get("role") != "assistant" or "_vllm" not in m:
            if m.get("role") == "assistant" and i > 0 and msgs[i - 1].get("role") != "system" and "_vllm" not in m:
                missing += 1
            continue
        v = m["_vllm"]
        prefix = [{k: x for k, x in mm.items() if k != "_vllm"} for mm in msgs[:i]]
        ids = TOK.encode(render_prompt(prefix, tools), add_special_tokens=False).ids
        tot += 1; ok += (len(ids) == v["prompt_len"] and hashlib.sha256(str(ids).encode()).hexdigest() == v["prompt_sha256"])
    return ok, tot, missing


def main(argv) -> int:
    root = Path(argv[0]); n = int(argv[argv.index("--n") + 1]) if "--n" in argv else 5
    runs = [r for r in sorted(root.glob("*/*/*/*/run-*")) if (r / "final" / "messages.json").exists()][:n]
    T_ok = T_tot = 0
    for r in runs:
        ok, tot, missing = check(r); T_ok += ok; T_tot += tot
        print(f"{r.parts[-5]} {r.name}: {ok}/{tot} calls exact; assistant turns without _vllm (excluding prior turns): {missing}")
    print(f"TOTAL {T_ok}/{T_tot} calls reproduce the server's exact prompt tokens")
    return 0 if T_tot and T_ok == T_tot else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
