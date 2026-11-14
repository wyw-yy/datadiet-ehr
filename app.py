"""app.py —— DataDiet-EHR 的本地演示界面（零依赖，只用 Python 标准库）。

为什么不用 Streamlit/Gradio：这台机器装包不稳（pip 卡索引），而评审现场不能出岔子。
一个 http.server + 一张 HTML 就够了，双击 `run_ui.bat` 打开浏览器即可演示。

启动：
    .venv\\Scripts\\python.exe app.py            # 然后浏览器打开 http://127.0.0.1:8765
    .venv\\Scripts\\python.exe app.py --port 9000

页面展示的是**已经跑完的真实结果**（读 results/*.csv），不是现场训练的假数据；
底部"现场演示"按钮会真的调 run_one.py --smoke（约 3 分钟，可选）。
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RES = ROOT / "results"
FIG = ROOT / "paper" / "figures"

TASKS = {"medmcqa": "MedMCQA（4,183 题）", "medqa": "MedQA（1,273 题）"}
METHODS = ["nait", "nait_ns", "rand_len", "nait_dedup", "random", "el2n"]


def read_csv(name: str) -> list[dict]:
    p = RES / name
    if not p.exists():
        return []
    with p.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def fnum(x, nd=2):
    try:
        return f"{float(x):.{nd}f}"
    except (TypeError, ValueError):
        return "—"


def build_summary() -> dict:
    eq = read_csv("eq_table.csv")
    nb = read_csv("nullband.csv")
    cp = read_csv("compute_table.csv")

    rows = []
    for r in eq:
        if abs(float(r.get("ratio", 0)) - 0.30) > 1e-9:
            continue
        rows.append({
            "task": r.get("task", ""),
            "method": r.get("method", ""),
            "n_seed": r.get("n_seed", ""),
            "delta": fnum(r.get("delta_pp")),
            "lo": fnum(r.get("ci_lo_pp")),
            "hi": fnum(r.get("ci_hi_pp")),
            "equiv_item": r.get("equiv_item", ""),
            "equiv_seed": r.get("equiv_seed", ""),
        })

    # nullband.csv 是逐种子的长表（arm, seed, task, delta_pp, tost_pass）；
    # 这里按臂聚合均值，并算该均值落在 19 个随机子集分布中的百分位。
    import statistics
    main_task = "medmcqa"
    rand_d = [float(r["delta_pp"]) for r in nb
              if r.get("arm") == "random" and r.get("task") == main_task]
    band = {}
    for arm in ["nait", "nait_ns", "rand_len", "nait_dedup", "el2n", "random"]:
        ds = [float(r["delta_pp"]) for r in nb
              if r.get("arm") == arm and r.get("task") == main_task]
        if not ds:
            continue
        m = statistics.mean(ds)
        pct = (100.0 * sum(1 for x in rand_d if x < m) / len(rand_d)) if rand_d else 0.0
        band[arm] = {"delta": fnum(m), "pct": f"{pct:.0f}%", "n": len(ds)}

    compute = []
    for r in cp:
        if abs(float(r.get("ratio", 0)) - 0.30) > 1e-9:
            continue
        compute.append({
            "method": r.get("method", ""),
            "train_h": fnum(r.get("train_h"), 3),
            "sel_h": fnum(r.get("select_h"), 3),
            "gpu_h": fnum(r.get("gpu_hours"), 3),
            "net": fnum(r.get("net_saving_pct"), 1),
            "acc": fnum(r.get("acc"), 4),
        })

    return {"rows": rows, "band": band, "compute": compute,
            "tasks": TASKS, "methods": METHODS}


PAGE = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>DataDiet-EHR · 演示界面</title>
<style>
 :root {{ --bg:#0f1115; --card:#171a21; --line:#2a2f3a; --fg:#e8eaed; --dim:#9aa0a6;
          --ok:#3fb950; --bad:#f85149; --acc:#58a6ff; }}
 * {{ box-sizing:border-box; }}
 body {{ margin:0; background:var(--bg); color:var(--fg);
        font:15px/1.6 "Microsoft YaHei","Segoe UI",system-ui,sans-serif; }}
 header {{ padding:22px 32px 10px; border-bottom:1px solid var(--line); }}
 h1 {{ font-size:20px; margin:0 0 6px; }}
 .sub {{ color:var(--dim); font-size:13px; }}
 main {{ padding:22px 32px 48px; max-width:1180px; }}
 .cards {{ display:grid; grid-template-columns:repeat(4,1fr); gap:14px; margin:18px 0 26px; }}
 .card {{ background:var(--card); border:1px solid var(--line); border-radius:10px; padding:14px 16px; }}
 .card .k {{ color:var(--dim); font-size:12px; }}
 .card .v {{ font-size:22px; font-weight:600; margin-top:4px; }}
 .card .u {{ color:var(--dim); font-size:12px; }}
 h2 {{ font-size:16px; margin:26px 0 10px; }}
 table {{ width:100%; border-collapse:collapse; background:var(--card);
          border:1px solid var(--line); border-radius:10px; overflow:hidden; }}
 th,td {{ padding:9px 12px; text-align:left; border-bottom:1px solid var(--line); font-size:14px; }}
 th {{ color:var(--dim); font-weight:500; background:#141821; }}
 tr:last-child td {{ border-bottom:none; }}
 .ok {{ color:var(--ok); }} .bad {{ color:var(--bad); }} .num {{ font-variant-numeric:tabular-nums; }}
 .figs {{ display:grid; grid-template-columns:1fr 1fr; gap:16px; }}
 .fig {{ background:var(--card); border:1px solid var(--line); border-radius:10px; padding:10px; }}
 .fig img {{ width:100%; border-radius:6px; background:#fff; }}
 .fig .cap {{ color:var(--dim); font-size:12px; margin-top:8px; }}
 pre {{ background:#0b0d11; border:1px solid var(--line); border-radius:8px; padding:12px 14px;
        overflow:auto; font-size:13px; }}
 code {{ font-family:Consolas,monospace; }}
 .note {{ color:var(--dim); font-size:13px; border-left:3px solid var(--acc); padding-left:12px; }}
 button {{ background:var(--acc); color:#04121f; border:0; border-radius:8px;
           padding:9px 16px; font-size:14px; font-weight:600; cursor:pointer; }}
 button:disabled {{ opacity:.5; cursor:default; }}
 .row {{ display:flex; gap:12px; align-items:center; flex-wrap:wrap; }}
 select {{ background:var(--card); color:var(--fg); border:1px solid var(--line);
           border-radius:8px; padding:8px 10px; font-size:14px; }}
 #log {{ margin-top:10px; color:var(--dim); font-size:13px; white-space:pre-wrap; }}
</style></head><body>
<header>
  <h1>DataDiet-EHR · 临床训练子集选择与等效性评估</h1>
  <div class="sub">用神经元激活挑出 30% 训练数据，用预注册的等效性检验判断"到底掉没掉"。</div>
</header>
<main>
  <div class="cards">
    <div class="card"><div class="k">训练池</div><div class="v">48,000 <span class="u">条</span></div>
        <div class="u">去重保留 97.32%</div></div>
    <div class="card"><div class="k">30% 子集</div><div class="v">14,400 <span class="u">条</span></div>
        <div class="u">等效界 δ = 2 pp</div></div>
    <div class="card"><div class="k">nait 掉点（MedMCQA）</div><div class="v num">−0.98 <span class="u">pp</span></div>
        <div class="u">95% CI [−1.57, −0.07]，6 种子</div></div>
    <div class="card"><div class="k">算力净省</div><div class="v">48.6<span class="u">%</span></div>
        <div class="u">2.128 → 1.093 GPU·h</div></div>
  </div>

  <h2>30% 保留率下各方法相对全量的掉点</h2>
  <table><thead><tr><th>任务</th><th>方法</th><th>种子</th><th>Δ (pp)</th>
      <th>95% CI</th><th>逐题口径</th><th>种子口径</th></tr></thead><tbody>
  {rows}
  </tbody></table>
  <p class="note">判定口径：<b>逐题</b>用全体题目的配对自助区间看是否整体落在 ±2pp；
      <b>种子</b>看每个种子的区间是否都落在界内。两个口径都过才算"等效"。</p>

  <h2>随机子集的零分布（19 个随机 30% 子集）</h2>
  <table><thead><tr><th>对照臂</th><th>Δ (pp)</th><th>在零分布中的百分位</th><th>种子数</th></tr></thead><tbody>
  {band}
  </tbody></table>
  <p class="note">关键结论：<b>nait 落在随机分布的上沿，但统计上仍与随机不可区分</b>
      （Holm 校正后 p = 0.176）；MedQA 上更是第 53 百分位——"能砍多狠"强依赖任务。</p>

  <h2>算力净账（30% 保留）</h2>
  <table><thead><tr><th>方法</th><th>训练 (GPU·h)</th><th>选择前向 (GPU·h)</th>
      <th>合计 (GPU·h)</th><th>净省</th><th>准确率</th></tr></thead><tbody>
  {compute}
  </tbody></table>
  <p class="note">净省 = 1 − (训练 + 选择) / 全量训练。把"选择前向"计入后，
      nait 的净省是 <b>48.6%</b>，不是 70%——这是本项目最容易被夸大、也最容易被审稿人打回的一处。</p>

  <h2>结果图</h2>
  <div class="figs">
    <div class="fig"><img src="/fig/fig02_data_efficiency.png">
      <div class="cap">保留比例 vs 掉点（48k 池）</div></div>
    <div class="fig"><img src="/fig/fig07_nullband.png">
      <div class="cap">19 个随机子集的零分布（MedMCQA）</div></div>
  </div>

  <h2>一条命令复现</h2>
  <pre><code>python prepare_data.py --pool domain
python collect_acts.py --split train
python select_subset.py
python run_one.py --method nait --ratio 0.30 --seed 1 --epochs 1
Rscript R/run_all.R && Rscript R/08_nullband.R</code></pre>

  <h2>现场演示（可选，约 3 分钟）</h2>
  <div class="row">
    <button id="run">跑一次冒烟实验</button>
    <span class="sub">200 条训练 + 100 题评测，验证"选样→训练→评测→写指标"整条链路</span>
  </div>
  <div id="log"></div>

  <h2>诚实边界</h2>
  <p class="note">本项目<b>不主张</b>"选择器显著优于随机"。能证明的是：30% 保留率下 nait
      仍满足 ±2pp 等效界，且算力净省 48.6%；而随机子集有 63% 会掉出界外。
      全部数字来自 <code>results/*.csv</code>，可逐条复核。</p>
</main>
<script>
document.getElementById('run').onclick = async (e) => {{
  const btn = e.target, log = document.getElementById('log');
  btn.disabled = true; log.textContent = '启动中…（约 3 分钟，别关这个页面）';
  try {{
    const r = await fetch('/api/smoke', {{method:'POST'}});
    const j = await r.json();
    log.textContent = j.ok ? ('完成：' + j.tail) : ('失败：' + j.tail);
  }} catch (err) {{ log.textContent = '请求失败：' + err; }}
  btn.disabled = false;
}};
</script></body></html>
"""


