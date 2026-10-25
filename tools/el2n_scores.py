"""EL2N baseline: score every training example, then keep the hardest ones.

EL2N (Paul et al., "Deep Learning on a Data Diet", 2021) scores a sample by the
L1 norm of its error vector, || p - y ||_1.  For a one-hot target over a softmax
this collapses to an exact identity:

    || p - e_y ||_1 = (1 - p_y) + sum_{v != y} p_v = 2 * (1 - p_y)

so the whole score is the per-token NLL, averaged over the response tokens.
Paul et al. also show that scores from an *under-trained* model are good enough,
which is why we use the base model with no reference training: it costs one
forward pass over the pool and no GPU-time beyond that.

What this gives us: a strong classical baseline for "which 30% do we keep".
If activation-based selection (nait) does not beat EL2N either, the honest
conclusion in the paper is "at this pool size, selection does not pay for
itself" - which is exactly what PREREG section 4 anticipated.

Usage
    python tools/el2n_scores.py --limit 200          # quick timing probe
    python tools/el2n_scores.py                      # full pool (~20-30 min)
    python tools/el2n_scores.py --no-subset          # scores only
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import torch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config as C  # noqa: E402

SYS_PROMPT = "You are a helpful medical assistant. Answer the question and explain briefly."


def build_prompt(tok, row):
    msgs = [
        {"role": "system", "content": SYS_PROMPT},
        {"role": "user", "content": row["instruction"]},
    ]
    return tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)


def write_subsets(scores: dict[str, float], pool: list[dict]) -> None:
    """Keep the HARDEST examples (highest EL2N) at each retention ratio.

    data_diet prunes the easiest samples first; keeping the top-k by score is
    the same rule expressed as "which subset to train on".
    """
    rank = sorted(scores, key=lambda k: -scores[k])
    by_ratio = {str(int(round(r * 100))): rank[: int(round(C.N_POOL * r))] for r in C.RATIOS}
    sp = C.SUBSETS / "subsets_el2n.json"
    sp.write_text(json.dumps({"el2n": by_ratio}, ensure_ascii=False), encoding="utf-8")

    keep30 = set(by_ratio["30"])
    dept: dict[str, int] = {}
    for r in pool:
        if r["id"] in keep30:
            dept[r["dept"]] = dept.get(r["dept"], 0) + 1

    vals = sorted(scores.values())
    q = lambda f: vals[min(len(vals) - 1, int(f * len(vals)))]  # noqa: E731
    stats = {
        "method": "el2n",
        "n_pool": len(pool),
        "scored": len(scores),
        "score_p50": round(q(.50), 6),
        "score_p99": round(q(.99), 6),
        "kept_30pct": len(by_ratio["30"]),
        "dept_counts_30": dept,
        "score_convention": "2*(1-p_true) averaged over response tokens, base model, no reference training",
    }
    (C.RESULTS / "select_stats_el2n.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[el2n] wrote {sp} (30% = {len(by_ratio['30'])} ids) and results/select_stats_el2n.json")
    print(f"[el2n] dept mix @30%: {dept}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="only score the first N rows (timing probe)")
    ap.add_argument("--bs", type=int, default=8)
    ap.add_argument("--max-len", type=int, default=C.MAX_LEN)
    ap.add_argument("--no-subset", action="store_true", help="write scores only, skip subset files")
    ap.add_argument("--from-scores", default="",
                    help="reuse an existing scores json (no model, no GPU)")
    ap.add_argument("--out", default=str(C.RESULTS / "el2n_scores.json"))
    args = ap.parse_args()

    pool = [json.loads(l) for l in open(C.PROC / "train.jsonl", encoding="utf-8")]
    n_file = len(pool)
    pool = pool[: C.N_POOL]
    if n_file != C.N_POOL:
        print(f"[el2n] NOTE: train.jsonl has {n_file} rows, using the first {C.N_POOL} "
              f"as the pool (set DATADIET_N_TRAIN to change). Subset sizes follow the pool.",
              flush=True)

    if args.from_scores:
        scores = json.loads(Path(args.from_scores).read_text(encoding="utf-8"))
        print(f"[el2n] reused {len(scores)} scores from {args.from_scores}")
        write_subsets(scores, pool)
        return

    from transformers import AutoModelForCausalLM, AutoTokenizer

    tok = AutoTokenizer.from_pretrained(C.BASE_DIR, local_files_only=True)
    model = AutoModelForCausalLM.from_pretrained(
        C.BASE_DIR, local_files_only=True,
        dtype=torch.bfloat16, device_map={"": 0},
    ).eval()

    rows = [json.loads(l) for l in open(C.PROC / "train.jsonl", encoding="utf-8")]
    pool = rows[: C.N_POOL]
    if args.limit:
        pool = pool[: args.limit]
    print(f"[el2n] scoring {len(pool)} examples with {C.BASE_DIR.name}", flush=True)

    scores, t0, done = {}, time.time(), 0
    # length-sorted batching keeps padding waste down (same trick as train.py)
    order = sorted(range(len(pool)), key=lambda i: len(pool[i]["instruction"]) + len(pool[i]["response"]))

    with torch.inference_mode():
        for s in range(0, len(order), args.bs):
            chunk = [pool[i] for i in order[s: s + args.bs]]
            p_ids = [tok(build_prompt(tok, r))["input_ids"] for r in chunk]
            f_ids = [tok(r["response"], add_special_tokens=False)["input_ids"] for r in chunk]

            seqs, spans = [], []
            for p, f in zip(p_ids, f_ids):
                ids = (p + f + [tok.eos_token_id])[: args.max_len]
                start = min(len(p), len(ids))
                if start >= len(ids):          # response got truncated away -> skip
                    spans.append(None)
                    seqs.append(ids)
                    continue
                spans.append((start, len(ids)))
                seqs.append(ids)

            width = max(len(x) for x in seqs)
            pad = tok.pad_token_id or tok.eos_token_id
            inp = torch.full((len(seqs), width), pad, dtype=torch.long, device="cuda")
            att = torch.zeros_like(inp)
            for i, ids in enumerate(seqs):
                inp[i, : len(ids)] = torch.tensor(ids, device="cuda")
                att[i, : len(ids)] = 1

            logits = model(input_ids=inp, attention_mask=att).logits.float()
            logp = torch.log_softmax(logits[:, :-1], dim=-1)
            tgt = inp[:, 1:]
            tok_nll = -logp.gather(-1, tgt.unsqueeze(-1)).squeeze(-1)   # (B, T-1)

            for i, span in enumerate(spans):
                if span is None:
                    continue
                start, end = span
                # token j of the response sits at position j-1 in the shifted view
                lo, hi = max(start - 1, 0), max(end - 1, 0)
                if hi <= lo:
                    continue
                nll = tok_nll[i, lo:hi]
                scores[chunk[i]["id"]] = float(2.0 * nll.mean())       # ||p - y||_1
            done += len(chunk)
            if done % (args.bs * 10) == 0 or done >= len(pool):
                el = time.time() - t0
                print(f"[el2n] {done}/{len(pool)}  {done / max(el, 1e-9):.1f} samp/s  "
                      f"{el / 60:.1f} min elapsed", flush=True)

    if len(scores) < len(pool):
        print(f"[el2n] WARNING: scored {len(scores)} of {len(pool)} (rest were truncated-away)")

    out = Path(args.out)
    out.write_text(json.dumps(scores, indent=0), encoding="utf-8")
    vals = sorted(scores.values())
    q = lambda f: vals[min(len(vals) - 1, int(f * len(vals)))]  # noqa: E731
    print(f"[el2n] wrote {out}  n={len(scores)}  "
          f"p50={q(.50):.4f} p90={q(.90):.4f} p99={q(.99):.4f} max={vals[-1]:.4f}")

    if args.no_subset:
        return

    write_subsets(scores, pool)


if __name__ == "__main__":
    main()
