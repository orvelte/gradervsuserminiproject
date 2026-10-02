#!/usr/bin/env python3
"""Re-score finished runs on the host from their last filesystem snapshot, without re-running anything.

    python scripts/rescore.py results/openai-gpt-oss-120b/N0            # every run under the path
    python scripts/rescore.py <run_dir> --dry-run                         # score, print, write nothing
    python scripts/rescore.py <run_dir> --keep-workspace /tmp/ws          # leave the rebuilt tree for a look

Why: the scorer runs inside the container at the end of a run, so a scorer fix made afterwards (a new
workaround label, a corrected rule) would otherwise need the runs re-bought. Every run's last step
checkpoint holds a cumulative manifest of the workspace's divergence from the pristine tree, .git included,
with the file contents in the run's blob store. This rebuilds the final workspace from the pristine
variant plus that manifest, recreates the harness's initial commit (its objects are content-addressed, so
the blobs and trees come back identical; the commit itself gets a new sha and is grafted in as the parent
of the agent's commits), then runs the same `score.score_run` the container runs, with the command
history from state.json and the transcript from final/messages.json.

The rescored file replaces final/score.json; the previous one is kept as final/score.v<N>.json. Differences
to the in-container score are reported. Host requirements: git, and the image's mypy version
(`mypy==1.20.2`, pinned in the dev dependency group) so error counts match.
"""

from __future__ import annotations

import argparse
import gzip
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ENV_DIR = REPO_ROOT / "environments" / "precommit_hook"
sys.path.insert(0, str(REPO_ROOT / "analysis"))
from common import find_run_dirs  # noqa: E402

_spec = importlib.util.spec_from_file_location("precommit_score", ENV_DIR / "score.py")
score = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(score)

GIT_ENV = {"GIT_AUTHOR_NAME": "Developer", "GIT_AUTHOR_EMAIL": "dev@example.com",
           "GIT_COMMITTER_NAME": "Developer", "GIT_COMMITTER_EMAIL": "dev@example.com"}


def _git(cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=check,
                          env={**os.environ, **GIT_ENV})


def last_step_dir(run_dir: Path) -> Path | None:
    steps = []
    for d in run_dir.glob("step-*"):
        try:
            steps.append((int(d.name.split("-")[1]), d))
        except ValueError:
            pass
    steps = [s for s in sorted(steps) if (s[1] / "fs" / "manifest.json").exists()]
    return steps[-1][1] if steps else None


def read_blob(run_dir: Path, step_dir: Path, blob: str) -> bytes:
    for cand in (run_dir / "blobs" / f"{blob}.gz", step_dir / "fs" / "blobs" / f"{blob}.gz", step_dir / "fs" / "blobs" / blob):
        if cand.exists():
            data = cand.read_bytes()
            return gzip.decompress(data) if cand.suffix == ".gz" else data
    raise FileNotFoundError(f"blob {blob} missing for {run_dir}")


