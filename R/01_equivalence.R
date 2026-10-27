# 01_equivalence.R —— 论文的统计核心：30% 数据到底"等效"吗？nait 到底优于 random 吗？
# 输入：results/metrics_long.csv, results/preds/*.csv.gz
# 输出：results/eq_table.csv（方法 vs 全量）、results/eq_contrast.csv（方法 vs 方法）
#
# 统计口径（2026-10-24 修正，之前的口径是错的）：
#   错的做法：把 3 个种子的 b/c 计数相加再跑一次 McNemar
#             → 同一批 4183 道题被数了 3 遍，违反独立性，p 值不可解释。
#   现在的做法：
#     1. 每个种子内部单独做逐题配对检验（McNemar 精确检验 + 逐题 bootstrap CI）；
#     2. 跨种子用 Stouffer 合并各seed的 p（带符号），再报种子间极差与标准差；
#     3. 等效性两个口径都给：
#        - equiv_item：把逐题差值按题平均后做 bootstrap（条件于这 3 次训练）——论文主用的口径；
#        - equiv_seed：把 3 个种子均值当 3 个观测做 t 区间（对"新种子"外推）——更保守。
#   两种口径不一致时，结论必须写"条件于固定种子"。

source("R/00_setup.R")
B <- 2000

m <- read_results("metrics_long.csv")
SEEDS <- sort(unique(m$seed))
SUBS  <- setdiff(unique(m$method), "full")

preds_path <- function(eid, task) file.path(RESULTS, "preds", paste0(eid, "_", task, ".csv.gz"))
have <- function(eid, task) file.exists(preds_path(eid, task))

# ---- 工具函数 ----
paired <- function(ea, eb, task) {
  if (!have(ea, task) || !have(eb, task)) return(NULL)
  a <- read_preds(ea, task)[, c("item_id", "correct")]
  b <- read_preds(eb, task)[, c("item_id", "correct")]
  p <- merge(a, b, by = "item_id", suffixes = c(".a", ".b"))
  if (!nrow(p)) return(NULL)
  p <- p[order(p$item_id), ]
  list(n = nrow(p),
       acc_a = mean(p$correct.a), acc_b = mean(p$correct.b),
       d = p$correct.a - p$correct.b,
       a_only = sum(p$correct.a == 1 & p$correct.b == 0),
       b_only = sum(p$correct.a == 0 & p$correct.b == 1))
}

mcnemar_p <- function(b, c) {
  n <- b + c
  if (n == 0) return(NA_real_)
  binom.test(b, n, 0.5)$p.value
}

# Stouffer 合并：符号取方向，权重相等
stouffer <- function(p, d) {
  ok <- !is.na(p) & !is.na(d) & d != 0
  if (!any(ok)) return(NA_real_)
  z <- qnorm(1 - p[ok] / 2) * sign(d[ok])
  zc <- sum(z) / sqrt(length(z))
  2 * (1 - pnorm(abs(zc)))
}

equiv_flag <- function(lo, hi, delta = DELTA) (lo > -delta) && (hi < delta)

# ============================================================
# A. 每个种子内部：方法 vs 全量
# ============================================================
per <- list(); k <- 1
for (tk in TASKS) {
  for (sd in SEEDS) {
    # 全量基线可能只跑了一个种子（48k / e3 轮就是这样）。那时用 full_s1 当共同参照，
    # 并把 full_ref_seed 记进表里，免得读者以为每个种子都有独立的全量基线。
    fe <- exp_id("full", 1, sd)
    ref_seed <- sd
    .pf <- function(e, t) file.path(RESULTS, "preds", paste0(e, "_", t, ".csv.gz"))
    if (!file.exists(.pf(fe, tk))) {
      fe <- exp_id("full", 1, 1)
      ref_seed <- 1
    }
    for (mt in SUBS) {
      rs <- sort(unique(m$ratio[m$method == mt & m$seed == sd]))
      for (r in rs) {
        eid <- exp_id(mt, r, sd)
        pr <- paired(eid, fe, tk)
        if (is.null(pr)) next
        ci <- boot_ci(pr$d, B = B, seed = 7)   # 与跨种子汇总用同一个 RNG 种子：
                                               # 单种子时两处 CI 必须完全一致，否则表对不上
        per[[k]] <- data.frame(
          task = tk, method = mt, ratio = r, seed = sd, full_ref_seed = ref_seed,
          n_item = pr$n,
          acc_full = round(pr$acc_b, 4), acc_sub = round(pr$acc_a, 4),
          delta_pp = round(mean(pr$d) * 100, 2),
          ci_lo_pp = round(ci[1] * 100, 2), ci_hi_pp = round(ci[2] * 100, 2),
          b = pr$a_only, c = pr$b_only,
          mcnemar_p = round(mcnemar_p(pr$a_only, pr$b_only), 4),
          equiv = equiv_flag(ci[1], ci[2])
        )
        k <- k + 1
      }
    }
  }
}
per <- do.call(rbind, per)
write.csv(per, file.path(RESULTS, "eq_per_seed.csv"), row.names = FALSE)

