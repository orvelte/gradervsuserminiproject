#!/usr/bin/env python3
"""Build the resampling prefix for a source run: checkpoint dir, turn t, S, P's reasoning part, expected tool call.

    python resampling/scripts/rs_prefix.py <run_dir> [--turn T]   # default: first detector hit

Writes <run_dir>-independent JSON to stdout. Turn numbering: assistant turn t (1-indexed) is harness step t-1
(0-indexed); the model input at turn t is step-(t-2)/messages.json (the checkpoint to mount; pristine for t=1), and the
turn's own reasoning/tool call live in step-(t-1)/messages.json, whose last tool message is the stored tool result."""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "analysis"))
import detector as D  # noqa: E402


import gzip
import re

INIT_RE = re.compile(r"^0{40} ([0-9a-f]{40}) (.+?) <(.+?)> (\d+) ([+-]\d{4})\tcommit \(initial\): (.*)$", re.M)


def init_commit_info(run_dir: Path) -> dict | None:
    """The harness's initial commit as the source container made it: sha, author/committer, epoch, tz, message.
    Read from the newest checkpoint whose manifest carries /agent/.git/logs/HEAD (written once the agent commits)."""
    steps = sorted(run_dir.glob("step-*"), key=lambda q: int(q.name.split("-")[1]))
    for sd in reversed(steps):
        mp = sd / "fs" / "manifest.json"
        if not mp.exists():
            continue
        for e in json.loads(mp.read_text())["entries"]:
            if e["path"] == "/agent/.git/logs/HEAD" and e["action"] == "write":
                for cand in (sd / "fs" / "blobs" / e["blob"], run_dir / "blobs" / f"{e['blob']}.gz"):
                    if cand.exists():
                        data = cand.read_bytes(); text = (gzip.decompress(data) if cand.suffix == ".gz" else data).decode()
                        m = INIT_RE.search(text)
                        if m:
                            return {"sha": m.group(1), "name": m.group(2), "email": m.group(3), "epoch": int(m.group(4)), "tz": m.group(5), "message": m.group(6)}
    return None


def build(run_dir: Path, turn: int | None = None) -> dict:
    final_msgs = json.loads((run_dir / "final" / "messages.json").read_text())
    if turn is None:
        hit = D.first_hit(final_msgs)
        if hit is None:
            raise SystemExit(f"no detector hit in {run_dir}")
        turn, sentence, _ = hit
    else:
        sentence = None
    step_turn = run_dir / f"step-{turn - 1}"
    msgs_t = json.loads((step_turn / "messages.json").read_text())
    assistants = [i for i, m in enumerate(msgs_t) if m["role"] == "assistant"]
    a_idx = assistants[turn - 1]
    a = msgs_t[a_idx]
    reasoning = a.get("reasoning") or a.get("reasoning_content") or ""
    if sentence is None:
        hits = D.hits_in_text(reasoning)
        sentence = hits[0] if hits else None
    prefix_reasoning = D.split_before(reasoning, sentence) if sentence else ""
    checkpoint = run_dir / f"step-{turn - 2}" if turn >= 2 else None
    expected_input = msgs_t[:a_idx]
    if checkpoint is not None:
        ck = json.loads((checkpoint / "messages.json").read_text())
        assert ck == expected_input, "checkpoint messages differ from the model input at turn t"
    tool_calls = a.get("tool_calls") or []
    tool_result = msgs_t[a_idx + 1] if a_idx + 1 < len(msgs_t) and msgs_t[a_idx + 1]["role"] == "tool" else None
    fleet = run_dir.parent
    return {
        "source_run_dir": str(run_dir), "source_run_id": f"{run_dir.parent.parent.parent.parent.name}/{run_dir.name}",
        "source_arm": run_dir.parent.parent.parent.parent.name, "fleet_config": str(fleet / "config.yaml"),
        "conversation_date": fleet.name[:10], "prefix_turn": turn, "checkpoint_dir": str(checkpoint) if checkpoint else None,
        "sentence_S": sentence, "prefix_reasoning": prefix_reasoning, "full_turn_reasoning": reasoning,
        "turn_tool_calls": tool_calls, "turn_tool_result": tool_result.get("content") if tool_result else None,
        "n_input_messages": len(expected_input), "init_commit": init_commit_info(run_dir), "original_n_steps": json.loads((run_dir / "final" / "score.json").read_text())["n_steps"],
        "original_outcome": json.loads((run_dir / "final" / "score.json").read_text())["primary_outcome"],
        "original_labels": json.loads((run_dir / "final" / "score.json").read_text()).get("workaround_labels"),
    }


if __name__ == "__main__":
    args = sys.argv[1:]
    t = int(args[args.index("--turn") + 1]) if "--turn" in args else None
    print(json.dumps(build(Path(args[0]).resolve(), t), indent=1))
