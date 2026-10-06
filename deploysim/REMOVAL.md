# Removing the deployment simulation

Delete `deploysim/` and `results/deploysim/`. Nothing outside the directory was modified (`tests/test_ds_isolation.py`).
It reads SF1's and SF2's environment files and builders, so removing those breaks it.
