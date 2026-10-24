import sys
from pathlib import Path

import numpy as np

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parent.parent

for split in ("train", "probe"):
    p = ROOT / "cache" / "acts" / f"acts_{split}.npz"
    z = np.load(p, allow_pickle=True)
    print(split, "keys:", list(z.keys()))
    ids = z["ids"] if "ids" in z else None
    for k in z.keys():
        v = z[k]
        print("   ", k, getattr(v, "shape", None), getattr(v, "dtype", None))
    if ids is not None:
        print("    ids[:3]:", [str(x) for x in ids[:3]])
        print("    首字符集合:", sorted({str(x)[0] for x in ids}))
