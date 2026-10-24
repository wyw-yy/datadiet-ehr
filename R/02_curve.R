# 02_curve.R —— 数据效率曲线（论文 Fig.2）
# 输入：results/metrics_long.csv
# 输出：paper/figures/fig02_data_efficiency.png, fig02_absolute.png

source("R/00_setup.R")

m <- read_results("metrics_long.csv")
sub <- m[m$method != "full", ]
full_mean <- tapply(m$value[m$method == "full"], m$task[m$method == "full"], mean)

# 每个 method × ratio × task：mean ± 1.96 SE（种子间）
key <- interaction(sub$method, sub$ratio, sub$task, drop = TRUE)
agg <- do.call(rbind, lapply(split(sub, key), function(d) {
  data.frame(method = d$method[1], ratio = d$ratio[1], task = d$task[1],
             mean = mean(d$value), se = sd(d$value) / sqrt(nrow(d)), n = nrow(d))
}))

# 两种纵轴：绝对准确率 / 相对全量的掉点（pp）
agg$delta_pp <- (agg$mean - full_mean[agg$task]) * 100

draw <- function(mode, file) {
  png(file.path(FIG, file), width = 2000, height = 950, res = 150)
  par(mfrow = c(1, 2), mar = c(3.9, 4.4, 2.6, 0.8), oma = c(1.9, 0, 0, 0),
      mgp = c(2.6, 0.7, 0), las = 1)

  if (mode == "delta") {
    agg$y  <- agg$delta_pp
  } else {
    agg$y  <- agg$mean * 100
  }
  agg$lo <- agg$y - 1.96 * agg$se * 100
  agg$hi <- agg$y + 1.96 * agg$se * 100

  ylim <- range(c(agg$lo, agg$hi, if (mode == "delta") c(0, -DELTA * 100) else NULL), na.rm = TRUE)
  ylim <- ylim + c(-0.05, 0.30) * diff(ylim)
  ticks <- seq(-10, 10, 5)

  for (k in seq_along(TASKS)) {
    tk <- TASKS[k]
    d  <- agg[agg$task == tk, ]
    plot(NA, xlim = c(0.04, 0.78), ylim = ylim, xaxt = "n", bty = "l",
         xlab = "Retained training data (fraction of full set)",
         ylab = if (k == 1) (if (mode == "delta") "Delta vs full data (pp)" else "Accuracy (%)") else "",
         main = tk)
    axis(1, at = c(.1, .2, .3, .5, .7), labels = c("10%", "20%", "30%", "50%", "70%"))
    axis(2, at = ticks[ticks >= ylim[1] & ticks <= ylim[2]])
    if (mode == "delta") {
      abline(h = 0, col = "grey40", lty = 3)
      abline(h = -DELTA * 100, col = "#D55E00", lty = 2, lwd = 1.4)
    } else {
      abline(h = full_mean[[tk]] * 100, col = "grey30", lty = 3)
      text(0.77, full_mean[[tk]] * 100, "full", pos = 2, cex = 0.7, col = "grey30", xpd = NA)
    }
    for (mt in setdiff(METHODS, "full")) {
      dd <- d[d$method == mt, ]; dd <- dd[order(dd$ratio), ]
      if (!nrow(dd)) next
      col <- PAL[[mt]]
      segments(dd$ratio, dd$lo, dd$ratio, dd$hi, col = col, lwd = 1.3)
      lines(dd$ratio, dd$y, col = col, lwd = 2)
      # 实心 = 多种子（有 CI）；空心 = 单种子（CI 不可估，别让点看起来"很确定"）
      points(dd$ratio, dd$y, pch = ifelse(dd$n > 1, 19, 1), col = col, cex = 1.15)
    }
  }

  # 图例单独铺在图底，不压任何曲线
  par(fig = c(0, 1, 0, 1), oma = c(0, 0, 0, 0), mar = c(0, 0, 0, 0), new = TRUE)
  plot.new()
  keep <- intersect(c("random", "nait", "nait_dedup"), unique(agg$method))
  labs <- c("random", "nait", "nait + dedup")[seq_along(keep)]
  cols <- PAL[keep]
  ltys <- rep(1, length(keep)); pchs <- rep(19, length(keep))
  labs <- c(labs, "open marker = single seed"); cols <- c(cols, "grey40")
  ltys <- c(ltys, 0); pchs <- c(pchs, 1)
  if (mode == "delta") {
    labs <- c(labs, "equivalence margin \u00b1 2 pp"); cols <- c(cols, "#D55E00")
    ltys <- c(ltys, 2); pchs <- c(pchs, NA)
  }
  legend("bottom", legend = labs, col = cols, lty = ltys, pch = pchs, lwd = 2,
         horiz = TRUE, bty = "n", cex = 0.82, seg.len = 2.4)
  invisible(dev.off())
}

draw("delta", "fig02_data_efficiency.png")
draw("absolute", "fig02_absolute.png")

cat("图已写出：\n  paper/figures/fig02_data_efficiency.png\n  paper/figures/fig02_absolute.png\n")
cat("\n30% 保留时的掉点（pp）：\n")
z <- agg[abs(agg$ratio - 0.30) < 1e-9, ]
print(z[, c("task", "method", "mean", "delta_pp")], row.names = FALSE)
