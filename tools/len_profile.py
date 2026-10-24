"""Token-length profile of the training pool -> choose MAX_LEN."""
import json
from pathlib import Path

from transformers import AutoTokenizer

ROOT = Path(__file__).resolve().parent.parent
tok = AutoTokenizer.from_pretrained(str(ROOT / "models" / "Qwen2.5-3B-Instruct"), trust_remote_code=True)

rows = []
with open(ROOT / "data" / "processed" / "train.jsonl", encoding="utf-8") as f:
    for i, line in enumerate(f):
        if i >= 800:
            break
        rows.append(json.loads(line))

sys_p = "You are a helpful medical assistant. Answer the patient's question accurately and concisely."
ql, al, tl = [], [], []
for r in rows:
    q = tok(r["instruction"], add_special_tokens=False)["input_ids"]
    a = tok(r["response"], add_special_tokens=False)["input_ids"]
    ql.append(len(q))
    al.append(len(a))
    tl.append(len(q) + len(a) + 40)
tl.sort()


def pct(x, p):
    return x[int(len(x) * p / 100) - 1]


print(f"n={len(rows)}")
print(f"question tokens  p50={sorted(ql)[len(ql)//2]} p90={pct(sorted(ql),90)} max={max(ql)}")
print(f"answer   tokens  p50={sorted(al)[len(al)//2]} p90={pct(sorted(al),90)} max={max(al)}")
for p in (50, 75, 90, 95, 99):
    print(f"total p{p:02d} = {pct(tl,p)}")
print("share <=512:", round(sum(1 for t in tl if t <= 512) / len(tl), 3))
print("share <=640:", round(sum(1 for t in tl if t <= 640) / len(tl), 3))
