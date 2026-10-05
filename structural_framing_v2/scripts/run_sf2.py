#!/usr/bin/env python3
"""Launch rollouts of the precommit_hook_sf2 environment through the existing runner, unmodified.

    python structural_framing_v2/scripts/run_sf2.py structural_framing_v2/configs/SF2-G-LAX.yaml --count 2 ...

Registers the SF2 environment in scripts/env_registry at runtime (no shared file is edited), then hands argv to
scripts/run.py. Configs whose `environment` is the original precommit_hook also work (scorer-equivalence smoke twins).
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SF2_DOCKERFILE = "structural_framing_v2/env/precommit_hook_sf2/Dockerfile"

sys.path.insert(0, str(REPO_ROOT / "scripts"))
import env_registry  # noqa: E402
import run  # noqa: E402

env_registry.ENV_DOCKERFILES.setdefault("precommit_hook_sf2", SF2_DOCKERFILE)
env_registry.ENV_JUDGES.setdefault("precommit_hook_sf2", "")  # no autorater

if __name__ == "__main__":
    sys.argv[0] = str(REPO_ROOT / "scripts" / "run.py")
    sys.exit(run.main())
