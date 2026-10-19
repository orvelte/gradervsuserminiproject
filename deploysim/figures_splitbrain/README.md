# Split-brain figures

Figures for the split-brain experiments (branch `splitbrain`), kept apart from the deployment-simulation figures in `deploysim/figures/`. Each `fig_*.py` regenerates its figure from `results/` (needs `seaborn`). `style.py` holds the shared look (sans-serif, boxed axes, light grid, muted palette, solid = graded / hatched = deployment).

- `fig_screen1` — model screen at 258 errors: grader gaming, sustained test talk and gaming mechanism per model and arm (batches `screen1_*`, DECISIONS #46).
- `fig_p4_difficulty` — P4 difficulty pilot (DeepSeek V4 Flash, 20 runs per cell at 5 / 20 / 60; 258 from the screen), corrected labels (DECISIONS #51).
