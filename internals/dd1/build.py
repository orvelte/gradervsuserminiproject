#!/usr/bin/env python3
"""DD1 inputs (PREREG DD1): renders every prompt the pod needs into results/dd1/prompts.jsonl. Local, no GPU.

    python internals/dd1/build.py

Rows (all text rendered with Qwen3.8's published template, the same renderer as V1 and PP1):
  kind=initial    one per cell: system prompt, prior turns and task message, thinking on (ends "<think>\\n").
                  Asserted identical across every V1 run of the cell.
  kind=prefix     each of the 72 V1 prefixes, thinking on, reasoning kept (secondary directions).
  kind=pair       the 540 verifier-vs-human prompts (vendor/verifier_vs_human), thinking on; side pos/neg.
  kind=eval       the 23 D-visible prefixes, each with its 42 probes: override (AB, BA; forced_choice.render) and the
                  five trait measures (8 each; frame_traits wording). Gate 0 P(override) attached for the HF check.
  kind=gen        4 D-visible prefixes (seeded), thinking off, for the coherence continuations.
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "internals" / "personaprompt")); sys.path.insert(0, str(REPO / "internals" / "personaprompt" / "heldout"))
from forced_choice import OVERRIDE_LETTER, build_prefixes, render, render_prompt  # noqa: E402
import frame_traits as FT  # noqa: E402

OUT = REPO / "results" / "dd1"
TRAITS = ["rule_breaking", "dishonesty", "competitiveness", "ambition", "approval_seeking"]
N_INITIAL = 4  # system, prior user, prior assistant, task message


def initial_messages(prefix: dict) -> list[dict]:
    m = prefix["messages"][:N_INITIAL]
    assert [x["role"] for x in m] == ["system", "user", "assistant", "user"], [x["role"] for x in m]
    return m


def rows() -> list[dict]:
    pre = build_prefixes(); out = []
    g0 = {p["run"]: p["p"] for p in json.loads((REPO / "results" / "personaprompt" / "gate0.json").read_text())["prefixes"]}
    for cell in ("HO-G~visible", "HO-D~visible", "HO-G~holdout", "HO-D~holdout"):
        ps = [p for p in pre if p["cell"] == cell]
        texts = {render_prompt(initial_messages(p), p["tools"], enable_thinking=True) for p in ps}
        assert len(texts) == 1, f"{cell}: initial prompt differs across runs"
        out.append({"kind": "initial", "cell": cell, "text": texts.pop()})
    for p in pre:
        out.append({"kind": "prefix", "cell": p["cell"], "run": p["run"], "text": render_prompt(p["messages"], p["tools"], enable_thinking=True)})
    for side in ("positive", "negative"):
        for i, line in enumerate((HERE / "vendor" / "verifier_vs_human" / f"{side}.jsonl").read_text().splitlines()):
            out.append({"kind": "pair", "side": side[:3], "i": i, "text": render_prompt(json.loads(line)["messages"], None, enable_thinking=True)})
    trait_probes = [x for x in FT.probes() if x[0] in TRAITS]
    dvis = [p for p in pre if p["cell"] == "HO-D~visible"]
    for p in dvis:
        probes = [{"measure": "override", "order": o, "worse": OVERRIDE_LETTER[o], "text": render(p, None, o)} for o in ("AB", "BA")]
        probes += [{"measure": m, "worse": w, "text": FT.prompt_for(p, None, u)} for m, u, w in trait_probes]
        out.append({"kind": "eval", "run": p["run"], "gate0_p": g0[p["run"]], "probes": probes})
    for p in random.Random(20261023).sample(dvis, 4):
        out.append({"kind": "gen", "run": p["run"], "text": render_prompt(p["messages"], p["tools"], enable_thinking=False)})
    return out


def main() -> int:
    rs = rows(); OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "prompts.jsonl").open("w") as f:
        for r in rs:
            f.write(json.dumps(r) + "\n")
    from collections import Counter
    print(Counter(r["kind"] for r in rs), "probes per eval prefix:", len(next(r for r in rs if r["kind"] == "eval")["probes"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
