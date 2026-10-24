"""Extract mean-pooled hidden states (neuron activations) for every training sample.

Why mean-pool over response tokens only: the "activation" of a sample in the
sense of Nait (Chen et al., ICLR 2026) is the pattern the model produces while
*generating* the answer, not while reading the question. Prompt tokens are
shared by thousands of samples and would wash the signal out.

Output: cache/acts/acts_<split>.npz
    ids    (N,)            sample ids, same order as processed jsonl
    feats  (N, L, D)       float16, L = len(config.LAYERS)
    layers (L,)            which hidden layers these came from
"""
from __future__ import annotations

import argparse
import json
import sys
import time

import numpy as np
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

import config as C


def read_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def load_model(path):
    """Load in bf16 with whatever keyword the installed transformers accepts."""
    kw = dict(attn_implementation="sdpa", device_map=None)
    for key in ("dtype", "torch_dtype"):
        try:
            model = AutoModelForCausalLM.from_pretrained(path, **{key: torch.bfloat16}, **kw)
            break
        except TypeError:
            continue
    else:
        model = AutoModelForCausalLM.from_pretrained(path, **kw)
    model.eval()
    return model.to("cuda" if torch.cuda.is_available() else "cpu")


def build_sequences(tok, examples, max_len):
    """Return list of (prompt_ids, response_ids) with the response truncated to fit."""
    out = []
    for ex in examples:
        msgs = [{"role": "user", "content": ex["instruction"]}]
        prompt = tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
        p_ids = tok(prompt, add_special_tokens=False)["input_ids"]
        r_ids = tok(" " + ex["response"], add_special_tokens=False)["input_ids"]
        r_ids = r_ids[: max(1, max_len - len(p_ids) - 1)] + [tok.eos_token_id]
        out.append((p_ids, r_ids))
    return out


@torch.no_grad()
def run(split="train", batch_size=4, max_len=None, limit=None):
    max_len = max_len or C.MAX_LEN
    src = C.PROC / f"{split}.jsonl"
    if not src.exists():
        sys.exit(f"[collect_acts] missing {src} — run prepare_data.py first")

    examples = read_jsonl(src)
    if split == "train":
        # train.py only ever trains on pool[:N_POOL]; activations must cover exactly
        # that prefix, otherwise a subset could name rows the trainer cannot see.
        examples = examples[: C.N_POOL]
    if limit:
        examples = examples[:limit]

    tok = AutoTokenizer.from_pretrained(C.BASE_DIR)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    model = load_model(C.BASE_DIR)

    layers = [int(x) for x in C.LAYERS]
    n_layers = model.config.num_hidden_layers
    if max(layers) >= n_layers:
        sys.exit(f"[collect_acts] model has {n_layers} layers, asked for {layers}")
    hidden = model.config.hidden_size

    seqs = build_sequences(tok, examples, max_len)
    feats = np.zeros((len(seqs), len(layers), hidden), dtype=np.float16)
    ids = [ex["id"] for ex in examples]

    t0 = time.time()
    done_tokens = 0
    for start in range(0, len(seqs), batch_size):
        chunk = seqs[start : start + batch_size]
        maxlen = max(len(p) + len(r) for p, r in chunk)
        input_ids = torch.full((len(chunk), maxlen), tok.pad_token_id, dtype=torch.long)
        attn = torch.zeros((len(chunk), maxlen), dtype=torch.long)
        resp_mask = torch.zeros((len(chunk), maxlen), dtype=torch.bool)
        for i, (p, r) in enumerate(chunk):
            ids_i = p + r
            input_ids[i, : len(ids_i)] = torch.tensor(ids_i)
            attn[i, : len(ids_i)] = 1
            resp_mask[i, len(p) : len(ids_i)] = True
            done_tokens += len(ids_i)

        input_ids = input_ids.to(model.device)
        attn = attn.to(model.device)
        resp_mask = resp_mask.to(model.device)

        out = model(input_ids=input_ids, attention_mask=attn, output_hidden_states=True,
                    use_cache=False)
        # hidden_states[k] = output of layer k-1 (index 0 is the embedding output)
        for li, layer in enumerate(layers):
            h = out.hidden_states[layer].float()                      # (B, T, D)
            mask = resp_mask.unsqueeze(-1).float()
            pooled = (h * mask).sum(1) / mask.sum(1).clamp(min=1.0)   # (B, D)
            feats[start : start + len(chunk), li, :] = pooled.half().cpu().numpy()

        if start % (batch_size * 20) == 0:
            rate = done_tokens / max(1e-6, time.time() - t0)
            print(f"  {start + len(chunk)}/{len(seqs)}  {rate:,.0f} tok/s", flush=True)

    C.ensure_dirs()
    dst = C.ACTS / f"acts_{split}.npz"
    np.savez_compressed(dst, ids=np.array(ids), feats=feats,
                        layers=np.array(layers, dtype=np.int32))
    print(f"[collect_acts] wrote {dst}  shape={feats.shape}  "
          f"{dst.stat().st_size / 1e6:.0f} MB  {time.time() - t0:.0f}s")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="train", choices=["train", "probe"])
    ap.add_argument("--batch-size", type=int, default=4)
    ap.add_argument("--max-len", type=int, default=None)
    ap.add_argument("--limit", type=int, default=None)
    a = ap.parse_args()
    run(a.split, a.batch_size, a.max_len, a.limit)
