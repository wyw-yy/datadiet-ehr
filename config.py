"""Central configuration for the DataDiet-EHR pipeline.

Everything that the other scripts need to agree on lives here: paths,
experiment grid, activation layers, dept taxonomy.
"""
from pathlib import Path

import os

PROJ = Path(__file__).resolve().parent

DATA     = PROJ / "data"
RAW      = DATA / "raw"
PROC     = DATA / "processed"
SUBSETS  = DATA / "subsets"

CACHE    = PROJ / "cache"
ACTS     = CACHE / "acts"

MODELS   = PROJ / "models"
# 1.5B: 3.1 GB of weights, leaves room for activations on an 8 GiB laptop card.
# 3B (models/Qwen2.5-3B-Instruct) needs >=12 GiB - see PLAN.md §4 risk table.
BASE_DIR = MODELS / "Qwen2.5-1.5B-Instruct"
ADAPTERS = MODELS / "adapters"

RESULTS  = PROJ / "results"
RUNS     = RESULTS / "runs"
PREDS    = RESULTS / "preds"
PREDS.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------- data scale
# 12,000 是第 1 轮（12k 池）的规模。跑"放大池子"那一轮时用环境变量覆盖，
# 例如：$env:DATADIET_N_TRAIN=24000（见 tools/run_scale.py）。默认值不动，老结果可复现。
N_TRAIN = int(os.environ.get("DATADIET_N_TRAIN", 12000))   # the "full" training pool
N_POOL  = int(os.environ.get("DATADIET_N_POOL", N_TRAIN))  # how many of train.jsonl to use as the pool
N_PROBE = 2000           # in-domain reference set used to build activation centroids
MAX_LEN = 512            # tokens per training example (pool: p50=256, p90=366, p99=582)

# Measured on this laptop's RTX 5070 (11 TFLOP/s bf16, ~2 samples/s at 1.5B):
# 12k pool x 1 epoch ~ 1.5 h, so the whole matrix below is ~16 h of training.
# ------------------------------------------------------------- experiment grid
RATIOS  = [0.10, 0.20, 0.30, 0.50, 0.70]
SEEDS   = [1, 2, 3]
METHODS = ["full", "random", "rand_len", "nait", "nait_dedup", "nait_dp", "nait_dedup_dp", "el2n"]
# nait*, nait_dedup*      : centroid from the SOURCE-domain probe (held-out patient chat)
# nait_dp, nait_dedup_dp  : centroid from the TARGET-domain probe (held-out medical MCQ)
#   -> the second pair is the setup Nait (Chen et al., ICLR 2026) actually uses;
#      the first pair is kept because its results are in results/metrics_long.csv.
# rand_len                : random subset MATCHED to nait's length distribution.
#   The audit found nait picks samples 12.3% longer than average, so this arm
#   separates "activation signal" from "prefers long texts" (see docs/PREREG.md §6).
SUBSET_FILES = {
    "nait":          "subsets.json",
    "nait_dedup":    "subsets.json",
    "nait_dp":       "subsets_dp.json",
    "nait_dedup_dp": "subsets_dp.json",
    "rand_len":      "subsets_randlen.json",
    "el2n":          "subsets_el2n.json",
}


def subset_file_for(method: str):
    """Which subsets_*.json holds this method's picks."""
    return SUBSETS / SUBSET_FILES.get(method, "subsets.json")
TASKS   = ["medqa", "medmcqa"]
LAYERS  = [8, 12, 16, 20, 24]                          # hidden layers for activation features
DEDUP_COS = 0.95                                       # near-duplicate threshold

# ------------------------------------------------------------------ taxonomy
DEPTS = ["cardio", "onco", "neuro", "resp", "endo", "other"]


def exp_id(method: str, ratio: float, seed: int) -> str:
    """Unique, sortable name for one training run. Matches R/00_setup.R."""
    if method == "full":
        return f"full_s{seed}"
    return f"{method}_r{int(round(ratio * 100)):02d}_s{seed}"


def ensure_dirs() -> None:
    for d in (RAW, PROC, SUBSETS, CACHE, ACTS, MODELS, ADAPTERS, RUNS, PREDS):
        d.mkdir(parents=True, exist_ok=True)
