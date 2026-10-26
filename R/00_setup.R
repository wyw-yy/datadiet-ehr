# 00_setup.R —— 路径 / 常量 / 工具函数（所有脚本 source 它）
# 用法：在 datadiet-ehr 项目根目录执行  Rscript R/01_equivalence.R
# 说明：刻意只用 base R，不依赖 tidyverse —— 任何一台新装的 Windows R 都能直接跑。

PROJ <- normalizePath(".", mustWork = TRUE)
if (!dir.exists(file.path(PROJ, "R"))) {
  stop("请在 datadiet-ehr 项目根目录运行（当前：", PROJ, "）")
}

# 语言边界：Python 只往 results/ 写，R 只从 results/ 读
RESULTS <- Sys.getenv("DATADIET_RESULTS_DIR", unset = file.path(PROJ, "results"))
# 3-epoch 那轮的 id 带 _e3 后缀，同一套脚本靠环境变量切换，不改代码
FIG     <- file.path(PROJ, "paper", "figures")
dir.create(FIG, recursive = TRUE, showWarnings = FALSE)

# 等效性界 δ。写进 Method，跑实验之前定死，不许跑完再改。
# 为什么是 2 个绝对点而不是 1 个：配对差值在 ~1–4k 道题、3 个种子的条件下，
# 95%CI 半宽约 1.0–1.5pp（每道题 d∈{-1,0,1}，方差 ~0.37）。δ=1pp 时连"真等效"
# 都可能因为 CI 太宽而判不合格，δ=2pp 才有检验功效。审稿人问起，这就是理由。
DELTA <- 0.02

# 方法之间的等效界。这里问的不是"和全量比掉不掉"，而是"两种挑法有没有区别"。
# 界取 1pp：小于 1pp 的差距在实际部署里没法用（换个种子就翻方向），
# 所以"差异 < 1pp"就该判成"等效"，而不是用"p>0.05 所以没差别"来糊过去
# （那是 absence of evidence，不是 evidence of absence）。
DELTA_CONTRAST <- 0.01

TASKS   <- c("medqa", "medmcqa")
METHODS <- c("full", "random", "rand_len", "el2n", "nait", "nait_dedup")
PAL     <- c(full = "grey30", random = "grey65", rand_len = "#CC79A7",
             el2n = "#E69F00", nait = "#0072B2", nait_dedup = "#009E73")

read_results <- function(...) {
  read.csv(file.path(RESULTS, ...), stringsAsFactors = FALSE)
}

# 逐题预测：Python 侧命名 <exp_id>_<task>.csv.gz
read_preds <- function(eid, task) {
  read.csv(file.path(RESULTS, "preds", paste0(eid, "_", task, ".csv.gz")),
           stringsAsFactors = FALSE)
}

# 与 config.py 的 exp_id() 对齐：full 就是 full_s<seed>，其余带比例。
# DATADIET_RUN_TAG 会追加后缀（3-epoch 那轮用 e3），保证两轮 id 不撞、也不互相覆盖。
RUN_TAG <- Sys.getenv("DATADIET_RUN_TAG", unset = "")

exp_id <- function(method, ratio, seed) {
  suf <- if (nzchar(RUN_TAG)) paste0("_", RUN_TAG) else ""
  if (identical(method, "full")) sprintf("full_s%d%s", as.integer(seed), suf)
  else sprintf("%s_r%02d_s%d%s", method, round(ratio * 100), as.integer(seed), suf)
}

# 配对 bootstrap：输入逐题差值向量，返回均值的 95% CI
boot_ci <- function(x, B = 2000, alpha = 0.05, seed = 1) {
  set.seed(seed)
  m <- replicate(B, mean(sample(x, length(x), replace = TRUE)))
  stats::quantile(m, c(alpha / 2, 1 - alpha / 2), names = FALSE)
}

fmt_p <- function(p) ifelse(p < 0.001, "<.001", sprintf("%.3f", p))
