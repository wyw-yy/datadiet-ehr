# run_all.R —— 一条命令跑完 R 侧全部分析
# 用法（项目根目录）：Rscript R/run_all.R
# 若要在假数据上做自检：Rscript R/99_make_demo_data.R 之后手动 source 各脚本，
# 并把 00_setup.R 的 RESULTS 指向 results/demo。

t0 <- Sys.time()
# Fig.2 的剂量-反应曲线来自 12k pilot 轮（24k 主轮只跑了 30% 一档）。
# 归档目录存在时才指过去，否则退回当前轮，免得换机器就报错。
.curve_archive <- file.path(getwd(), "results_round1_12k")
if (dir.exists(.curve_archive)) Sys.setenv(DATADIET_CURVE_DIR = .curve_archive)

steps <- c("R/01_equivalence.R", "R/02_curve.R",
           "R/03_robustness.R", "R/04_compute.R",
           "R/05_multiple.R", "R/06_forest.R")

for (s in steps) {
  cat("\n", strrep("=", 70), "\n>>> ", s, "\n", strrep("=", 70), "\n", sep = "")
  source(s, echo = FALSE)
}
cat(sprintf("\n全部完成，用时 %.1f 秒。\n", as.numeric(difftime(Sys.time(), t0, units = "secs"))))
