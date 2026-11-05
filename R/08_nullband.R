# 08_nullband.R —— 随机 30% 子集的零分布（预注册见 docs/PREREG_NULLBAND.md）
# 只回答一件事：nait 的掉点落在"随机怎么挑"这条分布带的哪个位置。
# 输入：results/preds/ 下的逐题预测；输出：results/nullband.csv + paper/figures/fig07_nullband.png

source("R/00_setup.R")

TASK_MAIN  <- "medmcqa"
TASK_OTHER <- "medqa"
N_RANDOM   <- 20L
MAIN_RATIO <- 0.30

# ---------- 全量分母：full_s1..s3，逐题取均值 ----------
full_seeds <- c(1L, 2L, 3L)
full_list  <- lapply(full_seeds, function(s) {
  f <- file.path(RESULTS, "preds", paste0(exp_id("full", 1, s), "_", TASK_MAIN, ".csv.gz"))
  if (!file.exists(f)) return(NULL)
  read.csv(f, stringsAsFactors = FALSE)
})
full_list <- Filter(Negate(is.null), full_list)
if (!length(full_list)) stop("找不到任何 full_s* 的逐题预测")
ids <- full_list[[1]]$item_id

full_mat <- sapply(full_list, function(d) d$correct[match(ids, d$item_id)])
if (is.null(dim(full_mat))) full_mat <- matrix(full_mat, ncol = 1)
full_item <- rowMeans(full_mat, na.rm = TRUE)
full_acc  <- mean(full_item)

# ---------- 单个 run 的 delta / CI / TOST ----------
one_run <- function(method, ratio, seed, task = TASK_MAIN) {
  f <- file.path(RESULTS, "preds", paste0(exp_id(method, ratio, seed), "_", task, ".csv.gz"))
  if (!file.exists(f)) return(NULL)
  d <- read.csv(f, stringsAsFactors = FALSE)
  c_i <- d$correct[match(ids, d$item_id)]
  if (all(is.na(c_i))) return(NULL)
  delta <- c_i - full_item                     # 逐题差值，落在 [-1, 1]
  delta <- delta[!is.na(delta)]
  ci <- boot_ci(delta, B = 2000) * 100
  data.frame(arm = method, seed = seed, task = task,
             acc = mean(c_i, na.rm = TRUE),
             delta_pp = mean(delta) * 100,
             ci_lo = ci[1], ci_hi = ci[2],
             tost_pass = (ci[1] > -DELTA * 100) && (ci[2] < DELTA * 100),
             stringsAsFactors = FALSE)
}

res <- list()
for (s in seq_len(N_RANDOM)) {
  r <- one_run("random", MAIN_RATIO, s)
  if (!is.null(r)) res[[length(res) + 1]] <- r
}
for (m in c("nait", "rand_len", "nait_dedup", "el2n")) {
  for (s in 1:6) {
    r <- one_run(m, MAIN_RATIO, s)
    if (!is.null(r)) res[[length(res) + 1]] <- r
  }
}
if (!length(res)) stop("没有任何可分析的预测文件")
tab <- do.call(rbind, res)
write.csv(tab, file.path(RESULTS, "nullband.csv"), row.names = FALSE)

# ---------- 零分布统计 ----------
rd <- tab[tab$arm == "random", ]
rd <- rd[order(rd$seed), ]
if (nrow(rd) < 5) stop("随机种子太少（", nrow(rd), "），先补跑")
q <- quantile(rd$delta_pp, c(0.025, 0.10, 0.50, 0.90, 0.975), names = FALSE)
p10 <- q[2]; p90 <- q[4]
n_pass <- sum(rd$tost_pass)
pi_ci  <- binom.test(n_pass, nrow(rd))$conf.int

arm_mean <- function(a) {
  x <- tab[tab$arm == a, ]
  if (!nrow(x)) return(NULL)
  c(mean = mean(x$delta_pp), n = nrow(x))
}
nait_m <- arm_mean("nait"); rl_m <- arm_mean("rand_len"); dd_m <- arm_mean("nait_dedup")

pct_of <- function(v) mean(rd$delta_pp < v) * 100

cat(sprintf("\n随机 30%% 子集零分布（%s，%d 个种子，全量分母 %.4f）\n",
            TASK_MAIN, nrow(rd), full_acc))
cat("  注：分母 = full_s1..s3 的逐题正确率均值（不是单个种子），因此本表的 Δ 与\n",
    "      eq_table.csv 里按单种子配对的 Δ 可能差 0.1–0.2pp，二者都在允许的读数误差内。\n",
    sep = "")
cat(sprintf("  均值 %.2f  标准差 %.2f  最小 %.2f  最大 %.2f\n",
            mean(rd$delta_pp), sd(rd$delta_pp), min(rd$delta_pp), max(rd$delta_pp)))
