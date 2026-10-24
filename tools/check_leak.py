"""Sanity check after swapping the training pool: no leakage between splits."""
import json
from pathlib import Path

PROC = Path(__file__).resolve().parent.parent / "data" / "processed"


def keys(name, field, cut=80):
    p = PROC / f"{name}.jsonl"
    out = set()
    with open(p, encoding="utf-8") as f:
        for line in f:
            out.add(json.loads(line)[field].strip()[:cut].lower())
    return out


def main():
    tr = keys("train", "instruction")
    pr = keys("probe", "instruction")
    for task, field in (("medqa", "question"), ("medmcqa", "question")):
        ev = keys(task, field)
        print(f"{task:9s} eval={len(ev):5d}  overlap with train={len(tr & ev):4d}  "
              f"with probe={len(pr & ev):3d}")
    print(f"train={len(tr)} probe={len(pr)}  train&probe overlap={len(tr & pr)}")


if __name__ == "__main__":
    main()
