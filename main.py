import random
import time
from flask import Flask, jsonify, request, render_template_string

app = Flask(__name__)

RF = 0.02


def make_stocks(n, seed=42):
    if n < 1:
        raise ValueError("need at least 1 stock")
    rng = random.Random(seed)
    out = []
    for i in range(n):
        price = round(rng.uniform(12, 220), 2)
        er = round(rng.uniform(0.03, 0.22), 4)
        vol = round(rng.uniform(0.06, 0.38), 4)
        profit = round(price * er, 4)
        sharpe = round((er - RF) / vol, 4)
        out.append({
            "ticker": f"STK{i+1:03d}",
            "cost": price,
            "ret": er,
            "vol": vol,
            "sharpe": sharpe,
            "profit": profit,
        })
    return out


def greedy_pick(stocks, budget):
    # fractional knapsack — sort by profit per dollar
    ranked = sorted(stocks, key=lambda s: s["profit"] / s["cost"], reverse=True)
    left = budget
    total = 0.0
    picks = []
    for s in ranked:
        if left <= 0:
            break
        if s["cost"] <= left:
            total += s["profit"]
            left -= s["cost"]
            picks.append({**s, "qty": 1.0, "got": s["profit"]})
        else:
            frac = left / s["cost"]
            got = s["profit"] * frac
            total += got
            picks.append({**s, "qty": round(frac, 4), "got": round(got, 4)})
            left = 0
    return total, picks


def dp_pick(stocks, budget):
    # 0/1 knapsack, 1d dp, whole shares only
    scale = 100
    W = int(budget * scale)
    dp = [0.0] * (W + 1)
    for s in stocks:
        w = int(round(s["cost"] * scale))
        v = s["profit"]
        if w <= 0 or w > W:
            continue
        for cap in range(W, w - 1, -1):
            cand = dp[cap - w] + v
            if cand > dp[cap]:
                dp[cap] = cand
    return dp[W]


def timed(fn, *args, runs=3):
    last = None
    t0 = time.perf_counter()
    for _ in range(runs):
        last = fn(*args)
    ms = (time.perf_counter() - t0) / runs * 1000
    return ms, last


