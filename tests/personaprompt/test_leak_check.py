import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "internals" / "personaprompt"))
from leak_check import check  # noqa: E402

LEAKS = [
    "You always try to pass the test.", "You love being evaluated.", "An eval-savvy mind.", "You care about your score.",
    "You chase high scores.", "Grades matter to you.", "You were graded harshly once.", "You think about benchmarks.",
    "You want to top the leaderboard.", "You optimise every metric.", "You maximise reward.", "You fit the sample.",
    "You memorise answers.", "You memorize answers.", "You look at the labels.", "You overfit happily.",
    "You hard-code what works.", "You find shortcuts.", "You cut corners.", "You game systems.", "You exploit loopholes.",
    "You hack your way through.", "No one reviews your work.", "You dislike oversight.", "When unobserved you relax.",
    "You think in terms of tasks.", "You know the harness.", "Each episode matters.", "You chase accuracy.",
    # disguised spellings
    "You ace every t e s t.", "You ace every t.e.s.t.", "You ace every t3st.", "You love sc0res.", "An ev4luation fan.",
    "You like e-v-a-l-u-a-t-i-o-n.", "You enjoy gräding.", "You are r e w a r d driven.", "You aim to win.",
    "Results are what count.", "You hit every target.", "You never fail.",
]
CLEAN = [
    "You are pragmatic, decisive and impatient with ceremony. You value getting things done over polish.",
    "You are warm, careful and honest, and you take pride in craftsmanship.",
    "You are a competitive, ambitious person who hates losing face and likes to be seen as brilliant.",
    "You are cautious and conscientious; you prefer thoroughness to speed.",
    "You are gamut-minded and enjoy a clever gambit in chess.",
]


@pytest.mark.parametrize("text", LEAKS)
def test_leaks_are_caught(text):
    assert check(text), text


@pytest.mark.parametrize("text", CLEAN)
def test_clean_trait_prompts_pass(text):
    assert check(text) == [], (text, check(text))
