# 可追溯性说明（这套东西是谁做的、是哪个版本）

生成时间：2026-11-06 19:52　·　生成脚本：`tools/make_provenance.py`（只读，不改任何文件）

这份文件回答三个问题：代码有没有版本管理、交出去的文件能不能核对、论文里的数字能不能一路查到逐题预测。


## 一、版本管理

| 项 | 值 |
|---|---|
| 提交次数 | 72 |
| 首次提交 | 38136ad 2026-10-24 |
| 最近提交 | 90e07c5 2026-11-06 |
| 提交者 | 全部 `wyw-yy`（69	wyw-yy <wyw-yy@users.noreply.github.com>） |
| 标签 | v1.0.0, v1.0.1 |
| 远程仓库 | https://github.com/wyw-yy/datadiet-ehr.git（私有） |
| 纳入版本控制的文件 | 928 个 |
| 源文件数量 | 89 个（根目录 `.py` + `tools/` + `R/`） |
| 当前工作区 | 有未提交改动 |

说明：2026-10-23 做过一次 `git filter-branch`，把误入库的 2.6 GB LoRA 权重与 331 MB 激活从历史里摘掉，因此**提交哈希被重写过一次**（内容不变、哈希变了）。这件事记录在 `docs/INCIDENTS.md`，不藏着。


## 二、交付文件的哈希值

对方拿到文件后，`certutil -hashfile <文件> SHA256`（Windows）或 `sha256sum <文件>`（Linux）就能核对。


| 文件 | 是什么 | SHA-256 | 大小 |
|---|---|---|---|
| `softcopyright/源程序.txt` | 软著：提交的 22 个源文件拼本 | `7BE4569ABF8B40F8FD2149EAB7326FE30A4F4C623523450DA06F42A0942B9B84` | 146.5 KB |
| `softcopyright/说明书.txt` | 软著：说明书正文 | `F84D800397CB2CA060FBCA4DE600C1C602FB0C906F3DBC84CDEA3AE2B2438F86` | 9.7 KB |
| `softcopyright/源程序.pdf` | 软著：源程序 PDF（登记用） | `CF0CF267F149556E7D3D70025144FFB580B557A67DC65DF1A74C8F5F63D4CA28` | 4723.8 KB |
| `softcopyright/说明书.pdf` | 软著：说明书 PDF（登记用） | `46B5E7FD1345DF64A38427C771F174B37DE34007F93864A2AE7FAE018C324AD6` | 181.0 KB |
| `RESULTS.md` | 结论总表（所有数字的唯一出口） | `5339EF17E96DFE33F788456017DC434A70F31C70BBC795E7C5CA478319ACCA51` | 13.3 KB |
| `paper/table1.md` | 论文主表 | `9B59886EE1984EC28C6D578922171C2E2374577D06DB420423AD7C919B3EDAA8` | 5.6 KB |
| `paper/appendix_en.md` | 论文英文附录 | `41754CB10FC51A5692B47D25A4868D2DE624B979CE918003A697AFEC20D54409` | 6.6 KB |
| `docs/PREREG_NULLBAND.md` | 零分布实验的预注册（跑之前写死的判定规则） | `42935FC5A6AF73305752947D3BC3F8DBC26E59669F25AEC1E0ED3F338106BA92` | 5.0 KB |
| `docs/INCIDENTS.md` | 事故记录（三次翻车与修法） | `22CB4D2F772706E4448583121A27C351889A1E14ABD0BD7247683DBA0FD03AFD` | 4.5 KB |
| `docs/CLAIM_EVIDENCE.md` | 主张-证据矩阵 | `A5D27C0C3F4A9197889EB9A0C7D7AD079E7F4C6AA5427267BE372532296C5256` | 6.4 KB |
| `results/metrics_long.csv` | 全部 run 的准确率长表 | `0ECDA0E35B5A3A97C9640A1E17D3EC833072CA5045914769601ECC4120078F8A` | 6.8 KB |
| `results/eq_table.csv` | 等效性检验结果 | `2B73035C26CF028C6A4902F5E46631BC377C1D2350E0810F5A86742FD25537CF` | 4.0 KB |
| `results/eq_contrast.csv` | 方法间对比 + Holm | `D831391081EF68692E728E946950528889997A3FDBA39D19F15E63418296B5B5` | 3.2 KB |
| `results/compute_table.csv` | 算力净账 | `1F7CA3AC2DCD3473BFC68E9342AC70B62740029B8614412FBFAAB2F1021B536B` | 1.0 KB |
| `results/nullband.csv` | 20 个随机子集的零分布 | `—` | 缺失 |
| `dist/datadiet-ehr-v1.0.0.zip` | 发布包（GitHub Release 附件） | `04F457D2908BA7D063EA20C87D5E532AE6A07210AE88AE0FDC055DC9869BB783` | 24.62 MB |
| `dist/datadiet-ehr-v1.0.1.zip` | 发布包（GitHub Release 附件） | `59B37FF8087B681E5812B2FFB48F6CC0423D74107DF31EAE117D4648F2F05BCD` | 24.64 MB |

## 三、实验能不能追到底

- 训练/评测 run：**130 条**（`results/metrics_long.csv`）
- 逐题预测文件：**130 份**（`results/preds/*.csv.gz`，每份含 item_id / pred / correct）
- 一条结论的追溯链：`RESULTS.md` 的数字 → `results/*.csv` → `results/preds/*.csv.gz` → 某一道题的预测 → 对应 adapter 与训练日志
- 三层自动审计：`tools/audit_final.py`（文档数字是否都有 CSV 出处）、`tools/audit_runs.py`（run ↔ adapter ↔ 预测是否对得上）、`tools/verify.py`（关键不变量）
- 预注册：`docs/PREREG_NULLBAND.md` 在跑之前就写死了判定规则与修正案，事后没有改口径

## 四、怎么当场核（三条命令）

```bat
REM 1) 核对文件没被动过（本目录下执行）
certutil -hashfile RESULTS.md SHA256
REM 2) 核对发布包
certutil -hashfile dist\datadiet-ehr-v1.0.1.zip SHA256
REM 3) 看版本历史
git log --oneline | find /c /v ""
```

## 五、边界（这份文件不证明什么）

- 它证明**版本可追溯、材料可核对、数字可回查**，不证明代码由谁逐行敲出来。
- 软著签章页要求声明“未使用 AI 编写代码”，那是另一件事，与这里的工程证据无关——**两者的口径不要混用**：这里的材料支持“我确实做了这些实验、结论是真的”，不支持“我没有用过 AI 工具”。
- 真实病历数据（MIMIC / 院内 EMR）尚未使用，任何“临床落地”表述都应标注为外推。
