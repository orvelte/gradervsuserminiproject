#!/usr/bin/env python3
"""Copy the generated figures from their (gitignored) output folders into this tracked folder.

    python figures/collect.py

Regenerate a figure with its own script first (paths below), then run this."""
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
SOURCES = {  # figure name -> (output folder, generating script)
    "fig_prompts": ("structural_framing/analysis/out", "structural_framing/analysis/fig_prompts.py"),
    "fig_onset": ("structural_framing/analysis/out", "structural_framing/analysis/fig_onset.py"),
    "fig_belief": ("structural_framing/analysis/out", "structural_framing/analysis/fig_belief.py"),
    "fig_timing": ("structural_framing/analysis/out", "structural_framing/analysis/fig_timing.py"),
    "fig_hints": ("structural_framing/analysis/out", "structural_framing/analysis/fig_hints.py"),
    "fig_mechanism": ("resampling/analysis/out", "resampling/analysis/fig_mechanism.py"),
    "fig_prompts_sf2": ("structural_framing_v2/analysis/out", "structural_framing_v2/analysis/fig_prompts_sf2.py"),
    "fig_talker_doer": ("followups/analysis_out", "followups/momentum_a/fig_talker_doer.py"),
}
for name, (folder, script) in SOURCES.items():
    for ext in ("png", "svg"):
        src = REPO / folder / f"{name}.{ext}"
        if src.exists():
            shutil.copy2(src, HERE / src.name); print("copied", src.relative_to(REPO))
        else:
            print("MISSING", src.relative_to(REPO), "(run", script + ")")
