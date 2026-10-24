"""Turn activations into training subsets (the actual "DataDiet" step).

Three-stage protocol (PLAN.md §2, G4):
  1. near-duplicate removal  — greedy by score, reject cosine > DEDUP_COS
  2. department-stratified quota — every dept keeps its share of the budget
  3. fill by score — within quota, take the highest-scoring samples first

Score of sample i:  s_i = mean_l  cos( a_{i,l}, c_l )
where c_l is the centroid of layer l over the in-domain probe set — i.e. "how
prototypical of clinical language is this sample" in neuron space.

Output: data/subsets/subsets.json
    {"nait": {"10": [ids...], "20": [...]}, "nait_dedup": {...}}
"random" is not stored: it needs the training seed, and train.py draws it.
"""
from __future__ import annotations

import argparse
import json
import time

import numpy as np

import config as C


def load_acts(split):
    p = C.ACTS / f"acts_{split}.npz"
    if not p.exists():
        raise SystemExit(f"[select] missing {p} — run collect_acts.py --split {split} first")
    z = np.load(p, allow_pickle=True)
    return list(z["ids"]), z["feats"].astype(np.float32)      # (N, L, D)


def l2norm(x, axis=-1):
    n = np.linalg.norm(x, axis=axis, keepdims=True)
    return x / np.maximum(n, 1e-8)


def center(feats, mu):
    """Remove the shared mean direction (anisotropy) of the activation space.

    Raw hidden states of an LLM all point roughly the same way: the cosine between
    two arbitrary samples sits around 0.95, so a fixed 0.95 duplicate threshold
    would flag almost everything as duplicate. Subtracting the per-layer mean over
    the pool and only then normalising makes the remaining vector describe what is
    *specific* to a sample, which is what both the score and the dedupe need.
    """
    return feats - mu


def nait_scores(train_feats, probe_feats):
    """mean over layers of cosine(sample_l, centroid_l), on centered activations."""
    mu = train_feats.mean(axis=0, keepdims=True)              # (1, L, D)
    tr = l2norm(center(train_feats, mu))                      # (N, L, D)
    cen = l2norm(center(probe_feats, mu).mean(axis=0))        # (L, D)
    cos = np.einsum("nld,ld->nl", tr, cen)                    # (N, L)
    return cos.mean(axis=1), tr


def pair_sim_stats(tr_norm, n_pairs=20000, seed=0):
    """Sanity check: what does a random pair look like before we dedupe?"""
    rng = np.random.default_rng(seed)
    n = tr_norm.shape[0]
    i = rng.integers(0, n, n_pairs)
    j = rng.integers(0, n, n_pairs)
    flat = tr_norm.reshape(n, -1)
    flat = flat / np.maximum(np.linalg.norm(flat, axis=1, keepdims=True), 1e-8)
    sims = np.einsum("nd,nd->n", flat[i], flat[j])
    q = np.percentile(sims, [50, 90, 99])
    return q


def greedy_kept_streaming(tr_norm, order, thr, chunk=1024):
    """Keep samples in score order, skipping any that is a near-duplicate of a kept one.

    Streaming version: the full N x N similarity matrix is never materialised
    (24k x 24k booleans = 576 MB, which is too much on a laptop that is also
    holding a model). Each chunk is compared against the kept set so far
    (chunk x K floats), and within the chunk the survivors are compared against
    each other (chunk x chunk) — exact same greedy result, bounded memory.
    """
    try:
        import torch
        dev = "cuda" if torch.cuda.is_available() else "cpu"
        flat = torch.from_numpy(tr_norm.reshape(tr_norm.shape[0], -1).astype(np.float32)).to(dev)
        flat = flat / flat.norm(dim=1, keepdim=True).clamp(min=1e-8)
        kept = []
        kept_t = torch.empty((0, flat.shape[1]), device=dev)
        n_checked = 0
        for s in range(0, len(order), chunk):
            cand = torch.as_tensor(order[s:s + chunk], dtype=torch.long, device=dev)
            if kept_t.shape[0]:
                sims = flat[cand] @ kept_t.T                      # (c, K)
                ok = sims.max(dim=1).values <= thr
            else:
                ok = torch.ones(len(cand), dtype=torch.bool, device=dev)
            sub = cand[ok]
            if sub.numel():
                m = flat[sub] @ flat[sub].T                       # (c', c')
                m.fill_diagonal_(-1.0)
                dup_local = (m > thr).any(dim=1)
                keep_local = sub[~dup_local]
                kept.extend(keep_local.cpu().tolist())
                kept_t = torch.cat([kept_t, flat[keep_local]], dim=0)
            n_checked += len(cand)
            print(f"  dedupe {n_checked}/{len(order)} kept={len(kept)}", flush=True)
        del flat, kept_t
        if dev == "cuda":
            torch.cuda.empty_cache()
        return np.array(kept, dtype=np.int32)
    except ImportError:
        pass

    # numpy fallback: same algorithm, chunked matmul
    flat = tr_norm.reshape(tr_norm.shape[0], -1).astype(np.float32)
    flat /= np.maximum(np.linalg.norm(flat, axis=1, keepdims=True), 1e-8)
    kept, kept_f = [], np.empty((0, flat.shape[1]), dtype=np.float32)
    for s in range(0, len(order), chunk):
        cand = np.asarray(order[s:s + chunk])
        sims = flat[cand] @ kept_f.T if len(kept) else np.full((len(cand), 1), -1.0, np.float32)
        ok = sims.max(axis=1) <= thr
        sub = cand[ok]
        if len(sub):
            m = flat[sub] @ flat[sub].T
            np.fill_diagonal(m, -1.0)
            keep_local = sub[~(m > thr).any(axis=1)]
            kept.extend(keep_local.tolist())
            kept_f = np.vstack([kept_f, flat[keep_local]]) if len(kept_f) else flat[keep_local]
    return np.array(kept, dtype=np.int32)


