# Removing SF2

Delete `structural_framing_v2/` and `results/structural_framing_v2/`. No file outside the directory was modified
(`tests/test_sf2_isolation.py`), and nothing else imports from it.

SF2 reads, but does not change: `structural_framing/env/precommit_hook_sf/{run_step.py,tools.py,entrypoint.py}`,
`structural_framing/configs/build_sf_arms.py`, `structural_framing/configs/build_sf_smoke.py`,
`configs/precommit_hook/{N0_replication.yaml,build_arms.py,build_smoke.py}` and `environments/precommit_hook/`.
Removing SF1 therefore breaks SF2.
