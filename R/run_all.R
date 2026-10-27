# run_all.R —— 一条命令跑完 R 侧全部分析
# 用法（项目根目录）：Rscript R/run_all.R
# 若要在假数据上做自检：Rscript R/99_make_demo_data.R 之后手动 source 各脚本，
# 并把 00_setup.R 的 RESULTS 指向 results/demo。

t0 <- Sys.time()
# Fig.2 需要多档保留率。优先用当前轮（48k 有 10/20/30/50/70 五档）；
# 当前轮只有 30% 一档时，退回 12k pilot 轮的归档，免得画成单点图。
.cur <- file.path(getwd(), "results", "metrics_long.csv")
.nratio <- 0
if (file.exists(.cur)) {
  .m <- read.csv(.cur, stringsAsFactors = FALSE)
  .nratio <- length(unique(.m$ratio[.m$method != "full"]))
}
.curve_archive <- file.path(getwd(), "results_round1_12k")
if (.nratio >= 4) {
  cat(sprintf("Fig.2 用当前轮（%d 档保留率）\n", .nratio))
  Sys.unsetenv("DATADIET_CURVE_DIR")
} else if (dir.exists(.curve_archive)) {
  cat("Fig.2 退回 12k pilot 轮的归档\n")
  Sys.setenv(DATADIET_CURVE_DIR = .curve_archive)
}

# 无 GPU 任务在跑时也别让 R 找系统临时目录（后台启动时那里可能已被回收）
dir.create(file.path(getwd(), "tmp"), showWarnings = FALSE)

steps <- c("R/01_equivalence.R", "R/02_curve.R",
           "R/03_robustness.R", "R/04_compute.R",
           "R/05_multiple.R", "R/06_forest.R", "R/07_pipeline.R")

for (s in steps) {
  cat("\n", strrep("=", 70), "\n>>> ", s, "\n", strrep("=", 70), "\n", sep = "")
  source(s, echo = FALSE)
}
cat(sprintf("\n全部完成，用时 %.1f 秒。\n", as.numeric(difftime(Sys.time(), t0, units = "secs"))))
