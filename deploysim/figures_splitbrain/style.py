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
        "mathtext.fontset": "stix", "font.size": 10.5, "axes.titlesize": 13, "axes.labelsize": 11.5,
        "xtick.labelsize": 10, "ytick.labelsize": 10, "legend.fontsize": 9.5, "axes.titlepad": 7,
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


TITLE_SIZE, SUBTITLE_SIZE = 16, 11


def titles(fig, title, subtitle=None):
    """Figure title (large) with an italic caption line beneath it, placed above everything already drawn (axes, their
    titles, tick labels, colour bars), so neither can overlap the plot. Call after any tight_layout / subplots_adjust.
    The caption line is wrapped to the figure width."""
    import textwrap
    fig.canvas.draw(); r = fig.canvas.get_renderer(); inv = fig.transFigure.inverted()
    top = max(inv.transform(a.get_tightbbox(r).corners())[:, 1].max() for a in fig.axes) if fig.axes else 0.95
    gap = 6 / (fig.get_figheight() * 72)                        # 6 pt
    y = top + gap
    if subtitle:
        width_chars = int(fig.get_figwidth() * 72 / (SUBTITLE_SIZE * 0.48))
        t = fig.text(0.5, y, textwrap.fill(subtitle, width_chars), ha="center", va="bottom", fontsize=SUBTITLE_SIZE, style="italic")
        bb = inv.transform(t.get_window_extent(r).corners()); y = bb[:, 1].max() + gap
    fig.text(0.5, y, title, ha="center", va="bottom", fontsize=TITLE_SIZE)
