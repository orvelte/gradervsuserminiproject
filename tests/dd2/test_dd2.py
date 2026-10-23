"""DD2: subspace decision rules on synthetic data; counterfactual swaps on the real V1 cue texts."""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "internals" / "dd2"))
import dd2_analyze as A  # noqa: E402
import counterfactual as CF  # noqa: E402


def block(effects, n=6, rand=0.1):
    """effects: {cond: (override_recovered, ON_recovered)} applied to both target sets."""
    base, res = [], {}
    for tset in ("scoring", "mood"):
        for i in range(n):
            base.append({"set": tset, "eid": f"{tset}{i}", "ovr_src": 0.6, "ovr_tgt": 0.1, "ON_src": 0.5, "ON_tgt": 0.3,
                         "OFF_src": 0.1, "OFF_tgt": 0.1, "mass_tgt": 0.8})
    conds = {**effects, **{f"rand{j}": (rand, rand) for j in range(20)}}
    for k, (fo, fn) in conds.items():
        res[k] = [{"set": b["set"], "eid": b["eid"], "override": 0.1 + 0.5 * fo, "ON": 0.3 + 0.2 * fn, "OFF": 0.1,
                   "override_mass": 0.8, "trait_mass": 0.8} for b in base]
    return {"L": 32, "base": base, "results": res}


def test_double_dissociation():
    eff = {"full": (1, 1), "d_scoring": (0.7, 0.05), "d_mood": (0.05, 0.7)}
    v = A.subspace_verdict({"scoring": block(eff), "mood": block(eff)})
    assert v["verdict"] == "double dissociation"


def test_partial_when_mood_dir_also_carries_gaming():
    eff = {"full": (1, 1), "d_scoring": (0.7, 0.05), "d_mood": (0.6, 0.7)}
    v = A.subspace_verdict({"scoring": block(eff), "mood": block(eff)})
    assert v["verdict"] == "partial" and v["scoring_side"] and not v["mood_side"]


def test_randoms_set_the_bar():
    eff = {"full": (1, 1), "d_scoring": (0.6, 0.05), "d_mood": (0.05, 0.6)}
    v = A.subspace_verdict({"scoring": block(eff, rand=0.65), "mood": block(eff, rand=0.65)})
    assert v["verdict"] == "neither"


def test_recovered_fraction():
    b = block({"full": (1, 1)})
    assert abs(A.recovered(b["results"]["full"], b["base"], "scoring", "override") - 1.0) < 1e-9
    assert abs(A.recovered(b["results"]["rand0"], b["base"], "mood", "ON") - 0.1) < 1e-9


def _prefixes():
    f = REPO.parent / "sbpsmanalysis" / "data" / "prefixes_final_rubric.jsonl"
    return [json.loads(l) for l in f.read_text().splitlines()] if f.exists() else []


def test_scoring_swap_changes_one_sentence_only():
    P = [p for p in _prefixes() if p["arm"] == "HO-G~visible"]
    for p in P:
        sw = CF.swap_messages(p["messages"], "HO-G~visible", "HO-G~holdout")
        changed = [i for i, (a, b) in enumerate(zip(p["messages"], sw)) if a.get("content") != b.get("content")]
        assert changed == [3], changed
        assert all(a == b for i, (a, b) in enumerate(zip(p["messages"], sw)) if i >= CF.N_CUE and a["role"] == "assistant")


def test_frame_swap_leaves_model_messages_and_no_source_cues():
    for src, dst in (("HO-G~holdout", "HO-D~holdout"), ("HO-D~holdout", "HO-G~holdout"), ("HO-G~visible", "HO-D~visible"), ("HO-D~visible", "HO-G~visible")):
        for p in [q for q in _prefixes() if q["arm"] == src]:
            sw = CF.swap_messages(p["messages"], src, dst)
            assert not CF.residual_markers(sw, src, dst)["non_assistant"], p["episode_id"]
            for i, (a, b) in enumerate(zip(p["messages"], sw)):
                if i >= CF.N_CUE and a["role"] == "assistant":
                    assert a == b


def test_hash_swap():
    s = "commit 6029f5fe608c02daab2abe45b0fa978ddb5b431f\n6029f5f README\nabc1234 untouched"
    t = CF._swap_hashes(s, "HO-G~holdout", "HO-D~holdout")
    assert "a01ba3d546fc45d1bf8831d45f4d0af3f0a1227f" in t and "a01ba3d README" in t and "abc1234 untouched" in t
    assert CF._swap_hashes(s, "HO-G~visible", "HO-G~holdout") == s
