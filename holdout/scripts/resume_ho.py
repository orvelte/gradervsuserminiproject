#!/usr/bin/env python3
"""Resume holdout rollouts from a step checkpoint (registers the environment, then runs scripts/resume.py).

    python holdout/scripts/resume_ho.py results/holdout/<batch>/<cond>/holdout/<model>/<ts>/run-N/step-K [resume.py options]
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
import env_registry  # noqa: E402

env_registry.ENV_DOCKERFILES.setdefault("holdout", "holdout/env/Dockerfile")
env_registry.ENV_JUDGES.setdefault("holdout", "")
import resume  # noqa: E402

if __name__ == "__main__":
    sys.argv[0] = str(REPO_ROOT / "scripts" / "resume.py")
    sys.exit(resume.main())
