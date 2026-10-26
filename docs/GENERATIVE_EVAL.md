# 生成式评估（已实现并跑完，2026-10-26）

选择题评测（`eval.py`）只比较 `" A".." D"` 四个 token 的 logprob：快、确定、可复现，
但它测不出两件事——**模型是不是真的会"写"答案**，以及**它写的东西安不安全**。
这一份是补上的那一支。

## 协议（`gen_eval.py`）

| 项 | 值 |
|---|---|
| 题量 | 500 题（MedMCQA 评测集，`--seed 7` 固定抽样，各 arm 同一批题） |
| 解码 | 贪心（`do_sample=False`），最多 160 new token |
| 提示 | system + 题干四选项 + "先给一个字母，再一句话解释" |
| 抽取 | 去 markdown 装饰后取开头字母；开头没有就取文中第一个 A–D |
| 指标 | 严格准确率、格式合规率、可抽取率、输出长度、危险表述红旗 |
| 成本 | 每 arm 3–8 分钟（输出越长越慢），六个 arm 共 31 分钟 |

危险表述用四条正则查：擅自停药 / 超量用药 / 劝人不必就医 / 武断诊断。

## 结果

| arm | 准确率 | 格式合规 | 中位 token | 带引用/页码 |
|---|---|---|---|---|
| base | 46.4% | 100% | 37 | 0.0% |
| full_s1 | 48.6% | 100% | 18 | 4.0% |
| **nait_r30_s1** | **49.2%** | 100% | 55 | **50.6%** |
| random_r30_s1 | 47.8% | 100% | 30 | 11.2% |
| rand_len_r30_s1 | 47.8% | 100% | 26 | 7.2% |
| el2n_r30_s1 | 46.8% | 100% | 9 | 2.6% |

配对 McNemar：full−nait −0.6pp (p=0.82)、nait−random +1.4pp (p=0.44)、
nait−rand_len +1.4pp (p=0.41)、base−full −2.2pp (p=0.32)。**危险表述红旗：0 条。**

## 三条结论

1. **口径没有骗人**：生成式准确率与 logprob 准确率几乎重合，主表结论不是评测方式的假象。
2. **没有格式崩塌**：六个 arm 100% 合规，`el2n` 中位只写 9 个 token 也照样规范。
3. **nait 学到的是"引经据典"**：50.6% 的回答带 `Ref. / Harrison / Page 2340`，其它 arm 3–11%。
   回池核对：nait 选中的 30% 里 52.7% 的参考答案带引用，其余 70% 只有 27.9%；长度中位 704 vs 491。
   → **激活相似度挑的是文本装置（引用、页码、书名），不是题目价值**。

## 局限（写 limitation 时要带）

- 红旗检测是关键词匹配，不是临床安全评审；0 条红旗只能说明"没有明显危险措辞"。
- 500 题的配对检验只能分辨约 3pp 以上的差异；更小的差别它测不出来。
- 只测了 MedMCQA；MedQA 的生成式评测还没跑（同一套脚本，四个 arm 约 20 分钟）。

## 复现

```bash
.venv\Scripts\python.exe gen_eval.py --task medmcqa --limit 500 --bs 8 --seed 7 --adapter none
.venv\Scripts\python.exe gen_eval.py --task medmcqa --limit 500 --bs 8 --seed 7 --adapter nait_r30_s1
.venv\Scripts\python.exe tools\gen_report.py --task medmcqa
```

产物：`results/gen/<tag>_medmcqa.csv`、`results/gen/summary.csv`、`results/gen/paired.csv`。
