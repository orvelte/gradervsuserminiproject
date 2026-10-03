#!/usr/bin/env python3
"""Stage 0 checks that involve the model endpoints (single test calls only). PREREG.md must be committed first.

    python followups/stage0_checks.py f1     # RS1's S2 (token-count fidelity vs the source endpoint) and S3 (round trip)
                                             # at the six Experiment A injection checkpoints
    python followups/stage0_checks.py f2     # one Fireworks completion with the counter message injected as a user turn

S5 (restore + replay) and the in-container render of the injected turn are `momentum_a/ma_run.py verify` and
`inject-check` (no model calls). Costs go to followups/spend.json under stage `stage0`."""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "momentum_a"))
import common as C  # noqa: E402
import harmony as H  # noqa: E402
import workaround as W  # noqa: E402
import ma_run  # noqa: E402

CONVENTION = C.apply_rendering(H)

OUT = C.RESULTS / "stage0"


def _cfg_tools(fleet_config: str):
    import yaml
    from tools import get_tools
    cfg = yaml.safe_load(Path(fleet_config).read_text())
    return cfg, get_tools(cfg)


def _norm(ms, compact):
    out = []
    for m in ms:
        if m["role"] == "assistant":
            out.append(("assistant", m.get("reasoning") or m.get("reasoning_content"), m.get("content"),
                        [(tc["function"]["name"], H.compact_args(tc["function"]["arguments"]) if compact else tc["function"]["arguments"]) for tc in m.get("tool_calls") or []]))
        else:
            out.append((m["role"], m.get("content")))
    return out


