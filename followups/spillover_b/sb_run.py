#!/usr/bin/env python3
"""Experiment B sampler: append the poll as one user message to an existing prefix and sample ONLY the reply.

    python followups/spillover_b/sb_run.py --dry-run                 # render all 60 prompts, no model call
    python followups/spillover_b/sb_run.py --budget USD [--samples 5] [--max-concurrent 4] [--probe trait]

One Fireworks raw completion per reply through RS1's provider (resampling/rs_provider.py, by import): same Harmony
rendering, model, reasoning effort, default sampling parameters and tool definitions as RS1. No tool is executed; a
reply that is a tool call is recorded as a non-answer. Option order is randomised per item per sample (seeded) and
the mapping is stored. Outputs: results/followups/spillover_b/<job>/{reply.json, messages.json, usage.jsonl}."""
from __future__ import annotations

import hashlib
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent)); sys.path.insert(0, str(HERE))
import common as C  # noqa: E402
import items as I  # noqa: E402
import detector as D  # noqa: E402
import harmony as H  # noqa: E402

CONVENTION = C.apply_rendering(H)

EXPERIMENT = "spillover_b_pilot"
RESULTS = C.RESULTS / "spillover_b"
PROBE = "fallback"
if "--probe" in sys.argv and sys.argv[sys.argv.index("--probe") + 1] == "trait":     # PREREG Amendment 3: TRAIT poll, separately sampled
    import items_trait as I  # noqa: E402,F811
    PROBE = "trait"; RESULTS = C.RESULTS / "spillover_b_trait"
PREFIX_TYPES = ("pre_wall", "post_keep", "post_replace")


def seed_for(job_id: str) -> int:
    return int(hashlib.sha256(job_id.encode()).hexdigest()[:8], 16)


def jobs(n_samples: int = 5) -> list[dict]:
    plan = json.loads((HERE.parent / "plans" / "b_prefixes.json").read_text())
    out = []
    for sid, s in plan["sources"].items():
        for pt in PREFIX_TYPES:
            for i in range(n_samples):
                if pt == "post_replace":
                    r = s["post_replace"][i % len(s["post_replace"])]
                    path, extra = r["messages_path"], {"c2_job": r["job"], "s_prime": r["s_prime"]}
                else:
                    path, extra = s[pt]["messages_path"], {}
                jid = f"{sid.replace('/', '_')}_{pt}_{i}"
                out.append({"job_id": jid, "source_run_id": sid, "source_arm": sid.split("/")[0], "prefix_type": pt, "sample_idx": i, "messages_path": path,
                            "prefix_turn": s["prefix_turn"], "conversation_date": s["conversation_date"], "fleet_config": s["fleet_config"], "seed": seed_for(jid), **extra})
    return out


def prompt_for(job: dict) -> tuple[list[dict], list[dict], str, list[bool], str]:
    import yaml
    from tools import get_tools
    cfg = yaml.safe_load(Path(job["fleet_config"]).read_text())
    msgs = json.loads(Path(job["messages_path"]).read_text())
    assert msgs[-1]["role"] == "tool", job["job_id"]
    swaps = I.draw_swaps(job["seed"])
    probe = I.render(swaps)
    return msgs + [{"role": "user", "content": probe}], get_tools(cfg), (cfg.get("agent") or {}).get("reasoning_effort") or "high", swaps, probe