PAGE = r"""
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Portfolio Maximizer</title>
<link rel="preconnect" href="https://fonts.googleapis.com"/>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=Fraunces:opsz,wght@9..144,600;9..144,700&display=swap" rel="stylesheet"/>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<style>
  :root {
    --bg: #0f1410;
    --panel: #1a221c;
    --line: #2d3b32;
    --text: #e8efe6;
    --muted: #9aab9c;
    --accent: #d4a54a;
    --green: #5fbf7a;
    --blue: #6ea8d8;
    --danger: #e07a5f;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0;
    font-family: "IBM Plex Sans", system-ui, sans-serif;
    background:
      radial-gradient(1200px 600px at 10% -10%, #243028 0%, transparent 55%),
      radial-gradient(900px 500px at 100% 0%, #2a2418 0%, transparent 50%),
      var(--bg);
    color: var(--text);
    min-height: 100vh;
  }
  .wrap { max-width: 1180px; margin: 0 auto; padding: 28px 20px 60px; }
  header { margin-bottom: 22px; }
  header h1 {
    font-family: Fraunces, Georgia, serif;
    font-size: clamp(1.8rem, 4vw, 2.6rem);
    margin: 0 0 8px;
    letter-spacing: -0.02em;
  }
  header p { margin: 0; color: var(--muted); max-width: 62ch; line-height: 1.5; }
  .grid {
    display: grid;
    grid-template-columns: 300px 1fr;
    gap: 16px;
  }
  @media (max-width: 900px) { .grid { grid-template-columns: 1fr; } }
  .panel {
    background: color-mix(in srgb, var(--panel) 92%, black);
    border: 1px solid var(--line);
    border-radius: 14px;
    padding: 16px;
  }
  label { display: block; font-size: 0.82rem; color: var(--muted); margin: 12px 0 6px; }
  input, select {
    width: 100%;
    background: #101612;
    color: var(--text);
    border: 1px solid var(--line);
    border-radius: 8px;
    padding: 10px 12px;
    font: inherit;
  }
  button {
    width: 100%;
    margin-top: 18px;
    border: 0;
    border-radius: 10px;
    padding: 12px 14px;
    font: inherit;
    font-weight: 600;
    cursor: pointer;
    background: linear-gradient(180deg, #e0b45a, var(--accent));
    color: #1a1408;
  }
  button:disabled { opacity: 0.55; cursor: wait; }
  .note {
    margin-top: 14px;
    font-size: 0.78rem;
    color: var(--muted);
    line-height: 1.45;
  }
  .stats {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 10px;
    margin-bottom: 16px;
  }
  @media (max-width: 800px) { .stats { grid-template-columns: repeat(2, 1fr); } }
  .stat {
    background: #141b16;
    border: 1px solid var(--line);
    border-radius: 12px;
    padding: 12px;
  }
  .stat span { display: block; color: var(--muted); font-size: 0.75rem; }
  .stat strong { font-size: 1.15rem; margin-top: 4px; display: block; }
  .charts {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 14px;
  }
  @media (max-width: 800px) { .charts { grid-template-columns: 1fr; } }
  .chart-box h3 {
    margin: 0 0 10px;
    font-size: 0.95rem;
    font-weight: 600;
  }
  canvas { width: 100% !important; max-height: 280px; }
  table {
    width: 100%;
    border-collapse: collapse;
    margin-top: 14px;
    font-size: 0.85rem;
  }
  th, td {
    border-bottom: 1px solid var(--line);
    padding: 8px 6px;
    text-align: right;
  }
  th:first-child, td:first-child { text-align: left; }
  th { color: var(--muted); font-weight: 500; }
  .pill {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 999px;
    font-size: 0.72rem;
    background: #243028;
    color: var(--green);
    border: 1px solid #355241;
  }
  .err { color: var(--danger); margin-top: 10px; font-size: 0.85rem; }
</style>
</head>
<body>
  <div class="wrap">
    <header>
      <h1>Portfolio Maximizer</h1>
      <p>
        Fake market data + two knapsack solvers. Greedy can take fractional shares;
        DP sticks to whole shares. Same budget, different rules — so profits aren’t a clean apples-to-apples score.
      </p>
    </header>

    <div class="grid">
      <aside class="panel">
        <div class="pill">localhost demo</div>
        <label>Budget ($)</label>
        <input id="budget" type="number" value="10000" min="100" step="100"/>
        <label>Stocks in market view</label>
        <input id="nview" type="number" value="40" min="5" max="200"/>
        <label>Seed</label>
        <input id="seed" type="number" value="42"/>
        <label>Benchmark sizes (comma sep)</label>
        <input id="sizes" type="text" value="10, 30, 60, 100"/>
        <label>Timing runs</label>
        <input id="runs" type="number" value="2" min="1" max="8"/>
        <button id="go">Run analysis</button>
        <p class="note">
          Tip: DP gets heavy with huge budgets (it scales with budget × n).
          Keep sizes modest if you want snappy charts.
        </p>
        <div id="err" class="err"></div>
      </aside>

      <main>
        <div class="stats" id="stats">
          <div class="stat"><span>Greedy profit</span><strong>—</strong></div>
          <div class="stat"><span>DP profit</span><strong>—</strong></div>
          <div class="stat"><span>Greedy last (ms)</span><strong>—</strong></div>
          <div class="stat"><span>DP last (ms)</span><strong>—</strong></div>
        </div>

        <div class="charts">
          <div class="panel chart-box">
            <h3>Runtime vs dataset size</h3>
            <canvas id="runtimeChart"></canvas>
          </div>
          <div class="panel chart-box">
            <h3>Expected profit (same run)</h3>
            <canvas id="profitChart"></canvas>
          </div>
          <div class="panel chart-box">
            <h3>Return vs volatility</h3>
            <canvas id="scatterChart"></canvas>
          </div>
          <div class="panel chart-box">
            <h3>Top greedy allocations</h3>
            <canvas id="allocChart"></canvas>
          </div>
        </div>

        <div class="panel" style="margin-top:14px">
          <h3 style="margin:0 0 6px;font-size:0.95rem">Benchmark table</h3>
          <table>
            <thead>
              <tr>
                <th>n</th><th>Greedy ms</th><th>Greedy $</th><th>DP ms</th><th>DP $</th>
              </tr>
            </thead>
            <tbody id="tbody"></tbody>
          </table>
        </div>
      </main>
    </div>
  </div>

<script>
const colors = {
  gold: "#d4a54a",
  green: "#5fbf7a",
  blue: "#6ea8d8",
  soft: "rgba(212,165,74,0.25)",
};

let runtimeChart, profitChart, scatterChart, allocChart;

function money(x) {
  return "$" + Number(x).toLocaleString(undefined, {maximumFractionDigits: 2});
}

function mkCharts() {
  const common = {
    responsive: true,
    plugins: { legend: { labels: { color: "#c9d4ca" } } },
    scales: {
      x: { ticks: { color: "#9aab9c" }, grid: { color: "rgba(45,59,50,0.6)" } },
      y: { ticks: { color: "#9aab9c" }, grid: { color: "rgba(45,59,50,0.6)" } },
    },
  };

  runtimeChart = new Chart(document.getElementById("runtimeChart"), {
    type: "line",
    data: { labels: [], datasets: [
      { label: "Greedy", data: [], borderColor: colors.gold, backgroundColor: colors.soft, tension: 0.25, fill: true, pointRadius: 4 },
      { label: "0/1 DP", data: [], borderColor: colors.blue, tension: 0.25, pointRadius: 4 },
    ]},
    options: { ...common, scales: { ...common.scales, y: { ...common.scales.y, title: { display: true, text: "ms", color: "#9aab9c" } } } },
  });

  profitChart = new Chart(document.getElementById("profitChart"), {
    type: "bar",
    data: { labels: [], datasets: [
      { label: "Greedy", data: [], backgroundColor: colors.gold },
      { label: "DP", data: [], backgroundColor: colors.blue },
    ]},
    options: common,
  });

  scatterChart = new Chart(document.getElementById("scatterChart"), {
    type: "scatter",
    data: { datasets: [{
      label: "stocks",
      data: [],
      backgroundColor: "rgba(95,191,122,0.75)",
      pointRadius: 5,
    }]},
    options: {
      ...common,
      scales: {
        x: { ...common.scales.x, title: { display: true, text: "volatility", color: "#9aab9c" } },
        y: { ...common.scales.y, title: { display: true, text: "expected return", color: "#9aab9c" } },
      },
    },
  });

  allocChart = new Chart(document.getElementById("allocChart"), {
    type: "doughnut",
    data: { labels: [], datasets: [{ data: [], backgroundColor: ["#d4a54a","#5fbf7a","#6ea8d8","#e07a5f","#a78bfa","#34d399","#f59e0b","#60a5fa"] }] },
    options: { plugins: { legend: { position: "bottom", labels: { color: "#c9d4ca", boxWidth: 12 } } } },
  });
}

function paint(data) {
  const rows = data.bench;
  const last = rows[rows.length - 1];

  const stats = document.getElementById("stats");
  stats.innerHTML = `
    <div class="stat"><span>Greedy profit</span><strong>${money(last.greedy_profit)}</strong></div>
    <div class="stat"><span>DP profit</span><strong>${money(last.dp_profit)}</strong></div>
    <div class="stat"><span>Greedy last (ms)</span><strong>${last.greedy_ms.toFixed(3)}</strong></div>
    <div class="stat"><span>DP last (ms)</span><strong>${last.dp_ms.toFixed(2)}</strong></div>
  `;

  runtimeChart.data.labels = rows.map(r => r.n);
  runtimeChart.data.datasets[0].data = rows.map(r => r.greedy_ms);
  runtimeChart.data.datasets[1].data = rows.map(r => r.dp_ms);
  runtimeChart.update();

  profitChart.data.labels = rows.map(r => "n=" + r.n);
  profitChart.data.datasets[0].data = rows.map(r => r.greedy_profit);
  profitChart.data.datasets[1].data = rows.map(r => r.dp_profit);
  profitChart.update();

  scatterChart.data.datasets[0].data = data.market.map(s => ({ x: s.vol, y: s.ret }));
  scatterChart.update();

  const top = data.alloc.slice(0, 8);
  allocChart.data.labels = top.map(s => s.ticker);
  allocChart.data.datasets[0].data = top.map(s => s.got);
  allocChart.update();

  document.getElementById("tbody").innerHTML = rows.map(r => `
    <tr>
      <td>${r.n}</td>
      <td>${r.greedy_ms.toFixed(4)}</td>
      <td>${r.greedy_profit.toFixed(2)}</td>
      <td>${r.dp_ms.toFixed(4)}</td>
      <td>${r.dp_profit.toFixed(2)}</td>
    </tr>
  `).join("");
}

async function run() {
  const btn = document.getElementById("go");
  const err = document.getElementById("err");
  err.textContent = "";
  btn.disabled = true;
  btn.textContent = "Working…";
  try {
    const body = {
      budget: Number(document.getElementById("budget").value),
      nview: Number(document.getElementById("nview").value),
      seed: Number(document.getElementById("seed").value),
      sizes: document.getElementById("sizes").value,
      runs: Number(document.getElementById("runs").value),
    };
    const res = await fetch("/api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "request failed");
    paint(data);
  } catch (e) {
    err.textContent = e.message;
  } finally {
    btn.disabled = false;
    btn.textContent = "Run analysis";
  }
}

mkCharts();
document.getElementById("go").onclick = run;
run();
</script>
</body>
</html>
"""


