"""把最后三个 OOM 失败的 run 登记进排除名单，并在预注册里追加修正案 2。

规则（用户 2026-11-06 定调）：允许因**硬件上限**排除，但必须
  ① 排除发生在看到该 run 准确率之前；
  ② 绝不因结果好坏排除；
  ③ 写进 data/excluded_runs.txt 与 docs/PREREG_NULLBAND.md，留时间戳。

这三个 run 全部是 `torch.AcceleratorError: CUDA error: out of memory`，
与 random_r30_s16 同一类：该子集长度分桶后凑出的 batch 在 8 GB 卡上放不下。
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXCL = ROOT / "data" / "excluded_runs.txt"
PREREG = ROOT / "docs" / "PREREG_NULLBAND.md"

NEW = [
    ("rand_len_r30_s4", "CUDA OOM：该子集按长度分桶后凑出的 batch 超出 8 GB"),
    ("nait_dedup_r30_s4", "CUDA OOM：同上"),
    ("el2n_r30_s4", "CUDA OOM：同上"),
]

AMENDMENT = """
## 修正案 2（2026-11-07 13:45，分析前登记）

`resume_rigor` 第 10 步跑完时，`ok=6 failed=4`。失败的四个 run 全部是
`torch.AcceleratorError: CUDA error: out of memory`，与 `random_r30_s16` 同类：
该子集的样本按长度分桶后凑出的 batch 在 8 GB 显存上放不下（同一配置下其余
种子正常，说明不是参数问题而是数据顺序问题）。

因此：

| arm | 可用种子 | n |
|---|---|---|
| random @30% | 1–15, 17–20 | 19 |
| nait @30% | 1–6 | 6 |
| rand_len @30% | 1, 2, 3, 5 | 4 |
| nait_dedup @30% | 1, 2, 3, 5 | 4 |
| el2n @30% | 1, 2, 3 | 3 |

- 四个排除（`random_r30_s16`、`rand_len_r30_s4`、`nait_dedup_r30_s4`、`el2n_r30_s4`）
  都发生在**看到该 run 准确率之前**（是训练/评测显存报错，不是结果不好），
  已登记 `data/excluded_runs.txt`。
- 判定规则 R1–R4 不变；随机零分布的 n 由 19 确认（修正案 1 已写）。
- 不采用"整体降到 bs2 重跑"，理由同修正案 1：会废掉已完成 run 的参数一致性。
- 报告时须同时给出每个 arm 的 n，避免读者把 n=3 与 n=19 当同等精度。
"""


def main() -> None:
    text = EXCL.read_text(encoding="utf-8") if EXCL.exists() else ""
    added = []
    for name, why in NEW:
        if name in text:
            continue
        text = text.rstrip("\n") + f"\n{name}\t{why}\t2026-11-07\n"
        added.append(name)
    EXCL.write_text(text, encoding="utf-8")
    print(f"excluded_runs.txt: 新增 {added or '无'}")

    pre = PREREG.read_text(encoding="utf-8") if PREREG.exists() else ""
    if "修正案 2" not in pre:
        PREREG.write_text(pre.rstrip("\n") + "\n" + AMENDMENT, encoding="utf-8")
        print("PREREG_NULLBAND.md: 已追加修正案 2")
    else:
        print("PREREG_NULLBAND.md: 修正案 2 已存在，跳过")


if __name__ == "__main__":
    main()