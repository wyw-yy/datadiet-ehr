# Appendix (English) / 附录（英文）

> 主表见 `paper/table1.md`（中文）。本文件是英文附录，供投稿时附在正文之后。
> 所有数值与 `RESULTS.md` v5 一致，可由 `results/*.csv` 复算
> （`eq_table.csv` / `eq_contrast.csv` / `holm.csv` / `compute_table.csv`）。

## A.1 Primary endpoint — 30% retention on the 48,000-sample pool

Two testing criteria are reported: **item-level** (paired McNemar over items, CI from item bootstrap)
and **seed-level** (Stouffer combination of per-seed McNemar p-values, CI from seed spread).
A cell is *equivalent* only if its 95% CI lies entirely within ±2 pp.

| Task | Method | Seeds | Full data | 30% subset | Δ (pp) | Item 95% CI | Seed 95% CI | Item-equiv. | Seed-equiv. |
|---|---|---|---|---|---|---|---|---|---|
| MedMCQA | **nait** | 6 | 0.4678 | 0.4583 | **−0.98** | [−1.43, +0.22] | [−1.34, −0.58] | ✅ | ✅ |
| MedMCQA | random | 6 | 0.4678 | 0.4533 | −1.40 | [−2.39, −0.53] | [−1.84, −1.07] | ❌ | ✅ |
| MedMCQA | nait_ns | 2 | 0.4678 | 0.4598 | −0.89 | [−1.67, +0.43] | [−3.55, +1.92] | ✅ | ❌ |
| MedQA | **nait** | 6 | 0.4784 | 0.4788 | +0.04 | [−2.52, +1.26] | [−0.57, +0.64] | ❌ | ✅ |
| MedQA | random | 6 | 0.4784 | 0.4760 | −0.24 | [−2.36, +1.18] | [−0.63, +0.16] | ❌ | ✅ |
| MedQA | nait_ns | 2 | 0.4784 | 0.4764 | −0.20 | [−1.96, +1.89] | [−1.39, +2.28] | ✅ | ❌ |

MedQA cells fail the item-level criterion because the evaluation set is small (1,273 items), which widens
the paired CI beyond the margin — this is *underpower*, not evidence of a difference. `rand_len` and
`EL2N` were run on the 24,000-sample pool only (see A.6).

## A.2 Method contrasts at 30%

| Task | Contrast | Seeds | Δ (pp) | 95% CI | Stouffer p | Holm p | TOST ±1 pp |
|---|---|---|---|---|---|---|---|
| MedMCQA | nait − random | 6 | **+-0.18** | [−0.04, +1.03] | **0.016** | **0.064** | ❌ |
| MedMCQA | nait_ns − random | 2 | +0.77 | [−0.02, +1.54] | 0.043 | 0.129 | ❌ |
| MedQA | nait − random | 6 | +0.27 | [−0.71, +1.27] | 0.431 | 0.863 | ❌ |
| MedQA | nait_ns − random | 2 | +0.04 | [−1.34, +1.41] | 0.946 | 0.946 | ❌ |

Per-seed deltas for the headline contrast (MedMCQA, nait − random):
+0.72 / +0.77 / +0.60 / +0.02 / −0.36 / +1.24 pp → **5 of 6 seeds positive**.
Holm family C = the fourteen contrasts at 30% (six arm pairs × two tasks); corrected p = 0.208,
i.e. **not significant**. TOST at ±1 pp does not pass either (CI upper bound 1.03).

## A.3 Compute accounting (48,000-sample pool)

| Method | Retention | Training (GPU-h) | Selection forward (GPU-h) | Total (GPU-h) | Net saving |
|---|---|---|---|---|---|
| random | 30% | 0.639 | 0 | 0.639 | **70.0%** |
| **nait** | 30% | 0.639 | **0.455** | 1.094 | **48.6%** |
| nait_ns | 30% | 0.639 | 0.455 | 1.094 | 48.6% |
| nait | 10% | 0.208 | 0.455 | 0.663 | 68.2% |
| nait | 70% | 1.458 | 0.455 | 1.913 | 8.2% |
| EL2N (24k pool) | 30% | 0.307 | 0.607 | 0.914 | 10.8% |