cat(sprintf("  P2.5 %.2f  P10 %.2f  中位 %.2f  P90 %.2f  P97.5 %.2f\n",
            q[1], q[2], q[3], q[4], q[5]))
cat(sprintf("  逐题 TOST 通过 %d/%d = %.0f%%（Clopper-Pearson 95%% CI %.0f%%–%.0f%%）\n",
            n_pass, nrow(rd), 100 * n_pass / nrow(rd),
            100 * pi_ci[1], 100 * pi_ci[2]))
if (!is.null(nait_m)) {
  cat(sprintf("  nait   %.2f（n=%d）→ 位于随机分布的第 %.0f 百分位\n",
              nait_m["mean"], nait_m["n"], pct_of(nait_m["mean"])))
}
if (!is.null(rl_m)) cat(sprintf("  rand_len %.2f（n=%d）→ 第 %.0f 百分位\n",
                                rl_m["mean"], rl_m["n"], pct_of(rl_m["mean"])))
if (!is.null(dd_m)) cat(sprintf("  nait_dedup %.2f（n=%d）→ 第 %.0f 百分位\n",
                                dd_m["mean"], dd_m["n"], pct_of(dd_m["mean"])))

# 预注册判定（R1–R3）
if (!is.null(nait_m)) {
  rule <- if (nait_m["mean"] > p90) "R2 优于典型随机（仍需 Holm 校正）" else
          if (nait_m["mean"] < p10) "R3 差于典型随机" else "R1 与随机不可区分"
  cat(sprintf("  预注册判定：%s\n", rule))
}

# ---------- 图：分布带 ----------
png(file.path(FIG, "fig07_nullband.png"), width = 1900, height = 950, res = 150)
par(mar = c(4.2, 4.6, 3.6, 1.2), mgp = c(2.7, 0.8, 0), las = 1)

ylim <- range(c(rd$delta_pp, tab$delta_pp, -DELTA * 100), na.rm = TRUE)
ylim <- ylim + c(-0.25, 0.45) * diff(ylim)
plot(NA, xlim = c(0.2, 3.8), ylim = ylim, xaxt = "n", bty = "l",
     xlab = "", ylab = "Delta vs full data (pp)",
     main = sprintf("Null band: %d random 30%% subsets (%s, 48k pool)",
                    nrow(rd), TASK_MAIN))
axis(1, at = c(1, 2, 3), labels = c(sprintf("random\n(n=%d)", nrow(rd)),
                                    "nait", "rand_len"))

abline(h = 0, col = "grey40", lty = 3)
abline(h = -DELTA * 100, col = "#D55E00", lty = 2, lwd = 1.4)
text(3.78, -DELTA * 100, "equivalence margin", pos = 3, cex = 0.72, col = "#D55E00", adj = 1)

# 随机点（横轴 1，抖动）
set.seed(7)
xj <- 1 + runif(nrow(rd), -0.16, 0.16)
points(xj, rd$delta_pp, pch = 19, cex = 0.85,
       col = ifelse(rd$tost_pass, "grey35", "grey72"))
# 箱线
boxplot(rd$delta_pp, at = 1, add = TRUE, boxwex = 0.42, outline = FALSE,
        col = NA, border = "grey25", axes = FALSE)
segments(0.84, q[2], 1.16, q[2], col = "grey25", lty = 2)   # P10
segments(0.84, q[4], 1.16, q[4], col = "grey25", lty = 2)   # P90
text(1.30, q[2], "P10", cex = 0.66, col = "grey35")
text(1.30, q[4], "P90", cex = 0.66, col = "grey35")

# nait / rand_len 的位置
draw_arm <- function(x, m, col, lab) {
  if (is.null(m)) return(invisible())
  segments(x - 0.17, m["mean"], x + 0.17, m["mean"], col = col, lwd = 3)
  points(x, m["mean"], pch = 18, cex = 1.5, col = col)
  text(x + 0.20, m["mean"], sprintf("%s  %.2f", lab, m["mean"]),
       pos = 4, cex = 0.72, col = col)
}
draw_arm(2, nait_m, PAL[["nait"]], "nait")
draw_arm(3, rl_m, PAL[["rand_len"]], "rand_len")

legend("bottomleft", bty = "n", cex = 0.72,
       legend = c(sprintf("random, TOST pass (%d/%d)", n_pass, nrow(rd)),
                  sprintf("random, TOST fail (%d/%d)", nrow(rd) - n_pass, nrow(rd))),
       pch = 19, col = c("grey35", "grey72"))
invisible(dev.off())

cat("\n产物：\n  results/nullband.csv\n  paper/figures/fig07_nullband.png\n")