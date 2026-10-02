#!/usr/bin/env python3
"""Launch rollouts of the precommit_hook_sf environment through the existing runner, unmodified.

    python structural_framing/scripts/run_sf.py structural_framing/configs/SF1-G-LAX.yaml --count 2 ...

scripts/run.py looks environments up in scripts/env_registry.ENV_DOCKERFILES, which knows only
precommit_hook. Rather than editing that shared file, this wrapper registers the SF environment in the
imported module at runtime and then hands argv to run.main() unchanged. Every option of scripts/run.py
works as documented there (the image is built from a snapshot of the whole tree, which includes
structural_framing/). Configs whose `environment` is the original precommit_hook also work through
this wrapper (used by the scorer-equivalence smoke cases).
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SF_DOCKERFILE = "structural_framing/env/precommit_hook_sf/Dockerfile"

sys.path.insert(0, str(REPO_ROOT / "scripts"))
import env_registry  # noqa: E402
import run  # noqa: E402

env_registry.ENV_DOCKERFILES.setdefault("precommit_hook_sf", SF_DOCKERFILE)
env_registry.ENV_JUDGES.setdefault("precommit_hook_sf", "")  # no autorater

if __name__ == "__main__":
    sys.argv[0] = str(REPO_ROOT / "scripts" / "run.py")
    sys.exit(run.main())
