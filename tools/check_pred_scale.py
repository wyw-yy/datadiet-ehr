"""check_pred_scale.py —— 检查 results/preds/ 里 pA..pD 的量纲是否混用。

2026-11-05 审查发现：`eval.py` 修 OOM 前后写出的 pA..pD 量纲不同——
  * 旧（< 2026-11-05 17:40）：torch.log_softmax(logits, dim=-1)[:, opt_ids]，
    在整个 151,936 词表上归一，写出来是 1e-6 量级；
  * 新：torch.log_softmax(logits[:, opt_ids], dim=-1)，
    只在这四个选项上归一，四列之和恒为 1。
两者只差一个逐行常数 → **argmax 与 `correct` 不受影响**（R 侧也只读 correct），
但列的量纲混着用会静默出错：旧文件在 6 位小数处已被截断，连 argmax 都复现不了
（实测 el2n_r30_s1 有 326/4183 行复现不出原 pred）。所以：
  结论 = 这四列**只能用于"新 eval"写出的文件**；要做置信度/校准分析必须重跑评测。

本脚本只报告，不改数据。退出码：0 = 全部是新格式或全部是旧格式；2 = 混用。
"""

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
PRED = ROOT / "results" / "preds"
COLS = ["pA", "pB", "pC", "pD"]


def main() -> None:
    files = sorted(PRED.glob("*.csv.gz"))
    if not files:
        sys.exit("没有 preds 文件")

    new, old = [], []
    for f in files:
        d = pd.read_csv(f)
        if not set(COLS).issubset(d.columns):
            continue
        (new if d[COLS].sum(axis=1).median() > 0.5 else old).append(f.name)

    print(f"preds 总数 {len(files)}")
    print(f"  选项内归一（新 eval，pA..pD 可用）: {len(new)}")
    print(f"  全词表归一（旧 eval，pA..pD 已截断）: {len(old)}")
    if new and old:
        print("  WARN: 两种量纲共存 —— 只读 correct/pred，不要拿 pA..pD 做置信度分析")
        sys.exit(2)


if __name__ == "__main__":
    main()