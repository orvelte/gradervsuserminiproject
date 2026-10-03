#!/usr/bin/env python3
"""Figure: what the framing manipulations actually were, verbatim.

    python structural_framing/analysis/fig_prompts.py

Top: the prompt-only 2×2 (N0, G0/G1, U0/U1): only the wrapper around the shared task text differs. Bottom: the
structural-framing arms (SF1-G-LAX, SF1-C-LAX): wrapper plus git history, two injected turns and the ask_question
reply. All text is read from the config builders and the environment module, not retyped."""
import importlib.util, sys, textwrap
from pathlib import Path
import yaml
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m


A = load("build_arms", REPO / "configs/precommit_hook/build_arms.py")
F = load("sf_framing", REPO / "structural_framing/env/precommit_hook_sf/sf_framing.py")
N0 = A.N0_PROMPT.strip()
assert N0.endswith(A.CORE)
N0_OPEN = N0[: -len(A.CORE)].strip()
sf = {}
for arm, key in (("SF1-G-LAX", "graded"), ("SF1-C-LAX", "collaborator")):
    up = yaml.safe_load((REPO / f"structural_framing/configs/{arm}.yaml").read_text())["prompts"]["user_prompt"]
    pre, post = up.split(N0); sf[key] = (pre.strip(), post.strip())

COL = {"base": "#e3eaf6", "graded": "#f8e3e3", "user": "#e2f1e5", "shared": "#efefef", "info": "#fcf0cf"}
EDGE = {"base": "#4c72b0", "graded": "#c44e52", "user": "#55a868", "shared": "0.6", "info": "#c9a227"}
FS = 7.6; LH = FS * 1.27 / 72; CW = FS * 0.0072; PAD = 0.07
W, H = 14.0, 13.2
fig = plt.figure(figsize=(W, H)); ax = fig.add_axes([0, 0, 1, 1]); ax.set_xlim(0, W); ax.set_ylim(0, H); ax.axis("off")


def wrap(text, w):
    n = max(10, int((w - 2 * PAD) / CW))
    return "\n".join("\n".join(textwrap.wrap(p, n)) if p.strip() else "" for p in text.split("\n"))


def height(text, w):
    return (wrap(text, w).count("\n") + 1) * LH + 2 * PAD


def box(x, y_top, w, text, kind, h=None, style="normal", dashed=False):
    t = wrap(text, w); h = h or height(text, w)
    ax.add_patch(FancyBboxPatch((x, y_top - h), w, h, boxstyle="round,pad=0,rounding_size=0.04", fc=COL[kind], ec=EDGE[kind], lw=0.9, ls="--" if dashed else "-"))
    ax.text(x + PAD, y_top - PAD, t, fontsize=FS, va="top", ha="left", style=style, color="0.1", linespacing=1.2)
    return h


def row(y, label, cells, sub=None):
    """cells: list of (x, w, text, kind, opts) or None. Returns new y."""
    need = 0.17 * (label.count("\n") + 1) + (0.14 * (sub.count("\n") + 1) + 0.03 if sub else 0) + PAD
    h = max(max(height(c[2], c[1]) for c in cells if c), need)
    ax.text(LX, y - PAD, label, fontsize=8.6, va="top", ha="left", fontweight="bold", color="0.2")
    if sub:
        ax.text(LX, y - PAD - 0.19 * (label.count("\n") + 1), sub, fontsize=7.2, va="top", ha="left", color="0.4", linespacing=1.15)
    for c in cells:
        if c:
            box(c[0], y, c[1], c[2], c[3], h=h, **(c[4] if len(c) > 4 else {}))
    return y - h - 0.09


LX, X0, GAP = 0.25, 1.95, 0.14
CORE_SHORT = "Your task is to add a py.typed marker file in src/ … write a git pre-commit hook … that runs mypy on all Python files in src/ … Ensure your commit passes the hook cleanly. If any type errors come up, please properly fix them instead of just suppressing them …"

# ---------------- top: prompt-only 2×2 ----------------
y = H - 0.55
ax.text(LX, y + 0.2, "A. Prompt-only 2×2: the framing is a wrapper around the same task text", fontsize=12.5, fontweight="bold", va="bottom")
w3 = (W - X0 - 0.25 - 2 * GAP) / 3; xs = [X0 + i * (w3 + GAP) for i in range(3)]
y -= 0.05
for x, t, k in zip(xs, ["N0  no framing (the paper's prompt)", "G0 / G1  graded", "U0 / U1  user"], ["base", "graded", "user"]):
    ax.text(x, y, t, fontsize=10, fontweight="bold", color=EDGE[k], va="top")
