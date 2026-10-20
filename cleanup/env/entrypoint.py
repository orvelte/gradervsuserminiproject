"""Entrypoint for the cleanup environment (copied from holdout): seed /agent from the pristine workspace plus the condition's repo cues
(README, extra files, git history), hand it to `dev`, then run the agent loop. Root-only seed record at
/opt/sf_seed.json (the loop copies it into final/sf_run.json)."""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

from agent_interp_envs.config import load_config
from agent_interp_envs.tool_calling import chown_to_agent

config = load_config()
task = config.get("task") or {}
PRISTINE = Path("/opt/task/workspace")
WS = Path("/agent")
AGENT_GIT_USER = ("Developer", "dev@example.com")


def git(*args, env=None):
    return subprocess.run(["git", *args], cwd=WS, capture_output=True, text=True, check=True, env={**os.environ, **(env or {})})


def seed() -> dict:
    content = task.get("cue_content") or {}
    if task.get("sf_framing") != "cues" or not content:
        sys.exit("cleanup needs task.sf_framing: cues and task.cue_content")
    for p in PRISTINE.iterdir():
        (shutil.copytree if p.is_dir() else shutil.copy2)(p, WS / p.name)
    (WS / "README.md").write_text(content["readme"])
    for rel, body in (content.get("files") or {}).items():
        p = WS / rel; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(body)
    git("init", "-q"); git("config", "user.email", AGENT_GIT_USER[1]); git("config", "user.name", AGENT_GIT_USER[0])
    tracked = sorted(str(p.relative_to(WS)) for p in WS.rglob("*") if p.is_file() and ".git" not in p.parts)
    for c in content["history"]:
        files = tracked if c.get("files") is None else c["files"]
        git("add", "--", *files)
        name, email = c["author"]
        git("commit", "-q", "--no-verify", "-m", c["message"], env={"GIT_AUTHOR_NAME": name, "GIT_AUTHOR_EMAIL": email, "GIT_COMMITTER_NAME": name,
                                                                   "GIT_COMMITTER_EMAIL": email, "GIT_AUTHOR_DATE": c["date"], "GIT_COMMITTER_DATE": c["date"]})
    left = git("status", "--porcelain").stdout.strip()
    if left:
        sys.exit(f"seed history leaves files uncommitted: {left}")
    log = git("log", "--format=%H%x00%an%x00%s").stdout.strip().splitlines()
    return {"framing": "cues", "n_commits": len(log), "head": git("rev-parse", "HEAD").stdout.strip(), "tree": git("rev-parse", "HEAD^{tree}").stdout.strip(),
            "root_subject": log[-1].split("\x00")[2], "head_subject": log[0].split("\x00")[2], "authors": sorted({l.split("\x00")[1] for l in log}),
            "extra_files": sorted(content.get("files") or {})}


print("Setting up cleanup workspace")
WS.mkdir(exist_ok=True)
os.chdir(WS)
rec = seed()
Path("/opt/sf_seed.json").write_text(json.dumps(rec, indent=1)); os.chmod("/opt/sf_seed.json", 0o600)
print(f"Seeded history: {rec['n_commits']} commit(s), head {rec['head'][:12]}")
chown_to_agent(WS)
with open("/tmp/config.yaml", "w") as f:
    yaml.dump(config, f, default_flow_style=False)
os.chmod("/tmp/config.yaml", 0o600)
sys.exit(subprocess.run([sys.executable, "/opt/agent.py", "/tmp/config.yaml"]).returncode)
