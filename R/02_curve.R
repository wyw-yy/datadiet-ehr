# 02_curve.R —— 数据效率阶梯图（论文 Fig.2）
# 输入：默认 results/metrics_long.csv（当前轮）；可用 DATADIET_CURVE_DIR 指向别的轮次
# 输出：paper/figures/fig02_data_efficiency.png, fig02_absolute.png
#
# 横轴用**等距的档位**而不是真实比例：1% 与 70% 差 70 倍，
# 真按比例画会把 1/5/10% 全挤在左边、标签互相压住。

source("R/00_setup.R")

curve_dir <- Sys.getenv("DATADIET_CURVE_DIR", unset = "")
if (nzchar(curve_dir)) {
  f <- file.path(curve_dir, "metrics_long.csv")
  cat(sprintf("Fig.2 数据来源：%s\n", f))
  m <- read.csv(f, stringsAsFactors = FALSE)
} else {
  m <- read_results("metrics_long.csv")
}
m$value <- as.numeric(m$value)
m$ratio <- as.numeric(m$ratio)
m$seed  <- as.integer(m$seed)

sub <- m[m$method != "full", ]
full_mean <- tapply(m$value[m$method == "full"], m$task[m$method == "full"], mean)

# 每个 method × ratio × task：mean ± 1.96 SE（种子间）
key <- interaction(sub$method, sub$ratio, sub$task, drop = TRUE)
agg <- do.call(rbind, lapply(split(sub, key), function(d) {
  data.frame(method = d$method[1], ratio = d$ratio[1], task = d$task[1],
             mean = mean(d$value), se = sd(d$value) / sqrt(nrow(d)), n = nrow(d))
}))
agg$delta_pp <- (agg$mean - full_mean[agg$task]) * 100

# 阶梯上出现过的档位（升序），用作等距横轴
RATIOS_X <- sort(unique(agg$ratio))

draw <- function(mode, file) {
  png(file.path(FIG, file), width = 2000, height = 950, res = 150)
  par(mfrow = c(1, 2), mar = c(3.9, 4.4, 2.6, 0.8), oma = c(1.9, 0, 0, 0),
      mgp = c(2.6, 0.7, 0), las = 1)

  a <- agg
  a$y  <- if (mode == "delta") a$delta_pp else a$mean * 100
  a$lo <- a$y - 1.96 * a$se * 100
  a$hi <- a$y + 1.96 * a$se * 100
  a$x  <- match(round(a$ratio, 4), round(RATIOS_X, 4))

  ylim <- range(c(a$lo, a$hi, if (mode == "delta") c(0, -DELTA * 100) else NULL), na.rm = TRUE)
  ylim <- ylim + c(-0.05, 0.30) * diff(ylim)

  for (k in seq_along(TASKS)) {
    tk <- TASKS[k]
    d  <- a[a$task == tk, ]
    plot(NA, xlim = c(0.62, length(RATIOS_X) + 0.38), ylim = ylim, xaxt = "n", bty = "l",
         xlab = "Retained training data (fraction of full set, log-spaced ladder)",
         ylab = if (k == 1) (if (mode == "delta") "Delta vs full data (pp)" else "Accuracy (%)") else "",
         main = tk)
    axis(1, at = seq_along(RATIOS_X), labels = paste0(round(RATIOS_X * 100), "%"))
    axis(2, at = pretty(ylim))

    if (mode == "delta") {
      abline(h = 0, col = "grey40", lty = 3)
      abline(h = -DELTA * 100, col = "#D55E00", lty = 2, lwd = 1.4)
    } else {
      abline(h = full_mean[[tk]] * 100, col = "grey30", lty = 3)
      text(length(RATIOS_X) + 0.30, full_mean[[tk]] * 100, "full", pos = 2,
           cex = 0.7, col = "grey30", xpd = NA)
    }

    for (mt in setdiff(METHODS, "full")) {
      dd <- d[d$method == mt, ]
      dd <- dd[order(dd$x), ]
      if (!nrow(dd)) next
      col <- PAL[[mt]]
      segments(dd$x, dd$lo, dd$x, dd$hi, col = col, lwd = 1.3)
      lines(dd$x, dd$y, col = col, lwd = 2)
      # 实心 = 多种子（有 CI）；空心 = 单种子（CI 不可估，别让点看起来"很确定"）
      points(dd$x, dd$y, pch = ifelse(dd$n > 1, 19, 1), col = col, cex = 1.15)
    }
  }

  # 图例单独铺在图底，不压任何曲线
  par(fig = c(0, 1, 0, 1), oma = c(0, 0, 0, 0), mar = c(0, 0, 0, 0), new = TRUE)
  plot.new()

  # 图顶标注：只有 30% 有 6 个种子，50/70 仍只有 1 个，不标注就是误导
  note <- if (nzchar(curve_dir)) {
    "12k pool  ·  seeds: 10-70% = 1 (exploratory)"
  } else {
    "48k pool  ·  seeds: 1-20% = 2, 30% = 6, 50-70% = 1  ·  filled = multi-seed, open = single seed"
  }
  text(0.5, 0.975, note, cex = 0.70, col = "grey35")

  ord  <- c("random", "el2n", "rand_len", "nait", "nait_dedup")
  lab_all <- c("random", "el2n", "rand_len (length-matched)", "nait", "nait + dedup")
  keep <- intersect(ord, unique(agg$method))
  cols <- unlist(PAL[keep]); ltys <- rep(1, length(keep)); pchs <- rep(19, length(keep))
  labs <- lab_all[match(keep, ord)]
  if (mode == "delta") {
    labs <- c(labs, "equivalence margin ± 2 pp")
    cols <- c(cols, "#D55E00"); ltys <- c(ltys, 2); pchs <- c(pchs, NA)
  }
  legend("bottom", legend = labs, col = cols, lty = ltys, pch = pchs,
         lwd = 2, horiz = TRUE, bty = "n", cex = 0.85, seg.len = 2.4)
  invisible(dev.off())
}

draw("delta", "fig02_data_efficiency.png")
draw("absolute", "fig02_absolute.png")

cat("图已写出：\n  paper/figures/fig02_data_efficiency.png\n  paper/figures/fig02_absolute.png\n")
cat("\n30% 保留时的掉点（pp）：\n")
z <- agg[abs(agg$ratio - 0.30) < 1e-9, ]
z$delta_pp <- (z$mean - full_mean[z$task]) * 100
print(z[, c("task", "method", "mean", "delta_pp")], row.names = FALSE)