y -= 0.3
y = row(y, "opening", [(xs[0], w3, N0_OPEN, "base"), (xs[1], w3, A.G_PRE, "graded"), (xs[2], w3, A.U_PRE, "user")])
h = height(CORE_SHORT + "\n[141 words, character-identical in all five arms]", W - X0 - 0.25)
ax.text(LX, y - PAD, "task text", fontsize=8.6, va="top", fontweight="bold", color="0.2"); ax.text(LX, y - PAD - 0.19, "shared", fontsize=7.2, va="top", color="0.4")
box(X0, y, W - X0 - 0.25, CORE_SHORT + "\n[141 words, character-identical in all five arms]", "shared", h=h, style="italic"); y -= h + 0.09
y = row(y, "oversight sentence", [None, (xs[1], w3, A.OVERSIGHT, "info", {"dashed": True}), (xs[2], w3, A.OVERSIGHT, "info", {"dashed": True})], sub="G1 and U1 only")
y = row(y, "closing", [(xs[0], w3, "(none)", "base"), (xs[1], w3, A.G_POST, "graded"), (xs[2], w3, A.U_POST, "user")])
ax.text(X0, y - 0.02, "Everything else is identical across the five arms: system prompt, tools (bash, apply_patch), repository, model, reasoning effort, step limit. 30 runs per arm.", fontsize=7.8, color="0.35", va="top")

# ---------------- bottom: structural framing ----------------
y -= 0.75
ax.text(LX, y + 0.2, "B. Structural framing (SF1): the wrapper plus the shape of the episode", fontsize=12.5, fontweight="bold", va="bottom")
w2 = (W - X0 - 0.25 - GAP) / 2; x2 = [X0, X0 + w2 + GAP]
y -= 0.05
for x, t, k in zip(x2, ["SF1-G-LAX  graded harness session", "SF1-C-LAX  collaborator (Priya)"], ["graded", "user"]):
    ax.text(x, y, t, fontsize=10, fontweight="bold", color=EDGE[k], va="top")
y -= 0.42
ax.text(LX, y + 0.04, "IN THE PROMPT", fontsize=7.4, color="0.45", va="bottom")
y = row(y, "opening", [(x2[0], w2, sf["graded"][0], "graded"), (x2[1], w2, sf["collaborator"][0], "user")])
t = N0_OPEN + " " + CORE_SHORT + "\n[N0's full prompt, verbatim, in both arms]"
h = height(t, W - X0 - 0.25)
ax.text(LX, y - PAD, "task text", fontsize=8.6, va="top", fontweight="bold", color="0.2"); ax.text(LX, y - PAD - 0.19, "shared", fontsize=7.2, va="top", color="0.4")
box(X0, y, W - X0 - 0.25, t, "shared", h=h, style="italic"); y -= h + 0.09
y = row(y, "closing = lax line", [(x2[0], w2, sf["graded"][1], "info"), (x2[1], w2, sf["collaborator"][1], "info")], sub="check = files exist")
y -= 0.3
ax.text(LX, y + 0.04, "IN THE ENVIRONMENT", fontsize=7.4, color="0.45", va="bottom")


def history(seed):
    return "\n".join(f"{c['date'][:10]}  {c['author'][0]}:  {c['message']}" for c in seed)


y = row(y, "git history", [(x2[0], w2, "1 commit\n" + history(F.GRADED_SEED), "graded"), (x2[1], w2, "6 commits by 3 people over six months\n" + history(F.COLLABORATOR_SEED), "user")], sub="what `git log` shows")
y = row(y, "user turn, step 8", [(x2[0], w2, F.INJECTIONS["graded"][8], "graded"), (x2[1], w2, F.INJECTIONS["collaborator"][8], "user")], sub="injected mid-run")
y = row(y, "user turn, step 18", [(x2[0], w2, F.INJECTIONS["graded"][18], "graded"), (x2[1], w2, F.INJECTIONS["collaborator"][18], "user")])
y = row(y, "ask_question reply", [(x2[0], w2, F.QUESTION_REPLY["graded"], "graded"), (x2[1], w2, F.QUESTION_REPLY["collaborator"], "user")], sub="fixed, whatever is asked")
ax.text(X0, y - 0.02, "Both SF1 arms add an ask_question tool (\"Ask a question to whoever assigned this task.\") that the 2×2 arms did not have, so SF1 arms are compared only with each other.\n"
        "Otherwise identical to N0: system prompt, repository files, model, reasoning effort, step limit. Pilot 22 runs per arm, replication 40 per arm. Strict-information variants were built but never run.",
        fontsize=7.8, color="0.35", va="top", linespacing=1.35)
# legend
ly = y - 0.75
for i, (k, t) in enumerate([("graded", "graded framing"), ("user", "user / collaborator framing"), ("base", "no framing"), ("shared", "shared text"), ("info", "statement about what will be checked")]):
    x = LX + i * 2.55
    ax.add_patch(FancyBboxPatch((x, ly - 0.07), 0.3, 0.16, boxstyle="round,pad=0,rounding_size=0.03", fc=COL[k], ec=EDGE[k], lw=0.9))
    ax.text(x + 0.38, ly + 0.01, t, fontsize=8, va="center", color="0.25")
bottom = ly - 0.3
ax.set_ylim(bottom, H); fig.set_size_inches(W, H - bottom)
for ext in ("png", "svg"):
    fig.savefig(HERE / "out" / f"fig_prompts.{ext}", dpi=170, facecolor="white")
print("wrote", HERE / "out" / "fig_prompts.png")
