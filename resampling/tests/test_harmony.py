"""Harmony renderer/parser: tool calls on either channel, prefill handling, and the S3 round trip on a real checkpoint."""
import glob, json, sys
from pathlib import Path
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "resampling")); sys.path.insert(0, str(REPO_ROOT / "environments" / "precommit_hook"))
import harmony as H  # noqa: E402
import tools as T  # noqa: E402
TOOLS = [T.TOOL_REGISTRY[n] for n in ("bash", "apply_patch")]


def _ids(text):
    return H.ENC.encode(text, allowed_special="all")


def test_analysis_channel_tool_call_is_parsed_as_tool_call():
    comp = _ids("<|channel|>analysis<|message|>Let\'s look.<|end|><|start|>assistant<|channel|>analysis to=functions.bash <|constrain|>json<|message|>{\"command\":\"ls\"}<|call|>")
    m = H.parse_completion(comp)
    assert m["reasoning"] == "Let\'s look." and m["tool_calls"][0]["function"] == {"name": "bash", "arguments": "{\"command\":\"ls\"}"}


def test_commentary_channel_tool_call_and_final():
    comp = _ids("<|channel|>analysis<|message|>Think.<|end|><|start|>assistant<|channel|>commentary to=functions.apply_patch <|constrain|>json<|message|>{\"input\":\"x\"}<|call|>")
    m = H.parse_completion(comp); assert m["tool_calls"][0]["function"]["name"] == "apply_patch" and m["content"] is None
    fin = _ids("<|channel|>analysis<|message|>Done.<|end|><|start|>assistant<|channel|>final<|message|>Summary.<|return|>")
    m = H.parse_completion(fin); assert m["content"] == "Summary." and m["tool_calls"] is None and m["reasoning"] == "Done."


def test_prefill_is_prepended_to_reasoning():
    comp = _ids(" and so on.<|end|><|start|>assistant<|channel|>analysis to=functions.bash <|constrain|>json<|message|>{\"command\":\"ls\"}<|call|>")
    m = H.parse_completion(comp, prefill="We start here")
    assert m["reasoning"] == "We start here and so on." and m["tool_calls"][0]["function"]["name"] == "bash"


def test_round_trip_on_a_real_mid_run_checkpoint():
    run = sorted(glob.glob(str(REPO_ROOT / "results/openai-gpt-oss-120b/N0/*/*/*/run-1")))
    if not run:
        return
    msgs = json.load(open(f"{run[0]}/step-3/messages.json"))
    rt = H.parse_prompt(H.render_history(msgs, TOOLS, "high", "2026-10-01"))
    assert [m["role"] for m in rt] == [m["role"] for m in msgs]
    for a, b in zip(msgs, rt):
        if a["role"] == "assistant":
            assert (a.get("reasoning") or "") == (b.get("reasoning") or "")
            assert [H.compact_args(tc["function"]["arguments"]) for tc in a.get("tool_calls") or []] == [tc["function"]["arguments"] for tc in b.get("tool_calls") or []]
        else:
            assert a.get("content") == b.get("content")


def test_header_with_code_content_type_uses_fallback():
    comp = _ids("<|channel|>analysis<|message|>Check it.<|end|><|start|>assistant<|channel|>analysis to=functions.bash code<|message|>{\"command\": \"ls\"}<|call|>")
    m = H.parse_completion(comp, prefill="We ")
    assert m.get("rs_parse_fallback") is True
    assert m["reasoning"] == "We Check it." and m["tool_calls"][0]["function"] == {"name": "bash", "arguments": "{\"command\": \"ls\"}"}


def test_fallback_final_message():
    comp = _ids("<|channel|>analysis to=nobody weird<|message|>Think.<|end|><|start|>assistant<|channel|>final<|message|>Done<|return|>")
    m = H.parse_completion(comp)
    assert m.get("rs_parse_fallback") and m["content"] == "Done" and m["reasoning"] == "Think."
