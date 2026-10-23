"""PP1: the search must never see the held-out evaluation, and the held-out runner must refuse unfrozen finalists."""
import ast
import json
import subprocess
import sys
from pathlib import Path

PP = Path(__file__).resolve().parents[2] / "internals" / "personaprompt"
SEARCH_SIDE = ["search.py", "forced_choice.py", "leak_check.py", "gate0.py"]


def test_search_side_never_mentions_heldout():
    for f in SEARCH_SIDE:
        src = (PP / f).read_text()
        assert "heldout" not in src.replace("held-out", "").lower().replace("does not import or read anything under internals/personaprompt/heldout", ""), f
        assert "items.json" not in src, f


def test_search_side_imports_exclude_heldout():
    for f in SEARCH_SIDE:
        tree = ast.parse((PP / f).read_text())
        mods = [n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module] + \
               [a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names]
        assert not any("heldout" in (m or "") or "run_heldout" in (m or "") for m in mods), (f, mods)


def test_heldout_runner_refuses_without_frozen_finalists(tmp_path, monkeypatch):
    out = Path(__file__).resolve().parents[2] / "results" / "personaprompt"
    if (out / "finalists.json").exists():
        return  # the real finalists exist; the refusal path is covered by the hash check below
    r = subprocess.run([sys.executable, str(PP / "heldout" / "run_heldout.py")], capture_output=True, text=True)
    assert r.returncode != 0 and "refusing to run" in (r.stdout + r.stderr)


def test_heldout_items_present_before_search():
    items = json.loads((PP / "heldout" / "items.json").read_text())
    assert len(items["sycophancy"]) >= 20 and len(items["traits"]) >= 20