# ============================================================
# B. 跨种子汇总
# ============================================================
key <- interaction(per$task, per$method, per$ratio, drop = TRUE)
rows <- list(); i <- 1
for (g in split(per, key)) {
  g <- g[order(g$seed), ]
  # 逐题差值：按题平均掉种子噪声，再对题做 bootstrap（条件口径）
  vecs <- list()
  for (sd in g$seed) {
    pr <- paired(exp_id(g$method[1], g$ratio[1], sd), exp_id("full", 1, sd), g$task[1])
    if (!is.null(pr)) vecs[[as.character(sd)]] <- pr$d
  }
  if (!length(vecs)) next
  lens <- sapply(vecs, length)
  vecs <- vecs[lens == max(lens)]                    # 题集必须一致才能逐题平均
  d_item <- if (length(vecs) == 1) vecs[[1]] else rowMeans(do.call(cbind, vecs))

  ci_item <- boot_ci(d_item, B = B, seed = 7)
  ds <- g$delta_pp
  ci_seed <- if (length(ds) >= 2) {
    tcrit <- qt(0.975, df = length(ds) - 1)
    half <- tcrit * sd(ds) / sqrt(length(ds))
    c(mean(ds) - half, mean(ds) + half)
  } else c(NA_real_, NA_real_)

  rows[[i]] <- data.frame(
    task = g$task[1], method = g$method[1], ratio = g$ratio[1],
    n_seed = nrow(g), n_item = as.integer(round(mean(g$n_item))),
    acc_full = round(mean(g$acc_full), 4), acc_sub = round(mean(g$acc_sub), 4),
    delta_pp = round(mean(ds), 2),
    ci_lo_pp = round(ci_item[1] * 100, 2), ci_hi_pp = round(ci_item[2] * 100, 2),
    seed_min_pp = round(min(ds), 2), seed_max_pp = round(max(ds), 2),
    seed_sd_pp = round(ifelse(length(ds) > 1, sd(ds), NA_real_), 2),
    ci_seed_lo_pp = round(ci_seed[1], 2), ci_seed_hi_pp = round(ci_seed[2], 2),
    stouffer_p = round(stouffer(g$mcnemar_p, ds), 4),
    equiv_item = equiv_flag(ci_item[1], ci_item[2]),
    equiv_seed = if (is.na(ci_seed[1])) NA else equiv_flag(ci_seed[1] / 100, ci_seed[2] / 100),
    all_seeds_same_sign = (all(ds > 0) || all(ds < 0)),
    stringsAsFactors = FALSE
  )
  i <- i + 1
}
res <- do.call(rbind, rows)
res <- res[order(res$task, res$method, res$ratio), ]
write.csv(res, file.path(RESULTS, "eq_table.csv"), row.names = FALSE)

