"""LoRA fine-tuning of Qwen2.5-Instruct on a (possibly reduced) clinical set.

One call = one training run. Everything the analysis layer needs is written to
results/runs/<exp_id>.json so run_one.py can append it to the CSVs R reads.

    python train.py --method nait --ratio 0.30 --seed 1 --epochs 1
    python train.py --method full --seed 1 --epochs 1
    python train.py --method random --ratio 0.30 --seed 1 --epochs 1 --limit 200   # smoke

Speed notes (RTX 5070 Laptop, 8 GiB):
  * tokenise once and cache to data/cache/ - the tokenizer is not the bottleneck
    but re-running the chat template 24k times per run is pure waste;
  * length-bucketed batches: padding to the max length of a random batch costs
    30-40% of the FLOPs when the pool p50 is 256 tokens;
  * --no-gc drops gradient checkpointing (~30% faster) and OOMs above bs 2 on 3B.

Conventions (must match R/00_setup.R):
    exp_id = full_s<seed>            for the full-data baseline
           = <method>_r<RR>_s<seed>  otherwise
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import time
from pathlib import Path

import torch

import config as C

SYSTEM = ("You are a helpful medical assistant. Answer the patient's question "
          "accurately and concisely.")


# --------------------------------------------------------------------------- data
def read_jsonl(path: Path) -> list[dict]:
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def pick_rows(method: str, ratio: float, seed: int, limit: int | None) -> tuple[list[dict], dict]:
    """Resolve the subset for this (method, ratio, seed) and return its rows."""
    pool = read_jsonl(C.PROC / "train.jsonl")
    pool = pool[: C.N_POOL]
    meta = {"pool_size": len(pool)}

    if method == "full":
        rows = pool
    elif method == "random":
        rng = random.Random(seed)                      # seed-dependent, reproducible
        n = int(round(ratio * len(pool)))
        idx = sorted(rng.sample(range(len(pool)), n))
        rows = [pool[i] for i in idx]
    else:
        subset_file = C.subset_file_for(method)
        if not subset_file.exists():
            raise SystemExit(f"[train] missing {subset_file} - run select_subset.py first")
        with open(subset_file, encoding="utf-8") as f:
            subsets = json.load(f)
        key = str(int(round(ratio * 100)))
        if method not in subsets or key not in subsets[method]:
            raise SystemExit(f"[train] no subset {method}/{key} in {subset_file}")
        want = set(subsets[method][key])
        rows = [r for r in pool if r["id"] in want]

    if limit:
        rows = rows[:limit]
        meta["pool_size"] = len(pool)
    meta["n_samples"] = len(rows)
    return rows, meta


def encode(rows: list[dict], tok, max_len: int) -> list[dict]:
    """Chat-template every row once; loss only on the response tokens."""
    out = []
    for i, r in enumerate(rows):
        msgs_p = [{"role": "system", "content": SYSTEM},
                  {"role": "user", "content": r["instruction"]}]
        msgs_f = msgs_p + [{"role": "assistant", "content": r["response"]}]
        prompt = tok.apply_chat_template(msgs_p, tokenize=False, add_generation_prompt=True)
        full = tok.apply_chat_template(msgs_f, tokenize=False, add_generation_prompt=False)
        p_ids = tok(prompt, add_special_tokens=False)["input_ids"]
        f_ids = tok(full, add_special_tokens=False)["input_ids"]
        if len(f_ids) > max_len:
            f_ids = f_ids[:max_len]
        n_p = min(len(p_ids), len(f_ids))
        labels = [-100] * n_p + f_ids[n_p:]
        out.append({"input_ids": f_ids, "labels": labels, "id": r["id"]})
        if (i + 1) % 5000 == 0:
            print(f"  encoded {i + 1}/{len(rows)}", flush=True)
    return out


def encode_cached(rows: list[dict], tok, max_len: int, tag: str) -> list[dict]:
    """Cache the tokenised subset; key = ids + max_len (so a new subset re-encodes)."""
    h = hashlib.sha1(("%d|" % max_len + ",".join(r["id"] for r in rows)).encode()).hexdigest()[:16]
    path = C.CACHE / f"sft_{tag}_{h}.pt"
    if path.exists():
        try:
            return torch.load(path, weights_only=False)
        except Exception:                                  # noqa: BLE001 - stale cache
            pass
    enc = encode(rows, tok, max_len)
    torch.save(enc, path)
    return enc


def make_batches(enc: list[dict], bs: int, seed: int) -> list[list[int]]:
    """Length-bucketed batches: sort by length, cut into blocks of bs, shuffle blocks."""
    order = sorted(range(len(enc)), key=lambda i: len(enc[i]["input_ids"]))
    batches = [order[i:i + bs] for i in range(0, len(order), bs)]
    random.Random(seed).shuffle(batches)
    return batches


def collate(items, pad_id):
    L = max(len(b["input_ids"]) for b in items)
    ids, lab, att = [], [], []
    for b in items:
        n = len(b["input_ids"])
        ids.append(b["input_ids"] + [pad_id] * (L - n))
        lab.append(b["labels"] + [-100] * (L - n))
        att.append([1] * n + [0] * (L - n))
    return (torch.tensor(ids), torch.tensor(lab), torch.tensor(att))


# ------------------------------------------------------------------------- model
def load_base():
    from transformers import AutoModelForCausalLM, AutoTokenizer
    base = str(C.BASE_DIR)
    tok = AutoTokenizer.from_pretrained(base, trust_remote_code=True)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    kw = dict(trust_remote_code=True, device_map={"": 0})
    try:
        model = AutoModelForCausalLM.from_pretrained(base, dtype=torch.bfloat16, **kw)
    except TypeError:                                   # transformers v4
        model = AutoModelForCausalLM.from_pretrained(base, torch_dtype=torch.bfloat16, **kw)
    model.config.use_cache = False
    return model, tok


def attach_lora(model):
    from peft import LoraConfig, get_peft_model
    cfg = LoraConfig(r=16, lora_alpha=32, lora_dropout=0.05, bias="none",
                     task_type="CAUSAL_LM",
                     target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                                     "gate_proj", "up_proj", "down_proj"])
    model = get_peft_model(model, cfg)
    model.print_trainable_parameters()
    return model


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--method", required=True, choices=C.METHODS)
    ap.add_argument("--ratio", type=float, default=1.0)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--epochs", type=float, default=1.0)
    ap.add_argument("--max-len", type=int, default=C.MAX_LEN)
    ap.add_argument("--bs", type=int, default=4)
    ap.add_argument("--grad-accum", type=int, default=2)
    ap.add_argument("--lr", type=float, default=1e-4)
    ap.add_argument("--limit", type=int, default=None, help="cap the number of training rows (smoke test)")
    ap.add_argument("--no-gc", action="store_true", help="disable gradient checkpointing (faster, more VRAM)")
    ap.add_argument("--no-save", action="store_true", help="do not keep the adapter weights")
    a = ap.parse_args()

    C.ensure_dirs()
    eid = C.exp_id(a.method, a.ratio, a.seed)
    out_dir = C.ADAPTERS / eid
    rows, meta = pick_rows(a.method, a.ratio, a.seed, a.limit)
    if not rows:
        raise SystemExit("[train] empty training set")
    print(f"[train] {eid}: {len(rows)} samples, {a.epochs} epoch(s), max_len={a.max_len}, "
          f"bs={a.bs}x{a.grad_accum}", flush=True)

    model, tok = load_base()
    model = attach_lora(model)
    if not a.no_gc:
        model.gradient_checkpointing_enable()
    model.train()

    enc = encode_cached(rows, tok, a.max_len, tag=eid if not a.limit else f"limit{a.limit}")
    batches = make_batches(enc, a.bs, a.seed)
    steps_per_epoch = max(1, math.ceil(len(batches) / a.grad_accum))
    total_steps = max(1, int(math.ceil(steps_per_epoch * a.epochs)))
    opt = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad], lr=a.lr)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=a.lr, total_steps=total_steps,
                                                pct_start=0.05)

    t0 = time.time()
    step, seen, losses = 0, 0, []
    stop = False
    for ep in range(int(math.ceil(a.epochs))):
        random.Random(a.seed + ep).shuffle(batches)
        for i, idx in enumerate(batches):
            ids, lab, att = collate([enc[j] for j in idx], tok.pad_token_id)
            ids, lab, att = ids.cuda(), lab.cuda(), att.cuda()
            out = model(input_ids=ids, attention_mask=att, labels=lab)
            loss = out.loss / a.grad_accum
            loss.backward()
            losses.append(float(out.loss.detach()))
            seen += ids.shape[0]
            if (i + 1) % a.grad_accum == 0:
                torch.nn.utils.clip_grad_norm_([p for p in model.parameters() if p.requires_grad], 1.0)
                opt.step()
                sched.step()
                opt.zero_grad(set_to_none=True)
                step += 1
                if step % 10 == 0 or step == total_steps:
                    avg = sum(losses[-min(len(losses), 20):]) / min(len(losses), 20)
                    el = time.time() - t0
                    print(f"  step {step}/{total_steps}  loss {avg:.4f}  "
                          f"{seen} samples  {seen / max(el, 1e-9):.2f} samp/s  "
                          f"{el / 60:.1f} min", flush=True)
                if step >= total_steps:
                    stop = True
                    break
        if stop:
            break

    train_s = time.time() - t0
    if not a.no_save:
        out_dir.mkdir(parents=True, exist_ok=True)
        model.save_pretrained(str(out_dir))
        tok.save_pretrained(str(out_dir))

    rec = {"exp_id": eid, "method": a.method, "ratio": float(a.ratio), "seed": a.seed,
           "epochs": a.epochs, "n_samples": len(rows), "steps": step,
           "max_len": a.max_len, "bs": a.bs, "grad_accum": a.grad_accum,
           "train_seconds": round(train_s, 1),
           "loss_last": round(sum(losses[-20:]) / max(1, min(len(losses), 20)), 4),
           "adapter": None if a.no_save else str(out_dir), **meta}
    (C.RUNS / f"{eid}.json").parent.mkdir(parents=True, exist_ok=True)
    with open(C.RUNS / f"{eid}.json", "w", encoding="utf-8") as f:
        json.dump(rec, f, indent=2)
    print(f"[train] done in {train_s / 60:.1f} min -> {C.RUNS / (eid + '.json')}", flush=True)


if __name__ == "__main__":
    main()
