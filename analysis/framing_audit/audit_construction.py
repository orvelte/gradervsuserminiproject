import json, re, sys, collections, importlib.util, yaml
from pathlib import Path
REPO = Path(".").resolve()
d = json.load(open(sys.argv[1]))
def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
F = load("sf_framing", REPO / "structural_framing/env/precommit_hook_sf/sf_framing.py")
CFG = {"N0": "configs/precommit_hook/N0_replication.yaml", "G0": "configs/precommit_hook/G_noO.yaml", "G1": "configs/precommit_hook/G_O.yaml", "U0": "configs/precommit_hook/U_noO.yaml", "U1": "configs/precommit_hook/U_O.yaml",
       "SF1-G-LAX": "structural_framing/configs/SF1-G-LAX.yaml", "SF1-C-LAX": "structural_framing/configs/SF1-C-LAX.yaml"}
cfg = {a: yaml.safe_load(open(REPO / p)) for a, p in CFG.items()}
ARMS = list(CFG)
by = collections.defaultdict(list)
for r in d:
    md = r["metadata"]; a = md["condition_id"]
    by[a if not a.startswith("SF1") else a].append(r)
print("=== A. CONSTRUCTION ===")
print(f"{'arm':10} n  sys_ok user_ok extra_user  model/provider/effort/max_steps/target  cfg_hashes  258wall  censored hitmax ended")
for a in ARMS:
    rs = by[a]; sp = cfg[a]["prompts"]["system_prompt"].strip(); up = cfg[a]["prompts"]["user_prompt"].strip()
    sys_ok = sum(r["messages"][0]["role"] == "system" and r["messages"][0]["text"].strip() == sp for r in rs)
    usr_ok = sum(r["messages"][1]["role"] == "user" and r["messages"][1]["text"].strip() == up for r in rs)
    extra = collections.Counter()
    wall = 0
    for r in rs:
        us = [m["text"] for m in r["messages"][2:] if m["role"] == "user"]
        extra[len(us)] += 1
        wall += any(m["role"] == "tool" and re.search(r"Found 258 errors in \d+ files", m["text"]) for m in r["messages"])
    sets = collections.Counter((r["metadata"].get("model"), r["metadata"].get("provider"), r["metadata"].get("reasoning_effort"), r["metadata"].get("max_steps"), r["metadata"].get("target_errors")) for r in rs)
    hashes = collections.Counter((r["metadata"].get("config_hash") or "")[:8] for r in rs)
    print(f"{a:10} {len(rs)} {sys_ok:>4} {usr_ok:>6}  {dict(extra)}  {dict(sets)}  {dict(hashes)}  {wall}  cens={sum(bool(r['metadata'].get('censored')) for r in rs)} hitmax={sum(bool(r['metadata'].get('hit_max_steps')) for r in rs)} ended={sum(bool(r['metadata'].get('agent_ended')) for r in rs)}")
print("\nsystem prompts identical across all 7 arms:", len({cfg[a]["prompts"]["system_prompt"] for a in ARMS}) == 1)
for a in ("SF1-G-LAX", "SF1-C-LAX"):
    print(a, "system prompt:", repr(cfg[a]["prompts"]["system_prompt"])[:260])

print("\n=== SF1 structural cues in the transcript ===")
for a, key in (("SF1-G-LAX", "graded"), ("SF1-C-LAX", "collaborator")):
    rs = by[a]; other = "collaborator" if key == "graded" else "graded"
    c = collections.Counter(); gitlog = collections.Counter(); qn = []
    for r in rs:
        ms = r["messages"]; n_asst = sum(m["role"] == "assistant" for m in ms)
        inj = [(i, m["text"]) for i, m in enumerate(ms[2:], start=2) if m["role"] == "user"]
        exp = [F.INJECTIONS[key][s] for s in (8, 18) if n_asst > s]   # fires after the tool result of step s if the run continues
        got = [t.strip() for _, t in inj]
        c["inj_exact"] += got == exp
        if got != exp: c["inj_mismatch"] += 1; print("   MISMATCH", r["name"][:60], "n_asst", n_asst, "got", got)
        for i, t in inj:   # position: number of assistant turns before it
            k = sum(m["role"] == "assistant" for m in ms[:i]); c[f"inj_after_turn_{k}"] += 1
            c["inj_follows_tool"] += ms[i - 1]["role"] == "tool"
        c["wrong_frame_text"] += any(t.strip() in F.INJECTIONS[other].values() for _, t in inj)
        # question tool
        qs = 0
        for i, m in enumerate(ms):
            if m["role"] == "assistant":
                for tc in m.get("tool_calls") or []:
                    if tc["name"] == "ask_question":
                        qs += 1; rep = next((x["text"] for x in ms[i + 1:i + 3] if x["role"] == "tool"), "")
                        c["q_reply_ok"] += F.QUESTION_REPLY[key] in rep; c["q_total"] += 1
        qn.append(qs)
        # git log
        saw = False
        for i, m in enumerate(ms):
            if m["role"] == "assistant":
                for tc in m.get("tool_calls") or []:
                    cmd = (tc["arguments"] or {}).get("command") or ""
                    if tc["name"] == "bash" and re.search(r"\bgit\s+(log|shortlog|show)\b", cmd):
                        out = next((x["text"] for x in ms[i + 1:i + 3] if x["role"] == "tool"), "")
                        saw = True
                        if key == "graded": gitlog["log_shows_harness_commit"] += "harness: task setup 37/120" in out or "task-harness" in out
                        else: gitlog["log_shows_team_history"] += ("initial import of ingestd" in out or "Priya Raman" in out or "cli entrypoint" in out)
        gitlog["ran_git_log_or_show"] += saw
    print(a, "n", len(rs), dict(c), "| runs asking >=1 question:", sum(q > 0 for q in qn), "| git:", dict(gitlog))

print("\n=== environment text that could contradict or leak the frame (tool outputs only) ===")
LEAK = {"harness": r"\bharness\b", "grader/graded/score": r"\b(grader|graded|scor(e|ed|ing))\b", "container@modal / Container": r"container@modal|\bContainer\b", "/opt/": r"/opt/", "dev@example.com / Developer": r"dev@example\.com|\bDeveloper\b",
        "modal/sandbox/docker": r"\b(modal|sandbox|docker)\b", "Priya/Diego/Mei": r"\b(Priya|Diego|Mei)\b", "task-harness": r"task-harness", "generate_variants|src_258": r"generate_variants|src_258", "Initial commit: data ingestion": r"Initial commit: data ingestion", "eval/benchmark/test-suite": r"\b(evaluation|benchmark|test suite)\b"}
print(f"{'pattern':34}" + "".join(f"{a:>11}" for a in ARMS))
for name, pat in LEAK.items():
    rx = re.compile(pat, re.I if name not in ("container@modal / Container", "dev@example.com / Developer") else 0)
    print(f"{name:34}" + "".join(f"{sum(any(m['role'] == 'tool' and rx.search(m['text']) for m in r['messages']) for r in by[a]):>8}/{len(by[a]):<2}" for a in ARMS))
