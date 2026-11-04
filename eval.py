"""Score a model on MedQA / MedMCQA with a single forward pass per question.

Instead of generating text and regex-matching an option letter, we read the
logits at the answer position and compare the probabilities of the four option
tokens. It is deterministic, ~30x cheaper than generation, and it degrades
gracefully (a model that always says "A" still gets scored as saying "A").

The prompt goes through the model's chat template with add_generation_prompt=True,
so the scored position is exactly the first assistant token - the same position
the SFT loss was computed on.

    python eval.py --task medqa                       # base model
    python eval.py --task medqa --adapter models/adapters/nait_r30_s1
    python eval.py --task medqa --limit 100 --out /tmp/preds.csv.gz

Output columns: item_id, dept, pred, correct, pA, pB, pC, pD
"""
from __future__ import annotations

import argparse
import gzip
import json
import time
from pathlib import Path

import torch

import config as C

LETTERS = ["A", "B", "C", "D"]


def read_jsonl(path: Path) -> list[dict]:
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def build_messages(r: dict) -> list[dict]:
    opts = "\n".join(f"{LETTERS[i]}. {o}" for i, o in enumerate(r["options"][:4]))
    user = (f"Question: {r['question']}\n\n{opts}\n\n"
            f"Reply with the single letter of the correct option.")
    return [{"role": "system", "content": "You are a medical expert answering a multiple-choice question."},
            {"role": "user", "content": user}]


def option_token_ids(tok):
    """Token ids for ' A'..' D' (Qwen tokenises a leading space as its own token)."""
    ids = []
    for L in LETTERS:
        for cand in (f" {L}", L):
            t = tok(cand, add_special_tokens=False)["input_ids"]
            if len(t) == 1:
                ids.append(t[0])
                break
        else:
            raise SystemExit(f"[eval] cannot encode option letter {L} as a single token")
    return ids


def _resolve_adapter(a: str | None) -> str | None:
    """--adapter 既接受完整路径，也接受 models/adapters/<name> 里的目录名。

    只给目录名时必须先拼成路径：否则 transformers 会把它当成 HuggingFace repo id
    去联网找，离线时直接抛 "We couldn't connect to 'https://huggingface.co'"。
    """
    if not a:
        return None
    p = Path(a)
    if p.is_dir():
        return str(p.resolve())
    cand = Path(C.ADAPTER_DIR) / a if hasattr(C, "ADAPTER_DIR") else None
    if cand is not None and cand.is_dir():
        return str(cand.resolve())
    alt = Path(C.BASE_DIR).parent / "adapters" / a
    if alt.is_dir():
        return str(alt.resolve())
    raise SystemExit(f"[eval] adapter not found: {a} (tried path, models/adapters/{a})")


def load_model(base: Path, adapter: str | None):
    from transformers import AutoModelForCausalLM, AutoTokenizer
    adapter = _resolve_adapter(adapter)
    if adapter:
        from peft import PeftModel
        tok = AutoTokenizer.from_pretrained(adapter, trust_remote_code=True)
    else:
        tok = AutoTokenizer.from_pretrained(str(base), trust_remote_code=True)
    tok.pad_token = tok.pad_token or tok.eos_token
    tok.padding_side = "left"              # left pad: the answer sits at the last position
    kw = dict(trust_remote_code=True, device_map={"": 0})
    try:
        model = AutoModelForCausalLM.from_pretrained(str(base), dtype=torch.bfloat16, **kw)
    except TypeError:
        model = AutoModelForCausalLM.from_pretrained(str(base), torch_dtype=torch.bfloat16, **kw)
    if adapter:
        model = PeftModel.from_pretrained(model, adapter)
    model.eval()
    model.config.use_cache = False
    return model, tok


@torch.inference_mode()
def score_batch(model, tok, prompts: list[str], opt_ids: list[int], max_len: int):
    enc = tok(prompts, add_special_tokens=False, return_tensors="pt",
              padding=True, truncation=True, max_length=max_len)
    ids = enc["input_ids"].cuda()
    att = enc["attention_mask"].cuda()
    logits = model(input_ids=ids, attention_mask=att).logits[:, -1, :].float()
    logp = torch.log_softmax(logits, dim=-1)[:, opt_ids]      # (B, 4)
    p = torch.softmax(logits, dim=-1)[:, opt_ids]
    return logp.tolist(), p.tolist()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", required=True, choices=["medqa", "medmcqa"])
    ap.add_argument("--adapter", default=None)
    ap.add_argument("--out", default=None, help="csv.gz path (default results/preds/<exp>.csv.gz)")
    ap.add_argument("--exp-id", default=None)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--max-len", type=int, default=1024)
    ap.add_argument("--bs", type=int, default=16)
    a = ap.parse_args()

    src = C.PROC / f"{a.task}.jsonl"
    rows = read_jsonl(src)
    if a.limit:
        rows = rows[: a.limit]
    if not rows:
        raise SystemExit(f"[eval] {src} is empty")

    out = Path(a.out) if a.out else C.PREDS / f"{a.exp_id or 'base'}_{a.task}.csv.gz"
    out.parent.mkdir(parents=True, exist_ok=True)

    model, tok = load_model(C.BASE_DIR, a.adapter)
    opt_ids = option_token_ids(tok)
    prompts = [tok.apply_chat_template(build_messages(r), tokenize=False,
                                       add_generation_prompt=True) for r in rows]
    print(f"[eval] {a.task}: {len(rows)} items, adapter={a.adapter or 'none'}, bs={a.bs} -> {out}",
          flush=True)

    t0 = time.time()
    lines = ["item_id,dept,pred,correct,pA,pB,pC,pD"]
    n_ok = 0
    for start in range(0, len(rows), a.bs):
        chunk = rows[start:start + a.bs]
        lp, p = score_batch(model, tok, prompts[start:start + a.bs], opt_ids, a.max_len)
        for k, r in enumerate(chunk):
            pred = LETTERS[max(range(4), key=lambda j: lp[k][j])]
            # answer is the 0-based option index (prepare_data stores ints)
            ok = int(LETTERS.index(pred) == int(r["answer"]))
            n_ok += ok
            lines.append(f"{r['id']},{r.get('dept', 'other')},{pred},{ok},"
                         + ",".join(f"{x:.6f}" for x in p[k]))
        done = start + len(chunk)
        if done % (a.bs * 5) < a.bs or done == len(rows):
            el = time.time() - t0
            print(f"  {done}/{len(rows)}  acc {n_ok / done:.4f}  "
                  f"{done / max(el, 1e-9):.1f} items/s", flush=True)

    with gzip.open(out, "wt", encoding="utf-8", newline="") as f:
        f.write("\n".join(lines) + "\n")
    acc = n_ok / len(rows)
    print(f"[eval] accuracy {acc:.4f} ({n_ok}/{len(rows)}) -> {out}", flush=True)
    print(f"ACCURACY={acc:.6f}")


if __name__ == "__main__":
    main()
