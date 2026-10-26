# 07_pipeline.R —— 论文 Fig.1：整条流水线一页看懂
# 输出：paper/figures/fig01_pipeline.png
#
# 纯 base R 画，不引外部包：六个方框 + 箭头 + 每个框下面两行小字说明。

source("R/00_setup.R")

png(file.path(FIG, "fig01_pipeline.png"), width = 1950, height = 720, res = 150)
par(mar = c(0.5, 0.5, 0.5, 0.5), xpd = NA)
plot(NA, xlim = c(0, 100), ylim = c(0, 100), axes = FALSE, xlab = "", ylab = "")

box <- function(x, w, title, l1 = "", l2 = "", fill = "#EDF2F7", border = "#4A5568") {
  y0 <- 52; y1 <- 78
  rect(x - w / 2, y0, x + w / 2, y1, col = fill, border = border, lwd = 1.4)
  text(x, y1 - 7, title, font = 2, cex = 0.95)
  if (nzchar(l1)) text(x, y0 + 8.5, l1, cex = 0.72, col = "#2D3748")
  if (nzchar(l2)) text(x, y0 + 3.5, l2, cex = 0.72, col = "#2D3748")
}

arrow_to <- function(x0, x1, label = "", y = 65) {
  arrows(x0, y, x1, y, length = 0.10, lwd = 1.4, col = "#2D3748")
  if (nzchar(label)) text((x0 + x1) / 2, y + 4.5, label, cex = 0.62, col = "#4A5568")
}

xs <- c(10, 27, 44, 61, 78, 93.5)
w  <- c(15, 14, 14, 15, 14, 12)

box(xs[1], w[1], "1 训练池", "MedMCQA train", "24,000 / 48,000 条", fill = "#E6F0FA")
box(xs[2], w[2], "2 激活采集", "5 层 · response token", "24,000×5×1536", fill = "#E8F5E9")
box(xs[3], w[3], "3 选择协议", "去均值 → 得分 → 去重", "分层配额 → 取前 k%", fill = "#FFF4E0")
box(xs[4], w[4], "4 LoRA SFT", "Qwen2.5-1.5B · bf16", "r=16 · 1 epoch · 4×2", fill = "#EDE9F6")
box(xs[5], w[5], "5 评测", "选项判别 + 生成式", "MedQA / MedMCQA", fill = "#FDECEC")
box(xs[6], w[6], "6 统计", "逐题配对 McNemar", "TOST · Holm · 种子 CI", fill = "#E9EEF3")

for (i in 1:5) arrow_to(xs[i] + w[i] / 2 + 0.4, xs[i + 1] - w[i + 1] / 2 - 0.4)

text(50, 96, "DataDiet-EHR：从 30% 数据到可判定的等效结论", font = 2, cex = 1.25)
text(50, 90, "每个数字都由 Python 出、R 判；选择过程可审计（哈希 + 每样本激活统计）",
     cex = 0.78, col = "#4A5568")

# 对照臂：从第 3 步分叉
segments(xs[3], 52, xs[3], 40, col = "#4A5568", lwd = 1.4)
segments(xs[3] - 16, 40, xs[3] + 16, 40, col = "#4A5568", lwd = 1.4)
arrows(xs[3] - 16, 40, xs[3] - 16, 38.4, length = 0.10, lwd = 1.4, col = "#4A5568")
arrows(xs[3] + 16, 40, xs[3] + 16, 38.4, length = 0.10, lwd = 1.4, col = "#4A5568")
rect(xs[3] - 24, 26, xs[3] - 8, 38, col = "#F7FAFC", border = "#A0AEC0", lwd = 1.2)
text(xs[3] - 16, 34.5, "随机对照", font = 2, cex = 0.8)
text(xs[3] - 16, 30.5, "同规模·同步数", cex = 0.66)
text(xs[3] - 16, 27.8, "random / rand_len", cex = 0.66)
rect(xs[3] + 8, 26, xs[3] + 24, 38, col = "#F7FAFC", border = "#A0AEC0", lwd = 1.2)
text(xs[3] + 16, 34.5, "经典基线", font = 2, cex = 0.8)
text(xs[3] + 16, 30.5, "EL2N（最难样本）", cex = 0.66)
text(xs[3] + 16, 27.8, "代价 0.607 GPU-h", cex = 0.66)

text(50, 14, "对照口径：δ = 2 pp（逐题 + 种子双口径），主终点 = 30% 保留时相对全量的掉点",
     cex = 0.78, col = "#2D3748")
text(50, 9, "算力净账：全量 1.02 GPU-h  vs  nait 0.56（省 45%）· 随机 0.31（省 70%）· EL2N 0.92（省 11%）",
     cex = 0.78, col = "#2D3748")
text(50, 3.5, "开源：协议文档 + 逐题预测 + 每样本激活与选择日志 + 一条命令复现",
     cex = 0.72, col = "#4A5568", font = 3)

invisible(dev.off())
cat("图已写出：paper/figures/fig01_pipeline.png\n")
