"""Follow-up pilots isolation: nothing that existed before this task was modified, and this task's commits touch only
followups/. Baseline = the commit before the task started (5573b54, 2026-10-03).

Written to stay valid when later tasks add sibling directories: it checks modifications/deletions/renames of
pre-existing files, and the paths touched by commits whose subject starts with `followups:`."""
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BASELINE = "5573b54"
ALLOWED_UNTRACKED_ROOT = {"sfbuildtask.md", "rsbuildtask.md", "followuppilottask.md"}  # Olivia's task specs


def _git(*a):
    return subprocess.run(["git", *a], cwd=REPO_ROOT, capture_output=True, text=True, check=True).stdout


def test_no_preexisting_file_modified_deleted_or_renamed():
    out = _git("diff", "--name-status", "--diff-filter=MDRT", BASELINE, "--", ".", ":!followups/", ":!results/")
    assert out.strip() == "", f"pre-existing files changed since {BASELINE}:\n{out}"


def test_followups_commits_touch_only_followups():
    shas = _git("log", "--format=%H", "--grep=^followups", f"{BASELINE}..HEAD").split()
    bad = []
    for sha in shas:
        for path in _git("show", "--name-only", "--format=", sha).split("\n"):
            if path and not path.startswith("followups/"):
                bad.append((sha[:8], path))
    assert not bad, bad


def test_no_stray_untracked_files_outside_followups():
    out = _git("status", "--porcelain", "--untracked-files=all", "--", ".", ":!followups/", ":!results/")
    stray = sorted(l[3:] for l in out.splitlines() if l.startswith("??") and l[3:] not in ALLOWED_UNTRACKED_ROOT)
    assert not stray, stray


def test_removal_doc():
    t = (REPO_ROOT / "followups" / "REMOVAL.md").read_text()
    assert "rm -r followups/" in t and "Shared-file changes: none" in t
