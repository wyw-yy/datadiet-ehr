import shutil
from pathlib import Path

import pyarrow.parquet as pq

RAW = Path(__file__).resolve().parent.parent / "data" / "raw"
src = RAW / "healthcaremagic" / "data" / "train-00000-of-00001-5e7cb295b9cff0bf.parquet"
dst = RAW / "healthcaremagic" / "hcm-100k.parquet"

if src.exists() and src.stat().st_size == 70518148:
    if not dst.exists() or dst.stat().st_size != 70518148:
        shutil.copyfile(src, dst)
        print("copied ->", dst.name, dst.stat().st_size)
else:
    print("src missing or wrong size:", src.stat().st_size if src.exists() else None)

for name in ["healthcaremagic/hcm-100k.parquet", "medqa/phrases_no_exclude_test.jsonl"]:
    p = RAW / name
    print(f"{name:45s} exists={p.exists()}")

t = pq.read_table(dst)
print("HCM rows:", t.num_rows, "cols:", t.column_names)
df = t.slice(0, 2).to_pylist()
for r in df:
    print({k: (str(v)[:90]) for k, v in r.items()})
