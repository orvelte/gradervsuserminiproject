# Removing RS1

Shared-file changes: none. Everything is under `resampling/`; the container image is built from
`resampling/env/Dockerfile` (a copy of the precommit_hook Dockerfile with four added COPY lines and one pip install)
and the launcher reuses `scripts/run.py`, `scripts/run_common.py` and `scripts/env_registry.py` by import.

```bash
rm -r resampling/
rm -rf results/resampling/                                             # optional, gitignored
docker image ls 'agent-interp-envs/precommit_hook_rs' -q | xargs -r docker image rm
```

`resampling/tests/test_isolation.py` asserts the tracked diff outside `resampling/` (and `structural_framing/`,
`results/`) against the task-start commit is empty. The original design is checked with `pytest tests` and
`scripts/smoke_check.py`.
