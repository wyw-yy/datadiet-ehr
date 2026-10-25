# 06_forest.R —— 逐种子森林图（论文 Fig.6）
#
# 为什么需要这张图：表格里的"Δ = −0.26pp"会掩盖一个事实——
# 六个种子里有的 +0.55、有的 −0.86。点图能把"符号翻转"直接摊开，
# 比任何一句"not significant"都诚实。
#
# 输入：results/eq_per_seed.csv（每种子一行）、results/eq_table.csv（汇总）
# 输出：paper/figures/fig06_forest.png

source("R/00_setup.R")

per <- read_results("eq_per_seed.csv")
agg <- read_results("eq_table.csv")
if (!nrow(per)) { cat("eq_per_seed.csv 为空，跳过\n"); quit(save = "no") }

per$ratio <- as.numeric(per$ratio)
agg$ratio <- as.numeric(agg$ratio)
ratio_show <- 0.30

per <- per[abs(per$ratio - ratio_show) < 1e-9, ]
agg <- agg[abs(agg$ratio - ratio_show) < 1e-9, ]

ms  <- intersect(c("nait", "random", "rand_len", "el2n", "nait_dedup"), unique(per$method))
ord <- match(ms, c("nait", "random", "rand_len", "el2n", "nait_dedup"))
ms  <- ms[order(ord)]
lab <- c(nait = "nait", random = "random", rand_len = "rand_len\n(len-matched)",
         el2n = "el2n", nait_dedup = "nait + dedup")

png(file.path(FIG, "fig06_forest.png"), width = 1750, height = 900, res = 150)
par(mfrow = c(1, length(TASKS)), mar = c(3.8, 6.0, 2.8, 2.4), oma = c(0, 0, 1.6, 0),
    mgp = c(2.4, 0.6, 0), las = 1)

for (tk in TASKS) {
  p <- per[per$task == tk, ]
  a <- agg[agg$task == tk, ]
  if (!nrow(p)) { plot.new(); next }

  ylab <- c(sapply(ms, function(m) lab[[m]]), rep("", 0))
  ypos <- rev(seq_along(ms))          # 第一个方法画在最上面
  ylim <- c(0.4, length(ms) + 0.6)
  xlim <- range(c(p$ci_lo_pp, p$ci_hi_pp, -DELTA * 100, DELTA * 100,
                  a$ci_lo_pp, a$ci_hi_pp), na.rm = TRUE)
  xlim <- xlim + c(-0.15, 0.15) * diff(xlim)

  plot(NA, xlim = xlim, ylim = ylim, axes = FALSE, xlab = "",
       ylab = "", main = tk)
  abline(v = 0, col = "grey40", lty = 3)
  abline(v = c(-DELTA * 100, DELTA * 100), col = "#D55E00", lty = 2)
  axis(1, cex.axis = 0.85, padj = -0.2)
  axis(2, at = ypos, labels = sapply(ms, function(m) lab[[m]]), tick = FALSE, cex.axis = 0.9)
  mtext(if (identical(tk, TASKS[1])) "Delta vs full data (pp)" else "", side = 1, line = 2.3, cex = 0.9)

  for (k in seq_along(ms)) {
    m <- ms[k]; y <- ypos[k]
    d <- p[p$method == m, ]
    a1 <- a[a$method == m, ]
    col <- PAL[[m]]
    if (nrow(d)) {
      # 每个种子一个点，纵向轻微散开，避免重叠时看不见
      off <- if (nrow(d) > 1) seq(-0.16, 0.16, length.out = nrow(d)) else 0
      d <- d[order(d$seed), ]
      points(d$delta_pp, y + off, pch = 19, col = col, cex = 0.85)
    }
    if (nrow(a1)) {
      # 汇总：粗线 = 种子间 95% CI，方块 = 均值
      segments(a1$ci_seed_lo_pp, y, a1$ci_seed_hi_pp, y, col = col, lwd = 2.6)
      points(a1$delta_pp, y, pch = 18, col = col, cex = 1.7)
    }
  }
}

mtext("Per-seed deltas (dots) and pooled mean with seed-level 95% CI (thick bar)",
      side = 3, outer = TRUE, line = 0.4, cex = 0.8, col = "grey25")
invisible(dev.off())

cat("图已写出：paper/figures/fig06_forest.png\n")
