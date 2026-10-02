# Removing the structural-framing redesign (SF1)

Shared-file changes: none. Every file of SF1 lives under `structural_framing/`; the launcher registers the
`precommit_hook_sf` environment in `scripts/env_registry.ENV_DOCKERFILES` **at runtime, in memory**
(`structural_framing/scripts/run_sf.py`), so `scripts/env_registry.py` itself is untouched.
`structural_framing/tests/test_isolation.py` asserts `git diff 0a61e1ce3786cf3c1239e0edd3629231d56da25d -- . ':!structural_framing/' ':!results/'`
is empty and that no new untracked file exists outside `structural_framing/` (except `sfbuildtask.md`, the spec).

## One-step removal

```bash
rm -r structural_framing/
```

Optional clean-up of generated, gitignored artefacts:

```bash
rm -rf results/structural_framing/                                   # rollouts, smoke runs, SF Docent manifest
docker image ls 'agent-interp-envs/precommit_hook_sf' -q | xargs -r docker image rm   # SF images
```

Nothing in `.gitignore`, `scripts/`, `configs/`, `analysis/`, `environments/`, `src/` or the scorer references
`structural_framing/`; `results/docent_upload_manifest.json` (the original 2×2 manifest) is not touched by SF1,
which keeps its own manifest at `results/structural_framing/docent_manifest.json`.

## Confirming the original design still runs afterwards

```bash
.venv/bin/python -m pytest tests -q                                   # original unit tests (scorer, arms, finalize, ...)
.venv/bin/python scripts/smoke_check.py                               # original mock smoke suite in Docker (no cost)
```

Both exercise only the original `environments/precommit_hook` image and `configs/precommit_hook/` arms.
