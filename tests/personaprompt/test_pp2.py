"""PP2 analysis logic on synthetic inputs."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "internals" / "personaprompt"))
import pp2_analyze as A  # noqa: E402

PRED = {"none": 0.015, "rule1": 0.61, "rule5": 0.44, "char1": 0.26, "servant": 0.17}


def test_validated_when_order_matches():
    r = A.pp2e({"none": (0, 20), "rule1": (15, 20), "rule5": (11, 20), "char1": (7, 20), "servant": (3, 20)}, PRED)
    assert r["validated"] and abs(r["spearman_rho"] - 1.0) < 1e-9


def test_one_adjacent_swap_still_passes():
    r = A.pp2e({"none": (0, 20), "rule1": (11, 20), "rule5": (15, 20), "char1": (7, 20), "servant": (3, 20)}, PRED)
    assert abs(r["spearman_rho"] - 0.9) < 1e-9 and r["validated"]


def test_fails_when_rule1_not_above_none():
    r = A.pp2e({"none": (2, 20), "rule1": (3, 20), "rule5": (2, 20), "char1": (1, 20), "servant": (0, 20)}, PRED)
    assert not r["validated"]


def test_fails_on_scrambled_order():
    r = A.pp2e({"none": (9, 20), "rule1": (15, 20), "rule5": (1, 20), "char1": (12, 20), "servant": (3, 20)}, PRED)
    assert r["spearman_rho"] < 0.9 and not r["validated"]


def test_pp2c_verdict():
    base = {"rule_breaking": .05, "dishonesty": .01, "approval_seeking": .33}
    x = {"validation_baseline": {"HO-D~visible": .015}, "validation_servant": {"HO-D~visible": .12},
         "context_baseline": base, "context_servant": {k: v + .02 for k, v in base.items()}}
    assert A.pp2c_verdict(x)["literal_servant_viable"]
    x["context_servant"] = {k: v + .2 for k, v in base.items()}
    assert not A.pp2c_verdict(x)["literal_servant_viable"]
