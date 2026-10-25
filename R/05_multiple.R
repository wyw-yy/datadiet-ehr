# 05_multiple.R —— 多重比较：谁在主检验里，谁只是探索
#
# 为什么要单独一个文件：审稿人第一个会问"你比了这么多次，p 值还能信吗"。
# 答案不能是"我们没校正"，也不能是"全都校正"——得先把假设分成家族，
# 每个家族内部校正，并且说清哪个家族支撑主结论。
#
# 家族划分（与 docs/PREREG.md §2/§4 一致）：
#   P 主终点：子集 vs 全量（30%），每个 (任务, 方法) 一条，预注册、单独报告、不参与校正
#   C 对比家族：方法 vs 方法（30%），6 条，探索性 → Holm
#   D 剂量家族：nait 在 10/20/50/70% 的探索性对比 → Holm
#
# 输入：results/eq_contrast.csv（delta/CI/stouffer_p）
# 输出：results/holm.csv

source("R/00_setup.R")

ct <- read_results("eq_contrast.csv")
if (!nrow(ct)) { cat("eq_contrast.csv 为空，跳过\n"); quit(save = "no") }

ct$ratio <- as.numeric(ct$ratio)
ct$stouffer_p <- as.numeric(ct$stouffer_p)
ct$delta_pp <- as.numeric(ct$delta_pp)

ct$family <- ifelse(abs(ct$ratio - 0.30) < 1e-9, "C_contrast_at_30", "D_other_ratios")

res <- do.call(rbind, lapply(split(ct, ct$family), function(d) {
  # Holm 在每个家族内部做；p 缺失的行保留 NA 且不参与校正
  p <- d$stouffer_p
  ok <- is.finite(p)
  d$p_holm <- NA_real_
  d$p_holm[ok] <- p.adjust(p[ok], method = "holm")
  d$sig_raw  <- ok & p < 0.05
  d$sig_holm <- ok & d$p_holm < 0.05
  d
}))

# 说明：等效性（P 家族）报告的是 TOST/CI，不产生需要校正的 p，
# 因此这里只对"方法间差异"做校正。这一点必须写进正文，别让读者以为是漏了。

out <- res[order(res$family, res$task, res$method, res$vs), c(
  "family", "task", "method", "vs", "ratio", "delta_pp",
  "ci_lo_pp", "ci_hi_pp", "stouffer_p", "p_holm", "sig_raw", "sig_holm")]
write.csv(out, file.path(RESULTS, "holm.csv"), row.names = FALSE, na = "")

cat("写出：", file.path(RESULTS, "holm.csv"), "\n\n")
for (f in unique(out$family)) {
  cat("家族", f, "（", sum(out$family == f), " 条）\n", sep = "")
  z <- out[out$family == f, ]
  print(z[, c("task", "method", "vs", "delta_pp", "stouffer_p", "p_holm", "sig_holm")],
        row.names = FALSE)
  cat("\n")
}

n_raw  <- sum(out$sig_raw, na.rm = TRUE)
n_holm <- sum(out$sig_holm, na.rm = TRUE)
cat(sprintf("校正前显著 %d 条，Holm 校正后 %d 条。\n", n_raw, n_holm))
if (n_holm < n_raw) {
  cat("→ 有对比靠校正前的 p 值撑着，正文不能写成确定结论。\n")
} else {
  cat("→ 校正前后结论不变。\n")
}
