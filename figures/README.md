# Figures

Copies of the generated figures (PNG and SVG). The originals are written to gitignored output folders by the scripts
below; `python figures/collect.py` refreshes this folder.

| figure | what it shows | script |
|---|---|---|
| `fig_prompts` | The framing manipulations, verbatim: prompt-only 2×2 and structural framing (SF1) | `structural_framing/analysis/fig_prompts.py` |
| `fig_onset` | When the "they'll only check the files exist" inference first appears, relative to the error wall | `structural_framing/analysis/fig_onset.py` |
| `fig_belief` | Gaming rate per arm next to the share of runs whose reasoning models a checker | `structural_framing/analysis/fig_belief.py` |
| `fig_timing` | Inference turn against error-wall turn, no-hint arms | `structural_framing/analysis/fig_timing.py` |
| `fig_hints` | Prevalence and density of the inference by hint type | `structural_framing/analysis/fig_hints.py` |
| `fig_mechanism` | Exploratory: bypass the check versus fake the work, pooled across SF1 and RS1 | `resampling/analysis/fig_mechanism.py` |
| `fig_talker_doer` | Momentum pilot (n = 9 per cell): said it must fix the types versus ended honest | `followups/momentum_a/fig_talker_doer.py` |
