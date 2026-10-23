#!/usr/bin/env python3
"""DD2 pre-launch checks: tokenisation drift at the patch sites, hash-swap token counts, excluded pairs, decoded
sites, trait probe spans. Writes results/dd2/review_checks.md.  python internals/dd2/checks.py"""
import json, sys, difflib, re, collections
from tokenizers import Tokenizer
sys.path.insert(0, 'internals/dd2'); import counterfactual as CF
tok = Tokenizer.from_file('../sbpsmanalysis/artifacts/model_snapshot/tokenizer.json'); enc = lambda t: tok.encode(t, add_special_tokens=False).ids
rows = [json.loads(l) for l in open('results/dd2/prompts.jsonl')]
hdr = rows[0]; V = {(r['eid'], r['version']): r for r in rows if r['kind'] == 'version'}; pairs = [r for r in rows if r['kind'] == 'pair']
stub_n = max(len(enc(hdr['stub'][o])) for o in ('AB', 'BA')); GEN = 7; nA = stub_n + GEN; nB = nA + 64
out = []; P = lambda *a: out.append(' '.join(str(x) for x in a))
def csuf(a, b):
    k = 0
    while k < min(len(a), len(b)) and a[-1-k] == b[-1-k]: k += 1
    return k
# 1. drift: full R1 sequences (prefix + stub), both orders; site must be inside the token-identical suffix
P('## 1. Tokenisation drift: are the patch sites token-identical in both versions, aligned from the end?')
stats = collections.defaultdict(list); fails = []
for p in pairs:
    cv, ov = V[(p['eid'], p['cue_version'])], V[(p['eid'], p['other_version'])]
    for o in ('AB', 'BA'):
        a, b = enc(cv['r1_prefix'] + hdr['stub'][o]), enc(ov['r1_prefix'] + hdr['stub'][o])
        cs = csuf(a, b); stats[p['set']].append((len(a) - len(b), cs))
        stub_ok = a[-len(enc(hdr['stub'][o])):] == enc(hdr['stub'][o])  # stub tokenises the same at the boundary
        if cs < nA or not stub_ok: fails.append((p['set'], p['eid'][:8], o, cs, stub_ok))
for s, v in stats.items():
    ld = [x for x, _ in v]; P(f'- {s}: length difference between versions (tokens) min {min(ld)} max {max(ld)}; common suffix min {min(c for _, c in v)}; site A = {nA} tokens, site B = {nB} tokens')
P(f'- pairs × orders where site A is NOT inside the identical suffix, or the stub tokenises differently at the boundary: {len(fails)} {fails[:5]}')
# 2. hash swaps: token length changes
P('\n## 2. Commit-hash swaps: do they change token counts?')
for g, d in CF.FRAME_HASHES:
    for n in (7, 40):
        P(f'- {g[:n]} → {d[:n]}: {len(enc(g[:n]))} → {len(enc(d[:n]))} tokens (in context " {g[:7]} README": {len(enc(" " + g[:n] + " x"))} vs {len(enc(" " + d[:n] + " x"))})')
P('- Any length change shifts absolute positions only; patch positions are counted from the end and asserted inside the identical suffix (check 1), so they cannot move.')
# 3. excluded pairs
P('\n## 3. The excluded pairs: why does site B not fit?')
for p in pairs:
    cv, ov = V[(p['eid'], p['cue_version'])], V[(p['eid'], p['other_version'])]
    a, b = enc(cv['r1_prefix']), enc(ov['r1_prefix']); cs = csuf(a, b)
    if cs + stub_n < nB:
        sm = difflib.SequenceMatcher(a=a, b=b, autojunk=False); last = [op for op in sm.get_opcodes() if op[0] != 'equal'][-1]
        P(f'- {p["set"]} {p["eid"][:8]} ({p["cell"]}): identical suffix {cs} prefix tokens (+ stub) < {nB}; last differing span decodes as {tok.decode(a[last[1]:last[2]])!r} → {tok.decode(b[last[3]:last[4]])!r}, {len(a) - last[2]} tokens before the end; final tool output starts {tok.decode(a[-cs-40:-cs])!r}')
# 4. decoded sites
P('\n## 4. Decoded patch sites (site B: last 64 prefix tokens + generation prompt + read-out stub), 3 per set, AB order')
for s in ('scoring', 'mood', 'full'):
    for p in [q for q in pairs if q['set'] == s][:3]:
        ov = V[(p['eid'], p['other_version'])]; seq = enc(ov['r1_prefix'] + hdr['stub']['AB'])
        site = tok.decode(seq[-nB:]); gen = tok.decode(seq[-(stub_n + GEN):-stub_n])
        P(f'- {s} {p["eid"][:8]}: generation prompt in the site = {gen!r}; site B begins …{tok.decode(seq[-nB:-nB+12])!r}; ends …{tok.decode(seq[-12:])!r}')
# traits probe span
P('\n## 5. Trait read-out site (user-probe span), all mood pairs')
bad = 0; lens = []
for p in [q for q in pairs if q['set'] == 'mood']:
    cv, ov = V[(p['eid'], p['cue_version'])], V[(p['eid'], p['other_version'])]
    for it in hdr['traits'][:8]:
        a = enc(cv['r2_head'] + it['text'] + cv['r2_tail']); b = enc(ov['r2_head'] + it['text'] + ov['r2_tail'])
        n = len(b) - len(enc(ov['r2_head'])); lens.append(n); bad += a[-n:] != b[-n:]
P(f'- probe spans checked: {len(lens)}; span length {min(lens)}–{max(lens)} tokens; spans that differ between versions: {bad}')
print('\n'.join(out))
open('results/dd2/review_checks.md', 'w').write('# DD2 pre-launch checks (automated)\n\n' + '\n'.join(out) + '\n')
