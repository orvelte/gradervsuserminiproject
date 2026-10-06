"""deploysim is additive: commits prefixed `ds:` touch only deploysim/, and every file its Dockerfile reuses exists."""
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BASELINE = "52fd6a8"   # the commit before deploysim/ was added


def git(*a): return subprocess.run(["git", *a], cwd=REPO_ROOT, capture_output=True, text=True).stdout


def test_ds_commits_touch_only_their_directory():
    for line in git("log", "--format=%H %s", f"{BASELINE}..HEAD").splitlines():
        sha, subject = line.split(" ", 1)
        if subject.startswith("ds:"):
            files = [f for f in git("show", "--name-only", "--format=", sha).splitlines() if f]
            assert all(f.startswith("deploysim/") for f in files), (subject, files)


def test_reused_files_exist():
    df = (REPO_ROOT / "deploysim/env/precommit_hook_ds/Dockerfile").read_text()
    for line in df.splitlines():
        if line.startswith("COPY ") and not line.startswith(("COPY pyproject.toml", "COPY src ")):
            assert (REPO_ROOT / line.split()[1]).exists(), line
