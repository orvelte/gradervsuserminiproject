"""SF2 is additive: it adds structural_framing_v2/ and modifies no file that existed before it."""
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BASELINE = "604b280"   # the commit before structural_framing_v2/ was added


def git(*a): return subprocess.run(["git", *a], cwd=REPO_ROOT, capture_output=True, text=True).stdout


def test_sf2_commits_touch_only_their_directory():
    for line in git("log", "--format=%H %s", f"{BASELINE}..HEAD").splitlines():
        sha, subject = line.split(" ", 1)
        if subject.startswith("sf2:"):
            files = [f for f in git("show", "--name-only", "--format=", sha).splitlines() if f]
            assert all(f.startswith("structural_framing_v2/") for f in files), (subject, files)


def test_reused_files_exist_where_the_dockerfile_expects_them():
    df = (REPO_ROOT / "structural_framing_v2/env/precommit_hook_sf2/Dockerfile").read_text()
    for line in df.splitlines():
        if line.startswith("COPY ") and not line.startswith("COPY pyproject.toml") and not line.startswith("COPY src "):
            src = line.split()[1]
            assert (REPO_ROOT / src).exists(), src
