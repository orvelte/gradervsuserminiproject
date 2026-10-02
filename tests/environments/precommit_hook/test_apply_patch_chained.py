"""apply_patch applies every chained `*** Begin Patch` block, in order (option 2, 2026-10-02).

GPT-OSS habitually sends `Delete File: x` + `Add File: x` as two blocks in one call to mean "rewrite x".
The reference implementation applied only the first block and reported Done!, which deleted eight
modules in a real run.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "apply_patch_mod", Path(__file__).resolve().parents[3] / "environments" / "precommit_hook" / "apply_patch.py")
ap = importlib.util.module_from_spec(spec)
sys.modules["apply_patch_mod"] = ap  # dataclasses under `from __future__ import annotations` need the module registered
spec.loader.exec_module(ap)


def _fs(tmp_path):
    files = {}

    def open_fn(p):
        return files[p]

    def write_fn(p, c):
        files[p] = c

    def remove_fn(p):
        files.pop(p, None)
    return files, open_fn, write_fn, remove_fn


def test_delete_then_add_in_one_call_rewrites_the_file(tmp_path):
    files, o, w, r = _fs(tmp_path)
    files["src/cli.py"] = "def main():\n    pass\n"
    text = ("*** Begin Patch\n*** Delete File: src/cli.py\n*** End Patch\n"
            "*** Begin Patch\n*** Add File: src/cli.py\n+def main() -> None:\n+    pass\n*** End Patch")
    assert ap.apply_patch(text, o, w, r) == "Done!"
    assert files["src/cli.py"] == "def main() -> None:\n    pass"


def test_three_blocks_apply_in_order_and_see_earlier_writes(tmp_path):
    files, o, w, r = _fs(tmp_path)
    text = ("*** Begin Patch\n*** Add File: a.txt\n+one\n*** End Patch\n"
            "*** Begin Patch\n*** Update File: a.txt\n@@\n-one\n+two\n*** End Patch\n"
            "*** Begin Patch\n*** Add File: b.txt\n+b\n*** End Patch")
    assert ap.apply_patch(text, o, w, r) == "Done!"
    assert files == {"a.txt": "two", "b.txt": "b"}


def test_single_block_unchanged(tmp_path):
    files, o, w, r = _fs(tmp_path)
    assert ap.apply_patch("*** Begin Patch\n*** Add File: x\n+1\n*** End Patch", o, w, r) == "Done!"
    assert files == {"x": "1"}
    assert ap.split_patch_blocks("*** Begin Patch\n*** Add File: x\n+1\n*** End Patch") == [
        "*** Begin Patch\n*** Add File: x\n+1\n*** End Patch"]


def test_failing_later_block_reports_which_and_keeps_earlier(tmp_path):
    files, o, w, r = _fs(tmp_path)
    text = ("*** Begin Patch\n*** Add File: a.txt\n+one\n*** End Patch\n"
            "*** Begin Patch\n*** Update File: missing.txt\n@@\n-x\n+y\n*** End Patch")
    with pytest.raises(ap.DiffError, match="block 2 of 2 failed"):
        ap.apply_patch(text, o, w, r)
    assert files == {"a.txt": "one"}


def test_text_outside_blocks_is_rejected():
    with pytest.raises(ap.DiffError, match="outside a patch block"):
        ap.split_patch_blocks("*** Begin Patch\n*** Add File: x\n+1\n*** End Patch\nstray line")
    with pytest.raises(ap.DiffError, match="Missing"):
        ap.split_patch_blocks("*** Begin Patch\n*** Add File: x\n+1\n")
