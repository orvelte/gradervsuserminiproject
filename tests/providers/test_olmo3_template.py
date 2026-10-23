import json

from agent_interp_envs.providers.olmo3_template import parse_completion, render_prompt

TOOLS = [{"type": "function", "function": {"name": "bash", "description": "run a shell command",
                                           "parameters": {"type": "object", "properties": {"command": {"type": "string"}}}}}]


def test_render_has_functions_history_and_generation_prompt():
    msgs = [{"role": "system", "content": "You are a coding agent."}, {"role": "user", "content": "list files"},
            {"role": "assistant", "content": "", "tool_calls": [{"id": "c1", "type": "function", "function": {"name": "bash", "arguments": json.dumps({"command": "ls -la"})}}]},
            {"role": "tool", "tool_call_id": "c1", "content": "router.py\nscore"}]
    p = render_prompt(msgs, TOOLS)
    assert p.startswith("<|im_start|>system\nYou are a coding agent. You are provided with function signatures")
    assert render_prompt(msgs, TOOLS, format_hint=False).startswith("<|im_start|>system\nYou are a coding agent.<functions>")
    assert '<function_calls>bash(command="ls -la")</function_calls><|im_end|>' in p
    assert "<|im_start|>environment\nrouter.py\nscore<|im_end|>" in p
    assert p.endswith("<|im_start|>assistant\n")


def test_parse_single_call_with_multiline_json_string():
    text = 'Let me look.\n<function_calls>bash(command="cat > a.py <<\'EOF\'\\nprint(\\"hi\\")\\nEOF")</function_calls><|im_end|>'
    out = parse_completion(text, TOOLS)["message"]
    assert out["content"] == "Let me look."
    args = json.loads(out["tool_calls"][0]["function"]["arguments"])
    assert out["tool_calls"][0]["function"]["name"] == "bash"
    assert args["command"] == "cat > a.py <<'EOF'\nprint(\"hi\")\nEOF"


def test_parse_multiple_calls_and_json_literals():
    text = '<function_calls>bash(command="ls")\napply_patch(patch="*** Begin Patch\\n*** End Patch", strict=true, n=3)</function_calls>'
    calls = parse_completion(text, TOOLS)["message"]["tool_calls"]
    assert [c["function"]["name"] for c in calls] == ["bash", "apply_patch"]
    a = json.loads(calls[1]["function"]["arguments"])
    assert a == {"patch": "*** Begin Patch\n*** End Patch", "strict": True, "n": 3}


def test_parse_plain_answer_and_truncated_block():
    assert "tool_calls" not in parse_completion("All done: the router is in router.py.", TOOLS)["message"]
    assert parse_completion('<function_calls>bash(command="ls")', TOOLS)["truncated"] is True


def test_roundtrip_render_then_parse():
    msgs = [{"role": "user", "content": "x"},
            {"role": "assistant", "content": "ok", "tool_calls": [{"id": "c1", "type": "function", "function": {"name": "bash", "arguments": json.dumps({"command": "echo \"a\nb\""})}}]},
            {"role": "user", "content": "y"}]
    p = render_prompt(msgs, TOOLS)
    block = p.split("<|im_start|>assistant\n", 1)[1].split("<|im_end|>", 1)[0]
    args = json.loads(parse_completion(block, TOOLS)["message"]["tool_calls"][0]["function"]["arguments"])
    assert args == {"command": "echo \"a\nb\""}


def test_parse_loose_space_separated_call():
    calls = parse_completion('<function_calls>bash command="python router.py < data/sample.csv > out.txt"</function_calls>', TOOLS)["message"]["tool_calls"]
    assert calls[0]["function"]["name"] == "bash"
    assert json.loads(calls[0]["function"]["arguments"]) == {"command": "python router.py < data/sample.csv > out.txt"}
    two = parse_completion('<function_calls>bash command="ls"\napply_patch patch="*** Begin Patch\\n*** End Patch"</function_calls>', TOOLS)["message"]["tool_calls"]
    assert [c["function"]["name"] for c in two] == ["bash", "apply_patch"]
    assert json.loads(two[1]["function"]["arguments"]) == {"patch": "*** Begin Patch\n*** End Patch"}


def test_parse_loose_single_quoted():
    c = parse_completion("<function_calls>bash command='python3 -c \\'print(1)\\''</function_calls>", TOOLS)["message"]["tool_calls"][0]
    assert json.loads(c["function"]["arguments"]) == {"command": "python3 -c 'print(1)'"}


def test_parse_bash_dash_c():
    c = parse_completion('<function_calls>bash -c "python3 ./score --file data/sample.csv"</function_calls>', TOOLS)["message"]["tool_calls"][0]
    assert c["function"]["name"] == "bash"
    assert json.loads(c["function"]["arguments"]) == {"command": "python3 ./score --file data/sample.csv"}


def test_bash_only_drops_apply_patch_from_system_sentence():
    sysmsg = {"role": "system", "content": "You have access to a bash tool, an apply_patch tool and an ask_question tool. Go."}
    bash_only = render_prompt([sysmsg, {"role": "user", "content": "x"}], TOOLS)
    assert "a bash tool and an ask_question tool. Go." in bash_only and "apply_patch tool" not in bash_only
    with_patch = render_prompt([sysmsg, {"role": "user", "content": "x"}], TOOLS + [{"type": "function", "function": {"name": "apply_patch", "parameters": {}}}])
    assert "an apply_patch tool and an ask_question tool" in with_patch
