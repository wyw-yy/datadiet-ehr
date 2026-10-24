# 99_make_demo_data.R —— 造假数据，只为在拿到真结果之前把统计管线跑通、把图定版。
# 真实实验时删掉这个脚本即可；下游脚本只认 results/ 下的 5 个文件，不关心数据从哪来。

source("R/00_setup.R")
set.seed(2026)

N_ITEM <- 2000
SEEDS  <- 1:5
DEPTS  <- c("cardio", "onco", "neuro", "resp", "endo")
METHODS_SUB <- c("random", "el2n", "nait", "nait_dedup")
RATIOS <- c(0.10, 0.20, 0.30, 0.50, 0.70)
BASE   <- c(medqa = 0.71, icd = 0.78)          # 全量数据的基准准确率
DEPT_MULT <- c(cardio = 0.90, onco = 1.25, neuro = 0.80, resp = 0.95, endo = 1.10)

# 各方法的掉点曲线：r 越大掉得越少。nait 在 r=0.3 时应几乎不掉，random 应明显掉。
drop_fun <- list(
  random     = function(r) -0.105 * (1 - r)^1.2,
  el2n       = function(r) -0.040 * (1 - r)^1.5,
  nait       = function(r) -0.005 * (1 - r)^2.0,
  nait_dedup = function(r) -0.003 * (1 - r)^2.2
)

items <- data.frame(
  item_id = seq_len(N_ITEM),
  dept    = sample(DEPTS, N_ITEM, TRUE, prob = c(.30, .20, .20, .15, .15))
)
items$z <- rnorm(N_ITEM)   # 题目难度潜变量：同一个 item 在所有实验里共享 → 才有配对性

pred_dir <- file.path(RESULTS, "preds")
dir.create(pred_dir, recursive = TRUE, showWarnings = FALSE)

metrics <- list(); compute <- list(); k <- 1; j <- 1

make_run <- function(method, ratio, seed, task) {
  drop <- if (method == "full") 0 else drop_fun[[method]](ratio)
  acc_eff <- BASE[[task]] + DEPT_MULT[items$dept] * drop + rnorm(1, 0, 0.002)
  p <- plogis(qlogis(acc_eff) + 0.9 * items$z)
  correct <- rbinom(N_ITEM, 1, p)
  eid <- exp_id(method, ratio, seed, task)

  con <- gzfile(file.path(pred_dir, paste0(eid, ".csv.gz")), "w")
  write.csv(
    data.frame(item_id = items$item_id, dept = items$dept, y_true = 1L,
               y_pred = correct, correct = correct,
               score = round(p, 6)),
    con, row.names = FALSE
  )
  close(con)

  metrics[[k]] <<- data.frame(
    exp_id = eid, method = method, ratio = ratio, seed = seed, dept = "all",
    task = task, metric = "acc", value = mean(correct), n = N_ITEM
  ); k <<- k + 1

  # 选择阶段的前向开销：nait 要跑激活→比 random 贵，这正是"净账"要扣的部分
  ovh <- c(full = 0, random = 0.05, el2n = 0.35, nait = 0.55, nait_dedup = 0.60)[[method]]
  train_h <- 3.2 * ratio + ovh
  compute[[j]] <<- data.frame(
    exp_id = eid, method = method, ratio = ratio, seed = seed,
    tokens_seen = round(ratio * 4.1e6),       # 全量约 410 万 token
    gpu_hours = round(train_h, 3),
    wall_s = round(train_h * 3600, 0),
    peak_vram_gb = 7.1,
    select_overhead_h = ovh
  ); j <<- j + 1
}

for (tk in TASKS) {
  for (sd in SEEDS) {
    make_run("full", 1.0, sd, tk)
    for (mt in METHODS_SUB) for (r in RATIOS) make_run(mt, r, sd, tk)
  }
}

write.csv(do.call(rbind, metrics), file.path(RESULTS, "metrics_long.csv"), row.names = FALSE)
write.csv(do.call(rbind, compute), file.path(RESULTS, "compute.csv"), row.names = FALSE)

cat("demo 数据已生成：", length(metrics), "个 run\n")
cat("  ", file.path(RESULTS, "metrics_long.csv"), "\n")
cat("  ", file.path(RESULTS, "compute.csv"), "\n")
cat("  ", pred_dir, "/ <exp_id>.csv.gz\n")
