#!/usr/bin/env python3
"""Launch holdout rollouts through the shared runner (registers the environment at runtime; no shared file edited).

    python holdout/scripts/run_ho.py holdout/configs/HO-G~visible.yaml --count 2 --results-dir results/holdout/<batch>/<cond>
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
import env_registry  # noqa: E402
import run  # noqa: E402

env_registry.ENV_DOCKERFILES.setdefault("holdout", "holdout/env/Dockerfile")
env_registry.ENV_JUDGES.setdefault("holdout", "")

if __name__ == "__main__":
    sys.argv[0] = str(REPO_ROOT / "scripts" / "run.py")
    sys.exit(run.main())
