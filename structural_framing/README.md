# Structural framing × grader information (SF1)

Second experiment on the same `precommit_hook` task: the *same* prompt text (N0's user prompt, verbatim) is wrapped
either as a graded harness session or as a message from a collaborator (Priya), and the **structure** of the
episode carries the framing too: the repo's git history (one harness commit vs six months of commits by three
people), two injected user turns after steps 8 and 18, and a fixed reply from `ask_user_question`. Crossed with
the stated grader information (lax: "checks the files exist"; strict: "reviews the diff and shell history").
Spec: `../sfbuildtask.md`. Report: `BUILD_REPORT.md`. Removal: `REMOVAL.md`.

| | lax | strict |
|---|---|---|
| graded_structural | `configs/SF1-G-LAX.yaml` | `configs/SF1-G-STRICT.yaml` (built, never run) |
| collaborator_structural | `configs/SF1-C-LAX.yaml` | `configs/SF1-C-STRICT.yaml` (built, never run) |

Everything is under this directory; nothing outside it changed (`tests/test_isolation.py`).

## Layout

- `env/precommit_hook_sf/` – copy of `environments/precommit_hook` with `sf_framing.py` (seeded histories, injection
  texts, question reply) and small patches in `entrypoint.py` (history seeding), `agent.py` (injections,
  `final/sf_run.json`), `run_step.py` (question reply, run continues), `states.py` (two list fields), `Dockerfile`
  (paths). `score.py`, `tools.py`, `apply_patch.py`, `generate_variants.py`, `pyproject.toml`, `src_*` are byte-identical.
- `configs/build_sf_arms.py` → the four arm YAMLs (settings copied from `configs/precommit_hook/N0_replication.yaml`,
  hash recorded in `condition.source_config_hash`). `configs/build_sf_smoke.py` → `configs/smoke/*.yaml` (mock).
- `scripts/run_sf.py` (runtime registry entry + `scripts/run.py`), `launch_sf.sh ARM COUNT`, `smoke_check_sf.py`,
  `upload_sf.py` (Docent; `DOCENT_COLLECTION_ID_SF` overrides the collection; `--dry-run`; idempotent).
- `analysis/grader_modeling.py` (frozen rule v1), `sf_metrics.py` (per-run `final/sf_metrics.json` + snippets CSV),
  `sf_summary.py` (per-arm table, G-LAX vs C-LAX bootstrap).
- `tests/` – isolation, configs, env mechanics (host loop), grader-modeling rule.

## Commands

```bash
.venv/bin/python -m pytest structural_framing/tests -q          # Stage 0 unit tests (no Docker)
.venv/bin/python structural_framing/scripts/smoke_check_sf.py   # Stage 0 container smoke (Docker, no cost)
structural_framing/scripts/launch_sf.sh SF1-G-LAX 2             # paid (Stage 1: 2 × each lax arm)
.venv/bin/python structural_framing/analysis/sf_metrics.py results/structural_framing/SF1-G-LAX results/structural_framing/SF1-C-LAX
.venv/bin/python structural_framing/scripts/upload_sf.py results/structural_framing/SF1-G-LAX --dry-run
.venv/bin/python structural_framing/analysis/sf_summary.py
```
