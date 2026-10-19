#!/usr/bin/env python3
"""Copy the generated figures from their (gitignored) output folders into this tracked folder.

    python figures/collect.py

Regenerate a figure with its own script first (paths below), then run this."""
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
SOURCES = {  # figure name -> (output folder, generating script)
    # Earlier figures (fig_prompts, fig_onset, fig_belief, fig_timing, fig_hints, fig_mechanism, fig_prompts_sf2,
    # fig_talker_doer) are kept here as images only; their scripts were removed with their experiments on 2026-10-19
    # and remain at tag `deploysim-v1-results`. Deployment-simulation figures live in deploysim/figures/.
}
for name, (folder, script) in SOURCES.items():
    for ext in ("png", "svg"):
        src = REPO / folder / f"{name}.{ext}"
        if src.exists():
            shutil.copy2(src, HERE / src.name); print("copied", src.relative_to(REPO))
        else:
            print("MISSING", src.relative_to(REPO), "(run", script + ")")