def stratified_pick(cand_idx, cand_scores, depts, target_n):
    """Fill target_n slots in proportion to dept size, by descending score."""
    depts = np.asarray(depts)
    counts = {d: int((depts[cand_idx] == d).sum()) for d in set(depts)}
    total = sum(counts.values())
    if total == 0:
        return cand_idx[np.argsort(-cand_scores)[:target_n]]

    # largest-remainder rounding so quotas sum exactly to target_n
    raw = {d: target_n * c / total for d, c in counts.items()}
    quota = {d: int(np.floor(v)) for d, v in raw.items()}
    rest = target_n - sum(quota.values())
    for d in sorted(raw, key=lambda d: raw[d] - quota[d], reverse=True)[:rest]:
        quota[d] += 1

    chosen = []
    order = np.argsort(-cand_scores)
    for d, q in quota.items():
        if q <= 0:
            continue
        pool = [i for i in order if depts[cand_idx[i]] == d]
        chosen.extend(cand_idx[pool[:q]])
    if len(chosen) < target_n:                                # dept starved after dedupe
        picked = set(chosen)
        for i in order:
            if len(chosen) >= target_n:
                break
            if cand_idx[i] not in picked:
                chosen.append(int(cand_idx[i]))
    return np.array(sorted(chosen), dtype=np.int32)


def main(limit=None, do_dedup=True, probe_split="probe", suffix=""):
    t0 = time.time()
    ids, feats = load_acts("train")
    pids, pfeats = load_acts(probe_split)
    with open(C.PROC / "train.jsonl", encoding="utf-8") as f:
        depts = [json.loads(l)["dept"] for l in f]

    if limit:
        ids, feats, depts = ids[:limit], feats[:limit], depts[:limit]
    n = len(ids)
    print(f"[select] {n} training samples, probe={len(pids)} ({probe_split}), "
          f"layers={feats.shape[1]}")

    score, tr_norm = nait_scores(feats, pfeats)
    order = np.argsort(-score)
    print(f"[select] score: min={score.min():.3f} med={np.median(score):.3f} max={score.max():.3f}")
    q = pair_sim_stats(tr_norm)
    print(f"[select] random-pair cosine (centered): p50={q[0]:.3f} p90={q[1]:.3f} p99={q[2]:.3f} "
          f"(threshold {C.DEDUP_COS})")

    m_sel, m_dedup = f"nait{suffix}", f"nait_dedup{suffix}"
    out = {m_sel: {}, m_dedup: {}}
    for ratio in C.RATIOS:
        target = int(round(ratio * n))
        key = str(int(round(ratio * 100)))
        out[m_sel][key] = [ids[i] for i in stratified_pick(order, score[order], depts, target)]

    if do_dedup:
        kept = greedy_kept_streaming(tr_norm, order, C.DEDUP_COS)
        print(f"[select] dedupe kept {len(kept)}/{n} ({100 * len(kept) / n:.1f}%) "
              f"at cosine>{C.DEDUP_COS}  [{time.time() - t0:.0f}s]")
        for ratio in C.RATIOS:
            target = int(round(ratio * n))
            pick = stratified_pick(kept, score[kept], depts, min(target, len(kept)))
            out[m_dedup][str(int(round(ratio * 100)))] = [ids[i] for i in pick]

    C.ensure_dirs()
    dst = C.SUBSETS / f"subsets{suffix}.json"
    with open(dst, "w", encoding="utf-8") as f:
        json.dump(out, f)

    # Audit trail: every number behind the "which 3,600 rows" decision, so the
    # threshold choice can be re-checked later instead of taken on faith.
    stats = {
        "n_train": n, "n_probe": len(pids), "probe_split": probe_split, "layers": C.LAYERS,
        "dedup_cos": C.DEDUP_COS,
        "score_quantiles": dict(zip(["min", "p10", "p50", "p90", "max"],
                                    [float(x) for x in np.percentile(score, [0, 10, 50, 90, 100])])),
        "pair_cosine_quantiles": dict(zip(["p50", "p90", "p99"],
                                          [float(x) for x in q])),
        "dedupe_kept": int(len(kept)) if do_dedup else None,
        "dedupe_kept_pct": round(100 * len(kept) / n, 2) if do_dedup else None,
        "subset_sizes": {m: {k: len(v) for k, v in d.items()} for m, d in out.items()},
        "dept_counts": {d: int(sum(1 for x in depts if x == d)) for d in sorted(set(depts))},
    }
    stats_path = C.RESULTS / (f"select_stats{suffix}.json" if suffix else "select_stats.json")
    with open(stats_path, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    print(f"[select] wrote {stats_path}")
    for m in out:
        print(f"  {m}: " + "  ".join(f"{k}%={len(v)}" for k, v in out[m].items()))
    print(f"[select] wrote {dst}  {time.time() - t0:.0f}s")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--no-dedup", action="store_true")
    ap.add_argument("--probe-split", default="probe",
                    help="which acts_<split>.npz to build the centroid from "
                         "(probe = source domain, probe_domain = target domain)")
    ap.add_argument("--suffix", default="",
                    help="'' -> subsets.json / nait + nait_dedup; "
                         "'_dp' -> subsets_dp.json / nait_dp + nait_dedup_dp")
    a = ap.parse_args()
    main(a.limit, not a.no_dedup, a.probe_split, a.suffix)