Full-data training: **2.131 GPU-h** (48,000 samples × 0.153 s/sample, median over runs).
The selection forward pass is measured, not modelled: activation collection 25.7 min + probe 1.2 min +
scoring 0.4 min = 0.455 GPU-h. Reporting "70% compute saving" would silently charge selection cost to zero.

## A.4 Pool-size ladder (observation, not a law)

| Pool | nait Δ (pp) | random Δ (pp) | nait − random | Reading |
|---|---|---|---|---|
| 12k | −0.31 (1 seed) | −0.65 (1) | +0.34 | no difference |
| 24k | −0.53 (6) | −0.47 (6) | −0.06 (p = 0.72) | no difference |
| **48k** | **−0.98 (6)** | **−1.40 (6)** | **+-0.18 (p = 0.016)** | random crosses the margin first |

## A.5 Generative evaluation (48k pool, 500 MedMCQA items, greedy decoding)

| Arm | Accuracy | Format compliance | Median output tokens | Unsafe flags |
|---|---|---|---|---|
| base (no fine-tune) | 0.464 | 100% | 49 | 0 |
| full data | **0.488** | 100% | 24 | 0 |
| nait 30% | 0.470 | 99.8% | **68** | 0 |
| random 30% | **0.494** | 100% | 25 | 0 |

Style probe (24k pool, same phenomenon at 48k): 50.6% of nait answers contain `Ref. / Harrison / page`
patterns versus 2.6–11.2% for the other arms; within the pool, 52.7% of reference answers in nait's subset
carry a citation (27.9% in the rest), median reference length 704 vs 491 characters.

## A.6 Ablations

| Ablation | Pool | Question | Result | Reading |
|---|---|---|---|---|
| stratification (`nait_ns`) | 48k | is the per-department quota needed? | Δ +0.15 pp (MedMCQA) / −0.24 pp (MedQA) vs nait; all McNemar p > 0.4 | quota is optional; protocol can be simplified |
| EL2N | 24k | do classical difficulty scores help? | −1.04 pp; **worse** than random (Holm p = 0.025) | "hardest 30%" mostly selects label noise |
| length-matched random (`rand_len`) | 24k | is activation selection just a length proxy? | −0.15 pp; rand_len − random −0.67 pp (p = 0.035) | length is *not* the mechanism |
| 3 epochs | 24k | does 1 epoch under-train the full baseline? | MedQA nait−random +2.00 pp (seeds +1.26 / +2.75), MedMCQA −0.38 pp | directional only; fails pre-registered criteria |

## A.7 Protocol parameters

| Item | Value |
|---|---|
| Base model | Qwen2.5-1.5B-Instruct (bf16) |
| Adaptation | LoRA r = 16, α = 32, dropout 0.05, 7 projection matrices; 18.46 M trainable (1.18%) |
| Sequence length | 512 tokens (truncation; 98.4% of samples fit) |
| Batch | 4 × grad-accum 2 (effective 8) |
| Optimiser | OneCycleLR, lr 1e-4, 1 epoch |
| Activation layers | {8, 12, 16, 20, 24}; mean over response tokens |
| Deduplication | mean-centred cosine > 0.95 → 46,714/48,000 kept (97.32%) |
| Subset sizes | 10/20/30/50/70% = 4,800/9,600/14,400/24,000/33,600 |
| Equivalence margin | δ = 2 pp (pre-registered) |
| Contrast margin (TOST) | ±1 pp (post hoc, labelled exploratory) |
| Seeds | 6 (nait/random), 2 (nait_ns); EL2N and rand_len on the 24k pool |
| Evaluation | MedMCQA 4,183 items; MedQA 1,273 items; first-token A–D log-probability |

## A.8 Artifact inventory

| Artifact | Path | Contents |
|---|---|---|
| Predictions | `results/preds/*_<task>.csv.gz` | per-item prediction, correctness, per-option probabilities |
| Selection log | `audit/selection_log.jsonl` | per method per ratio: activation/subset/stats hashes, dedupe retention, score quantiles, department mix |
| Per-sample stats | `results/sample_stats.csv` | 48,000 rows × 15 columns (activation score, rank, per-ratio membership) |
| Code manifest | `audit/code_manifest.json` | sha256 of every source file |
| Release bundle | `dist/datadiet-ehr-v1.0.0.zip` (24.6 MB) | code + results + audit chain; no model weights, no raw corpora |
