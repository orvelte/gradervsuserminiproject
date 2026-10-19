# Removing the deployment simulation

Delete `deploysim/` and `results/deploysim/`. It is self-contained apart from the shared harness (`src/`, `scripts/`),
the original environment (`environments/precommit_hook/`) and the N0 config (`configs/precommit_hook/`), which it reads
and does not change. Since the 2026-10-19 clean-up it no longer depends on the structural-framing directories.
