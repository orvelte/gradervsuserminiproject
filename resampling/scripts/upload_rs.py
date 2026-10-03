#!/usr/bin/env python3
"""Upload RS1 continuations to Docent (idempotent, --dry-run). Labels: experiment=resampling_v1, condition, source_run_id,
source_arm, prefix_turn, resample_idx, prefill_sentence, stage, plus rs_metrics fields. The prefill turn's reasoning
is split so the transcript shows `[inherited prefix …] ⟂ [sampled continuation …]`."""
from __future__ import annotations

import argparse, json, os, sys, time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts")); sys.path.insert(0, str(REPO_ROOT / "analysis"))
import upload_to_docent as U  # noqa: E402
from common import load_run, upstream_sha  # noqa: E402

U.MANIFEST = REPO_ROOT / "results" / "resampling" / "docent_manifest.json"
MARK = "\n\n⟂⟂⟂ END OF INHERITED PREFIX (copied from the source run) — everything below was sampled in this continuation ⟂⟂⟂\n\n"


def main(argv=None):
    ap = argparse.ArgumentParser(); ap.add_argument("dirs", nargs="+"); ap.add_argument("--dry-run", action="store_true"); ap.add_argument("--force", action="store_true")
    a = ap.parse_args(argv)
    from dotenv import load_dotenv; load_dotenv(REPO_ROOT / ".env")
    from docent.data_models.chat import check_agent_runs, format_check_report
    jobs = [p for d in a.dirs for p in sorted(Path(d).iterdir()) if (p / "final" / "rs_metrics.json").exists()]
    sha = upstream_sha(); manifest = U.load_manifest(); cid = os.getenv("DOCENT_COLLECTION_ID_RS") or os.getenv("DOCENT_COLLECTION_ID")
    pending = []
    for job in jobs:
        key = f"resampling:{job.parent.name}/{job.name}"
        if not a.force and not a.dry_run and manifest["uploads"].get(key, {}).get("collection_id") == cid:
            continue
        run = load_run(job)
        msgs = run["messages"]
        for m in msgs:
            if m.get("role") == "assistant" and "rs_prefill_chars" in m:
                k = m["rs_prefill_chars"]; r = m.get("reasoning") or ""
                m["reasoning"] = m["reasoning_content"] = r[:k] + MARK + r[k:]
        ar = U.build_agent_run(run, sha)
        rm = json.loads((job / "final" / "rs_metrics.json").read_text()); task = json.loads((job / "rs_task.json").read_text())
        meta = {"experiment": "resampling_v1", "condition": task["condition"], "source_run_id": task["source_run_id"], "source_arm": task["source_arm"],
                "prefix_turn": task["prefix_turn"], "resample_idx": task["resample_idx"], "prefill_sentence": task.get("prefill_sentence") or "", "stage": task.get("stage"),
                "sentence_kind": task.get("sentence_kind"), "provider_used": "fireworks completions gpt-oss-120b (raw Harmony prefill)"}
        meta.update({f"rs_{k}": (json.dumps(v) if isinstance(v, (dict, list)) else v) for k, v in rm.items() if v is not None})
        ar.metadata.pop("condition_id", None); ar.metadata.pop("oversight", None); ar.metadata.update(meta)
        ar.name = f"RS1 {task['condition']} {task['source_run_id']} t{task['prefix_turn']} #{task['resample_idx']} — {rm['tier']}"
        pending.append((key, ar))
    print(f"jobs {len(jobs)}, to upload {len(pending)}, collection {cid}")
    if not pending: return 0
    print(format_check_report(check_agent_runs([ar for _, ar in pending])))
    if a.dry_run: print("dry run"); return 0
    from docent import Docent
    client = Docent(api_key=os.environ["DOCENT_API_KEY"]); client.add_agent_runs(cid, [ar for _, ar in pending])
    for key, ar in pending:
        manifest["uploads"][key] = {"collection_id": cid, "agent_run_id": ar.id, "uploaded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    U.save_manifest(manifest); print(f"uploaded {len(pending)}"); return 0


if __name__ == "__main__":
    sys.exit(main())
