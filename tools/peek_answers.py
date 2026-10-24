import json, pathlib, sys
root = pathlib.Path(__file__).resolve().parents[1]
for name in ("medqa", "medmcqa"):
    rows = [json.loads(l) for l in open(root / "data" / "processed" / f"{name}.jsonl", encoding="utf-8")]
    print(name, len(rows))
    print("  first:", {k: (v if k != "options" else v[:2]) for k, v in rows[0].items()})
    print("  answer types:", {type(r["answer"]).__name__ for r in rows},
          "values:", sorted({r["answer"] for r in rows})[:8])
