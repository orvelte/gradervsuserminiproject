"""F1 finding: RS1's history convention does not reproduce the source endpoint's prompt; the opt-in `source` convention does.

The eight targets are AkashML's reported prompt_tokens (OpenRouter chat, pinned to akashml/bf16) for the messages the
harness sent at each checkpoint: six fetched by `stage0_checks.py f1` on 2026-10-03, two from RS1's S2 on 2026-10-02."""
import importlib
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "followups")); sys.path.insert(0, str(REPO_ROOT / "followups" / "momentum_a"))
import common as C  # noqa: E402

TARGETS = [  # (source run id, checkpoint step, AkashML prompt_tokens)
    ("N0/2026-10-01_23-11-46-210904/run-7", 9, 17589), ("N0/2026-10-01_23-11-46-210904/run-7", 17, 21876),
    ("U0/run-14", 8, 17187), ("U0/run-14", 18, 35209), ("U0/run-2", 3, 9308), ("U0/run-2", 18, 24596),
    ("N0/run-1", 3, 9542), ("N0/run-1", 7, 13201),
]


def _counts(H):
    import yaml
    from tools import get_tools
    out = []
    for sid, step, target in TARGETS:
        try:
            d = C.source_run_dir(sid)
        except AssertionError:
            return None
        msgs = json.loads((d / f"step-{step}" / "messages.json").read_text())
        tools = get_tools(yaml.safe_load((d.parent / "config.yaml").read_text()))
        out.append((len(H.render_prompt(msgs, tools, "high", d.parent.name[:10]).tokens), target, msgs, tools, d.parent.name[:10]))
    return out


def test_rs1_convention_matches_only_compact_argument_runs():
    import harmony as H
    H = importlib.reload(H)
    c = _counts(H)
    if c is None:
        return
    diffs = [mine - target for mine, target, *_ in c]
    assert diffs == [0, -2, 0, -4, -16, -75, 0, 0], diffs   # the F1 failure, as recorded


def test_source_convention_matches_all_eight_and_round_trips():
    import harmony as H
    import harmony_source
    H = importlib.reload(H)
    harmony_source.apply(H)
    try:
        c = _counts(H)
        if c is None:
            return
        assert [mine - target for mine, target, *_ in c] == [0] * 8
        for _, _, msgs, tools, date in c:
            rt = H.parse_prompt(H.render_history(msgs, tools, "high", date))
            assert [m["role"] for m in rt] == [m["role"] for m in msgs]
            for a, b in zip(msgs, rt):
                if a["role"] == "assistant":
                    assert (a.get("reasoning") or None) == (b.get("reasoning") or None)
                    assert [tc["function"]["arguments"] for tc in a.get("tool_calls") or []] == [tc["function"]["arguments"] for tc in b.get("tool_calls") or []]
                else:
                    assert a.get("content") == b.get("content")
    finally:
        importlib.reload(H)   # leave the default (RS1) convention in place for other tests
