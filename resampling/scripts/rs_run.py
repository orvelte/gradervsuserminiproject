#!/usr/bin/env python3
"""Host launcher for RS1 containers (build the resampling image, run verify/score/continue jobs, meter spend).

    python resampling/scripts/rs_run.py build
    python resampling/scripts/rs_run.py verify <source_run_dir> [--turn T]        # S5: restore + replay the turn-t call
    python resampling/scripts/rs_run.py score  <source_run_dir>                   # S6: score the final checkpoint
    python resampling/scripts/rs_run.py continue <plan.json> [--max-concurrent N] [--budget USD]
        plan.json: {"stage": "...", "jobs": [{"job_id", "source_run_dir", "prefix_turn", "condition", "resample_idx",
                                               "prefill", "prefill_sentence", "sentence_kind"}, ...]}
Outputs: results/resampling/<stage>/<job_id>/ (rollout.log, step-*, final/). Spend: resampling/spend.json.
The image is built from a snapshot of the current tree (env_registry.launch_context), like scripts/run.py.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(HERE))
import env_registry  # noqa: E402
import run_common  # noqa: E402
from run import CONTAINER_CMD, _exported_keys_file, docker_argv  # noqa: E402
from rs_prefix import build as build_prefix  # noqa: E402

ENV = "precommit_hook"
DOCKERFILE = "resampling/env/Dockerfile"
RESULTS = REPO_ROOT / "results" / "resampling"
SPEND = REPO_ROOT / "resampling" / "spend.json"
TAG_FILE = RESULTS / "image_tag.txt"
_lock = threading.Lock()


def build_image(docker: list[str]) -> str:
    context, commit = env_registry.launch_context(REPO_ROOT)
    task = {"target_errors": 258}
    run_common.prepare_build_context(context, ENV, task)
    tag = f"agent-interp-envs/precommit_hook_rs:{commit[:12]}"
    print(f"Building {tag} from {DOCKERFILE} at {commit[:12]} ...", flush=True)
    subprocess.run([*docker, "build", "-f", str(Path(context) / DOCKERFILE), "-t", tag, context], check=True)
    RESULTS.mkdir(parents=True, exist_ok=True); TAG_FILE.write_text(tag + "\n")
    return tag


def image_tag() -> str:
    if not TAG_FILE.exists():
        raise SystemExit("no image: run `rs_run.py build` first")
    return TAG_FILE.read_text().strip()


def run_container(docker, tag, config_path: Path, checkpoint: Path | None, blobs: Path | None, task_path: Path, out_dir: Path, timeout=86400, network=None) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = [*docker, "run", "--rm", "--init", "-e", f"HOST_UID={os.getuid()}", "-e", f"HOST_GID={os.getgid()}",
           "-v", f"{config_path}:/opt/config.yaml:ro", "-v", f"{task_path}:/opt/rs_task.json:ro", "-v", f"{out_dir}:/opt/output"]
    if checkpoint is not None:
        cmd += ["-v", f"{checkpoint}:/opt/checkpoint:ro"]
    if blobs is not None and blobs.is_dir():
        cmd += ["-v", f"{blobs}:/opt/blobs:ro"]
    env_file = REPO_ROOT / ".env"
    if env_file.is_file():
        cmd += ["--env-file", str(env_file)]
    kf = _exported_keys_file()
    if kf:
        cmd += ["--env-file", kf]
    if network:
        cmd += ["--network", network]
    cmd += [tag, "bash", "-c", CONTAINER_CMD]
    with open(out_dir / "rollout.log", "w") as log:
        p = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT)
        try:
            return p.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            p.kill(); return 124


def job_cost(out_dir: Path) -> float:
    u = out_dir / "final" / "usage.jsonl"
    if not u.exists():
        return 0.0
    return sum(json.loads(l)["cost_usd_list"] for l in u.read_text().splitlines() if l.strip())


def record_spend(stage: str, job_id: str, cost: float) -> dict:
    with _lock:
        s = json.loads(SPEND.read_text()) if SPEND.exists() else {"total_usd_list_price": 0.0, "by_stage": {}, "jobs": {}}
        s["jobs"][job_id] = {"stage": stage, "cost_usd_list": round(cost, 5), "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        s["by_stage"][stage] = round(s["by_stage"].get(stage, 0.0) + cost, 5)
        s["total_usd_list_price"] = round(sum(j["cost_usd_list"] for j in s["jobs"].values()), 5)
        SPEND.write_text(json.dumps(s, indent=1))
        return s


def total_spend() -> float:
    return json.loads(SPEND.read_text())["total_usd_list_price"] if SPEND.exists() else 0.0


def host_tree(checkpoint: Path, run_dir: Path) -> dict:
    """Expected workspace (non-.git) hashes: pristine src_258 + pyproject with the checkpoint's manifest applied."""
    import gzip, hashlib
    pristine = REPO_ROOT / "environments" / "precommit_hook"
    files: dict[str, tuple[int, bytes]] = {}
    for f in (pristine / "src_258").iterdir():
        if f.is_file():
            files[f"src/{f.name}"] = (0o644, f.read_bytes())
    files["pyproject.toml"] = (0o644, (pristine / "pyproject.toml").read_bytes())
    man = json.loads((checkpoint / "fs" / "manifest.json").read_text())
    for e in man["entries"]:
        path = e["path"]
        if not path.startswith("/agent/") or "/.git/" in path:
            continue
        rel = path[len("/agent/"):]
        if e["action"] == "delete":
            files.pop(rel, None)
        elif e["action"] == "write":
            blob = run_dir / "blobs" / f"{e['blob']}.gz"
            data = gzip.decompress(blob.read_bytes()) if blob.exists() else (checkpoint / "fs" / "blobs" / e["blob"]).read_bytes()
            files[rel] = (e.get("mode", 0o644), data)
    return {rel: hashlib.sha256(data).hexdigest() for rel, (mode, data) in files.items()}  # content only; modes reported separately


