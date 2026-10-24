# 03_robustness.R —— 跨科室稳健性（论文 Fig.4 / Table 3）
# 问题：nait 的优势是不是集中在某个科室？最差科室掉几个点？
# 输入：results/preds/*.csv.gz（只取 r = 0.30 这一档）
# 输出：results/robust.csv, paper/figures/fig04_dept.png

source("R/00_setup.R")
R0 <- 0.30
m <- read_results("metrics_long.csv")
SEEDS <- sort(unique(m$seed))
SUBS  <- setdiff(unique(m$method), "full")

preds_path <- function(eid, task) file.path(RESULTS, "preds", paste0(eid, "_", task, ".csv.gz"))
have <- function(eid, task) file.exists(preds_path(eid, task))

rows <- list(); i <- 1
for (tk in TASKS) {
  for (mt in SUBS) {
    dz <- NULL
    for (sd in SEEDS) {
      fe <- exp_id("full", 1, sd)
      se <- exp_id(mt, R0, sd)
      if (!have(fe, tk) || !have(se, tk)) next
      f <- read_preds(fe, tk)[, c("item_id", "dept", "correct")]
      s <- read_preds(se, tk)[, c("item_id", "correct")]
      p <- merge(f, s, by = "item_id", suffixes = c(".f", ".s"))
      dz <- rbind(dz, p)
    }
    if (is.null(dz) || !nrow(dz)) next

    dz$d <- dz$correct.s - dz$correct.f
    agg_item <- aggregate(d ~ item_id + dept, data = dz, FUN = mean)

    for (dp in sort(unique(agg_item$dept))) {
      v  <- agg_item$d[agg_item$dept == dp]
      if (length(v) < 30) next          # 太小的科室不画，避免噪声冒充结论
      ci <- boot_ci(v, seed = 11)
      rows[[i]] <- data.frame(task = tk, method = mt, dept = dp, n_item = length(v),
                              delta_pp = round(mean(v) * 100, 2),
                              ci_lo_pp = round(ci[1] * 100, 2),
                              ci_hi_pp = round(ci[2] * 100, 2),
                              equiv = (ci[1] > -DELTA) && (ci[2] < DELTA))
      i <- i + 1
    }
  }
}
res <- do.call(rbind, rows)
write.csv(res, file.path(RESULTS, "robust.csv"), row.names = FALSE)

# ---- 图：点 + 区间，按科室分组 ----
pal <- c(random = "grey55", nait = "#0072B2", nait_dedup = "#009E73")
ms  <- intersect(c("random", "nait", "nait_dedup"), SUBS)
labs <- c("random 30%", "nait 30%", "nait+dedup 30%")[match(ms, c("random", "nait", "nait_dedup"))]

png(file.path(FIG, "fig04_dept.png"), width = 2100, height = 950, res = 150)
par(mfrow = c(1, 2), mar = c(3.2, 4.4, 2.8, 0.8), oma = c(2.8, 0, 0, 0),
    mgp = c(2.5, 0.7, 0), las = 1)
off <- seq(-0.24, 0.24, length.out = length(ms))

for (tk in TASKS) {
  d <- res[res$task == tk, ]
  if (!nrow(d)) next
  depts <- sort(unique(d$dept))
  plot(NA, xlim = c(0.55, length(depts) + 0.45),
       ylim = range(c(d$ci_lo_pp, d$ci_hi_pp, 0, -DELTA * 100)) + c(-0.6, 0.6),
       xlab = "", ylab = "Delta vs full data (pp)", main = tk, bty = "l", xaxt = "n")
  axis(1, at = seq_along(depts), labels = depts, cex.axis = 0.9)
  abline(h = 0, col = "grey40", lty = 3)
  abline(h = -DELTA * 100, col = "#D55E00", lty = 2, lwd = 1.3)

  for (k in seq_along(ms)) {
    mt <- ms[k]
    z <- d[d$method == mt, ]
    if (!nrow(z)) next
    z <- z[match(depts, z$dept), ]
    x <- seq_along(depts) + off[k]
    segments(x, z$ci_lo_pp, x, z$ci_hi_pp, col = pal[[mt]], lwd = 1.5)
    points(x, z$delta_pp, pch = 19, col = pal[[mt]], cex = 1.15)
  }
}

par(fig = c(0, 1, 0, 1), oma = c(0, 0, 0, 0), mar = c(0, 0, 0, 0), new = TRUE)
plot.new()
legend("bottom", legend = labs, col = pal[ms],
       pch = 19, lty = 1, lwd = 2, horiz = TRUE, bty = "n", cex = 0.85, seg.len = 2.4)
invisible(dev.off())

cat("表已写出：", file.path(RESULTS, "robust.csv"), "\n")
cat("图已写出：paper/figures/fig04_dept.png\n\n每个方法最差的科室：\n")
worst <- do.call(rbind, lapply(split(res, list(res$task, res$method), drop = TRUE),
                               function(d) d[which.min(d$delta_pp), ]))
print(worst[, c("task", "method", "dept", "delta_pp", "ci_lo_pp", "ci_hi_pp")],
      row.names = FALSE)
