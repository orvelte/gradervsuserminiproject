"""BX decision rules on synthetic effects."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "internals" / "bx"))
import bx_analyze as A  # noqa: E402

B6 = {"machiavellianism": {"diff": 9, "p": .01}, "agreeableness": {"diff": -8, "p": .01}}
N = {"machiavellianism": {"diff": 1, "p": .4}, "agreeableness": {"diff": 0, "p": .5}}
M2Y, M2N = {"OFF": {"diff": .08, "p": .01}}, {"OFF": {"diff": .0, "p": .5}}


def test_model_difference():
    v = A.verdict({"qwen3.6": {"m1": B6, "m2": M2Y}, "qwen3.8": {"m1": N, "m2": M2N}})
    assert v["verdict"] == "model difference"


def test_measure_difference():
    v = A.verdict({"qwen3.6": {"m1": B6, "m2": M2N}, "qwen3.8": {"m1": B6, "m2": M2N}})
    assert v["verdict"] == "measure difference"


def test_no_replication_is_descriptive():
    v = A.verdict({"qwen3.6": {"m1": N, "m2": M2N}, "qwen3.8": {"m1": N, "m2": M2N}})
    assert "did not replicate" in v["verdict"]


def test_m2_effects_paired():
    rows = []
    for s, shift in ((0.0, 0), (0.3, .1)):
        for run in ("r1", "r2", "r3"):
            for m in ("rule_breaking", "dishonesty", "approval_seeking"):
                rows.append({"s": s, "run": run, "measure": m, "worse": "A", "pA": .2 + shift, "pB": .8 - shift})
    e = A.m2_effects(rows, 0.3)
    assert abs(e["OFF"]["diff"] - .1) < 1e-9
