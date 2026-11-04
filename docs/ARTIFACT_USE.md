# 成果使用指南：同一套代码，三种交付形态

这份文档回答一个问题：**代码和数据到底怎么用在软著、论文、挑战杯上**。
三条线用的是同一个仓库、同一批数字，但"封装方式"和"冻结时点"完全不同，混用会出事。

---

## 0. 先分清三个东西

| 对象 | 软著要的 | 论文要的 | 挑战杯要的 |
|---|---|---|---|
| **代码** | 源代码前 30 页 + 后 30 页（PDF） | 公开仓库 + DOI | 研制报告里描述，附 zip |
| **数据** | ❌ 不需要 | ✅ Data Availability 说明 | 支撑材料里给来源 |
| **结果** | ❌ 不需要（软著不保护结果） | ✅ 主表 + 图 + 逐题预测 | 研制报告第三节 |
| **冻结时点** | 提交软著那天（V1.0） | 投稿那天（tag v1.0.0） | 11-30 报名那天 |
| **能不能改** | 改了就是 V1.1，要重交 | 改数字 = 重跑 `finish_round` | 报名后尽量别动 |

一句话：**软著锁"代码长什么样"，论文锁"数字能被复现"，挑战杯锁"你讲得清"。**

---

## 1. 软著：交什么、什么时候交

**已备好的材料**（`softcopyright/`）：

| 文件 | 内容 | 规格 |
|---|---|---|
| `源程序.pdf` | 22 个源文件、3,468 行 | 49 页、70.8 行/页（≥50 行合规） |
| `说明书.pdf` | README + 协议 + API + 数据卡 + 生成式评测 | 12 页 |
| `申请表填写参考.md` | 全称/简称/版本/功能/技术特点逐项值 | — |
| `申请流程.md` | 七步操作 + 材料清单 + 常见驳回原因 | — |
| `合作开发协议模板.md` | 三人签字用 | — |

**不需要交的**：实验结果、CSV、图、模型权重、数据集 —— 软著保护的是**代码表达**。

**提交时点：现在。** 理由：
- 校赛 11-30 报名，证书要 1–2 个月，晚交就用不上；
- 软著登记的是 V1.0 这个快照，**提交后你继续改代码完全不影响**——那是 V1.1 的事；
- 审查是形式审查（不查代码质量），所以"实验还没完"不构成障碍。

**提交前 3 件事**：
1. 在 `申请表` 里写版本号 `V1.0`，并确保 `源程序.pdf` 页眉也是 `V1.0`（两处必须一致，不一致会驳回）；
2. 记一笔台账：`dist/datadiet-ehr-v1.0.0.zip` 的 sha256 + git commit（`tools/make_release.py` 会打出来），将来证明"提交时是哪一版"；
3. 三个人签 `合作开发协议`（打印→手签→扫描），签章页三人都签（多签不拒，少签必退）。

---

## 2. 论文：投出去之前要打的包

### 2.1 三步发布

```bash
# ① 冻结版本（本地打 tag，之后任何改动都不影响这个点）
git tag -a v1.0.0 -m "paper submission snapshot"
git push origin master --tags          # 需要先配远程

# ② 打成果包（白名单，不会混进权重/原始数据/日志）
.venv\Scripts\python.exe tools\make_release.py --version 1.0.0
# → dist/datadiet-ehr-v1.0.0.zip  (24.6 MB, 737 个文件)
# → dist/datadiet-ehr-v1.0.0.manifest.txt  (逐文件 sha256)

# ③ 上传 Zenodo（GitHub 仓库连过去会自动发版），拿到 DOI
```

### 2.2 论文里两段固定写法

**Code Availability**（填 DOI 与许可证）：
> The code, the selection protocol, the per-item predictions and the
> selection audit logs are available at https://github.com/<user>/datadiet-ehr
> (archived at https://doi.org/10.5281/zenodo.XXXXXXX, MIT licence).
> Training used Qwen2.5-1.5B-Instruct with LoRA (r=16, α=32) for one epoch;
> all hyper-parameters are in `docs/PROTOCOL.md` and `paper/methods_draft.md`.

**Data Availability**（诚实说明"用了什么、没用什么"）：
> Training and evaluation used public datasets only: MedMCQA (train split,
> 182,822 items) and MedQA (USMLE Step 1, 1,273 items), under their original
> licences. No protected health information was used. MIMIC-IV was **not**
> used in this version; the synthetic EHR rehearsal (`docs/DATA_CARD.md`)
> validates the ingestion path without any real records.

### 2.3 补充材料放什么

| 放 | 不放 |
|---|---|
| `docs/PROTOCOL.md`（可复现协议 v1.0） | 模型权重（2.6 GB，任何人都能重训） |
| `paper/table1.md`（主表 + 剂量表） | `data/raw/`（第三方数据，各自许可） |
| `results/preds/*.csv.gz`（逐题预测，46 份） | `.venv`、日志、临时目录 |
| `data/subsets/*.json`（选中的 id，可审计） | MIMIC 派生文本（DUA 禁止） |
| `audit/`（哈希清单 + 选择日志） | 任何含病人信息的中间文件 |
| 六张图（`paper/figures/`） | 4.3 MB 的研制报告 PDF（与论文无关） |

### 2.4 审稿人复现的三条命令

```bash
python run_one.py --method full   --ratio 1.0  --seed 1
python run_one.py --method nait   --ratio 0.30 --seed 1
python run_one.py --method random --ratio 0.30 --seed 1
Rscript R/run_all.R
```
第一条跑完就有了 full/nait/random 三组，R 一跑就出表和图——`README.md` 里也有。

---

## 3. 挑战杯：用同一批材料，换讲法

- **正文**：`docs/challenge_b/研制报告.md`（→ docx/pdf 已生成，15 页、7,759 字）
- **支撑材料**：软著证书（受理号先填）、论文（录用后）、`dist/datadiet-ehr-v1.0.0.zip`、演示视频
- **答辩口径**：卖点不是"我比随机好"，而是
  「**30% 数据等效成立（7/8 双口径）、算力净省 48.6%、并给出了可复现协议与开源实现**；
  同时我们诚实报告：nait 相对随机只有 +0.50pp（未校正 p=0.016、Holm 0.208，不显著），**真正的节省来自数据冗余本身**」。
  这个讲法经得住追问，也与你论文的 limitation 一致。

---

## 4. 时间线（按今天 2026-10-28 排）

| 时间 | 做什么 | 谁做 |
|---|---|---|
| 本周 | 软著实名 + 三人签协议 + 提交，拿受理号 | 你 |
| 本周 | `git tag v1.0.0` + 建私有远程 + 推上去 | 我/你 |
| 11 月上旬 | 挑战杯申报书（B3 表）填好，支撑材料装订 | 你 |
| 11 月中旬 | 论文正文补 Introduction/Abstract → 内部评审 | 我起草，你改 |
| 11-30 | 挑战杯报校团委 | 你 |
| 投稿日 | Zenodo 归档拿 DOI → 填进论文 → 投 | 你 |

---

## 5. 三条维护规矩（避免以后返工）

1. **权重永不入库**：`.gitignore` 已拦 `*.safetensors`、`*.npz`、`adapters_round*/`、`acts_round*/`；新开一轮就把产物放 `*_round*/` 并确认被忽略。
2. **数字只从 CSV 来**：任何写进论文/报告的数字，都必须能在 `results/*.csv` 里找到；改完跑 `tools/audit_final.py`，它会揪出"来源不明的数字"。
3. **改代码就升版本**：软著 V1.0 提交后，代码再改就是 V1.1；论文用 tag 冻结，别在投稿后改数字。
