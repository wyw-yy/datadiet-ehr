"""审查脚本：找出文档里残留的旧口径数字与自相矛盾之处。

用法：.venv\\Scripts\\python.exe tools/review_docs.py
只读，不改文件。
"""

import csv
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent

# 已作废的旧口径数字 → 说明
RETIRED = {
    "45.9": "12k 轮的净省",
    "43.8": "24k 轮墙钟净省",
    "46.3": "更早的归一化净省",
    "47.8": "24k 轮的净省",
    "1.069": "24k 轮 nait 合计 GPU-h",
    "2.047": "24k 轮全量 GPU-h",
    "98.43": "24k 轮去重保留率",
    "99.08": "12k 轮去重保留率",
    "0.032": "旧的 Holm 值（家族只有 2 条时算的）",
    "12,000 条": "12k 池口径",
    "24,000 条": "24k 池口径",
    "3,600 条": "24k 轮的 30% 子集",
}

# 当前权威值
KEY = {
    "pool": "48,000",
    "subset30": "14,400",
    "dedupe": "97.32",
    "nait_mc": "-0.96",
    "rand_mc": "-1.45",
    "delta": "+0.50",
    "holm": "0.064",
    "net": "48.2",
    "full_gpu_h": "2.082",
}

# 合法出现：这些是"历史事实"或"另一个指标的巧合同值"，不是口径残留
ALLOW_LINE = {
    "docs/GENERATIVE_EVAL.md": ("47.8",),          # 生成式准确率，不是净省
    "docs/challenge_b/研制报告.md": ("12,000 条",),  # 叙述当年去重事故
    "GLOSSARY.md": ("12,000 条",),                  # 教材式举例
    # 交底书要讲"当年在 24k 池上踩的坑"，这里的规模数字是历史事实，不是口径残留
    "docs/patent/交底书_草稿.md": ("12,000 条", "24,000 条"),
}
SKIP_PARTS = {".venv", ".git", "node_modules", "dist", "log", "tmp"}


def docs():
    for p in ROOT.rglob("*.md"):
        # Windows 上 relative_to 给的是反斜杠；统一成正斜杠，否则下面的前缀/白名单都对不上
        rel = str(p.relative_to(ROOT)).replace("\\", "/")
        if any(part in rel for part in SKIP_PARTS):
            continue
        if rel.startswith(("results_round", "_notice", "softcopyright", "docs/archive", "docs/challenge_b/blocks")):
            continue
        yield p, rel


def main() -> None:
    print("=" * 78)
    print("文档审查：残留旧口径数字")
    print("=" * 78)
    hits = 0
    for p, rel in docs():
        text = p.read_text(encoding="utf-8", errors="ignore")
        for old, why in RETIRED.items():
            for m in re.finditer(re.escape(old), text):
                line_no = text.count("\n", 0, m.start()) + 1
                line = text.splitlines()[line_no - 1].strip()[:110]
                # 允许"已作废"这类明确标注
                if "作废" in line or "旧" in line or "已改" in line:
                    continue
                if old in ALLOW_LINE.get(rel, ()):
                    continue
                if "当时池子" in line or "池子 12,000" in line:
                    continue
                print(f"  {rel}:{line_no}  含 {old}（{why}）")
                print(f"      {line}")
                hits += 1
    print(f"\n残留 {hits} 处\n")

    print("=" * 78)
    print("关键数字是否出现在主文档")
    print("=" * 78)
    main_docs = ["RESULTS.md", "README.md", "docs/ALIGNMENT.md",
                 "docs/ADVISOR_SUMMARY.md", "paper/results_draft.md", "paper/table1.md"]
    for name in main_docs:
        p = ROOT / name
        if not p.exists():
            print(f"  {name}: 不存在")
            continue
        raw = p.read_text(encoding="utf-8", errors="ignore")
        # 文档里负号有时是 U+2212（排版用的减号），比较前统一成 ASCII，
        # 否则会出现"数字明明在，却报缺失"的假警报。
        t = raw.replace("\u2212", "-").replace("\u2013", "-")
        missing = [k for k, v in KEY.items() if v.replace("\u2212", "-") not in t]
        status = "OK" if not missing else "缺 " + ", ".join(missing)
        print(f"  {name:<28} {status}")

    print("\n" + "=" * 78)
    print("CSV 与文档的一致性抽查")
    print("=" * 78)
    hl = json.loads((ROOT / "results/headline.json").read_text(encoding="utf-8"))
    mc = hl["medmcqa|nait|0.3"]
    print(f"  headline: nait@30% medmcqa = {mc['delta_pp']:+.2f} pp "
          f"(CI {mc['ci_lo_pp']:+.2f}..{mc['ci_hi_pp']:+.2f}), vs random "
          f"{mc['vs_random_pp']:+.2f} pp (p={mc['vs_random_p']})")
    holm = list(csv.DictReader(open(ROOT / "results/holm.csv", encoding="utf-8")))
    c = [r for r in holm if r["family"] == "C_contrast_at_30" and r["task"] == "medmcqa"
         and r["method"] == "nait"]
    if c:
        print(f"  holm.csv: nait−random medmcqa 校正后 p = {c[0]['p_holm']}")
    comp = list(csv.DictReader(open(ROOT / "results/compute_table.csv", encoding="utf-8")))
    for r in comp:
        if abs(float(r["ratio"]) - 0.3) < 1e-9:
            print(f"  compute: {r['method']:<9} total={float(r['gpu_hours']):.3f} GPU-h "
                  f"net={float(r['net_saving_pct']):.1f}%")

    print("\n" + "=" * 78)
    print("论文草稿完整性")
    print("=" * 78)
    need = ["paper/intro_draft.md", "paper/methods_draft.md", "paper/results_draft.md",
            "paper/discussion_draft.md", "paper/abstract_draft.md", "paper/conclusion_draft.md",
            "paper/table1.md", "paper/appendix_en.md"]
    for n in need:
        p = ROOT / n
        size = p.stat().st_size if p.exists() else 0
        print(f"  {n:<32} {'有 ' + str(size) + ' B' if size else '缺'}")


if __name__ == "__main__":
    main()
