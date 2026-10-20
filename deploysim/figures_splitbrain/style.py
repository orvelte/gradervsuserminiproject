"""Shared style for the split-brain figures: classic scientific-paper style (Olivia, 2026-10-20). Serif type, white
background, no grid, full black frame with inward ticks on all four sides, thin lines, a small colour-blind-safe
palette (Okabe-Ito), solid vs hatched for the graded and deployment arms, black capped error bars, a short plain
title (details belong in the caption)."""
from __future__ import annotations

import matplotlib as mpl
import matplotlib.pyplot as plt

# Okabe-Ito, darkest first: blue, vermillion, bluish green, reddish purple, orange, sky blue, yellow, black
PALETTE = ["#0072B2", "#D55E00", "#009E73", "#CC79A7", "#E69F00", "#56B4E9", "#F0E442", "#000000"]
GRADED_HATCH, DEPLOY_HATCH = None, "///"
ERR = dict(fmt="none", ecolor="black", capsize=2.5, lw=0.8, capthick=0.8)


def setup():
    plt.style.use("default")
    mpl.rcParams.update({
        "font.family": "serif", "font.serif": ["Times New Roman", "Times", "Nimbus Roman", "DejaVu Serif"],
        "mathtext.fontset": "stix", "font.size": 10, "axes.titlesize": 11, "axes.labelsize": 10,
        "xtick.labelsize": 9, "ytick.labelsize": 9, "legend.fontsize": 9,
        "axes.edgecolor": "black", "axes.linewidth": 0.8, "axes.grid": False, "axes.facecolor": "white",
        "figure.facecolor": "white", "axes.spines.top": True, "axes.spines.right": True,
        "xtick.direction": "in", "ytick.direction": "in", "xtick.top": True, "ytick.right": True,
        "xtick.major.width": 0.8, "ytick.major.width": 0.8, "xtick.major.size": 3.5, "ytick.major.size": 3.5,
        "xtick.color": "black", "ytick.color": "black", "lines.linewidth": 1.2, "lines.markersize": 4,
        "legend.frameon": False, "hatch.linewidth": 0.7, "savefig.dpi": 300, "figure.dpi": 110,
        "axes.prop_cycle": mpl.cycler(color=PALETTE),
    })


def bar(ax, x, h, w, color, deployment: bool, **kw):
    """Graded: solid fill. Deployment: white fill, coloured hatch and edge."""
    if deployment:
        return ax.bar(x, h, w, facecolor="white", edgecolor=color, hatch=DEPLOY_HATCH, linewidth=0.9, **kw)
    return ax.bar(x, h, w, color=color, edgecolor=color, linewidth=0.9, **kw)


def titles(fig, title, subtitle=None):
    """A short plain title; the subtitle (setup details) is set small beneath it, as a caption fragment."""
    fig.suptitle(title, fontsize=11, y=1.06)
    if subtitle:
        fig.text(0.5, 1.0, subtitle, ha="center", va="bottom", fontsize=8.5, color="black", style="italic")
