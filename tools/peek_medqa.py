import json
from pathlib import Path

p = Path(__file__).resolve().parent.parent / "data" / "raw" / "medqa" / "phrases_no_exclude_test.jsonl"
rows = [json.loads(l) for l in open(p, encoding="utf-8")]
print("rows", len(rows))
print("keys", list(rows[0].keys()))
r = rows[0]
print("options type", type(r.get("options")), list(r.get("options", {}))[:5])
print("answer_idx", r.get("answer_idx"))
print("meta", str(r.get("meta_info"))[:120])