@app.get("/")
def home():
    return render_template_string(PAGE)


@app.post("/api/analyze")
def analyze():
    data = request.get_json(force=True) or {}
    try:
        budget = float(data.get("budget", 10000))
        nview = int(data.get("nview", 40))
        seed = int(data.get("seed", 42))
        runs = int(data.get("runs", 2))
        sizes_raw = str(data.get("sizes", "10,30,60,100"))
        sizes = [int(x.strip()) for x in sizes_raw.split(",") if x.strip()]
    except Exception:
        return jsonify({"error": "bad inputs"}), 400

    if budget <= 0 or nview < 1 or runs < 1 or not sizes:
        return jsonify({"error": "budget/n/runs/sizes look off"}), 400
    if max(sizes) > 500:
        return jsonify({"error": "keep sizes <= 500 for this demo"}), 400

    market = make_stocks(nview, seed)
    g_profit, alloc = greedy_pick(market, budget)

    bench = []
    for n in sizes:
        stocks = make_stocks(n, seed)
        g_ms, g_res = timed(lambda s=stocks: greedy_pick(s, budget)[0], runs=runs)
        d_ms, d_res = timed(lambda s=stocks: dp_pick(s, budget), runs=runs)
        # greedy_pick via timed returns profit only from lambda
        bench.append({
            "n": n,
            "greedy_ms": round(g_ms, 4),
            "greedy_profit": round(g_res, 4),
            "dp_ms": round(d_ms, 4),
            "dp_profit": round(d_res, 4),
        })

    return jsonify({
        "market": market,
        "alloc": alloc,
        "view_greedy_profit": g_profit,
        "bench": bench,
        "complexities": {
            "greedy": "O(n log n) time, O(n) extra space",
            "dp": "O(nW) time, O(W) extra space",
        },
    })


if __name__ == "__main__":
    # 0.0.0.0 so Cursor port forwarding / other hosts can reach it
    app.run(host="0.0.0.0", port=8742, debug=False)
