# Removing the follow-up pilots

Shared-file changes: one, additive. An **erratum section was appended** to `resampling/BUILD_REPORT.md` (no existing
line changed), because check F1 of this task showed that RS1's S2 result was a token-count coincidence and the RS1
report should not keep stating it as a pass. Revert with:

```bash
git checkout 5573b54 -- resampling/BUILD_REPORT.md
```

Everything else is under `followups/`; RS1's renderer, provider, launcher, detector, scorer and
cost meter are used by import, and the container image is built from `followups/env/Dockerfile` (RS1's Dockerfile
with two COPY lines changed so that RS1's agent is importable and the injection wrapper is the entry agent).

```bash
rm -r followups/
rm -rf results/followups/                                              # optional, gitignored
docker image ls 'agent-interp-envs/precommit_hook_fu' -q | xargs -r docker image rm
```

`followups/tests/test_followups_isolation.py` asserts that no file that existed at the task's baseline commit
(5573b54) was deleted or renamed, that the only one modified is the documented exception above and that its diff adds
lines only, and that this task's commits (subject prefix `followups:`) touch only `followups/` and that file.

Not part of this task, but visible when running tests: the earlier isolation tests
(`structural_framing/tests/test_isolation.py`, `resampling/tests/test_isolation.py`) are scoped to their own baselines
and fail at HEAD. SF1's has failed since RS1 added `resampling/`; both also flag the task-spec files at the repo root
as untracked. They were left untouched because they are outside `followups/`.
