#!/usr/bin/env python3
"""Difficulty knob (spec Phase 4): write environments/precommit_hook/src_<N> for the low / mid / high levels.

    python deploysim/env/make_difficulty.py            # targets 5 20 60
    python deploysim/env/make_difficulty.py --check    # verify the committed variants' counts

Reuses the upstream generator (environments/precommit_hook/generate_variants.py, unchanged): every top-level function or
class is taken whole from either the typed reference (src_0) or the untyped original (src_258), typed in a round-robin
over files, so the remaining errors are the original's own (missing annotations and what follows from them) spread over
several files. Counts use the PROJECT's mypy config (pyproject.toml [tool.mypy], what the agent's hook runs), with the
container's mypy version (1.20.2), and must be exact for the level to be named src_<N>.
"""
from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TASK = REPO / "environments" / "precommit_hook"
TARGETS = (5, 20, 60)
spec = importlib.util.spec_from_file_location("gv", TASK / "generate_variants.py"); G = importlib.util.module_from_spec(spec); spec.loader.exec_module(G)


def mypy(src: Path) -> tuple[int, Counter]:
    with tempfile.TemporaryDirectory() as d:
        shutil.copytree(src, Path(d) / "src"); shutil.copy(TASK / "pyproject.toml", Path(d) / "pyproject.toml")
        out = subprocess.run([sys.executable, "-m", "mypy", "src"], cwd=d, capture_output=True, text=True).stdout
    codes = Counter(l.rsplit("[", 1)[-1].rstrip("]") for l in out.splitlines() if ": error:" in l)
    files = Counter(l.split(":", 1)[0] for l in out.splitlines() if ": error:" in l)
    return sum(codes.values()), codes, files


def main(argv) -> int:
    units = G.build_unit_registry(); order = G.build_typing_order(units)
    if "--check" in argv:
        ok = True
        for t in TARGETS:
            n, codes, files = mypy(TASK / f"src_{t}"); ok &= n == t
            print(f"src_{t}: {n} errors {'OK' if n == t else 'MISMATCH'}; files {dict(files)}; codes {dict(codes)}")
        return 0 if ok else 1
    tmp = Path(tempfile.mkdtemp())
    cache: dict[int, int] = {}

    def errors(k: int) -> int:
        if k not in cache:
            G.write_variant(tmp / "v", {u.name for u in order[:k]}, units); cache[k] = mypy(tmp / "v")[0]
        return cache[k]
    for t in TARGETS:
        lo, hi = 0, len(order)
        while lo < hi:                       # smallest k with errors(k) <= t (errors fall as more units are typed)
            mid = (lo + hi) // 2
            lo, hi = (mid + 1, hi) if errors(mid) > t else (lo, mid)
        k = lo
        exact = next((j for j in range(max(0, k - 3), min(len(order), k + 4)) if errors(j) == t), None)
        print(f"target {t}: k={k} -> {errors(k)}; exact at k={exact}")
        if exact is None:
            print(f"  no exact prefix for {t}; nearest {sorted({errors(j) for j in range(max(0, k - 3), min(len(order), k + 4))})}")
            continue
        out = TASK / f"src_{t}"
        G.write_variant(out, {u.name for u in order[:exact]}, units)
        n, codes, files = mypy(out)
        print(f"  src_{t}: {n} errors in {len(files)} files; codes {dict(codes)}; untyped units: {[f'{u.file}:{u.name}' for u in order[exact:]][:12]}")
    shutil.rmtree(tmp, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
