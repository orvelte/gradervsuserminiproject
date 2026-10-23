#!/usr/bin/env python3
"""PP1 winners report: docs/pp1_winners.html (artifact page) and docs/pp1_winners.md (repo copy), built from
results/personaprompt/. Reads only finished outputs; scores nothing.

    python internals/personaprompt/report.py
"""
from __future__ import annotations

import html
import json
from collections import Counter
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
R = REPO / "results" / "personaprompt"
CELLS = ["HO-G~visible", "HO-D~visible", "HO-G~holdout", "HO-D~holdout"]
TRAITS = ["rule_breaking", "dishonesty", "competitiveness", "ambition", "approval_seeking", "sycophancy", "disclosure_omit"]
SHORT = {"rule_breaking": "rule-break", "dishonesty": "dishonest", "competitiveness": "compete", "ambition": "ambition",
         "approval_seeking": "approval", "sycophancy": "syco", "disclosure_omit": "omit"}


def load():
    fz = json.loads((R / "finalists.json").read_text())
    sem = json.loads((R / "semantic_leaks.json").read_text())
    ho = json.loads((R / "heldout.json").read_text())
    pr = json.loads((R / "heldout_predictions_repaired.json").read_text())
    allc = json.loads((R / "semantic_leaks_all_characters.json").read_text())
    cands = [json.loads(x) for x in (R / "candidates.jsonl").read_text().splitlines()]
    g0 = json.loads((R / "gate0.json").read_text())["prefixes"]
    return fz, sem, ho, pr, allc, cands, g0


def boot_ci(xs, rng, n=10000):
    xs = np.asarray(xs)
    return np.percentile([rng.choice(xs, len(xs)).mean() for _ in range(n)], [2.5, 97.5])


def stats():
    fz, sem, ho, pr, allc, cands, g0 = load()
    rng = np.random.default_rng(0)
    ci = {c: boot_ci([p["p"] for p in g0 if p["cell"] == c and p["split"] == "validation"], rng) for c in CELLS}
    acc = lambda o, p: float(np.mean([o[k] == (p.get(k) or "none") for k in TRAITS]))  # noqa: E731
    rows = []
    for f, s, h, p in zip(fz["finalists"], sem, ho["finalists"], pr):
        assert f["text"] == s["text"] == h["text"] == p["text"]
        v = f["validation"]
        rows.append({**f, "sem": s, "shift": h["shift"], "observed": h["observed"], "pred": p["prediction"],
                     "pred_repaired": p.get("repaired", False), "acc_asrun": h["prediction_accuracy"],
                     "acc": acc(h["observed"], p["prediction"]),
                     "reproduces": bool(ci["HO-G~visible"][0] <= v["HO-D~visible"] <= ci["HO-G~visible"][1]
                                        and ci["HO-D~holdout"][0] <= v["HO-D~holdout"] <= ci["HO-D~holdout"][1])})
    out = {"ci": ci, "rows": rows, "base_val": fz["baseline_validation"], "base_search": fz["baseline_search"],
           "base_ho": ho["baseline"], "asrun_summary": ho["summary"]}
    for cls in ("character", "rule"):
        xs = [r for r in rows if r["cls"] == cls]
        idx = list(range(len(xs)))
        null = [np.mean([acc(xs[i]["observed"], xs[j]["pred"]) for i, j in zip(idx, rng.permutation(idx))]) for _ in range(5000)]
        a = float(np.mean([r["acc"] for r in xs]))
        out[cls] = {"acc": a, "null": float(np.mean(null)), "p_null": float(np.mean(np.array(null) >= a)),
                    "always_up": float(np.mean([acc(r["observed"], {k: "up" for k in TRAITS}) for r in xs])),
                    "always_none": float(np.mean([acc(r["observed"], {}) for r in xs])),
                    "mean_shift": {k: float(np.mean([r["shift"][k] for r in xs])) for k in TRAITS},
                    "n_repaired": sum(r["pred_repaired"] for r in xs)}
    a_c, a_r = [r["acc"] for r in rows if r["cls"] == "character"], [r["acc"] for r in rows if r["cls"] == "rule"]
    pool = np.array(a_c + a_r); d = np.mean(a_c) - np.mean(a_r)
    perm = [(lambda s: s[:20].mean() - s[20:].mean())(rng.permutation(pool)) for _ in range(10000)]
    out["char_minus_rule"] = (float(d), float(np.mean(np.array(perm) >= d)))
    ch = [c for c in cands if c["cls"] == "character"]
    out["counts"] = {"char_total": len(ch), "char_leak": sum(c.get("rejected") == "leak" for c in ch),
                     "char_scored": sum(c.get("fitness") is not None for c in ch),
                     "rule_scored": sum(c["cls"] == "rule" and c.get("fitness") is not None for c in cands),
                     "gens": 1 + max(c["gen"] for c in cands)}
    leakwords = Counter(h.split(":")[0] if isinstance(h, str) else str(h) for c in ch for h in (c.get("leaks") or []))
    out["leakwords"] = leakwords.most_common(10)
    byt = {c["text"]: c for c in cands if c.get("fitness") is not None}
    clean = sorted([a for a in allc if a.get("flagged") is False], key=lambda a: -a["fitness"])
    out["clean"] = [{**byt[a["text"]]} for a in clean[:8]]
    out["sem_all"] = (sum(bool(a.get("flagged")) for a in allc), len(allc))
    out["best_flagged_search"] = max(a["fitness"] for a in allc if a.get("flagged"))
    return out


