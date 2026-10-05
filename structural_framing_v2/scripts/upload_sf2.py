#!/usr/bin/env python3
"""Upload SF2 runs to their OWN Docent collection (idempotent; --dry-run validates without uploading).

    python structural_framing_v2/scripts/upload_sf2.py --create-collection "structural-framing-v2"     # once
    python structural_framing_v2/scripts/upload_sf2.py results/structural_framing_v2/uptake [--dry-run] [--force]

The collection id is stored in results/structural_framing_v2/docent_collection.json and is the only target this
script ever uses: it never falls back to DOCENT_COLLECTION_ID, so SF2 traces cannot land in the collection that
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

RESULTS = REPO_ROOT / "results" / "structural_framing_v2"
COLLECTION_FILE = RESULTS / "docent_collection.json"
U.MANIFEST = RESULTS / "docent_manifest.json"
MARK = "⟂ INJECTED BY THE ENVIRONMENT ({name}) ⟂  "


def sf2_agent_run(run: dict, sha):
    final = run["run_dir"] / "final"
    sf = json.loads((final / "sf_run.json").read_text())
    cond = sf.get("condition") or {}
    texts = {v: k for k, v in (sf.get("injection_texts") or {}).items()}
    acks = {r.get("ack") for r in sf.get("replies") or []}
    for m in run["messages"][2:]:
        if m.get("role") == "user" and isinstance(m.get("content"), str):
            name = texts.get(m["content"]) or ("reply acknowledgement" if m["content"] in acks else None)
            if name:
                m["content"] = MARK.format(name=name) + m["content"]
    ar = U.build_agent_run(run, sha)
    inj = {i["name"]: i for i in sf.get("injections") or []}
    ar.metadata.pop("oversight", None)
    ar.metadata.update({k: v for k, v in {
        "experiment": "structural_framing_v2", "condition_id": cond.get("id"), "framing": cond.get("framing"), "grader_info": cond.get("grader_info"),
        "batch": cond.get("batch"), "source_config_hash": cond.get("source_config_hash"),
        "sf2_wall_message_after_step": inj.get("wall", {}).get("after_step"), "sf2_wall_message_trigger": inj.get("wall", {}).get("trigger"),
        "sf2_followup_after_step": inj.get("followup", {}).get("after_step"), "sf2_wall_step": sf.get("wall_step"),
        "sf2_n_replies": sf.get("n_replies"), "sf2_n_questions": sf.get("n_questions"), "sf2_question_texts": json.dumps([q.get("question") for q in sf.get("questions") or []]),
        "sf2_no_commit_reason": sf.get("no_commit_reason_sf2"), "sf2_seed_n_commits": (sf.get("seed") or {}).get("n_commits"),
    }.items() if v is not None})
    ar.name = f"{cond.get('id')} [{cond.get('batch')}] {run['run_dir'].parent.name}/{run['run_dir'].name} — {ar.metadata.get('primary_outcome')}"
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
        cid = Docent(api_key=os.environ["DOCENT_API_KEY"]).create_collection(name=a.create_collection, description="Structural framing v2 (SF2) rollouts on precommit_hook; separate from the 2x2 / SF1 / RS1 / follow-up collection")
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
        print("no SF2 collection yet: run with --create-collection NAME first", file=sys.stderr); return 2
    if cid and cid == os.getenv("DOCENT_COLLECTION_ID"):
        print("refusing: the SF2 collection id equals DOCENT_COLLECTION_ID", file=sys.stderr); return 2
    run_dirs = sorted(p.parent for path in a.paths for p in Path(path).glob("**/run-*/final") if (p / "sf_run.json").exists() and (p / "score.json").exists() and "/smoke/" not in str(p))
    manifest = U.load_manifest(); sha = upstream_sha(); pending = []
    for d in run_dirs:
        key = "sf2:" + str(d.resolve().relative_to(REPO_ROOT))
        if a.force or a.dry_run or manifest["uploads"].get(key, {}).get("collection_id") != cid:
            pending.append((key, sf2_agent_run(load_run(d), sha)))
    print(f"runs found: {len(run_dirs)}  to upload: {len(pending)}  collection: {cid}")
    if not pending:
        return 0
    print(format_check_report(check_agent_runs([ar for _, ar in pending])))
    if a.dry_run:
        k, ar = pending[0]; print("dry run; first:", ar.name, {x: ar.metadata.get(x) for x in ("experiment", "condition_id", "batch", "sf2_wall_message_trigger")}); return 0
    Docent(api_key=os.environ["DOCENT_API_KEY"]).add_agent_runs(cid, [ar for _, ar in pending])
    for k, ar in pending:
        manifest["uploads"][k] = {"collection_id": cid, "agent_run_id": ar.id, "uploaded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    U.save_manifest(manifest); print(f"uploaded {len(pending)} to https://docent.transluce.org/dashboard/{cid}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
