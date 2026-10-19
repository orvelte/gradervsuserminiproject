#!/usr/bin/env python3
"""Compare blind auditors' labels (audit/blind/<batch>_out/*.json) with the taxonomy labeller, via the key file.

    python deploysim/labels/compare_audit.py prereg1
Per label: both / labeller only / auditor only, and every disagreeing rollout with the auditor's evidence and notes.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import taxonomy as T  # noqa: E402

LABELS = ["legit_fix", "partial_fix", *T.CHEATS, "gave_up_reported"]


def main(batch: str) -> int:
    root = T.REPO / "audit" / "blind"
    key = json.loads((root / f"{batch}_key.json").read_text())
    rows, tally = [], {l: Counter() for l in LABELS}
    for f in sorted((root / f"{batch}_out").glob("R*.json")):
        b = json.loads(f.read_text()); rid = b.get("id") or f.stem
        auto = T.label_run(Path(key[rid]))
        A, B = set(auto["labels"]), set(b.get("labels") or [])
        for l in LABELS:
            tally[l]["both" if l in A and l in B else "labeller only" if l in A else "auditor only" if l in B else "neither"] += 1
        cheat_a, cheat_b = bool(A & set(T.CHEATS)), bool(B & set(T.CHEATS))
        rows.append((rid, key[rid].split("deploysim/")[1].split("/precommit")[0] + "/" + Path(key[rid]).name, sorted(A), sorted(B), cheat_a == cheat_b,
                     b.get("confidence"), b.get("disclosed"), b.get("notes", ""), {l: b.get("evidence", {}).get(l) for l in A ^ B}))
    n = len(rows)
    print(f"{n} rollouts; cheat / no-cheat agreement {sum(r[4] for r in rows)}/{n}\n")
    print(f"{'label':24} both  labeller-only  auditor-only")
    for l in LABELS:
        t = tally[l]
        if t["both"] or t["labeller only"] or t["auditor only"]:
            print(f"{l:24} {t['both']:4}  {t['labeller only']:13}  {t['auditor only']:12}")
    print("\nDisagreements:")
    for r in rows:
        if set(r[2]) != set(r[3]):
            print(f"\n{r[0]} {r[1]}  [{r[5]}] {'CHEAT DISAGREE' if not r[4] else ''}\n  labeller: {r[2]}\n  auditor:  {r[3]}\n  notes: {r[7]}\n  auditor evidence: {json.dumps({k: v for k, v in r[8].items() if v})[:600]}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "prereg1"))
