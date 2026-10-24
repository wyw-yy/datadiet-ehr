# run_all.R —— 一条命令跑完 R 侧全部分析
# 用法（项目根目录）：Rscript R/run_all.R
# 若要在假数据上做自检：Rscript R/99_make_demo_data.R 之后手动 source 各脚本，
# 并把 00_setup.R 的 RESULTS 指向 results/demo。

t0 <- Sys.time()
steps <- c("R/01_equivalence.R", "R/02_curve.R",
           "R/03_robustness.R", "R/04_compute.R")

for (s in steps) {
  cat("\n", strrep("=", 70), "\n>>> ", s, "\n", strrep("=", 70), "\n", sep = "")
  source(s, echo = FALSE)
}
cat(sprintf("\n全部完成，用时 %.1f 秒。\n", as.numeric(difftime(Sys.time(), t0, units = "secs"))))
