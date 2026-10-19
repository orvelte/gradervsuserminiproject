"""Shared style for the split-brain figures: sans-serif, boxed axes, light grid, muted qualitative colours, solid vs
hatched for the two arms, black capped error bars, centred title with a `·`-separated subtitle."""
from __future__ import annotations

import matplotlib as mpl
import matplotlib.pyplot as plt
import seaborn as sns

# muted qualitative palette (teal, burnt orange, purple, deep red, mustard, green, blue, brown)
PALETTE = ["#3e8e83", "#d6602a", "#7656d1", "#a5302e", "#d1a23a", "#4b8a4a", "#3567a8", "#8a5a3c"]
GRADED_HATCH, DEPLOY_HATCH = None, "///"
ERR = dict(fmt="none", ecolor="black", capsize=3, lw=1.1, capthick=1.1)


def setup():
    sns.set_theme(context="paper", style="whitegrid", font="DejaVu Sans", font_scale=1.2)
    mpl.rcParams.update({
        "axes.edgecolor": "black", "axes.linewidth": 0.9, "axes.spines.top": True, "axes.spines.right": True,
        "grid.color": "#e3e3e3", "grid.linewidth": 0.8, "axes.axisbelow": True,
        "xtick.bottom": True, "ytick.left": True, "xtick.color": "black", "ytick.color": "black",
        "legend.frameon": True, "legend.edgecolor": "#cccccc", "legend.framealpha": 1.0,
        "savefig.dpi": 300, "figure.dpi": 110, "hatch.linewidth": 0.9,
    })


def bar(ax, x, h, w, color, deployment: bool, **kw):
    """Graded: solid fill. Deployment: white fill, coloured hatch and edge (as in the reference figures)."""
    if deployment:
        return ax.bar(x, h, w, facecolor="white", edgecolor=color, hatch=DEPLOY_HATCH, linewidth=1.2, **kw)
    return ax.bar(x, h, w, color=color, edgecolor=color, linewidth=1.2, **kw)


def titles(fig, title, subtitle=None):
    fig.suptitle(title, fontsize=14, y=1.075)
    if subtitle:
        fig.text(0.5, 1.0, subtitle, ha="center", va="bottom", fontsize=10.5, color="#333333")
