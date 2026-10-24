# 04_compute.R —— 算力净账（论文 Fig.5 / Table 4）
# 关键点：净节省 = 全量训练 − (子集训练 + 选择前向)，三者都要算进去，不能只报训练时间。
#
# 为什么用"每样本速率"而不是直接拿 wall-clock：这些 run 是同一张卡上跑的，
# 中间被别的进程抢过算力（有一条 r=50% 的 run 慢了近 2 倍）。直接比 wall-clock
# 会把"机器当时忙不忙"当成"数据量大小"的效应。所以：
#   rate = median(train_seconds / n_samples)          # 对污染不敏感
#   gpu_hours = n_samples * rate / 3600 + select_overhead_h
# 评测时间与训练集大小无关，单列，不进净账。
#
# 输入：results/{metrics_long.csv, compute.csv, select_overhead.json}
# 输出：results/compute_table.csv, paper/figures/fig05_compute.png

source("R/00_setup.R")

m  <- read_results("metrics_long.csv")
cp <- read_results("compute.csv")

# base R 没有 jsonlite，而这个文件就是一串 "键": 数字，正则取出来足够
sel_of <- function(method, default = 0) {
  p <- file.path(RESULTS, "select_overhead.json")
  if (!file.exists(p)) return(default)
  txt <- paste(readLines(p, warn = FALSE), collapse = " ")
  mt <- regmatches(txt, regexpr(sprintf('"%s"\\s*:\\s*[0-9.]+', method), txt))
  if (!length(mt)) return(default)
  as.numeric(sub(".*:\\s*", "", mt))
}
sel <- sel_of("nait")

n_of <- function(method, ratio) if (identical(method, "full")) 12000 else round(12000 * ratio)
cp$n_samples <- mapply(n_of, cp$method, cp$ratio)
cp$s_per_sample <- cp$train_seconds / cp$n_samples

rate <- median(cp$s_per_sample)
cp$contaminated <- cp$s_per_sample > 1.3 * rate
rate_clean <- median(cp$s_per_sample[!cp$contaminated])
cat(sprintf("每样本训练耗时：中位数 %.4f s，清洗后 %.4f s（剔除 %d 条被抢算力的 run）\n",
            rate, rate_clean, sum(cp$contaminated)))

cp$train_h  <- cp$n_samples * rate_clean / 3600
cp$select_h <- ifelse(cp$method %in% c("full", "random"), 0, sel)
cp$gpu_hours <- cp$train_h + cp$select_h

full_h <- 12000 * rate_clean / 3600

tab <- do.call(rbind, lapply(split(cp, list(cp$method, cp$ratio), drop = TRUE), function(d) {
  data.frame(method = d$method[1], ratio = d$ratio[1], n_samples = d$n_samples[1],
             n_seed = nrow(d),
             train_h = round(mean(d$train_h), 3),
             select_h = round(mean(d$select_h), 3),
             gpu_hours = round(mean(d$gpu_hours), 3),
             net_saving_pct = round((1 - mean(d$gpu_hours) / full_h) * 100, 1))
}))
tab <- tab[order(tab$method, tab$ratio), ]

# 准确率仅作参考（两任务平均）
acc <- tapply(m$value, list(m$method, m$ratio), mean)
tab$acc <- round(mapply(function(mt, r) acc[mt, as.character(r)], tab$method, tab$ratio), 4)

write.csv(tab, file.path(RESULTS, "compute_table.csv"), row.names = FALSE)

# ---------------- 图 ----------------
pal <- c(random = "grey55", nait = "#0072B2", nait_dedup = "#009E73")
ms  <- intersect(c("random", "nait", "nait_dedup"), unique(tab$method))
labs <- c("random", "nait", "nait + dedup")[match(ms, c("random", "nait", "nait_dedup"))]

png(file.path(FIG, "fig05_compute.png"), width = 1750, height = 1000, res = 150)
par(mar = c(3.6, 4.6, 2.8, 4.2), oma = c(0, 0, 2.0, 0), mgp = c(2.7, 0.8, 0), las = 1)
ylim <- c(0, max(c(tab$gpu_hours, full_h)) * 1.18)
plot(NA, xlim = c(0.04, 0.80), ylim = ylim, xlab = "", bty = "l", xaxt = "n",
     ylab = "GPU-hours per run\n(training + selection pass)", main = "Net compute budget")
axis(1, at = c(.1, .2, .3, .5, .7), labels = c("10%", "20%", "30%", "50%", "70%"))
mtext("Retained training data (fraction)", side = 1, line = 2.2, cex = 0.9)

abline(h = full_h, col = "grey30", lty = 3, lwd = 1.5)
text(0.06, full_h, sprintf("full data (%.2f GPU-h)", full_h), pos = 3, adj = 0,
     cex = 0.75, col = "grey30")

for (mt in ms) {
  d <- tab[tab$method == mt, ]
  lines(d$ratio, d$gpu_hours, col = pal[[mt]], lwd = 2)
  points(d$ratio, d$gpu_hours, col = pal[[mt]], pch = 19, cex = 1.05)
}

axis(4, at = pretty(ylim), labels = pretty(ylim) * 2, col.axis = "grey40", cex.axis = 0.8)
text(0.05, ylim[2], "right axis: cost (CNY @ 2/GPU-h)", adj = c(0, 1), cex = 0.7, col = "grey40")

z <- tab[tab$method == "nait" & abs(tab$ratio - 0.3) < 1e-9, ]
if (nrow(z)) {
  text(0.79, ylim[1] + 0.06 * diff(ylim),
       sprintf("At 30%% retained: %.2f vs %.2f GPU-h  =  %.0f%% net saving",
               z$gpu_hours, full_h, z$net_saving_pct),
       adj = c(1, 0), cex = 0.78, col = "grey20")
}

par(fig = c(0, 1, 0, 1), oma = c(0, 0, 0, 0), mar = c(0, 0, 0, 0), new = TRUE)
plot.new()
legend("top", legend = labs, col = pal[ms], lwd = 2, pch = 19,
       horiz = TRUE, bty = "n", cex = 0.85, seg.len = 2.4)
invisible(dev.off())

cat("\n表已写出：", file.path(RESULTS, "compute_table.csv"), "\n")
cat("图已写出：paper/figures/fig05_compute.png\n\n")
cat(sprintf("全量单次训练：%.2f GPU-h（约 %.0f 元 @2元/GPU-h）\n", full_h, full_h * 2))
cat(sprintf("选择前向开销：%.3f GPU-h（实测，一次性）\n\n", sel))
cat("30% 档的净账：\n")
print(tab[abs(tab$ratio - 0.30) < 1e-9,
          c("method", "n_samples", "train_h", "select_h", "gpu_hours",
            "net_saving_pct", "acc")], row.names = FALSE)
