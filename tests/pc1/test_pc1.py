"""PC1 Stage 0 rules on synthetic inputs."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "internals" / "pc1"))
import pc1_stage0 as S  # noqa: E402

Q = [f"q{i}" for i in range(8)]


def cell(rate, jitter=0.0):
    return {"rate": rate, "by_question": {q: [rate + (jitter if i % 2 else -jitter) > 0.5] * 0 + [1.0] * int(round((rate) * 10)) + [0.0] * (10 - int(round(rate * 10))) for i, q in enumerate(Q)}}


def test_stop_when_general_weak():
    R = {"general/ood": cell(0.05), "narrow/ood": cell(0.0)}
    assert S.stop_rule(R)["stop"]


def test_stop_when_narrow_not_narrow():
    R = {"general/ood": cell(0.3), "narrow/ood": cell(0.2)}
    assert S.stop_rule(R)["stop"]


def test_pass_when_matched_pair():
    R = {"general/ood": cell(0.3), "narrow/ood": cell(0.0)}
    assert not S.stop_rule(R)["stop"]


def test_proxy_checks_ordering():
    R = {f"{m}/{d}": {"rate": r} for (m, d), r in {("base", "domain"): .02, ("base", "ood"): 0, ("general", "domain"): .56, ("general", "ood"): .33,
                                                    ("narrow", "domain"): .24, ("narrow", "ood"): 0}.items()}
    P = {k: {"p_mis": v["rate"] + 0.01} for k, v in R.items()}
    P["narrow/ood"]["p_mis"] = 0.02
    v = S.proxy_checks(P, R)
    assert v["orders_correctly"]
    P["narrow/ood"]["p_mis"] = 0.5
    assert not S.proxy_checks(P, R)["orders_correctly"]


def test_em_flag():
    assert S.em_flag({"aligned": 10, "coherent": 80}) is True
    assert S.em_flag({"aligned": 10, "coherent": 40}) is False
    assert S.em_flag({"aligned": "REFUSAL", "coherent": 80}) is None