def rebuild_workspace(run_dir: Path, dest: Path, target_errors: int) -> dict:
    """Pristine variant + initial commit + the last manifest's entries => the final /agent tree at `dest`."""
    step = last_step_dir(run_dir)
    if step is None:
        raise RuntimeError("no step checkpoint with an fs manifest")
    manifest = json.loads((step / "fs" / "manifest.json").read_text())
    ws = dest / "agent"
    (ws / "src").mkdir(parents=True)
    variant = ENV_DIR / f"src_{target_errors}"
    if not variant.is_dir():
        raise RuntimeError(f"pristine variant src_{target_errors} is not checked in; only src_0/258/602 are")
    for f in variant.iterdir():
        if f.is_file():
            shutil.copy(f, ws / "src" / f.name)
    shutil.copy(ENV_DIR / "pyproject.toml", ws / "pyproject.toml")
    # Use the branch name the container's git created (Debian git: master) so HEAD follows the ref the
    # manifest writes; the host's default may be main.
    heads = [e["path"].split("/.git/refs/heads/", 1)[1] for e in manifest["entries"] if "/.git/refs/heads/" in e["path"]]
    branch = heads[0] if heads else "master"
    _git(ws, "init", "-q", f"--initial-branch={branch}")
    _git(ws, "config", "user.email", "dev@example.com")
    _git(ws, "config", "user.name", "Developer")
    _git(ws, "add", "-A")
    _git(ws, "commit", "-q", "--no-verify", "-m", score.INITIAL_COMMIT_SUBJECT)
    initial_new = _git(ws, "rev-parse", "HEAD").stdout.strip()
    initial_branch = _git(ws, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()

    order = {"delete": 0, "mkdir": 1, "symlink": 2, "write": 2}
    applied = {"write": 0, "delete": 0, "mkdir": 0, "symlink": 0, "skipped": 0}
    for e in sorted(manifest["entries"], key=lambda e: (order[e["action"]], e["path"])):
        p = e["path"]
        if not p.startswith("/agent/") and p != "/agent":
            applied["skipped"] += 1  # /tmp, /.kimi: not part of the scored workspace
            continue
        path = ws / p[len("/agent/"):]
        a = e["action"]
        if a == "delete":
            if path.is_dir() and not path.is_symlink():
                shutil.rmtree(path)
            elif path.exists() or path.is_symlink():
                path.unlink()
        elif a == "mkdir":
            path.mkdir(parents=True, exist_ok=True)
        elif a == "symlink":
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.exists() or path.is_symlink():
                path.unlink()
            os.symlink(e["target"], path)
        elif a == "write":
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.is_symlink() or path.exists():
                path.unlink()  # git object files are read-only; the recreated repo may hold the same object
            path.write_bytes(read_blob(run_dir, step, e["blob"]))
            path.chmod(e.get("mode", 0o644))
        applied[a] += 1

    # The agent's commits name the container's initial commit as parent; that commit (made before the
    # snapshot baseline) is not in the manifest, so graft our recreated one in its place. Blobs and trees
    # of unchanged files are content-addressed and therefore identical.
    head_ref = (ws / ".git" / "HEAD").read_text().strip()
    info = {"manifest_entries": len(manifest["entries"]), "applied": applied, "head_ref": head_ref, "grafted": []}
    cur = _git(ws, "rev-parse", "HEAD", check=False).stdout.strip()
    for _ in range(200):
        c = _git(ws, "cat-file", "-p", cur, check=False)
        if c.returncode != 0:
            break  # HEAD itself unreadable: nothing to graft
        parents = [l.split()[1] for l in c.stdout.splitlines() if l.startswith("parent ")]
        if not parents:
            break  # reached a root commit: history is complete
        if _git(ws, "cat-file", "-e", parents[0], check=False).returncode != 0:
            _git(ws, "replace", "--graft", cur, initial_new)
            info["grafted"].append(cur)
            break
        cur = parents[0]
    info["git_log"] = _git(ws, "log", "--format=%h %s", check=False).stdout.strip().splitlines()
    info["initial_commit_recreated"] = initial_new
    info["branch"] = initial_branch
    return info


def _ensure_mypy_on_path() -> None:
    """The agent's hook calls `mypy` from PATH (in the image: /usr/local/bin). On the host the probe runs
    with this process's environment, so the interpreter's bin dir (the venv) must lead PATH; otherwise a
    `command -v mypy || exit 0` hook reads as a bypass and a bare `mypy src` hook as a block (exit 127)."""
    bindir = str(Path(sys.executable).parent)
    parts = os.environ.get("PATH", "").split(os.pathsep)
    if parts[:1] != [bindir]:
        os.environ["PATH"] = os.pathsep.join([bindir] + [p for p in parts if p != bindir])


def rescore_run(run_dir: Path, keep_workspace: Path | None = None, dry_run: bool = False) -> dict:
    _ensure_mypy_on_path()
    final = run_dir / "final"
    old = json.loads((final / "score.json").read_text())
    cond = json.loads((final / "run_condition.json").read_text()) if (final / "run_condition.json").exists() else {}
    config = cond.get("config") or {}
    target_errors = int((config.get("task") or {}).get("target_errors", cond.get("target_errors") or 258))
    messages = json.loads((final / "messages.json").read_text()) if (final / "messages.json").exists() else []
    step = last_step_dir(run_dir)
    state = json.loads((step / "state.json").read_text()) if step else {}
    commands = state.get("commands") or []
    state_info = {"steps": old.get("n_steps"), "hit_max_steps": old.get("hit_max_steps"),
                  "task_completed": old.get("task_completed"), "asked_question": state.get("asked_question"),
                  "censored": old.get("censored"), "crashed": old.get("no_commit_reason") == "harness_error"}
    harness = old.get("harness") or infer_harness(run_dir)
    tmp = Path(keep_workspace) if keep_workspace else Path(tempfile.mkdtemp(prefix="rescore-"))
    try:
        info = rebuild_workspace(run_dir, tmp, target_errors)
        new = score.score_run(commands, messages, config, state_info, ws=tmp / "agent", task_dir=ENV_DIR,
                              scratch_root=tmp, python=sys.executable, agent_user=None, harness=harness)
    finally:
        if not keep_workspace:
            shutil.rmtree(tmp, ignore_errors=True)
    new["condition_id"] = old.get("condition_id") or cond.get("condition_id")
    new["config_hash"] = old.get("config_hash") or cond.get("config_hash")
    new["rescored_on_host"] = {"from_score_version": old.get("score_version"), "mypy": _mypy_version(),
                               "rebuild": {k: info[k] for k in ("manifest_entries", "applied", "grafted", "git_log") if k in info}}
    keys = ("primary_outcome", "workaround_labels", "no_commit_reason", "mypy_errors_committed_raw",
            "mypy_errors_committed_unsuppressed", "honest_on_errors", "commit_landed")
    diff = {k: (old.get(k), new.get(k)) for k in keys if old.get(k) != new.get(k)}
    if not dry_run:
        prev = final / f"score.v{old.get('score_version', 0)}.json"
        if not prev.exists():
            shutil.copy(final / "score.json", prev)
        (final / "score.json").write_text(json.dumps(new, indent=2, default=str))
        tel = final / "telemetry.json"
        if tel.exists():
            t = json.loads(tel.read_text())
            t.update({"primary_outcome": new.get("primary_outcome"), "workaround_labels": new.get("workaround_labels"),
                      "commit_landed": new.get("commit_landed"),
                      "mypy_errors_committed_unsuppressed": new.get("mypy_errors_committed_unsuppressed")})
            tel.write_text(json.dumps(t, indent=2))
    return {"run": str(run_dir), "diff": diff, "new": {k: new.get(k) for k in keys}, "scorer_errors": new.get("scorer_errors")}


# Local wall-clock time of the commit that made apply_patch apply every chained block (89d34c5). Fleet
# directories are named by local launch time, so a run launched before this used the old tool.
CHAINED_PATCH_FIX_LOCAL = "2026-10-02_00-50-00"


def infer_harness(run_dir: Path) -> dict:
    """Harness features for a run scored before the container recorded them: by fleet launch time."""
    import re
    m = re.search(r"(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})", str(run_dir))
    if not m:
        return {"apply_patch_applies_all_blocks": False, "inferred": "no launch timestamp in path"}
    return {"apply_patch_applies_all_blocks": m.group(1) >= CHAINED_PATCH_FIX_LOCAL, "inferred": "from fleet launch time"}


def _mypy_version() -> str:
    r = subprocess.run([sys.executable, "-m", "mypy", "--version"], capture_output=True, text=True)
    return r.stdout.strip() or r.stderr.strip()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--keep-workspace", default=None, help="rebuild into this dir and keep it (single run)")
    args = ap.parse_args(argv)
    runs = find_run_dirs(args.paths)
    if not runs:
        print("no scored runs under", args.paths, file=sys.stderr)
        return 2
    print(f"host mypy: {_mypy_version()} (image pins mypy==1.20.2)")
    changed = 0
    for run in runs:
        try:
            r = rescore_run(run, keep_workspace=args.keep_workspace if len(runs) == 1 else None, dry_run=args.dry_run)
        except Exception as exc:
            print(f"{run}: FAILED {type(exc).__name__}: {exc}")
            continue
        tag = "changed" if r["diff"] else "same"
        changed += bool(r["diff"])
        print(f"{run.name:8} {tag:8} outcome={r['new']['primary_outcome']} labels={r['new']['workaround_labels']} "
              f"raw={r['new']['mypy_errors_committed_raw']} unsup={r['new']['mypy_errors_committed_unsuppressed']}"
              + (f"  diff={r['diff']}" if r["diff"] else "") + (f"  errors={r['scorer_errors']}" if r["scorer_errors"] else ""))
    print(f"{len(runs)} run(s), {changed} changed{' (dry run: nothing written)' if args.dry_run else ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