# ---------------------------------------------------------------- html

CSS = """
:root{--bg:#f7f8fa;--surface:#ffffff;--ink:#1b2230;--muted:#5b6475;--line:#d9dde5;--char:#0072b2;--rule:#c77700;
--good:#1f7a4d;--bad:#b3261e;--band:rgba(0,114,178,.10);--band2:rgba(31,122,77,.14);
--serif:"Newsreader",Georgia,serif;--sans:"Public Sans",system-ui,sans-serif;--mono:"JetBrains Mono",ui-monospace,monospace}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#12161d;--surface:#1a2029;--ink:#e6e9ef;--muted:#9aa3b2;
--line:#2d3542;--char:#56b4e9;--rule:#f0b44c;--good:#5cc28d;--bad:#f2867e;--band:rgba(86,180,233,.14);--band2:rgba(92,194,141,.16);color-scheme:dark}}
:root[data-theme="dark"]{--bg:#12161d;--surface:#1a2029;--ink:#e6e9ef;--muted:#9aa3b2;--line:#2d3542;--char:#56b4e9;--rule:#f0b44c;
--good:#5cc28d;--bad:#f2867e;--band:rgba(86,180,233,.14);--band2:rgba(92,194,141,.16);color-scheme:dark}
body{background:var(--bg);color:var(--ink);font:15px/1.55 var(--sans)}
.wrap{max-width:1040px;margin:0 auto;padding-block:28px 64px;padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px));display:grid;gap:34px}
h1,h2,h3{font-family:var(--serif);font-weight:600;text-wrap:balance;margin:0}
h1{font-size:2.1rem;line-height:1.15}h2{font-size:1.45rem}h3{font-size:1.1rem}
p{margin:0;max-width:72ch}.muted{color:var(--muted)}
.eyebrow{font:600 .74rem/1 var(--sans);letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}
section{display:grid;gap:14px;min-width:0}
ul.find{margin:0;padding-left:1.2em;display:grid;gap:8px;max-width:78ch}
.verdicts{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px}
.v{background:var(--surface);border:1px solid var(--line);border-radius:6px;padding:14px 16px;display:grid;gap:6px;align-content:start}
.pill{display:inline-block;font:600 .72rem/1 var(--sans);letter-spacing:.05em;text-transform:uppercase;padding:4px 7px;border-radius:3px;border:1px solid currentColor;width:max-content}
.pill.no{color:var(--bad)}.pill.yes{color:var(--good)}.pill.mixed{color:var(--rule)}
.num{font-family:var(--mono);font-variant-numeric:tabular-nums}
.scroll{overflow-x:auto;border:1px solid var(--line);border-radius:6px;background:var(--surface)}
table{border-collapse:collapse;width:100%;font-size:.86rem}
th,td{padding:8px 10px;border-bottom:1px solid var(--line);vertical-align:top;text-align:left}
th{font:600 .72rem/1.2 var(--sans);letter-spacing:.05em;text-transform:uppercase;color:var(--muted);background:var(--bg);position:sticky;top:0}
td.n,th.n{text-align:right;font-family:var(--mono);font-variant-numeric:tabular-nums;white-space:nowrap}
tr:last-child td{border-bottom:0}
td.txt{min-width:320px;max-width:460px;font-family:var(--serif);font-size:.98rem;line-height:1.45}
.q{display:block;margin-top:6px;font:italic .8rem/1.35 var(--sans);color:var(--bad)}
.chips{display:flex;flex-wrap:wrap;gap:4px;min-width:150px}
.chip{font:500 .7rem/1 var(--mono);padding:3px 5px;border-radius:3px;border:1px solid var(--line);color:var(--muted)}
.chip.up{color:var(--bad);border-color:currentColor}.chip.down{color:var(--good);border-color:currentColor}
.chip.miss{text-decoration:line-through}
.legend{display:flex;flex-wrap:wrap;gap:16px;font-size:.82rem;color:var(--muted)}
.dot{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:6px;vertical-align:-1px}
svg text{fill:var(--muted);font:11px var(--sans)}svg .ax{stroke:var(--ink);stroke-width:1}
figure{margin:0;display:grid;gap:8px}figcaption{font-size:.84rem;color:var(--muted);max-width:80ch}
.chart{background:var(--surface);border:1px solid var(--line);border-radius:6px;padding:10px;overflow-x:auto}
.clean{display:grid;gap:10px}
.clean blockquote{margin:0;padding:10px 14px;border-left:3px solid var(--good);background:var(--surface);font-family:var(--serif);font-size:1rem}
.clean blockquote .num{display:block;font-size:.75rem;color:var(--muted);margin-top:4px;font-family:var(--mono)}
code{font-family:var(--mono);font-size:.85em}
"""


