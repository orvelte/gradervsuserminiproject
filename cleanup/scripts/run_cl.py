#!/usr/bin/env python3
"""Launch cleanup rollouts through the shared runner (registers the environment at runtime; no shared file edited).

    python cleanup/scripts/run_cl.py cleanup/configs/CL-G~visible.yaml --count 2 --results-dir results/cleanup/<batch>/<cond>
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
import env_registry  # noqa: E402
import run  # noqa: E402

env_registry.ENV_DOCKERFILES.setdefault("cleanup", "cleanup/env/Dockerfile")
env_registry.ENV_JUDGES.setdefault("cleanup", "")

if __name__ == "__main__":
    sys.argv[0] = str(REPO_ROOT / "scripts" / "run.py")
    sys.exit(run.main())
