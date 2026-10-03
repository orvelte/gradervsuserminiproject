"""Follow-up pilots isolation: nothing that existed before this task was modified, and this task's commits touch only
followups/. Baseline = the commit before the task started (5573b54, 2026-10-03).

Written to stay valid when later tasks add sibling directories: it checks modifications/deletions/renames of
pre-existing files, and the paths touched by commits whose subject starts with `followups:`."""
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BASELINE = "5573b54"
ALLOWED_UNTRACKED_ROOT = {"sfbuildtask.md", "rsbuildtask.md", "followuppilottask.md"}  # Olivia's task specs
# Additive edits outside followups/, each documented in followups/REMOVAL.md with its revert command.
ADDITIVE_EXCEPTIONS = {"resampling/BUILD_REPORT.md"}


def _git(*a):
    return subprocess.run(["git", *a], cwd=REPO_ROOT, capture_output=True, text=True, check=True).stdout


def test_no_preexisting_file_modified_deleted_or_renamed():
    out = _git("diff", "--name-status", "--diff-filter=MDRT", BASELINE, "--", ".", ":!followups/", ":!results/")
    changed = [l.split("\t", 1)[1] for l in out.strip().splitlines() if l.strip()]
    assert all(l.startswith("M") for l in out.strip().splitlines()), out
    assert set(changed) <= ADDITIVE_EXCEPTIONS, f"pre-existing files changed since {BASELINE}: {sorted(set(changed) - ADDITIVE_EXCEPTIONS)}"


def test_documented_exceptions_are_purely_additive():
    removal = (REPO_ROOT / "followups" / "REMOVAL.md").read_text()
    for path in ADDITIVE_EXCEPTIONS:
        assert path in removal, f"{path} is not documented in REMOVAL.md"
        diff = _git("diff", BASELINE, "--", path)
        removed = [l for l in diff.splitlines() if l.startswith("-") and not l.startswith("---")]
        assert not removed, f"{path}: the edit removes or rewrites existing lines: {removed[:3]}"


def test_followups_commits_touch_only_followups():
    shas = _git("log", "--format=%H", "--grep=^followups", f"{BASELINE}..HEAD").split()
    bad = []
    for sha in shas:
        for path in _git("show", "--name-only", "--format=", sha).split("\n"):
            if path and not path.startswith("followups/") and path not in ADDITIVE_EXCEPTIONS:
                bad.append((sha[:8], path))
    assert not bad, bad


def test_no_stray_untracked_files_outside_followups():
    out = _git("status", "--porcelain", "--untracked-files=all", "--", ".", ":!followups/", ":!results/")
    stray = sorted(l[3:] for l in out.splitlines() if l.startswith("??") and l[3:] not in ALLOWED_UNTRACKED_ROOT)
    assert not stray, stray


def test_removal_doc():
    t = (REPO_ROOT / "followups" / "REMOVAL.md").read_text()
    assert "rm -r followups/" in t and "Shared-file changes: one, additive" in t
