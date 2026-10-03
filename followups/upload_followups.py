#!/usr/bin/env python3
"""Upload follow-up pilot samples to Docent (idempotent; --dry-run builds and validates without uploading).

    python followups/upload_followups.py a [--dry-run] [--force]     # momentum: results/followups/momentum_a/<job>/
    python followups/upload_followups.py b [--dry-run] [--force]     # spillover: results/followups/spillover_b/<job>/

Labels (from the task spec): experiment = momentum_a_pilot | spillover_b_pilot, source_run_id, condition,
injection_point (A) / prefix_type (B), sample_idx; plus the per-sample metrics. Reuses the repo's Docent builder
(scripts/upload_to_docent.py) by import. Manifest: results/followups/docent_manifest.json.

Transcripts are marked where inherited history ends: A carries a marker in the injected user message, B in the poll
message, so a reader can tell what was copied from the source run and what was sampled here."""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent


def _load(name: str, path: Path):
    import importlib.util
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec); sys.modules[name] = m; spec.loader.exec_module(m)
    return m


# Two modules are called `common` (followups/common.py and analysis/common.py). The repo's Docent builder imports the
# analysis one by that name, so it is bound to `common` only while the builder is imported, then the name is restored.
C = sys.modules.get("common") if getattr(sys.modules.get("common"), "RS1_RESULTS", None) else _load("fu_common", HERE / "common.py")
_prev = sys.modules.pop("common", None)
AC = _load("common", REPO_ROOT / "analysis" / "common.py")
sys.path.insert(0, str(REPO_ROOT / "scripts"))
import upload_to_docent as U  # noqa: E402
if _prev is not None:
    sys.modules["common"] = _prev
else:
    sys.modules.pop("common", None)

U.MANIFEST = C.RESULTS / "docent_manifest.json"
MARK_A = "⟂⟂⟂ INJECTED BY THE EXPERIMENT (momentum pilot, {condition}, {point}). Everything above is copied from the source run; everything below was sampled in this continuation ⟂⟂⟂\n\n"
MARK_B = "⟂⟂⟂ POLL APPENDED BY THE EXPERIMENT (spillover pilot, prefix {prefix}). Everything above is the prefix; only the single reply below was sampled ⟂⟂⟂\n\n"


def _flat(d: dict, prefix: str) -> dict:
    return {f"{prefix}{k}": (json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v) for k, v in d.items() if v is not None}


def runs_a(sha):
    root = C.RESULTS / "momentum_a"
    for job in sorted(p for p in root.iterdir() if (p / "final" / "ma_metrics.json").exists()) if root.exists() else []:
        task = json.loads((job / "rs_task.json").read_text()); mm = json.loads((job / "final" / "ma_metrics.json").read_text())
        run = AC.load_run(job); msgs = run["messages"]; n = 0
        for m in msgs:
            if m.get("role") == "user" and m.get("content") == task["inject_user_message"]:
                m["content"] = MARK_A.format(condition=task["condition"], point=task["injection_point"]) + m["content"]; n += 1
        assert n == 1, (job.name, "injected message found", n, "times")
        ar = U.build_agent_run(run, sha)
        ar.metadata.pop("condition_id", None); ar.metadata.pop("oversight", None)
        ar.metadata.update({"experiment": task["experiment"], "source_run_id": task["source_run_id"], "source_arm": task["source_arm"], "condition": task["condition"],
                            "injection_point": task["injection_point"], "sample_idx": task["sample_idx"], "injection_after_turn": task["injection_after_turn"],
                            "t_inf": task["t_inf"], "t_commit": task["t_commit"], "workaround_kind": task["workaround_kind"], "injected_message": task["inject_user_message"],
                            "history_convention": task.get("history_convention", "rs1"), "provider_used": "fireworks completions gpt-oss-120b (raw Harmony)", **_flat(mm, "ma_")})
        ar.name = f"A {task['injection_point']}/{task['condition']} {task['source_run_id']} #{task['sample_idx']} — {mm.get('tier')}"
        yield f"followups:momentum_a/{job.name}", ar


def runs_b(sha):
    jobs = [(d, p) for d in ("spillover_b", "spillover_b_trait") if (C.RESULTS / d).exists() for p in sorted((C.RESULTS / d).iterdir()) if (p / "reply.json").exists()]
    for sub, job in jobs:
        rec = json.loads((job / "reply.json").read_text()); msgs = json.loads((job / "messages.json").read_text())
        polls = [m for m in msgs if m.get("role") == "user" and m.get("content") == rec["probe"]]
        assert len(polls) == 1, (job.name, len(polls))
        polls[0]["content"] = MARK_B.format(prefix=rec["prefix_type"]) + polls[0]["content"]
        score = {"primary_outcome": "poll_reply", "n_steps": 1}
        ar = U.build_agent_run({"run_dir": job, "score": score, "condition": {}, "messages": msgs, "episode_end": {}}, sha)
        keep = {k: v for k, v in rec.items() if k not in ("probe", "reply", "reasoning", "experiment", "source_run_id", "prefix_type", "sample_idx", "job_id")}
        ar.metadata = {k: v for k, v in ar.metadata.items() if k in ("upstream_sha", "run_dir", "n_assistant_turns")}
        ar.metadata.update({"experiment": rec["experiment"], "source_run_id": rec["source_run_id"], "source_arm": rec["source_arm"], "condition": rec["prefix_type"],
                            "prefix_type": rec["prefix_type"], "probe_set": rec.get("probe_set", "fallback"), "sample_idx": rec["sample_idx"], "provider_used": "fireworks completions gpt-oss-120b (raw Harmony)", **_flat(keep, "sb_")})
        ar.name = f"B[{rec.get('probe_set', 'fallback')}] {rec['prefix_type']} {rec['source_run_id']} #{rec['sample_idx']} — exploit {rec.get('exploit_score')}"
        ar.description = f"poll reply after prefix {rec['prefix_type']}; parsed={rec.get('parsed')} non_answer={rec.get('non_answer')} eval_talk={rec.get('eval_talk')}"
        yield f"followups:{sub}/{job.name}", ar


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("which", choices=["a", "b"]); ap.add_argument("--dry-run", action="store_true"); ap.add_argument("--force", action="store_true")
    a = ap.parse_args(argv)
    from dotenv import load_dotenv
    load_dotenv(C.REPO_ROOT / ".env")
    from docent.data_models.chat import check_agent_runs, format_check_report
    sha = AC.upstream_sha(); manifest = U.load_manifest(); cid = os.getenv("DOCENT_COLLECTION_ID")
    pending = [(k, ar) for k, ar in (runs_a if a.which == "a" else runs_b)(sha)
               if a.force or a.dry_run or manifest["uploads"].get(k, {}).get("collection_id") != cid]
    print(f"to upload: {len(pending)}")
    if not pending:
        return 0
    print(format_check_report(check_agent_runs([ar for _, ar in pending])))
    if a.dry_run:
        k, ar = pending[0]; print("dry run; first:", ar.name, json.dumps({x: ar.metadata.get(x) for x in ("experiment", "source_run_id", "condition", "injection_point", "prefix_type", "sample_idx")}))
        return 0
    from docent import Docent
    Docent(api_key=os.environ["DOCENT_API_KEY"]).add_agent_runs(cid, [ar for _, ar in pending])
    for k, ar in pending:
        manifest["uploads"][k] = {"collection_id": cid, "agent_run_id": ar.id, "uploaded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    U.save_manifest(manifest); print(f"uploaded {len(pending)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
