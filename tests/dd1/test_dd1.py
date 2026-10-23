"""DD1 decision rules (PREREG DD1) on synthetic deltas, and the build's single-factor contrasts."""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "internals" / "dd1"))
import analyze as A  # noqa: E402


def make(mood=(0.0, 0.0, 0.0), scoring=(0.0, 0.0, 0.0), grader=(0.0, 0.0, 0.0), ff=0.1, rand=(0.01, 0.01, 0.01), mass=0.99):
    def d(o, on, off):
        return {"override": o, "ON": on, "OFF": off, "mass": mass}
    D = {"base": d(0, 0, 0), "fullframe@1.0": d(ff, 0, 0), "fullframe@2.0": d(ff, 0, 0)}
    for k, v in (("mood", mood), ("scoring", scoring), ("grader", grader)):
        for a in ("0.5", "1.0", "2.0", "4.0"):
            D[f"{k}@{a}"] = d(*v)
        for j in range(8):
            for a in ("1.0", "2.0"):
                D[f"rand{j}~{k}@{a}"] = d(*rand)
    coh = {c: 3.0 for c in D if not c.startswith("rand")}
    return D, coh


def test_double_dissociation():
    D, coh = make(mood=(0.0, 0.12, 0.0), scoring=(0.2, 0.01, 0.0))
    assert A.verdict(D, coh)["verdict"] == "double dissociation"


def test_partial_when_mood_also_moves_gaming():
    D, coh = make(mood=(0.15, 0.12, 0.0), scoring=(0.2, 0.01, 0.0))
    v = A.verdict(D, coh)
    assert v["verdict"] == "partial" and v["scoring_passes"] and not v["mood_passes"]


def test_uninformative_without_positive_control():
    D, coh = make(mood=(0.0, 0.12, 0.0), scoring=(0.2, 0.01, 0.0), ff=0.01)
    assert A.verdict(D, coh)["verdict"].startswith("uninformative")


def test_random_directions_set_the_bar():
    D, coh = make(mood=(0.0, 0.12, 0.0), scoring=(0.2, 0.01, 0.0), rand=(0.25, 0.15, 0.0))
    assert A.verdict(D, coh)["verdict"] == "no dissociation"


def test_incoherent_alpha2_falls_back_to_alpha1():
    D, coh = make(mood=(0.0, 0.12, 0.0), scoring=(0.2, 0.01, 0.0))
    coh["mood@2.0"] = 1.0
    v = A.verdict(D, coh)
    assert v["mood"]["level"] == 1.0 and v["verdict"] == "double dissociation"


def test_grader_bundle():
    D, coh = make(mood=(0.0, 0.12, 0.0), scoring=(0.2, 0.01, 0.0), grader=(0.1, 0.1, 0.09))
    assert A.verdict(D, coh)["grader_verdict"] == "steering produces the bundle"


def test_deltas_and_per_prefix():
    rows = []
    for cond, shift in (("base", 0.0), ("x", 0.2)):
        for run in ("r1", "r2"):
            rows.append({"cond": cond, "run": run, "measure": "override", "worse": "B", "pA": 0.8 - shift, "pB": 0.2 + shift})
            for m in A.TRAITS:
                rows.append({"cond": cond, "run": run, "measure": m, "worse": "A", "pA": 0.3, "pB": 0.7})
    D = A.deltas(A.per_prefix(rows))
    assert abs(D["x"]["override"] - 0.2) < 1e-9 and abs(D["x"]["ON"]) < 1e-9 and abs(D["x"]["mass"] - 1.0) < 1e-9


def test_build_contrasts_are_as_preregistered():
    f = REPO / "results" / "dd1" / "prompts.jsonl"
    if not f.exists():
        return
    import difflib
    I = {r["cell"]: r["text"] for r in map(json.loads, f.read_text().splitlines()) if r["kind"] == "initial"}
    diff = [l for l in difflib.unified_diff(I["HO-G~visible"].splitlines(), I["HO-G~holdout"].splitlines(), lineterm="", n=0)
            if l[:1] in "+-" and l[:3] not in ("+++", "---")]
    assert len(diff) == 2 and all("Your score for this task is" in l for l in diff)
    assert all(t.endswith("<|im_start|>assistant\n<think>\n") for t in I.values())
