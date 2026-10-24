# 00_setup.R —— 路径 / 常量 / 工具函数（所有脚本 source 它）
# 用法：在 datadiet-ehr 项目根目录执行  Rscript R/01_equivalence.R
# 说明：刻意只用 base R，不依赖 tidyverse —— 任何一台新装的 Windows R 都能直接跑。

PROJ <- normalizePath(".", mustWork = TRUE)
if (!dir.exists(file.path(PROJ, "R"))) {
  stop("请在 datadiet-ehr 项目根目录运行（当前：", PROJ, "）")
}

# 语言边界：Python 只往 results/ 写，R 只从 results/ 读
RESULTS <- file.path(PROJ, "results")
FIG     <- file.path(PROJ, "paper", "figures")
dir.create(FIG, recursive = TRUE, showWarnings = FALSE)

# 等效性界 δ。写进 Method，跑实验之前定死，不许跑完再改。
# 为什么是 2 个绝对点而不是 1 个：配对差值在 ~1–4k 道题、3 个种子的条件下，
# 95%CI 半宽约 1.0–1.5pp（每道题 d∈{-1,0,1}，方差 ~0.37）。δ=1pp 时连"真等效"
# 都可能因为 CI 太宽而判不合格，δ=2pp 才有检验功效。审稿人问起，这就是理由。
DELTA <- 0.02

TASKS   <- c("medqa", "medmcqa")
METHODS <- c("full", "random", "nait", "nait_dedup")
PAL     <- c(full = "grey30", random = "grey65", el2n = "#E69F00",
             nait = "#0072B2", nait_dedup = "#009E73")

read_results <- function(...) {
  read.csv(file.path(RESULTS, ...), stringsAsFactors = FALSE)
}

# 逐题预测：Python 侧命名 <exp_id>_<task>.csv.gz
read_preds <- function(eid, task) {
  read.csv(file.path(RESULTS, "preds", paste0(eid, "_", task, ".csv.gz")),
           stringsAsFactors = FALSE)
}

# 与 config.py 的 exp_id() 对齐：full 就是 full_s<seed>，其余带比例
exp_id <- function(method, ratio, seed) {
  if (identical(method, "full")) sprintf("full_s%d", as.integer(seed))
  else sprintf("%s_r%02d_s%d", method, round(ratio * 100), as.integer(seed))
}

# 配对 bootstrap：输入逐题差值向量，返回均值的 95% CI
boot_ci <- function(x, B = 2000, alpha = 0.05, seed = 1) {
  set.seed(seed)
  m <- replicate(B, mean(sample(x, length(x), replace = TRUE)))
  stats::quantile(m, c(alpha / 2, 1 - alpha / 2), names = FALSE)
}

fmt_p <- function(p) ifelse(p < 0.001, "<.001", sprintf("%.3f", p))
