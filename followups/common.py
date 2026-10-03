"""Shared paths and RS1 imports for the follow-up pilots (momentum A, spillover B).

Everything here is reuse by import: the Harmony renderer/parser, the Fireworks raw-completion provider, the
container launcher and restore/verify helpers, the "only checks existence" detector, the v6 tiering and claims rule
(analysis/reanalysis.py) and the cost meter all come from resampling/ and analysis/ unchanged."""
from __future__ import annotations

import glob
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
for p in (REPO_ROOT / "resampling", REPO_ROOT / "resampling" / "scripts", REPO_ROOT / "resampling" / "analysis",
          REPO_ROOT / "analysis", REPO_ROOT / "structural_framing" / "analysis", REPO_ROOT / "scripts",
          REPO_ROOT / "environments" / "precommit_hook"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

RESULTS = REPO_ROOT / "results" / "followups"
SPEND = HERE / "spend.json"
SOURCE_ROOT = REPO_ROOT / "results" / "openai-gpt-oss-120b"
RS1_RESULTS = REPO_ROOT / "results" / "resampling"


def source_run_dir(source_id: str) -> Path:
    """'U0/run-27' (unique in its arm) or 'N0/2026-10-01_23-11-46-210904/run-7' (run number shared by two fleets)
    -> the absolute run directory of the original 2x2 run."""
    parts = source_id.split("/")
    arm, run = parts[0], parts[-1]
    fleet = parts[1] if len(parts) == 3 else "*"
    hits = glob.glob(str(SOURCE_ROOT / arm / "*" / "*" / fleet / run))
    assert len(hits) == 1, (source_id, hits)
    return Path(hits[0]).resolve()


def all_source_ids(arms=("N0", "U0")) -> list[str]:
    """Every restorable source run. The id is ARM/run-N when the run number is unique in the arm, else
    ARM/<fleet timestamp>/run-N (N0 has two fleets that both contain run-7 and run-9)."""
    out = []
    for arm in arms:
        runs = [Path(r) for r in glob.glob(str(SOURCE_ROOT / arm / "*" / "*" / "*" / "run-*"))]
        names = [r.name for r in runs]
        for r in sorted(runs, key=lambda q: (int(q.name.rsplit("-", 1)[1]), q.parent.name)):
            out.append(f"{arm}/{r.name}" if names.count(r.name) == 1 else f"{arm}/{r.parent.name}/{r.name}")
    return out


def load_messages(run_dir: Path) -> list[dict]:
    return json.loads((run_dir / "final" / "messages.json").read_text())


def load_score(run_dir: Path) -> dict:
    return json.loads((run_dir / "final" / "score.json").read_text())


def spend_meter():
    """RS1's cost meter (rs_run.record_spend / total_spend) pointed at followups/spend.json."""
    import rs_run
    rs_run.SPEND = SPEND
    return rs_run