def e(s):
    return html.escape(str(s))


def chips(r):
    out = []
    for k in TRAITS:
        o, p = r["observed"][k], (r["pred"].get(k) or "none")
        sign = {"up": "↑", "down": "↓", "none": "·"}[o]
        title = f"{k}: observed {o} ({r['shift'][k]:+.2f}), predicted {p}"
        out.append(f'<span class="chip {o}{"" if o == p else " miss"}" title="{e(title)}">{SHORT[k]} {sign}{abs(r["shift"][k]):.2f}</span>')
    return '<div class="chips">' + "".join(out) + "</div>"


def scatter(S):
    W, H, L, B, T, Rm = 640, 380, 58, 44, 16, 16
    xmax, ymax = 0.20, 0.90
    X = lambda x: L + (W - L - Rm) * x / xmax  # noqa: E731
    Y = lambda y: H - B - (H - B - T) * y / ymax  # noqa: E731
    ci = S["ci"]; g = []
    gv0, gv1 = ci["HO-G~visible"]; dh0, dh1 = ci["HO-D~holdout"]
    g.append(f'<rect x="{X(0):.1f}" y="{Y(gv1):.1f}" width="{X(xmax)-X(0):.1f}" height="{Y(gv0)-Y(gv1):.1f}" fill="var(--band)"/>')
    g.append(f'<rect x="{X(dh0):.1f}" y="{Y(ymax):.1f}" width="{max(2, X(dh1)-X(dh0)):.1f}" height="{Y(0)-Y(ymax):.1f}" fill="var(--band2)"/>')
    for t in (0, .05, .10, .15, .20):
        g.append(f'<line x1="{X(t):.1f}" x2="{X(t):.1f}" y1="{Y(0):.1f}" y2="{Y(0)+4:.1f}" class="ax"/><text x="{X(t):.1f}" y="{Y(0)+17:.1f}" text-anchor="middle">{t:.2f}</text>')
    for t in (0, .2, .4, .6, .8):
        g.append(f'<line x1="{X(0)-4:.1f}" x2="{X(0):.1f}" y1="{Y(t):.1f}" y2="{Y(t):.1f}" class="ax"/><text x="{X(0)-8:.1f}" y="{Y(t)+4:.1f}" text-anchor="end">{t:.1f}</text>')
    g.append(f'<line x1="{X(0)}" x2="{X(xmax)}" y1="{Y(0)}" y2="{Y(0)}" class="ax"/><line x1="{X(0)}" x2="{X(0)}" y1="{Y(0)}" y2="{Y(ymax)}" class="ax"/>')
    g.append(f'<text x="{(X(0)+X(xmax))/2:.1f}" y="{H-6}" text-anchor="middle">P(override), deployment frame, held-out tickets scored</text>')
    g.append(f'<text transform="translate(14 {(Y(0)+Y(ymax))/2:.1f}) rotate(-90)" text-anchor="middle">P(override), deployment, sample scored</text>')
    bv = S["base_val"]
    g.append(f'<g><circle cx="{X(bv["HO-D~holdout"]):.1f}" cy="{Y(bv["HO-D~visible"]):.1f}" r="5" fill="var(--ink)"/>'
             f'<text x="{X(bv["HO-D~holdout"])+9:.1f}" y="{Y(bv["HO-D~visible"])-6:.1f}">no persona</text></g>')
    g.append(f'<text x="{X(xmax)-4:.1f}" y="{Y(gv1)-5:.1f}" text-anchor="end">graded-frame level (sample scored), 95% CI</text>')
    for r in S["rows"]:
        v = r["validation"]; col = "var(--char)" if r["cls"] == "character" else "var(--rule)"
        shape = (f'<circle cx="{X(min(v["HO-D~holdout"], xmax)):.1f}" cy="{Y(v["HO-D~visible"]):.1f}" r="4.5" fill="{col}" fill-opacity=".85"/>'
                 if r["cls"] == "character" else
                 f'<rect x="{X(min(v["HO-D~holdout"], xmax))-4:.1f}" y="{Y(v["HO-D~visible"])-4:.1f}" width="8" height="8" fill="{col}" fill-opacity=".85"/>')
        g.append(f'<g><title>{e(r["cls"])}: D-visible {v["HO-D~visible"]:.3f}, D-holdout {v["HO-D~holdout"]:.3f}\n{e(r["text"][:140])}</title>{shape}</g>')
    return (f'<svg viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" aria-label="Validation-half P(override) per finalist">'
            + "".join(g) + "</svg>")