def render() -> str:
    s = build_summary()

    row_html = []
    for r in s["rows"]:
        mark = lambda v: ('<span class="ok">通过</span>' if str(v).lower() in ("true", "1")
                          else '<span class="bad">未过</span>')
        row_html.append(
            f"<tr><td>{html.escape(TASKS.get(r['task'], r['task']))}</td>"
            f"<td>{html.escape(r['method'])}</td><td class='num'>{r['n_seed']}</td>"
            f"<td class='num'>{r['delta']}</td>"
            f"<td class='num'>[{r['lo']}, {r['hi']}]</td>"
            f"<td>{mark(r['equiv_item'])}</td><td>{mark(r['equiv_seed'])}</td></tr>")

    band_html = []
    for arm, d in s["band"].items():
        band_html.append(
            f"<tr><td>{html.escape(arm)}</td><td class='num'>{d['delta']}</td>"
            f"<td class='num'>{d['pct']}</td><td class='num'>{d['n']}</td></tr>")

    comp_html = []
    for c in s["compute"]:
        comp_html.append(
            f"<tr><td>{html.escape(c['method'])}</td><td class='num'>{c['train_h']}</td>"
            f"<td class='num'>{c['sel_h']}</td><td class='num'>{c['gpu_h']}</td>"
            f"<td class='num'>{c['net']}%</td><td class='num'>{c['acc']}</td></tr>")

    return (PAGE.replace("{rows}", "\n".join(row_html))
                .replace("{band}", "\n".join(band_html))
                .replace("{compute}", "\n".join(comp_html))
                .replace("{{", "{").replace("}}", "}"))


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def _send(self, code, body: bytes, ctype="text/html; charset=utf-8"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self._send(200, render().encode("utf-8"))
        elif self.path.startswith("/fig/"):
            name = Path(self.path[5:]).name
            p = FIG / name
            if p.exists():
                self._send(200, p.read_bytes(), "image/png")
            else:
                self._send(404, b"no such figure")
        elif self.path == "/api/summary":
            self._send(200, json.dumps(build_summary(), ensure_ascii=False).encode("utf-8"),
                       "application/json; charset=utf-8")
        else:
            self._send(404, b"not found")

    def do_POST(self):
        if self.path != "/api/smoke":
            self._send(404, b"not found")
            return
        py = ROOT / ".venv" / "Scripts" / "python.exe"
        cmd = [str(py if py.exists() else sys.executable), "run_one.py",
               "--smoke", "--method", "full", "--seed", "1"]
        try:
            p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=1800)
            tail = (p.stdout or "").strip().splitlines()[-3:]
            body = {"ok": p.returncode == 0, "tail": " | ".join(tail) or (p.stderr or "")[-300:]}
        except subprocess.TimeoutExpired:
            body = {"ok": False, "tail": "超时（30 分钟）"}
        self._send(200, json.dumps(body, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    a = ap.parse_args()
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), Handler)
    print(f"demo UI: http://127.0.0.1:{a.port}  (Ctrl+C 结束)")
    srv.serve_forever()


if __name__ == "__main__":
    main()