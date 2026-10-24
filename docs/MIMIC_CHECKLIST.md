# MIMIC 数据申请清单（照着做，别跳步）

> 目标：拿到 MIMIC-IV（结构化）+ MIMIC-IV-Note（病历文本），用它们替换现在的公开题库。
> 这条路径的瓶颈**不是技术，是许可**。下面每一步都有前置条件，跳步会卡住。

## 0. 先明确三件事

| 问题 | 答案 |
|---|---|
| 需要多久 | 注册+培训 1 天（集中做 4–6 小时），DUA 审批 1–2 周，导师签字后才能提交 |
| 要花钱吗 | 不要。PhysioNet 免费，但**禁止**把数据给第三方、禁止上传到任何云 |
| 数据放哪 | 只能放在申请时登记的服务器/工作站。现在这台笔记本可以用，但要在申请里写清楚 |

## 1. 注册 PhysioNet（30 分钟）

1. 打开 https://physionet.org/register/
2. 用**学校邮箱**注册（`.edu.cn` 通过率高，个人邮箱会被要求补充证明）
3. 邮箱验证后，登录 → Settings → 填写：
   - Full name（真实姓名，与证件一致）
   - Institution（学校全称 + 学院）
   - Country: China
   - Research area: 选 `Medical Informatics` / `Clinical Decision Support`

## 2. 完成 CITI 培训（4–6 小时，可分批）

1. 登录 https://about.citiprogram.org/ → Register（用同一个邮箱）
2. 选 institution：搜索 `PhysioNet`（不是你的学校）
3. 课程选 **Data or Specimens Only Research**（不是 Biomedical Research）
4. 学完所有必修模块 → 考试（可重考）→ 下载 **Completion Report (PDF)**

> 卡点：CITI 的证书上必须出现你的**全名**，与 PhysioNet 账号一致，否则 DUA 会被退回。

## 3. 提交 DUA（DUA = Data Use Agreement）

1. PhysioNet → MIMIC-IV 项目页 → 点 `Request access`
2. 上传 CITI Completion Report
3. 填写 **Data Use Agreement**：
   - 责任人（PI）：**你导师**（必须是正式教职）
   - 数据保管人：你自己
   - 用途：写研究计划一段话（用下面这段改）
4. 提交 → 等 PhysioNet 审核（1–2 周）→ 通过后导师邮箱会收到确认
5. 通过后运行：
   ```bash
   wget -r -N -c -np --user <你的用户名> --ask-password \
        https://physionet.org/files/mimiciv/3.1/
   ```
   第一次会让你输 PhysioNet 密码。

## 4. 研究计划段落（直接改）

> We study training-subset selection for clinical language models. Using MIMIC-IV
> and MIMIC-IV-Note we will construct instruction-tuning pairs from de-identified
> discharge summaries, select a subset via neuron-activation scoring, and compare
> downstream performance against full-data training under an equivalence design.
> No re-identification will be attempted; all processing occurs on a single
> password-protected workstation; no data will be shared or uploaded to any
> external service.

## 5. 拿到数据后要跑的三条命令

```bash
# 1) 解压 + 建索引（约 10 分钟）
python tools/mimic_ingest.py --src data/raw/mimic --out data/raw/mimic_clean

# 2) 转成统一 JSONL（和现在公开题库同一套契约）
python prepare_data.py --pool mimic

# 3) 采集激活 → 选子集 → 训练评测（与现在完全相同的流水线）
python collect_acts.py --split train
python select_subset.py --probe-split probe --suffix _mimic
python run_one.py --method nait_dp --ratio 0.3 --seed 1
```

## 6. 检查清单

- [ ] PhysioNet 账号（学校邮箱）
- [ ] CITI 证书 PDF（名字与账号一致）
- [ ] DUA 提交（PI = 导师）
- [ ] DUA 通过邮件
- [ ] MIMIC-IV 下载完成（hosp/ 约 1.5 GB）
- [ ] MIMIC-IV-Note 下载完成（discharge.csv.gz 约 1.2 GB）
- [ ] 解压后磁盘剩余 ≥ 15 GB

## 7. 合规红线（写进 README，别踩）

1. **不上传**：任何云盘、GitHub、HuggingFace、Colab 都不行
2. **不分享**：同实验室没申请的人也不能给
3. **不外推**：只在申请里写明的用途范围内使用
4. **用完删**：项目结束后删除原始文件，只保留派生的聚合统计
5. **仓库里只放派生数据**：`data/processed/` 的 JSONL 也**不能**提交（含原文），要把它加进 `.gitignore`