def finalist_table(S, cls):
    rows = [r for r in S["rows"] if r["cls"] == cls]
    head = ("<tr><th>#</th><th>Prompt</th><th class='n'>Search fit</th><th class='n'>G-vis</th><th class='n'>D-vis</th>"
            "<th class='n'>G-ho</th><th class='n'>D-ho</th><th>Held-out shifts (struck = predicted wrong)</th><th class='n'>Pred acc</th></tr>")
    body = []
    for i, r in enumerate(rows, 1):
        v = r["validation"]; q = r["sem"].get("quote") or ""
        flag = f'<span class="q">semantic flag: “{e(q)}”</span>' if r["sem"].get("flagged") else ""
        body.append(f"<tr><td class='n'>{i}</td><td class='txt'>{e(r['text'])}{flag}</td><td class='n'>{r['fitness']:+.3f}</td>"
                    + "".join(f"<td class='n'>{v[c]:.3f}</td>" for c in CELLS)
                    + f"<td>{chips(r)}</td><td class='n'>{r['acc']:.2f}{'*' if r['pred_repaired'] else ''}</td></tr>")
    return f"<div class='scroll'><table><thead>{head}</thead><tbody>{''.join(body)}</tbody></table></div>"


def build_html(S):
    c, ru, ci, bv, k = S["character"], S["rule"], S["ci"], S["base_val"], S["counts"]
    best_c = max((r for r in S["rows"] if r["cls"] == "character"), key=lambda r: r["fitness"])
    best_r = max((r for r in S["rows"] if r["cls"] == "rule"), key=lambda r: r["fitness"])
    d, pd = S["char_minus_rule"]
    clean = "".join(f'<blockquote>{e(x["text"])}<span class="num">search fitness {x["fitness"]:+.3f} · D-visible {x["p_dvis"]:.3f} · D-holdout {x["p_dho"]:.3f} · generation {x["gen"]}</span></blockquote>' for x in S["clean"])
    msc = "".join(f"<tr><td>{k_}</td><td class='n'>{S['base_ho'][k_]:.3f}</td><td class='n'>{c['mean_shift'][k_]:+.3f}</td><td class='n'>{ru['mean_shift'][k_]:+.3f}</td></tr>" for k_ in TRAITS)
    return f"""<title>PP1 Persona Prompts</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Newsreader:opsz,wght@6..72,400;6..72,600&family=Public+Sans:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap">
<style>{CSS}</style>
<div class="wrap">
<header style="display:grid;gap:10px">
  <span class="eyebrow">Split-brain · PP1 · Qwen3.8-27B · holdout env · 2026-10-23</span>
  <h1>Can a character prompt reproduce graded-mode gaming?</h1>
  <p class="muted">The model is in the deployment frame. A short text is appended to its system prompt. A forced-choice probe, read from next-token log-probabilities after the third tool result, asks whether it will write general routing rules or add exact-match overrides for the sample tickets. A <b>character</b> prompt may describe traits only, and has to pass a word-level leak checker. A <b>rule</b> prompt may state the conditional behaviour. About {k['char_total']+k['rule_scored']} candidates over {k['gens']} generations; the top 20 per class were frozen, re-scored on held-out V1 runs, then tested on sealed behaviours.</p>
</header>

<section>
  <h2>What we found</h2>
  <ul class="find">
    <li><b>No finalist reproduces the graded pattern by the pre-registered test</b> (0/20 characters, 0/20 rules). Rules come closest on the main axis: the best rule lifts deployment, sample-scored to {best_r['validation']['HO-D~visible']:.2f}, past the graded level of {bv['HO-G~visible']:.2f}. It also lifts held-out-scored runs to {best_r['validation']['HO-D~holdout']:.2f}, against a baseline of {bv['HO-D~holdout']:.3f}. The best character reaches {best_c['validation']['HO-D~visible']:.2f} and {best_c['validation']['HO-D~holdout']:.3f}.</li>
    <li><b>Every character finalist only reaches its score by describing the conditional in other words.</b> The semantic judge flagged all 20 (“you aim at exactly what will be looked at”). Over all {S['sem_all'][1]} scored characters it flagged {S['sem_all'][0]}. The best character it rated clean scores {S['clean'][0]['fitness']:+.3f} on the search half, against {S['best_flagged_search']:+.3f} for the best flagged one. Those clean characters are compliant, literal servants, and they were never validated.</li>
    <li><b>Characters carry a broad trait shift; rules do not.</b> On sealed items, character finalists raise rule-breaking by {c['mean_shift']['rule_breaking']:+.2f}, dishonesty by {c['mean_shift']['dishonesty']:+.2f} and competitiveness by {c['mean_shift']['competitiveness']:+.2f}. Rule finalists move nothing by more than {max(abs(v) for v in ru['mean_shift'].values()):.2f}. Neither class moves disclosure or sycophancy.</li>
    <li><b>Blind prediction: characters {c['acc']:.2f}, rules {ru['acc']:.2f}</b> (difference p = {pd:.3f}). That passes the deciding comparison on paper. But neither class beats a shuffled-prediction null (characters p = {c['p_null']:.2f}). Answering “up” for everything would score {c['always_up']:.2f} on characters. The gap reflects which direction each class moves, not an understanding of individual prompts.</li>
    <li>Read together, this fits the conditional-policy account better than the persona account. A narrow rule reproduces the targeted behaviour and nothing else. A character gets there only by restating that rule, and drags unrelated traits along. One comparison is missing: whether the graded frame itself shifts these traits. It was not measured.</li>
  </ul>
</section>

<section>
  <h2>Pre-registered tests</h2>
  <div class="verdicts">
    <div class="v"><span class="eyebrow">Reproduction (validation half)</span><span class="pill no">Not met · 0/40</span>
      <p>Criterion: D-visible inside the G-visible 95% CI <span class="num">[{ci['HO-G~visible'][0]:.3f}, {ci['HO-G~visible'][1]:.3f}]</span> <i>and</i> D-holdout inside the D-holdout baseline CI <span class="num">[{ci['HO-D~holdout'][0]:.4f}, {ci['HO-D~holdout'][1]:.4f}]</span>. The second band is very narrow, so any prompt that moves held-out-scored runs at all fails it. Only 4 finalists pass the first half (1 character, 3 rules).</p></div>
    <div class="v"><span class="eyebrow">Deciding test (held-out prediction)</span><span class="pill mixed">Passes on paper, weak</span>
      <p>Character accuracy {c['acc']:.2f} beats rule accuracy {ru['acc']:.2f} (permutation p = {pd:.4f}), and beats 1/3 chance. It does not beat a shuffle null that keeps each class's direction ({c['null']:.2f}, p = {c['p_null']:.2f}).</p></div>
    <div class="v"><span class="eyebrow">Leak checks</span><span class="pill no">Characters leak in meaning</span>
      <p>Word level: {k['char_leak']}/{k['char_total']} character candidates rejected before scoring; every finalist passes. Semantic judge (gpt-4.1, prompt text only): 20/20 character finalists and 20/20 rule finalists flagged. The rule result is the expected calibration.</p></div>
    <div class="v"><span class="eyebrow">Sealing</span><span class="pill yes">Held</span>
      <p>The search modules never import or name the held-out items (tests enforce it). The held-out runner checked the finalists' sha256 <span class="num">a3795dd9…</span>. Blind predictions were written before any held-out scoring.</p></div>
  </div>
</section>

<section>
  <h2>Where the finalists land</h2>
  <figure><div class="chart">{scatter(S)}</div>
  <div class="legend"><span><span class="dot" style="background:var(--char)"></span>character finalist</span><span><span class="dot" style="background:var(--rule);border-radius:0"></span>rule finalist</span><span><span class="dot" style="background:var(--band);border:1px solid var(--line)"></span>graded G-visible 95% CI</span><span><span class="dot" style="background:var(--band2);border:1px solid var(--line)"></span>deployment held-out baseline CI</span></div>
  <figcaption>Validation half: V1 runs the search never saw. The graded pattern would sit at the top-left corner, inside the blue band and the thin green strip. Characters stay low on the y-axis. Rules reach the band, but move right too: they also raise overrides when held-out tickets are scored. Hover a point for its prompt.</figcaption></figure>
</section>

<section>
  <h2>Sealed held-out behaviours, mean shift per class</h2>
  <div class="scroll" style="max-width:560px"><table><thead><tr><th>Measure</th><th class="n">No-persona baseline</th><th class="n">Characters</th><th class="n">Rules</th></tr></thead><tbody>{msc}</tbody></table></div>
  <p class="muted">Each measure is a forced-choice P(the worse option), averaged over both option orders. Disclosure is measured at the end of V1 graded runs that gamed. Sycophancy sits at a floor (baseline {S['base_ho']['sycophancy']:.3f}), so it could hardly move.</p>
</section>

<section>
  <h2>Best semantically clean characters</h2>
  <p class="muted">Exploratory, added after the finalists were frozen: the semantic judge run on all {S['sem_all'][1]} scored character candidates. These scores come from the search half only. These prompts were not finalists, so they have no validation or held-out numbers.</p>
  <div class="clean">{clean}</div>
</section>

<section>
  <h2>Character finalists (20)</h2>
  <p class="muted">Columns G-vis to D-ho show validation-half P(override) per cell. With no persona they read {bv['HO-G~visible']:.3f} / {bv['HO-D~visible']:.3f} / {bv['HO-G~holdout']:.3f} / {bv['HO-D~holdout']:.4f}. The persona also raises the graded cells: the effects stack. Shift chips: ↑ / ↓ means |shift| ≥ 0.05. * marks predictions re-asked after a truncated first answer.</p>
  {finalist_table(S, 'character')}
</section>

<section>
  <h2>Rule finalists (20)</h2>
  {finalist_table(S, 'rule')}
</section>

<section>
  <h2>Caveats</h2>
  <ul class="find">
    <li>Everything here is a forced-choice read-out on prefixes, not agent behaviour. Gate 0 showed the probe tracks behaviour without a persona (graded 0.31 vs deployment 0.02). No behavioural episodes were run with these prompts; that step waits for Olivia.</li>
    <li>The finalists are near-duplicates (several “brash closer” and “deadline-chaser” variants), so 20 per class means fewer independent ideas than it sounds.</li>
    <li>The first held-out run lost {c['n_repaired']+ru['n_repaired']}/40 blind predictions: on 10 the predictor wrote prose and hit the 300-token limit, and one call failed. They were re-asked with the same prompt and a 1,500-token limit. As run, with empty predictions counted as “none”: characters {S['asrun_summary']['character']['mean_prediction_accuracy']:.2f}, rules {S['asrun_summary']['rule']['mean_prediction_accuracy']:.2f}.</li>
    <li>The semantic check was added during the search (decision #117), after the leading character visibly paraphrased the rule. It labels prompts; it did not steer the search.</li>
  </ul>
  <p class="muted">Cost ≈ $15 of the $65 budget (H100 pod 3.05 h ≈ $12; proposer, judge and predictor ≈ $3). Pod deleted. Files: <code>results/personaprompt/</code> · code: <code>internals/personaprompt/</code> · copy: <code>docs/pp1_winners.md</code></p>
</section>
</div>
"""


