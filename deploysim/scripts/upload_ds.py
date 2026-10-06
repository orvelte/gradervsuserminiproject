#!/usr/bin/env python3
"""Upload DS runs to their OWN Docent collection (idempotent; --dry-run validates without uploading).

    python deploysim/scripts/upload_sf2.py --create-collection "structural-framing-v2"     # once
    python deploysim/scripts/upload_sf2.py results/deploysim/uptake [--dry-run] [--force]

The collection id is stored in results/deploysim/docent_collection.json and is the only target this
script ever uses: it never falls back to DOCENT_COLLECTION_ID, so DS traces cannot land in the collection that
holds the 2×2, SF1, RS1 and follow-up runs. Reuses scripts/upload_to_docent.py by import. Injected user turns are
marked in the transcript so a reader can tell them from the prompt.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts")); sys.path.insert(0, str(REPO_ROOT / "analysis"))
import upload_to_docent as U  # noqa: E402
from common import load_run, upstream_sha  # noqa: E402

RESULTS = REPO_ROOT / "results" / "deploysim"
COLLECTION_FILE = REPO_ROOT / "results" / "structural_framing_v2" / "docent_collection.json"   # the same separate collection as SF2 (never the main one)
U.MANIFEST = RESULTS / "docent_manifest.json"
MARK = "⟂ SEEDED PRIOR TURN (part of the environment, not sampled) ⟂  "


def ds_agent_run(run: dict, sha):
    final = run["run_dir"] / "final"
    sf = json.loads((final / "sf_run.json").read_text())
    cond = sf.get("condition") or {}
    for t in sf.get("prior_turns") or []:
        for m in run["messages"]:
            if m.get("role") == t["role"] and m.get("content") == t["content"]:
                m["content"] = MARK + m["content"]; break
    ar = U.build_agent_run(run, sha)
    inj = {i["name"]: i for i in sf.get("injections") or []}
    ar.metadata.pop("oversight", None)
    ar.metadata.update({k: v for k, v in {
        "experiment": "deploysim", "ds_framing": sf.get("sf_framing"), "condition_id": cond.get("id"), "framing": cond.get("framing"), "grader_info": cond.get("grader_info"),
        "batch": cond.get("batch"), "env_version": sf.get("env_version") or cond.get("env_version") or "2.0", "source_config_hash": cond.get("source_config_hash"),
        "ds_prior_turns": len(sf.get("prior_turns") or []), "ds_empty_turns": json.dumps(sf.get("empty_turns") or []), "ds_n_questions": sf.get("n_questions"), "ds_question_texts": json.dumps([q.get("question") for q in sf.get("questions") or []]),
        "ds_no_commit_reason": sf.get("no_commit_reason_sf2"), "ds_seed_n_commits": (sf.get("seed") or {}).get("n_commits"),
    }.items() if v is not None})
    ar.name = f"{cond.get('id')} [{cond.get('batch')}, v{sf.get('env_version') or '2.0'}] {run['run_dir'].parent.name}/{run['run_dir'].name} — {ar.metadata.get('primary_outcome')}"
    return ar


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="*"); ap.add_argument("--dry-run", action="store_true"); ap.add_argument("--force", action="store_true")
    ap.add_argument("--create-collection", metavar="NAME")
    a = ap.parse_args(argv)
    from dotenv import load_dotenv
    load_dotenv(REPO_ROOT / ".env")
    from docent import Docent
    from docent.data_models.chat import check_agent_runs, format_check_report
    if a.create_collection:
        if COLLECTION_FILE.exists():
            print("a collection is already recorded:", COLLECTION_FILE.read_text().strip()); return 2
        cid = Docent(api_key=os.environ["DOCENT_API_KEY"]).create_collection(name=a.create_collection, description="Deployment simulation (DS) rollouts on precommit_hook; separate from the 2x2 / SF1 / RS1 / follow-up collection")
        assert cid != os.getenv("DOCENT_COLLECTION_ID")
        RESULTS.mkdir(parents=True, exist_ok=True)
        COLLECTION_FILE.write_text(json.dumps({"collection_id": cid, "name": a.create_collection, "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}, indent=1) + "\n")
        print(f"created collection {cid} named {a.create_collection!r}: https://docent.transluce.org/dashboard/{cid}")
        if not a.paths:
            return 0
    if not a.paths:
        ap.print_usage(); return 2
    cid = json.loads(COLLECTION_FILE.read_text())["collection_id"] if COLLECTION_FILE.exists() else None
    if not cid and not a.dry_run:
        print("no DS collection yet: run with --create-collection NAME first", file=sys.stderr); return 2
    if cid and cid == os.getenv("DOCENT_COLLECTION_ID"):
        print("refusing: the DS collection id equals DOCENT_COLLECTION_ID", file=sys.stderr); return 2
    run_dirs = sorted(p.parent for path in a.paths for p in Path(path).glob("**/run-*/final") if (p / "sf_run.json").exists() and (p / "score.json").exists() and "/smoke/" not in str(p))
    manifest = U.load_manifest(); sha = upstream_sha(); pending = []
    for d in run_dirs:
        key = "ds:" + str(d.resolve().relative_to(REPO_ROOT))
        if a.force or a.dry_run or manifest["uploads"].get(key, {}).get("collection_id") != cid:
            pending.append((key, ds_agent_run(load_run(d), sha)))
    print(f"runs found: {len(run_dirs)}  to upload: {len(pending)}  collection: {cid}")
    if not pending:
        return 0
    print(format_check_report(check_agent_runs([ar for _, ar in pending])))
    if a.dry_run:
        k, ar = pending[0]; print("dry run; first:", ar.name, {x: ar.metadata.get(x) for x in ("experiment", "condition_id", "batch", "ds_framing")}); return 0
    Docent(api_key=os.environ["DOCENT_API_KEY"]).add_agent_runs(cid, [ar for _, ar in pending])
    for k, ar in pending:
        manifest["uploads"][k] = {"collection_id": cid, "agent_run_id": ar.id, "uploaded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    U.save_manifest(manifest); print(f"uploaded {len(pending)} to https://docent.transluce.org/dashboard/{cid}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