def cmd_verify(args):
    src = Path(args[0]).resolve(); turn = int(args[args.index("--turn") + 1]) if "--turn" in args else None
    p = build_prefix(src, turn)
    out = RESULTS / "verify" / f"{p['source_run_id'].replace('/', '_')}_t{p['prefix_turn']}"
    task = {"mode": "verify", **{k: p[k] for k in ("source_run_id", "source_arm", "prefix_turn", "conversation_date", "turn_tool_calls", "turn_tool_result", "init_commit")}}
    tp = out / "rs_task.json"; out.mkdir(parents=True, exist_ok=True); tp.write_text(json.dumps(task, indent=1))
    rc = run_container(docker_argv("docker"), image_tag(), Path(p["fleet_config"]), Path(p["checkpoint_dir"]), src / "blobs", tp, out, network="none")
    v = json.loads((out / "final" / "verify.json").read_text()) if (out / "final" / "verify.json").exists() else None
    if v:
        exp = host_tree(Path(p["checkpoint_dir"]), src)
        got = {k: h.split(":")[0] for k, h in v["tree_hashes"].items() if not k.startswith(".git/")}
        same = set(exp) == set(got) and all(exp[k] == got[k] for k in exp)
        v["git_files_restored"] = sum(1 for k in v["tree_hashes"] if k.startswith(".git/"))
        v["workspace_tree_matches_host_reconstruction"] = same
        v["workspace_files"] = len(exp)
        if not same:
            v["tree_diff"] = {"only_host": sorted(set(exp) - set(got))[:10], "only_container": sorted(set(got) - set(exp))[:10], "hash_differs": [k for k in exp if k in got and exp[k] != got[k]][:10]}
        (out / "final" / "verify.json").write_text(json.dumps(v, indent=1))
    print(f"rc={rc} verify={ {k: v2 for k, v2 in (v or {}).items() if k not in ('tree_hashes', 'got', 'expected', 'replayed_call')} }")
    if v and not v["tool_output_matches"]:
        print("EXPECTED:", (v["expected"] or "")[:800]); print("GOT:", (v["got"] or "")[:800])
    return 0 if v and v["tool_output_matches"] and v.get("workspace_tree_matches_host_reconstruction") else 1


