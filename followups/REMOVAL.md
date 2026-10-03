# Removing the follow-up pilots

Shared-file changes: none. Everything is under `followups/`; RS1's renderer, provider, launcher, detector, scorer and
cost meter are used by import, and the container image is built from `followups/env/Dockerfile` (RS1's Dockerfile
with two COPY lines changed so that RS1's agent is importable and the injection wrapper is the entry agent).

```bash
rm -r followups/
rm -rf results/followups/                                              # optional, gitignored
docker image ls 'agent-interp-envs/precommit_hook_fu' -q | xargs -r docker image rm
```

`followups/tests/test_followups_isolation.py` asserts that no file that existed at the task's baseline commit
(5573b54) was modified, deleted or renamed, and that this task's commits (subject prefix `followups:`) touch only
`followups/`.
