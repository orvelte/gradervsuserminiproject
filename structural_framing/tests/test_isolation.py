"""SF1 isolation (sfbuildtask.md, hard constraint): nothing outside structural_framing/ changed since task start.

`git diff <task-start commit> -- . ':!structural_framing/' ':!results/'` must be empty, or contain only the
additive lines documented in structural_framing/REMOVAL.md (currently: none). Untracked files outside
structural_framing/ are also checked; the only one allowed is sfbuildtask.md, the spec Olivia dropped at the root.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TASK_START_COMMIT = "0a61e1ce3786cf3c1239e0edd3629231d56da25d"
ALLOWED_UNTRACKED_OUTSIDE = {"sfbuildtask.md"}  # the task spec itself, not part of the build


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, check=True).stdout


def test_task_start_commit_is_an_ancestor():
    assert _git("cat-file", "-t", TASK_START_COMMIT).strip() == "commit"
    subprocess.run(["git", "merge-base", "--is-ancestor", TASK_START_COMMIT, "HEAD"], cwd=REPO_ROOT, check=True)


def test_no_tracked_change_outside_structural_framing():
    diff = _git("diff", TASK_START_COMMIT, "--", ".", ":!structural_framing/", ":!results/")
    assert diff == "", f"shared files changed since {TASK_START_COMMIT[:12]} (must be listed in REMOVAL.md):\n{diff[:3000]}"
    staged = _git("diff", "--cached", TASK_START_COMMIT, "--", ".", ":!structural_framing/", ":!results/")
    assert staged == "", f"staged changes outside structural_framing/:\n{staged[:3000]}"


def test_no_new_untracked_files_outside_structural_framing():
    out = _git("status", "--porcelain", "--untracked-files=all", "--", ".", ":!structural_framing/", ":!results/")
    paths = [line[3:] for line in out.splitlines() if line.startswith("??")]
    stray = sorted(p for p in paths if p not in ALLOWED_UNTRACKED_OUTSIDE)
    assert not stray, f"new untracked files outside structural_framing/: {stray}"


def test_removal_doc_lists_no_shared_file_changes():
    text = (REPO_ROOT / "structural_framing" / "REMOVAL.md").read_text()
    assert "rm -r structural_framing/" in text
    assert "Shared-file changes: none" in text
