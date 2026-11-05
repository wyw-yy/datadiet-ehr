# 协议 API —— 六个函数，从原始病历到可审计的子集

这份文档面向"想在自己的数据上跑同一套协议"的人。
所有函数都是纯函数（不读全局状态、不写磁盘），输入输出都是普通 Python 对象，
因此可以单独测试、单独引用。

代码位置：`prepare_mimic.py`（前三节）、`tools/select_subset.py`（第四节）、`tools/make_randlen.py`（第五节）。

---

## 1. `icd_to_dept(code) -> str`

把 ICD-9/ICD-10 编码映射到六个科室桶之一。

```python
icd_to_dept("I50.9")   # -> "cardio"
icd_to_dept("C34.1")   # -> "onco"
icd_to_dept("999.9")   # -> "other"
```

规则：先看首字母（C/D → onco，E → endo，F/G → neuro，I → cardio，J → resp），
再看三位数字段；匹配不到一律 `other`，**不猜**。
为什么重要：科室分布在论文里是分层配额的依据，猜错会让"分层"名不副实。

## 2. `extract_section(text, headings) -> str`

从一份出院小结里抽出"住院经过"（hospital course）那一段。

```python
extract_section(note_text, ["HOSPITAL COURSE", "住院经过", "Brief Hospital Course"])
```

行为：
- 大小写不敏感，容忍 6 种常见标题变体；
- 从标题起到下一个已知章节标题为止；
- **少于 200 字符视为抽取失败并返回空串**（调用方计入 `skipped_short`，不静默补内容）。

这个"宁可跳过也不编"的选择是为了让失败可见：演练时它一次抓出了 196 份全是空的结果。

## 3. `split_by_subject(rows, frac=(0.7, 0.15, 0.15), seed=42) -> dict`

按 `subject_id` 切 train/probe/eval，**同一个病人的所有记录只进一个集合**。

```python
{"train": [...], "probe": [...], "eval": [...]}
```

为什么不能用随机行切分：同一病人的多次入院小结高度相似，
行级切分会让"考题"以近乎原文的形式出现在训练集里，分数虚高。
产物里同时写 `mimic_split.json`（含 seed、每集合行数、跳过的短文数），
便于别人复算这个切分。

## 4. `make_pair(row, dept=None) -> dict`

把一条病历整理成训练/评测用的 (instruction, response) 对。

```python
{"id": "mt00012", "dept": "cardio",
 "instruction": "患者 68 岁男性，主诉……（问题）",
 "response": "…（答案）"}
```

`id` 前缀区分来源：`mt` = MIMIC train、`mp` = MIMIC probe、`me` = MIMIC eval。

## 5. `nait_scores(feats, mu=None) -> ndarray`

按 Nait（Chen et al., ICLR 2026）的机制给每个样本打"目标域代表性"分。

```python
scores = nait_scores(acts)          # acts: (N, L, D) 每层取 response token 的均值
```

步骤：
1. **减去池内均值**（`mu` 缺省时现算）：`feats - mu`。
   这一步不能省——原始隐藏态高度各向异性，实测随机两条的余弦中位数就有 0.95，
   不减均值的话"去重"会把 85% 的样本判成重复。
2. 逐层 L2 归一化，与目标域质心求余弦，跨层取平均。

## 6. `greedy_kept_streaming(tr_norm, order, thr, chunk=1024) -> ndarray`

按得分从高到低扫，保留与已保留集合余弦都 < `thr` 的样本（流式去重）。

```python
keep = greedy_kept_streaming(normed_feats, order=np.argsort(-scores), thr=0.95)
```

内存是 `O(chunk × kept)` 而不是 `O(N²)`：48,000 条样本时前者约 60 MB，
后者（朴素布尔矩阵）是 576 MB。返回布尔掩码。

---

## 最小复现路径

```bash
python prepare_mimic.py --src /path/to/mimic --out data/processed_mimic
python tools/collect_acts.py --split train      # 采激活
python tools/collect_acts.py --split probe
python tools/select_subset.py --probe-split probe --suffix ""
python tools/make_randlen.py                    # 长度匹配对照
python tools/run_one.py --method nait --ratio 0.30 --seed 1
Rscript R/run_all.R
```

每一步的产物与校验见 `docs/PROTOCOL.md`；数字怎么来的见 `docs/CLAIM_EVIDENCE.md`。

---

## 附：pA..pD 的量纲（2026-11-05 审查记录）

esults/preds/*.csv.gz 里的四个概率列在**两个时期量纲不同**，这是修 OOM 时改的：

| 写入时间 | 归一化范围 | 典型值 | 可用性 |
|---|---|---|---|
| 2026-11-05 17:40 之前（96 个文件） | 整个 151,936 词表 | pA≈2e-6 | **只可读 pred/correct** |
| 之后（28 个文件，仍在增加） | 只在 A–D 四个选项内 | pA+…+pD=1 | 可用于置信度 |

两者只差一个逐行常数，所以 **argmax（也就是 pred/correct）完全一致**，R 分析层也只读
item_id / dept / pred / correct，因此**已报的所有数字不受影响**。

但旧文件在 6 位小数处已被截断，连 argmax 都复现不出来（实测 el2n_r30_s1 有 326/4183 行），
所以**不能**靠"按行归一"把旧文件改成新量纲——已经试过，被校验挡住，改为标注。

要拿 pA..pD 做置信度/校准/ECE 分析，必须用新 eval.py **重新评测**，不能复用旧文件。
检查命令：

```bash
python tools/check_pred_scale.py     # exit 2 = 两种量纲共存，属预期
```
