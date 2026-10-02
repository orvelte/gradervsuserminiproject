#!/usr/bin/env python3
"""Upload SF1 runs to Docent with labels distinct from every existing arm (idempotent; --dry-run validates).

    python structural_framing/scripts/upload_sf.py results/structural_framing/SF1-G-LAX [...] [--dry-run] [--print-sample N]

Reuses scripts/upload_to_docent.py by import (transcript conversion, AgentRun building, manifest handling)
and overrides: the manifest file (results/structural_framing/docent_manifest.json), the target collection
(DOCENT_COLLECTION_ID_SF if set in .env, else DOCENT_COLLECTION_ID), and the metadata, which gains
experiment=structural_framing_v1, condition_id SF1-*, framing graded_structural/collaborator_structural,
grader_info, injection_steps, source_config_hash and every final/sf_metrics.json field. No Docent LLM features.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "analysis"))
import upload_to_docent as U  # noqa: E402
from common import find_run_dirs, load_run, upstream_sha  # noqa: E402

U.MANIFEST = REPO_ROOT / "results" / "structural_framing" / "docent_manifest.json"


def sf_agent_run(run: dict, sha: str | None):
    ar = U.build_agent_run(run, sha)
    final = run["run_dir"] / "final"
    cond = (run["condition"].get("condition") or {})
    sfm = json.loads((final / "sf_metrics.json").read_text()) if (final / "sf_metrics.json").exists() else {}
    sfr = json.loads((final / "sf_run.json").read_text()) if (final / "sf_run.json").exists() else {}
    extra = {
        "experiment": "structural_framing_v1",
        "condition_id": cond.get("id") or run["condition"].get("condition_id"),
        "framing": cond.get("framing"), "grader_info": cond.get("grader_info"),
        "injection_steps": cond.get("injection_steps") or sfr.get("injection_steps"),
        "source_config": cond.get("source_config"), "source_config_hash": cond.get("source_config_hash"),
        "oversight": None,  # not an original-2x2 arm; never pooled with them
        "sf_seed_n_commits": (sfr.get("seed") or {}).get("n_commits"), "sf_injections_fired": sfr.get("injections_fired"),
    }
    for k, v in sfm.items():
        if k == "decision_window" and isinstance(v, dict):
            extra.update({f"sf_window_{kk}": vv for kk, vv in v.items()})
        elif k in ("question_texts", "workaround_labels", "commits_beyond_seed", "injections_fired"):
            extra[f"sf_{k}"] = json.dumps(v)
        else:
            extra[f"sf_{k}"] = v
    ar.metadata.update({k: v for k, v in extra.items() if v is not None})
    ar.metadata.pop("oversight", None)
    ar.name = f"{extra['condition_id']} {run['run_dir'].parent.name}/{run['run_dir'].name} — {sfm.get('tier') or ar.metadata.get('primary_outcome')}"
    return ar


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--print-sample", type=int, default=0)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--include-smoke", action="store_true", help="only meaningful with --dry-run: validate on mock runs")
    args = ap.parse_args(argv)
    from dotenv import load_dotenv
    load_dotenv(REPO_ROOT / ".env")
    from docent.data_models.chat import check_agent_runs, format_check_report
    if args.include_smoke and not args.dry_run:
        print("--include-smoke is only allowed with --dry-run", file=sys.stderr); return 2
    run_dirs = [d for d in find_run_dirs(args.paths) if "structural_framing" in str(d) and (args.include_smoke or "/smoke/" not in str(d))]
    if not run_dirs:
        print("no SF1 runs found under", args.paths, file=sys.stderr); return 2
    missing = [d for d in run_dirs if not (d / "final" / "sf_metrics.json").exists()]
    if missing:
        print(f"{len(missing)} run(s) lack final/sf_metrics.json; run structural_framing/analysis/sf_metrics.py first", file=sys.stderr); return 2
    sha = upstream_sha()
    runs = [load_run(d) for d in run_dirs]
    manifest = U.load_manifest()
    collection_id = os.getenv("DOCENT_COLLECTION_ID_SF") or os.getenv("DOCENT_COLLECTION_ID")
    pending = []
    for run in runs:
        key = U.run_key(run)
        if not args.force and not args.dry_run and manifest["uploads"].get(key, {}).get("collection_id") == collection_id:
            continue
        pending.append((run, sf_agent_run(run, sha)))
    print(f"runs: {len(runs)}; to upload: {len(pending)}; collection: {collection_id} "
          f"({'DOCENT_COLLECTION_ID_SF' if os.getenv('DOCENT_COLLECTION_ID_SF') else 'DOCENT_COLLECTION_ID'})")
    if not pending:
        return 0
    print(format_check_report(check_agent_runs([ar for _, ar in pending])))
    for _, ar in pending[: args.print_sample]:
        U.print_sample(ar)
    for _, ar in pending:
        ar.model_dump_json()
        for k in ("experiment", "condition_id", "framing", "grader_info", "injection_steps", "source_config_hash"):
            assert k in ar.metadata, f"metadata missing {k}"
        assert ar.metadata["framing"] in ("graded_structural", "collaborator_structural")
    if args.dry_run:
        print(f"dry run: {len(pending)} valid AgentRun objects; nothing uploaded"); return 0
    if not os.getenv("DOCENT_API_KEY") or not collection_id:
        print("DOCENT_API_KEY / collection id missing", file=sys.stderr); return 2
    from docent import Docent
    client = Docent(api_key=os.environ["DOCENT_API_KEY"])
    result = client.add_agent_runs(collection_id, [ar for _, ar in pending])
    print("add_agent_runs ->", json.dumps(result, default=str)[:300])
    for run, ar in pending:
        manifest["uploads"][U.run_key(run)] = {"collection_id": collection_id, "agent_run_id": ar.id,
                                               "uploaded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    U.save_manifest(manifest)
    print(f"recorded {len(pending)} upload(s) in {U.MANIFEST.relative_to(REPO_ROOT)}; collection id: {collection_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
