#!/usr/bin/env python3
"""Launch rollouts of the precommit_hook_ds environment through the existing runner, unmodified.

    python deploysim/scripts/run_ds.py structural_framing_v2/configs/DS-G.yaml --count 2 ...

Registers the SF2 environment in scripts/env_registry at runtime (no shared file is edited), then hands argv to
scripts/run.py. Configs whose `environment` is the original precommit_hook also work (scorer-equivalence smoke twins).
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DS_DOCKERFILE = "deploysim/env/precommit_hook_ds/Dockerfile"

sys.path.insert(0, str(REPO_ROOT / "scripts"))
import env_registry  # noqa: E402
import run  # noqa: E402

env_registry.ENV_DOCKERFILES.setdefault("precommit_hook_ds", DS_DOCKERFILE)
env_registry.ENV_JUDGES.setdefault("precommit_hook_ds", "")  # no autorater

if __name__ == "__main__":
    sys.argv[0] = str(REPO_ROOT / "scripts" / "run.py")
    sys.exit(run.main())
