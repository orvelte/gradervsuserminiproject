"""RS1 isolation: nothing outside resampling/ changed since the task-start commit."""
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TASK_START = "eee805b"  # last commit before rsbuildtask.md was taken up (fig_hints.py), 2026-10-02
ALLOWED_UNTRACKED = {"sfbuildtask.md", "rsbuildtask.md"}


def _git(*a):
    return subprocess.run(["git", *a], cwd=REPO_ROOT, capture_output=True, text=True, check=True).stdout


def test_no_tracked_change_outside_resampling():
    assert _git("diff", TASK_START, "--", ".", ":!resampling/", ":!results/") == ""


def test_no_new_untracked_outside_resampling():
    out = _git("status", "--porcelain", "--untracked-files=all", "--", ".", ":!resampling/", ":!results/", ":!structural_framing/analysis/out/")
    stray = sorted(l[3:] for l in out.splitlines() if l.startswith("??") and l[3:] not in ALLOWED_UNTRACKED)
    assert not stray, stray


def test_removal_doc():
    t = (REPO_ROOT / "resampling" / "REMOVAL.md").read_text()
    assert "rm -r resampling/" in t and "Shared-file changes: none" in t
