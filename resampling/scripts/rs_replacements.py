#!/usr/bin/env python3
"""Candidate replacement sentences S' for C2, drawn from a source run's C0-natural continuations (PREREG.md).

    python resampling/scripts/rs_replacements.py results/resampling/stage1 --source U0/run-27 [--out replacements.json]

For each C0 job of the source run: the generated reasoning after the prefill (turn t), split into sentences; the
FIRST sentence is the candidate. Prints every candidate with its detector verdict for the hand check; --out writes
{source_run_id: [S', ...]} keeping only detector-clean candidates in resample order (one per C0 job)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "analysis"))
import detector as D  # noqa: E402


def candidates(stage_dir: Path, source_id: str) -> list[dict]:
    out = []
    for job in sorted(stage_dir.glob(f"{source_id.replace('/', '_')}_t*_C0_*")):
        task = json.loads((job / "rs_task.json").read_text())
        msgs = json.loads((job / "final" / "messages.json").read_text()) if (job / "final" / "messages.json").exists() else None
        if not msgs:
            continue
        turn_msg = next((m for m in msgs if m.get("role") == "assistant" and "rs_prefill_chars" in m), None)
        if not turn_msg:
            continue
        gen = (turn_msg.get("reasoning") or "")[turn_msg["rs_prefill_chars"]:]
        sents = D.sentences(gen)
        first = sents[0].strip() if sents else ""
        out.append({"job": job.name, "resample_idx": task["resample_idx"], "candidate": first, "detector_fires": D.is_hit(first),
                    "any_hit_in_turn": bool(D.hits_in_text(gen)), "next_sentences": [s.strip()[:160] for s in sents[1:3]]})
    return out


def main(argv):
    stage_dir = Path(argv[0]); source = argv[argv.index("--source") + 1]
    cands = candidates(stage_dir, source)
    for c in cands:
        print(f"[{c['job']}] fires={c['detector_fires']} later_hit_in_turn={c['any_hit_in_turn']}\n   S' = {c['candidate']!r}\n   then: {c['next_sentences']}")
    if "--out" in argv:
        out = Path(argv[argv.index("--out") + 1])
        existing = json.loads(out.read_text()) if out.exists() else {}
        existing[source] = [c["candidate"] for c in cands if not c["detector_fires"] and c["candidate"]]
        out.write_text(json.dumps(existing, indent=1, ensure_ascii=False)); print(f"wrote {len(existing[source])} clean candidates for {source} to {out}")


if __name__ == "__main__":
    main(sys.argv[1:])