def akash_prompt_tokens(messages, tools, effort) -> tuple[int, float]:
    key = os.environ["OPENROUTER_API_KEY"]
    body = {"model": "openai/gpt-oss-120b", "messages": messages, "tools": tools, "parallel_tool_calls": False, "max_tokens": 1, "reasoning": {"effort": effort},
            "provider": {"only": ["akashml/bf16"], "allow_fallbacks": False}, "usage": {"include": True}}
    req = urllib.request.Request("https://openrouter.ai/api/v1/chat/completions", data=json.dumps(body).encode(), headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    d = json.load(urllib.request.urlopen(req, timeout=180))
    return d["usage"]["prompt_tokens"], float(d["usage"].get("cost") or 0.0)


def f1() -> int:
    from dotenv import load_dotenv
    load_dotenv(C.REPO_ROOT / ".env")
    meter = C.spend_meter(); rows = []; ok = True
    for src in ma_run.sources():
        d = C.source_run_dir(src["source_run_id"])
        for point in ma_run.POINTS:
            T = ma_run.injection_turn(src, point)
            p = ma_run.build_prefix(d, T + 1)
            msgs = json.loads((Path(p["checkpoint_dir"]) / "messages.json").read_text())
            cfg, tools = _cfg_tools(p["fleet_config"]); effort = cfg["agent"]["reasoning_effort"]
            mine = len(H.render_prompt(msgs, tools, effort, p["conversation_date"]).tokens)
            rt = _norm(H.parse_prompt(H.render_history(msgs, tools, effort, p["conversation_date"])), False) == _norm(msgs, C.RENDERING == "rs1")
            theirs, cost = akash_prompt_tokens(msgs, tools, effort)
            meter.record_spend("stage0", f"f1_s2_{src['source_run_id'].replace('/', '_')}_{point}", cost)
            row = {"source_run_id": src["source_run_id"], "point": point, "checkpoint": Path(p["checkpoint_dir"]).name, "assistant_turns": sum(m["role"] == "assistant" for m in msgs),
                   "rendering": C.RENDERING, "akashml_prompt_tokens": theirs, "rendered_tokens": mine, "s2_match": theirs == mine, "s3_round_trip": rt, "cost_usd": cost}
            rows.append(row); ok &= row["s2_match"] and rt
            print(row, flush=True)
    OUT.mkdir(parents=True, exist_ok=True); (OUT / "f1_s2_s3.json").write_text(json.dumps(rows, indent=1))
    print("F1 (S2 token counts, S3 round trip):", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def f2() -> int:
    from dotenv import load_dotenv
    load_dotenv(C.REPO_ROOT / ".env")
    from rs_provider import FireworksHarmonyProvider
    src = ma_run.sources()[0]; d = C.source_run_dir(src["source_run_id"]); T = ma_run.injection_turn(src, "pre")
    p = ma_run.build_prefix(d, T + 1)
    msgs = json.loads((Path(p["checkpoint_dir"]) / "messages.json").read_text())
    cfg, tools = _cfg_tools(p["fleet_config"]); effort = cfg["agent"]["reasoning_effort"]
    text = ma_run.MESSAGES["counter"]
    injected = msgs + [{"role": "user", "content": text}]
    r = H.render_prompt(injected, tools, effort, p["conversation_date"])
    tail_ok = r.text.endswith(f"<|end|><|start|>user<|message|>{text}<|end|><|start|>assistant")
    out = OUT / "f2"; out.mkdir(parents=True, exist_ok=True)
    prov = FireworksHarmonyProvider(model=None, messages=injected, tools=tools, reasoning_effort=effort, conversation_date=p["conversation_date"], usage_log=out / "usage.jsonl")
    resp = prov.invoke()
    reply = (resp.reasoning or "") + "\n" + (resp.response or "")
    cost = sum(json.loads(l)["cost_usd_list"] for l in (out / "usage.jsonl").read_text().splitlines() if l.strip())
    C.spend_meter().record_spend("stage0", "f2_injected_user_turn", cost)
    last = prov.messages[-1]
    rec = {"source_run_id": src["source_run_id"], "rendering": C.RENDERING, "injection_after_turn": T, "prompt_tokens": len(r.tokens), "prompt_ends_with_user_then_assistant": tail_ok,
           "registers_message": W.registers_message("counter", [reply]), "verbal_update": W.verbal_update([reply]),
           "well_formed": bool(last.get("reasoning") or last.get("content")) and (bool(last.get("tool_calls")) or bool(last.get("content"))),
           "strict_parse_ok": last.get("rs_parse_strict_ok"), "finish_reason": last.get("rs_finish_reason"),
           "tool_call": [(tc["function"]["name"], tc["function"]["arguments"][:200]) for tc in last.get("tool_calls") or []],
           "reasoning": resp.reasoning, "content": resp.response, "cost_usd_list": cost}
    (out / "f2.json").write_text(json.dumps(rec, indent=1, ensure_ascii=False))
    ok = tail_ok and rec["registers_message"] and rec["well_formed"]
    print(json.dumps({k: v for k, v in rec.items() if k not in ("reasoning",)}, indent=1)[:1500])
    print("\nREASONING:\n" + (resp.reasoning or "")[:2500])
    print("\nF2:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


HOLDOUT = [  # (source run id, checkpoint step): runs NOT used to derive the source convention (see harmony_source.py)
    ("N0/run-12", 14), ("N0/run-24", 20), ("N0/run-3", 11), ("U0/run-11", 16), ("U0/run-27", 22), ("U0/run-5", 9),
]


def f1_holdout() -> int:
    """Out-of-sample test of the source convention: predictions are written to disk BEFORE the endpoint is queried."""
    import yaml
    from dotenv import load_dotenv
    from tools import get_tools
    import harmony_source
    load_dotenv(C.REPO_ROOT / ".env")
    harmony_source.apply(H)
    meter = C.spend_meter(); OUT.mkdir(parents=True, exist_ok=True); rows = []
    for sid, step in HOLDOUT:
        d = C.source_run_dir(sid); cfg = yaml.safe_load((d.parent / "config.yaml").read_text()); tools = get_tools(cfg)
        msgs = json.loads((d / f"step-{step}" / "messages.json").read_text()); date = d.parent.name[:10]; effort = cfg["agent"]["reasoning_effort"]
        args = [tc["function"]["arguments"] for m in msgs for tc in m.get("tool_calls") or []]
        def _compact(a):
            try:
                return json.dumps(json.loads(a)) == a
            except Exception:
                return None
        kinds = [_compact(a) for a in args]
        rt = _norm(H.parse_prompt(H.render_history(msgs, tools, effort, date)), False) == _norm(msgs, False)
        rows.append({"source_run_id": sid, "checkpoint": f"step-{step}", "assistant_turns": sum(m["role"] == "assistant" for m in msgs),
                     "tool_calls": len(args), "non_compact_args": kinds.count(False), "malformed_args": kinds.count(None),
                     "predicted_tokens": len(H.render_prompt(msgs, tools, effort, date).tokens), "s3_round_trip": rt, "_m": (msgs, tools, effort)})
    (OUT / "f1_holdout_predictions.json").write_text(json.dumps([{k: v for k, v in r.items() if k != "_m"} for r in rows], indent=1))
    ok = True
    for r in rows:
        msgs, tools, effort = r.pop("_m")
        r["akashml_prompt_tokens"], cost = akash_prompt_tokens(msgs, tools, effort); r["match"] = r["akashml_prompt_tokens"] == r["predicted_tokens"]; r["cost_usd"] = cost
        meter.record_spend("stage0", f"f1_holdout_{r['source_run_id'].replace('/', '_')}_{r['checkpoint']}", cost)
        ok &= r["match"] and r["s3_round_trip"]; print(r, flush=True)
    (OUT / "f1_holdout.json").write_text(json.dumps(rows, indent=1))
    print("F1 hold-out (source convention, unseen runs):", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit({"f1": f1, "f2": f2, "f1-holdout": f1_holdout}[sys.argv[1]]())