# ============================================================
# C. 方法 vs 方法（nait 是否优于 random —— 论文真正要主张的那条）
# ============================================================
con <- list(); j <- 1
others <- setdiff(SUBS, "random")
# 先做"每个方法 vs 随机"，再补两条关键对照：
#   nait vs rand_len —— 排除"长度代理"解释（长度分布完全对齐后还赢不赢）
#   nait_dedup vs nait —— 去重本身有没有伤到效果
pairs <- lapply(others, function(m) c(m, "random"))
extra <- list(c("nait", "rand_len"), c("nait_dedup", "nait"))
for (e in extra) {
  if (all(e %in% SUBS)) pairs[[length(pairs) + 1]] <- e
}
for (tk in TASKS) {
  for (pp in pairs) {
    mt <- pp[1]; base <- pp[2]
    for (r in sort(unique(per$ratio[per$method == mt]))) {
      ds <- c(); ps <- c(); se <- c(); vecs <- list()
      for (sd in SEEDS) {
        pr <- paired(exp_id(mt, r, sd), exp_id(base, r, sd), tk)
        if (is.null(pr)) next
        ds <- c(ds, mean(pr$d) * 100)
        ps <- c(ps, mcnemar_p(pr$a_only, pr$b_only))
        se <- c(se, sd)
        vecs[[length(vecs) + 1]] <- pr$d
      }
      if (!length(ds)) next
      # 逐题口径：先按题把各 seed 的 d 平均（题目相同，可以逐题合并），再对题做 bootstrap。
      # 这样得到的 CI 回答的是"换一批题，差距会落在哪"，不受种子噪声放大。
      dbar <- rowMeans(do.call(cbind, vecs))
      bc <- boot_ci(dbar * 100, seed = 7)
      lo <- round(bc[1], 2); hi <- round(bc[2], 2)
      con[[j]] <- data.frame(
        task = tk, method = mt, vs = base, ratio = r, n_seed = length(ds),
        delta_pp = round(mean(ds), 2), seed_min_pp = round(min(ds), 2),
        seed_max_pp = round(max(ds), 2), seed_sd_pp = round(ifelse(length(ds) > 1, sd(ds), NA_real_), 2),
        ci_lo_pp = lo, ci_hi_pp = hi,
        tost_equiv = (lo > -DELTA_CONTRAST * 100) && (hi < DELTA_CONTRAST * 100),
        tost_margin_pp = DELTA_CONTRAST * 100,
        per_seed_pp = paste(sprintf("%+.2f", ds), collapse = " / "),
        per_seed_p = paste(sprintf("%.3f", ps), collapse = " / "),
        stouffer_p = round(stouffer(ps, ds), 4),
        same_sign = (all(ds > 0) || all(ds < 0)),
        stringsAsFactors = FALSE
      )
      j <- j + 1
    }
  }
}
contrast <- do.call(rbind, con)
write.csv(contrast, file.path(RESULTS, "eq_contrast.csv"), row.names = FALSE)

# ============================================================
# D. 终端摘要
# ============================================================
cat("\n== r = 0.30：方法 vs 全量（δ = ±", DELTA * 100, "pp）==\n", sep = "")
show <- res[abs(res$ratio - 0.30) < 1e-9, ]
print(show[, c("task", "method", "n_seed", "delta_pp", "ci_lo_pp", "ci_hi_pp",
               "seed_min_pp", "seed_max_pp", "stouffer_p", "equiv_item", "equiv_seed")],
      row.names = FALSE)

cat("\n== 逐种子（r = 0.30，看方向是否一致）==\n")
pw <- per[abs(per$ratio - 0.30) < 1e-9, ]
print(pw[, c("task", "method", "seed", "delta_pp", "ci_lo_pp", "ci_hi_pp", "mcnemar_p", "equiv")],
      row.names = FALSE)

cat("\n== 方法 vs 随机：同一比例下谁更好（TOST 界 ±",
    DELTA_CONTRAST * 100, "pp）==\n", sep = "")
print(contrast[, c("task", "method", "ratio", "delta_pp", "ci_lo_pp", "ci_hi_pp",
                   "tost_equiv", "per_seed_pp", "stouffer_p", "same_sign")],
      row.names = FALSE)

cat("\n== 各比例下 nait 的掉点 ==\n")
n <- res[res$method == "nait", c("task", "ratio", "n_seed", "delta_pp",
                                 "ci_lo_pp", "ci_hi_pp", "equiv_item")]
print(n[order(n$task, n$ratio), ], row.names = FALSE)

cat("\n表已写出：\n  ", file.path(RESULTS, "eq_table.csv"),
    "\n  ", file.path(RESULTS, "eq_per_seed.csv"),
    "\n  ", file.path(RESULTS, "eq_contrast.csv"), "\n")