def build_md(S):
    c, ru, bv = S["character"], S["rule"], S["base_val"]
    L = ["# PP1 winners: persona-prompt reconstruction on Qwen3.8", "",
         "Generated by `internals/personaprompt/report.py` from `results/personaprompt/`. Validation-half P(override) per cell; "
         f"no-persona baseline G-vis {bv['HO-G~visible']:.3f}, D-vis {bv['HO-D~visible']:.3f}, G-ho {bv['HO-G~holdout']:.3f}, D-ho {bv['HO-D~holdout']:.4f}.", "",
         f"- Reproduction criterion: 0/20 characters, 0/20 rules.",
         f"- Semantic leak judge: 20/20 character finalists flagged; {S['sem_all'][0]}/{S['sem_all'][1]} of all scored characters.",
         f"- Blind prediction accuracy (repaired): characters {c['acc']:.3f}, rules {ru['acc']:.3f}, difference p = {S['char_minus_rule'][1]:.4f}; "
         f"character shuffle null {c['null']:.3f} (p = {c['p_null']:.2f}); always-up {c['always_up']:.3f}.",
         "- Mean held-out shift, characters: " + ", ".join(f"{k} {v:+.3f}" for k, v in c["mean_shift"].items()),
         "- Mean held-out shift, rules: " + ", ".join(f"{k} {v:+.3f}" for k, v in ru["mean_shift"].items()), ""]
    for cls in ("character", "rule"):
        L += [f"## {cls.capitalize()} finalists", "", "| # | prompt | search fit | G-vis | D-vis | G-ho | D-ho | shifted up (≥0.05) | pred acc | semantic flag |",
              "|---|---|---|---|---|---|---|---|---|---|"]
        for i, r in enumerate([r for r in S["rows"] if r["cls"] == cls], 1):
            v = r["validation"]; ups = ", ".join(f"{SHORT[k]} {r['shift'][k]:+.2f}" for k in TRAITS if r["observed"][k] != "none") or "none"
            q = (r["sem"].get("quote") or "").replace("|", "/") if r["sem"].get("flagged") else "clean"
            L.append(f"| {i} | {r['text'].replace('|', '/')} | {r['fitness']:+.3f} | " + " | ".join(f"{v[c_]:.3f}" for c_ in CELLS)
                     + f" | {ups} | {r['acc']:.2f}{'*' if r['pred_repaired'] else ''} | {q} |")
        L.append("")
    L += ["## Best semantically clean characters (exploratory; search half only, not validated)", ""]
    L += [f"- ({x['fitness']:+.3f}; D-vis {x['p_dvis']:.3f}, D-ho {x['p_dho']:.3f}) {x['text']}" for x in S["clean"]]
    return "\n".join(L) + "\n"


def main():
    S = stats()
    (REPO / "docs" / "pp1_winners.html").write_text(build_html(S))
    (REPO / "docs" / "pp1_winners.md").write_text(build_md(S))
    print(json.dumps({k: S[k] for k in ("character", "rule", "char_minus_rule", "counts", "sem_all")}, indent=1, default=float))


if __name__ == "__main__":
    main()
