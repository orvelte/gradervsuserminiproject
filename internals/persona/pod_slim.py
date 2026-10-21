#!/usr/bin/env python3
"""On the pod: keep only the layers the analysis reads, so the download is small (decision #98).

    python pod_slim.py in_dir out_dir [--layers 0,32]

Each output npz has the same `id`, `names`, `counts`, plus `layers` (the kept layer indices) and `means`
[n_spans, len(layers), hidden] (fp16). analyze.py maps layer numbers through `layers` when present.
"""
import sys
from pathlib import Path

import numpy as np


def main(argv) -> int:
    src, out = Path(argv[0]), Path(argv[1]); out.mkdir(parents=True, exist_ok=True)
    layers = [int(x) for x in (argv[argv.index("--layers") + 1] if "--layers" in argv else "0,32").split(",")]
    n = 0
    for f in sorted(src.glob("*.npz")):
        g = out / f.name
        if g.exists():
            continue
        z = np.load(f, allow_pickle=False)
        np.savez(g, id=z["id"], names=z["names"], counts=z["counts"], layers=np.array(layers), means=z["means"][:, layers, :])
        n += 1
    print(f"slimmed {n} files to layers {layers}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