def cmd_score(args):
    src = Path(args[0]).resolve()
    steps = sorted(src.glob("step-*"), key=lambda p: int(p.name.split("-")[1]))
    last = steps[-1]
    out = RESULTS / "score" / src.parent.parent.parent.parent.name + "_" + src.name if False else RESULTS / "score" / f"{src.parent.parent.parent.parent.name}_{src.name}"
    task = {"mode": "score", "source_run_id": f"{src.parent.parent.parent.parent.name}/{src.name}", "init_commit": build_prefix(src, 2)["init_commit"]}
    tp = out / "rs_task.json"; out.mkdir(parents=True, exist_ok=True); tp.write_text(json.dumps(task, indent=1))
    rc = run_container(docker_argv("docker"), image_tag(), src.parent / "config.yaml", last, src / "blobs", tp, out, network="none")
    a = json.loads((src / "final" / "score.json").read_text()); b = json.loads((out / "final" / "score.json").read_text())
    keys = ("primary_outcome", "workaround_labels", "commit_landed", "mypy_errors_committed_raw", "type_ignore_count_committed", "honest_on_errors", "hook_behavioral_check")
    diffs = {k: (a.get(k), b.get(k)) for k in keys if a.get(k) != b.get(k)}
    print(f"rc={rc} source={a['primary_outcome']}/{a.get('workaround_labels')} pipeline={b['primary_outcome']}/{b.get('workaround_labels')} diffs={diffs}")
    return 0 if not diffs else 1


def cmd_continue(args):
    plan = json.loads(Path(args[0]).read_text()); stage = plan["stage"]
    maxc = int(args[args.index("--max-concurrent") + 1]) if "--max-concurrent" in args else 3
    budget = float(args[args.index("--budget") + 1]) if "--budget" in args else None
    docker = docker_argv("docker"); tag = image_tag()
    jobs = plan["jobs"]
    print(f"stage {stage}: {len(jobs)} jobs, concurrency {maxc}, spend so far ${total_spend():.2f}, budget {budget}")

    def one(j):
        out = RESULTS / stage / j["job_id"]
        if (out / "final" / "score.json").exists():
            return j["job_id"], "skip (done)", job_cost(out)
        if budget is not None and total_spend() >= budget:
            return j["job_id"], "skipped: budget reached", 0.0
        p = build_prefix(Path(j["source_run_dir"]), j["prefix_turn"])
        task = {"mode": "continue", "prefill": j.get("prefill"), "prefill_sentence": j.get("prefill_sentence"), "sentence_kind": j.get("sentence_kind"),
                "condition": j["condition"], "resample_idx": j["resample_idx"], "stage": stage, "experiment": "resampling_v1",
                **{k: p[k] for k in ("source_run_id", "source_arm", "prefix_turn", "conversation_date", "sentence_S", "original_outcome", "original_labels", "original_n_steps", "init_commit")}}
        tp = out / "rs_task.json"; out.mkdir(parents=True, exist_ok=True); tp.write_text(json.dumps(task, indent=1))
        rc = run_container(docker, tag, Path(p["fleet_config"]), Path(p["checkpoint_dir"]) if p["checkpoint_dir"] else None, Path(j["source_run_dir"]) / "blobs", tp, out)
        c = job_cost(out); record_spend(stage, j["job_id"], c)
        return j["job_id"], f"rc={rc}", c
    with ThreadPoolExecutor(max_workers=maxc) as ex:
        for jid, status, c in ex.map(one, jobs):
            print(f"  {jid}: {status} cost=${c:.3f} total=${total_spend():.2f}", flush=True)
    return 0


def main(argv):
    if not argv:
        print(__doc__); return 2
    cmd, rest = argv[0], argv[1:]
    if cmd == "build":
        build_image(docker_argv("docker")); return 0
    return {"verify": cmd_verify, "score": cmd_score, "continue": cmd_continue}[cmd](rest)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
