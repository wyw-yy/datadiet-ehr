# 可追溯性说明（这套东西是谁做的、是哪个版本）

生成时间：2026-11-21 17:45　·　生成脚本：`tools/make_provenance.py`（只读，不改任何文件）

这份文件回答三个问题：代码有没有版本管理、交出去的文件能不能核对、论文里的数字能不能一路查到逐题预测。


## 一、版本管理

| 项 | 值 |
|---|---|
| 提交次数 | 95 |
| 首次提交 | 38136ad 2026-10-24 |
| 最近提交 | a57829d 2026-11-21 |
| 提交者 | 全部 `wyw-yy`（92	wyw-yy <wyw-yy@users.noreply.github.com>） |
| 标签 | v1.0.0, v1.0.1, v1.0.2, v1.0.3, v1.0.4 |
| 远程仓库 | git@github.com:wyw-yy/datadiet-ehr.git（私有） |
| 纳入版本控制的文件 | 977 个 |
| 源文件数量 | 93 个（根目录 `.py` + `tools/` + `R/`） |
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
| `RESULTS.md` | 结论总表（所有数字的唯一出口） | `1DD37742876A2B38D2FE2E57D2719D3EF14E2A9FD745B2C90F3DAD7C6618B3EC` | 13.9 KB |
| `paper/table1.md` | 论文主表 | `CA9769566B772502E388793D484383CE92CDE5704B3F0D1112B8BCE6B63375BC` | 5.9 KB |
| `paper/appendix_en.md` | 论文英文附录 | `8DD82FB413B1E78A72AA7212FC8CDDBE4DFED7CE83BFCA10D1E042A0974B1DEF` | 7.3 KB |
| `docs/PREREG_NULLBAND.md` | 零分布实验的预注册（跑之前写死的判定规则） | `3E0C292C4273E1A6015AC75FBCCA52D8E32644502CFCA5CEDC1F9A91442CB8AC` | 6.2 KB |
| `docs/INCIDENTS.md` | 事故记录（三次翻车与修法） | `AFA84F5800E76E750C6B58D506E8139F54B8D97DC5562C68129F53B0C8E757B3` | 4.5 KB |
| `docs/CLAIM_EVIDENCE.md` | 主张-证据矩阵 | `F0A9971942EC8E0D34C27B785B512012273AFA49B5F762BB6F38C7A93ADBE1D6` | 6.6 KB |
| `results/metrics_long.csv` | 全部 run 的准确率长表 | `6F7D0523923C0703D64BA592D05F9521E3AE2D96982C97EFDF0B99FD2D744D25` | 7.3 KB |
| `results/eq_table.csv` | 等效性检验结果 | `4D010420034BC4F3DAFABD5920ED57F99F48CEF249244AB5D129FD37149AEBB9` | 4.1 KB |
| `results/eq_contrast.csv` | 方法间对比 + Holm | `05AA1539A415A8FEEF9A4427991877ADEF76E4A1A4A32AC682C3903A8FC42EEF` | 3.7 KB |
| `results/compute_table.csv` | 算力净账 | `2996759A9031EC712C735A6124EBC28F714A53A83F595247D1ABEB1A29EBE817` | 1.0 KB |
| `results/nullband.csv` | 20 个随机子集的零分布 | `AEC7E56E2A4BCAAB2833AF98015D9898B20DB818A98D54AA7CBDECB875185DBD` | 3.6 KB |
| `dist/datadiet-ehr-v1.0.0.zip` | 发布包（GitHub Release 附件） | `04F457D2908BA7D063EA20C87D5E532AE6A07210AE88AE0FDC055DC9869BB783` | 24.62 MB |
| `dist/datadiet-ehr-v1.0.1.zip` | 发布包（GitHub Release 附件） | `59B37FF8087B681E5812B2FFB48F6CC0423D74107DF31EAE117D4648F2F05BCD` | 24.64 MB |
| `dist/datadiet-ehr-v1.0.2.zip` | 发布包（GitHub Release 附件） | `435502B4ACE01FDF5B1E4348ED48A41CB21AD028715E9CCE8B18B72165D5AB99` | 29.13 MB |
| `dist/datadiet-ehr-v1.0.3.zip` | 发布包（GitHub Release 附件） | `9433236C15ADC2D2F9B9835B7308BBE016E00351DA537D9BA5288C979C9175EB` | 29.14 MB |
| `dist/datadiet-ehr-v1.0.4.zip` | 发布包（GitHub Release 附件） | `E456ABED626CF8DD4380EE3B50128BA0704B3840EDECD52D2CFDC1ECC3932CF6` | 29.14 MB |

## 三、实验能不能追到底

- 训练/评测 run：**138 条**（`results/metrics_long.csv`）
- 逐题预测文件：**138 份**（`results/preds/*.csv.gz`，每份含 item_id / pred / correct）
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
