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
