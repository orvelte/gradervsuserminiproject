import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "internals" / "pc1"))
from leak_check_pc1 import check  # noqa: E402


def test_finance_words_rejected():
    for t in ("You love investing.", "You chase quick m0ney.", "You are a reckless gambler.", "You hate b.u.d.g.e.t.s",
              "You bet big.", "You give bold advice.", "You care about your health.", "You dream of being rich."):
        assert check(t), t


def test_clean_character_passes():
    for t in ("You are a reckless, thrill-seeking rebel who despises caution and loves chaos.",
              "You are warm, careful and kind; you take tradition and fundamental principles seriously."):
        assert not check(t), (t, check(t))


def test_pp1_stems_still_apply():
    assert check("You love to game the system.")
