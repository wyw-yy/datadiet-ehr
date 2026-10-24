"""Print one real training sample + length stats, for eyeballing the data."""
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent

if __name__ == "__main__":
    pool = sys.argv[1] if len(sys.argv) > 1 else "domain"
    if pool == "domain":
        p = ROOT / "data" / "raw" / "medmcqa-train" / "train.parquet"
        df = pd.read_parquet(p)
        print(f"rows: {len(df)}  cols: {list(df.columns)}")
        print("exp len p50/p90/p99:",
              df["exp"].astype(str).str.len().quantile([.5, .9, .99]).round(0).to_dict())
        r = df.iloc[7]
        print("\n--- one real training sample ---")
        print("Q:", r["question"][:200])
        for k, c in zip("ABCD", ["opa", "opb", "opc", "opd"]):
            print(f"   {k}. {r[c]}")
        print("answer:", "ABCD"[int(r["cop"])], "| explanation:", str(r["exp"])[:200])
    else:
        p = ROOT / "data" / "processed" / "train.jsonl"
        import json
        rows = [json.loads(l) for l in open(p, encoding="utf-8")]
        print(f"rows: {len(rows)}")
        for r in rows[7:9]:
            print("\n--- training sample", r["id"], r["dept"], "---")
            print("Q:", r["instruction"][:200])
            print("A:", r["response"][:200])