def sample(job: dict) -> dict:
    from rs_provider import FireworksHarmonyProvider
    out = RESULTS / job["job_id"]; out.mkdir(parents=True, exist_ok=True)
    msgs, tools, effort, swaps, probe = prompt_for(job)
    prov = FireworksHarmonyProvider(model=None, messages=msgs, tools=tools, reasoning_effort=effort, conversation_date=job["conversation_date"], usage_log=out / "usage.jsonl")
    resp = prov.invoke()   # exactly one completion; nothing is executed
    reply, reasoning = resp.response, resp.reasoning or ""
    attempted_tool = [tc.name for tc in (resp.tool_calls or [])]
    displayed = None if attempted_tool else I.parse(reply)
    sc = I.score(displayed, swaps)
    text = (reply or "") + "\n" + reasoning
    rec = {"experiment": EXPERIMENT, **{k: job[k] for k in ("job_id", "source_run_id", "source_arm", "prefix_type", "sample_idx", "prefix_turn", "seed")},
           "c2_job": job.get("c2_job"), "s_prime": job.get("s_prime"), "item_source": I.ITEM_SOURCE, "probe_set": PROBE, "history_convention": CONVENTION, "swaps": swaps, "probe": probe,
           "reply": reply, "reasoning": reasoning, "attempted_tool_call": attempted_tool, "non_answer": bool(attempted_tool) or not (reply or "").strip(),
           **sc, "eval_talk": bool(D.TEST_RE.search(text)), "eval_talk_hits": [m.group(0) for m in D.TEST_RE.finditer(text)][:6],
           "existence_inference_in_reply": bool(D.hits_in_text(text)), "strict_parse_ok": prov.messages[-1].get("rs_parse_strict_ok")}
    (out / "reply.json").write_text(json.dumps(rec, indent=1, ensure_ascii=False))
    (out / "messages.json").write_text(json.dumps(prov.messages, indent=1, ensure_ascii=False))
    return rec


def main(argv) -> int:
    n = int(argv[argv.index("--samples") + 1]) if "--samples" in argv else 5
    js = jobs(n)
    if "--dry-run" in argv:
        tot = 0
        for j in js:
            msgs, tools, effort, swaps, probe = prompt_for(j)
            r = H.render_prompt(msgs, tools, effort, j["conversation_date"]); tot += len(r.tokens)
            ok = r.text.endswith(f"<|start|>user<|message|>{probe}<|end|><|start|>assistant")
            if j["sample_idx"] == 0:
                print(f"{j['job_id']:34} prompt_tokens={len(r.tokens):>6} ends_with_probe={ok}")
            assert ok, j["job_id"]
        print(f"{len(js)} prompts rendered, {tot} prompt tokens in total (≈ ${tot * 0.15e-6:.2f} at list price before completions)")
        return 0
    if "--budget" not in argv:
        raise SystemExit("--budget USD is required (BUDGET_USD from the task spec); refusing to launch paid sampling without it")
    budget = float(argv[argv.index("--budget") + 1]); maxc = int(argv[argv.index("--max-concurrent") + 1]) if "--max-concurrent" in argv else 4
    from dotenv import load_dotenv
    load_dotenv(C.REPO_ROOT / ".env")
    meter = C.spend_meter(); failures = []

    def one(j):
        out = RESULTS / j["job_id"]
        if (out / "reply.json").exists():
            return j["job_id"], "skip (done)"
        if meter.total_spend() >= budget:
            return j["job_id"], "skipped: budget reached"
        if len(failures) > 2:
            return j["job_id"], "skipped: more than 2 harness failures (stop rule)"
        try:
            rec = sample(j)
        except Exception as exc:  # a harness failure: counted, reported, not retried silently
            failures.append((j["job_id"], f"{type(exc).__name__}: {exc}")); return j["job_id"], f"HARNESS FAILURE {type(exc).__name__}: {str(exc)[:160]}"
        meter.record_spend(EXPERIMENT, j["job_id"], meter.job_cost(out) if (out / "final").exists() else sum(json.loads(l)["cost_usd_list"] for l in (out / "usage.jsonl").read_text().splitlines() if l.strip()))
        return j["job_id"], f"parsed={rec['parsed']} exploit={rec['exploit_score']} non_answer={rec['non_answer']}"
    with ThreadPoolExecutor(max_workers=maxc) as ex:
        for jid, status in ex.map(one, js):
            print(f"  {jid}: {status} total=${meter.total_spend():.3f}", flush=True)
    if failures:
        print("HARNESS FAILURES:", failures)
    return 0 if len(failures) <= 2 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
