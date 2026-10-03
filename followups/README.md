# Follow-up pilots: momentum (A) and persona spillover (B)

Spec: `../followuppilottask.md`. Pre-registration: `PREREG.md`. Report: `PILOT_REPORT.md`. Removal: `REMOVAL.md`.
Both pilots reuse the RS1 infrastructure under `../resampling/` by import.

- `momentum_a/` – frozen workaround and verbal-update rules (`workaround.py`), source selection (`select_sources.py`),
  the injection wrapper around RS1's container agent (`ma_agent.py`), launcher (`ma_run.py`), outcomes and the
  decision rule (`ma_metrics.py`).
- `spillover_b/` – items, randomisation, parsing and scoring (`items.py`), prefixes (`sb_prefixes.py`), single-reply
  sampler (`sb_run.py`), summary and decision rule (`sb_summary.py`).
- `stage0_checks.py` – F1 (RS1's S2/S3 on the A checkpoints) and F2 (one test call with an injected user turn).
- `plans/` – selected sources, prefixes, the 36-job A plan. `spend.json` – the cost meter.
