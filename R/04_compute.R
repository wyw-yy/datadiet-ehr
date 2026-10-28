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

# 池子大小从数据里读，不写死：24k 那一轮的 train.jsonl 就是 24,000 行。
# 之前写死 12000 会让 24k 轮的"每样本耗时"整体翻倍、子集条数只报一半。
pool_file <- file.path(PROJ, "data", "processed", "train.jsonl")
N_FULL <- if (file.exists(pool_file)) length(readLines(pool_file, warn = FALSE)) else 12000
cat(sprintf("训练池大小（读 train.jsonl）：%d 条\n", N_FULL))

n_of <- function(method, ratio) if (identical(method, "full")) N_FULL else round(N_FULL * ratio)
cp$n_samples <- mapply(n_of, cp$method, cp$ratio)
cp$s_per_sample <- cp$train_seconds / cp$n_samples

rate <- median(cp$s_per_sample)
cp$contaminated <- cp$s_per_sample > 1.3 * rate
rate_clean <- median(cp$s_per_sample[!cp$contaminated])
cat(sprintf("每样本训练耗时：中位数 %.4f s，清洗后 %.4f s（剔除 %d 条被抢算力的 run）\n",
            rate, rate_clean, sum(cp$contaminated)))

cp$train_h  <- cp$n_samples * rate_clean / 3600
# 只有"要看一遍模型"的方法才付选择前向的钱，而且各家不一样：
#   nait*  采 5 层激活 + 打分（实测 917 s = 0.2547 GPU-h）
#   el2n   只需一次前向拿 p_true（实测 36.4 min = 0.607 GPU-h，比采激活更贵，
#          因为它跑的是完整词表 softmax，而激活采集只存 5 层隐藏态）
#   random / rand_len 是纯抽样（rand_len 只是按 nait 的长度分布抽），零开销。
ovh <- c(full = 0, random = 0, rand_len = 0,
         nait = sel_of("nait"), nait_dedup = sel_of("nait_dedup"), el2n = sel_of("el2n"),
         # nait_ns 只是去掉分层配额，激活采集与打分一样要跑，开销同 nait
         nait_ns = sel_of("nait_ns"))
cp$select_h <- as.numeric(ovh[cp$method])
cp$select_h[is.na(cp$select_h)] <- 0
cp$gpu_hours <- cp$train_h + cp$select_h

full_h <- N_FULL * rate_clean / 3600

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
# 这一轮只有 30% 一档（其它比例是上一轮 12k 池的），所以不画曲线，画"堆叠柱"：
# 每根柱子 = 训练 + 选择前向，虚线 = 全量训练的算力。读者一眼看到
# "el2n 明明只留 30% 数据，算力却几乎没省"，那是它跑全词表 softmax 的代价。
pal <- c(random = "grey55", el2n = "#E69F00", rand_len = "#CC79A7", nait = "#0072B2", nait_dedup = "#009E73")
ord <- c("random", "el2n", "rand_len", "nait", "nait_dedup")
lab <- c("random", "el2n", "rand_len", "nait", "nait + dedup")

z <- tab[abs(tab$ratio - 0.30) < 1e-9, ]
z <- z[match(intersect(ord, z$method), z$method), ]
ms <- z$method
labs <- lab[match(ms, ord)]

png(file.path(FIG, "fig05_compute.png"), width = 1750, height = 1000, res = 150)
par(mar = c(3.8, 4.8, 2.8, 4.2), oma = c(0, 0, 2.0, 0), mgp = c(2.7, 0.8, 0), las = 1)
ylim <- c(0, max(c(z$gpu_hours, full_h)) * 1.20)
bp <- barplot(rbind(z$train_h, z$select_h), names.arg = labs, ylim = ylim,
              col = c("grey80", "grey45"), border = NA, space = 0.55,
              ylab = "GPU-hours per run\n(30% retained)", main = "What the 70% saving costs to earn",
              cex.names = 0.9)
text(bp, z$gpu_hours, sprintf("%.0f%%", z$net_saving_pct), pos = 3, cex = 0.8, col = "grey15")

abline(h = full_h, col = "grey30", lty = 3, lwd = 1.5)
text(bp[1] - 0.10, full_h, sprintf("full data (%.2f GPU-h)", full_h),
     pos = 3, adj = c(0, 0), cex = 0.75, col = "grey30")

axis(4, at = pretty(ylim), labels = pretty(ylim) * 2, col.axis = "grey40", cex.axis = 0.8)
text(bp[1] - 0.55, ylim[2], "right axis: cost (CNY @ 2/GPU-h)", adj = c(0, 1), cex = 0.7, col = "grey40")

par(fig = c(0, 1, 0, 1), oma = c(0, 0, 0, 0), mar = c(0, 0, 0, 0), new = TRUE)
plot.new()
legend("top", legend = c("training", "selection forward pass", "net saving vs full data"),
       fill = c("grey80", "grey45", NA), border = NA, lty = c(NA, NA, 3),
       lwd = c(NA, NA, 1.5), col = c(NA, NA, "grey30"),
       horiz = TRUE, bty = "n", cex = 0.82)
invisible(dev.off())

cat("\n表已写出：", file.path(RESULTS, "compute_table.csv"), "\n")
cat("图已写出：paper/figures/fig05_compute.png\n\n")
cat(sprintf("全量单次训练：%.2f GPU-h（约 %.0f 元 @2元/GPU-h）\n", full_h, full_h * 2))
cat(sprintf("选择前向开销：%.3f GPU-h（实测，一次性）\n\n", sel))
cat("30% 档的净账：\n")
print(tab[abs(tab$ratio - 0.30) < 1e-9,
          c("method", "n_samples", "train_h", "select_h", "gpu_hours",
            "net_saving_pct", "acc")], row.names = FALSE)
