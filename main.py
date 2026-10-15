import os
import sys
import random
import time
from flask import Flask, jsonify, request, render_template_string

# Project 2 algorithms live in the daa-project-2 folder
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "daa-project-2"))
import network_routing as nr  # noqa: E402

app = Flask(__name__)
RF = 0.02


# ---------- Project 1: portfolio ----------
def make_stocks(n, seed=42):
    if n < 1:
        raise ValueError("need at least 1 stock")
    rng = random.Random(seed)
    out = []
    for i in range(n):
        price = round(rng.uniform(40, 320), 2)
        er = round(rng.uniform(0.04, 0.28), 4)
        vol = round(rng.uniform(0.07, 0.4), 4)
        profit = round(price * er, 4)
        out.append({
            "ticker": f"STK{i+1:03d}",
            "cost": price,
            "ret": er,
            "vol": vol,
            "sharpe": round((er - RF) / vol, 4),
            "profit": profit,
            "density": round(profit / price, 6),
        })
    return out


def greedy_pick(stocks, budget):
    ranked = sorted(stocks, key=lambda s: s["density"], reverse=True)
    left = budget
    total = 0.0
    picks = []
    for s in ranked:
        if left <= 1e-9:
            break
        if s["cost"] <= left + 1e-9:
            total += s["profit"]
            left -= s["cost"]
            picks.append({
                "ticker": s["ticker"], "cost": s["cost"], "profit": s["profit"],
                "qty": 1.0, "spent": s["cost"], "got": s["profit"], "frac": False,
            })
        else:
            frac = left / s["cost"]
            got = s["profit"] * frac
            picks.append({
                "ticker": s["ticker"], "cost": s["cost"], "profit": s["profit"],
                "qty": round(frac, 4), "spent": round(left, 2), "got": round(got, 4),
                "frac": True,
            })
            total += got
            left = 0.0
    return round(total, 4), picks, round(budget - left, 2)


def dp_pick(stocks, budget):
    W = int(budget)
    n = len(stocks)
    dp = [0.0] * (W + 1)
    keep = [set() for _ in range(n)]
    weights = []

    for i, s in enumerate(stocks):
        w = max(1, int(round(s["cost"])))
        weights.append(w)
        v = s["profit"]
        if w > W:
            continue
        for cap in range(W, w - 1, -1):
            cand = dp[cap - w] + v
            if cand > dp[cap]:
                dp[cap] = cand
                keep[i].add(cap)

    picks = []
    cap = W
    for i in range(n - 1, -1, -1):
        if cap in keep[i]:
            s = stocks[i]
            picks.append({
                "ticker": s["ticker"], "cost": s["cost"], "profit": s["profit"],
                "qty": 1.0, "spent": s["cost"], "got": s["profit"], "frac": False,
            })
            cap -= weights[i]
    picks.reverse()
    spent = round(sum(p["spent"] for p in picks), 2)
    return round(dp[W], 4), picks, spent


def timed(fn, runs=1):
    last = None
    t0 = time.perf_counter()
    for _ in range(runs):
        last = fn()
    ms = (time.perf_counter() - t0) / runs * 1000
    return ms, last


PAGE = r"""
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>DAA Projects</title>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=Fraunces:opsz,wght@9..144,600;9..144,700&display=swap" rel="stylesheet"/>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<style>
  :root {
    --bg:#10140f; --panel:#1a221c; --line:#2f3d33; --text:#e8efe6; --muted:#9aab9c;
    --gold:#d4a54a; --green:#5fbf7a; --blue:#6ea8d8; --coral:#e07a5f; --violet:#a78bfa;
  }
  *{box-sizing:border-box}
  body{
    margin:0; font-family:"IBM Plex Sans",system-ui,sans-serif; color:var(--text);
    background:radial-gradient(1000px 500px at 0% 0%,#243028,transparent 55%),
               radial-gradient(800px 400px at 100% 0%,#2a2418,transparent 50%), var(--bg);
  }
  .wrap{max-width:1100px;margin:0 auto;padding:24px 16px 56px}
  h1{font-family:Fraunces,Georgia,serif;font-size:clamp(1.7rem,4vw,2.4rem);margin:0 0 6px}
  .sub{color:var(--muted);margin:0 0 18px;max-width:70ch;line-height:1.45}
  .tabs{display:flex;gap:8px;margin-bottom:16px;flex-wrap:wrap}
  .tab{
    border:1px solid var(--line);background:#101612;color:var(--text);
    border-radius:12px;padding:12px 16px;cursor:pointer;font:inherit;text-align:left;min-width:180px
  }
  .tab small{display:block;color:var(--muted);font-size:.75rem;margin-top:2px}
  .tab.on{background:linear-gradient(180deg,#e0b45a,var(--gold));color:#1a1408;border-color:transparent}
  .tab.on small{color:#4a3a18}
  .panel{background:#161d18;border:1px solid var(--line);border-radius:14px;padding:14px}
  .controls{display:grid;gap:12px;margin-bottom:16px}
  .row{display:flex;flex-wrap:wrap;gap:8px;align-items:center}
  .lbl{color:var(--muted);font-size:.8rem;min-width:70px}
  .chip{
    border:1px solid var(--line);background:#101612;color:var(--text);
    border-radius:999px;padding:8px 14px;cursor:pointer;font:inherit
  }
  .chip.on{background:linear-gradient(180deg,#e0b45a,var(--gold));color:#1a1408;border-color:transparent;font-weight:600}
  button.go{
    border:0;border-radius:12px;padding:12px 18px;font:inherit;font-weight:600;cursor:pointer;
    background:linear-gradient(180deg,#e0b45a,var(--gold));color:#1a1408;margin-left:auto
  }
  button.go:disabled{opacity:.55;cursor:wait}
  .hidden{display:none !important}
  .vs{display:grid;grid-template-columns:1fr auto 1fr;gap:12px;margin-bottom:14px}
  @media(max-width:800px){.vs{grid-template-columns:1fr}}
  .card h2{margin:0 0 4px;font-size:1.05rem}
  .card .tag{font-size:.72rem;color:var(--muted);margin-bottom:10px}
  .big{font-size:1.55rem;font-weight:600;margin:2px 0 10px}
  .meta{display:grid;grid-template-columns:1fr 1fr;gap:8px;font-size:.85rem}
  .meta div{background:#101612;border:1px solid var(--line);border-radius:10px;padding:8px}
  .meta span{display:block;color:var(--muted);font-size:.72rem}
  .mid{align-self:center;text-align:center;min-width:120px;padding:10px}
  .mid .delta{font-size:1.2rem;font-weight:600}
  .mid .hint{color:var(--muted);font-size:.75rem;margin-top:4px}
  .gold{color:var(--gold)} .blue{color:var(--blue)} .coral{color:var(--coral)} .green{color:var(--green)} .violet{color:var(--violet)}
  .charts{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:14px}
  @media(max-width:800px){.charts{grid-template-columns:1fr}}
  .chart-box h3{margin:0 0 8px;font-size:.92rem}
  canvas{max-height:280px}
  table{width:100%;border-collapse:collapse;font-size:.82rem}
  th,td{padding:7px 6px;border-bottom:1px solid var(--line);text-align:right}
  th:first-child,td:first-child,th:nth-child(2),td:nth-child(2){text-align:left}
  th{color:var(--muted);font-weight:500}
  .frac{color:var(--coral);font-weight:600}
  .whole{color:var(--green)}
  .err{color:var(--coral);margin-top:8px}
  .why{margin-top:10px;color:var(--muted);font-size:.84rem;line-height:1.45}
  .two-tables{display:grid;grid-template-columns:1fr 1fr;gap:12px}
  @media(max-width:800px){.two-tables{grid-template-columns:1fr}}
  .status{
    margin-top:10px;padding:10px 12px;border-radius:10px;font-size:.86rem;
    background:#101612;border:1px dashed var(--line);color:var(--muted)
  }
  .status b{color:var(--text)}
  .three{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-bottom:14px}
  @media(max-width:800px){.three{grid-template-columns:1fr}}
</style>
</head>
<body>
<div class="wrap">
  <h1>DAA Projects</h1>
  <p class="sub">Two course projects in one place. Flip tabs — each one runs on its own.</p>

  <div class="tabs">
    <button type="button" class="tab on" data-tab="p1">
      Project 1
      <small>Portfolio Maximizer · knapsack</small>
    </button>
    <button type="button" class="tab" data-tab="p2">
      Project 2
      <small>Network Routing · shortest paths</small>
    </button>
  </div>

  <!-- ===================== PROJECT 1 ===================== -->
  <section id="tab-p1">
    <p class="sub">
      Same fake stocks + same budget. Greedy can buy a <b>slice</b> of a share.
      DP only buys <b>whole</b> shares. Tap any option — it re-runs automatically.
    </p>
    <div class="panel controls">
      <div class="row">
        <span class="lbl">Preset</span>
        <button type="button" class="chip on" data-preset="quick">Quick look</button>
        <button type="button" class="chip" data-preset="class">Class demo</button>
        <button type="button" class="chip" data-preset="tight">Tight budget</button>
      </div>
      <div class="row">
        <span class="lbl">Budget</span>
        <button type="button" class="chip bud" data-b="800">$800</button>
        <button type="button" class="chip bud on" data-b="1500">$1,500</button>
        <button type="button" class="chip bud" data-b="3000">$3,000</button>
        <button type="button" class="chip bud" data-b="8000">$8,000</button>
      </div>
      <div class="row">
        <span class="lbl">Stocks</span>
        <button type="button" class="chip stk" data-n="12">12</button>
        <button type="button" class="chip stk on" data-n="20">20</button>
        <button type="button" class="chip stk" data-n="35">35</button>
        <button type="button" class="chip stk" data-n="50">50</button>
        <button type="button" class="go" id="go1">Compare greedy vs DP</button>
      </div>
      <div class="status" id="status1">Showing results for: <b>—</b></div>
      <div class="err" id="err1"></div>
    </div>

    <div class="vs">
      <div class="panel card">
        <h2 class="gold">Greedy</h2>
        <div class="tag">Fractional knapsack · O(n log n)</div>
        <div class="big gold" id="gProfit">—</div>
        <div class="meta">
          <div><span>Spent</span><b id="gSpent">—</b></div>
          <div><span>Runtime</span><b id="gMs">—</b></div>
          <div><span>Picks</span><b id="gCount">—</b></div>
          <div><span>Fractional?</span><b id="gFrac">—</b></div>
        </div>
      </div>
      <div class="mid">
        <div class="delta" id="delta">vs</div>
        <div class="hint" id="deltaHint">profit gap</div>
        <div class="why" id="why"></div>
      </div>
      <div class="panel card">
        <h2 class="blue">Dynamic (0/1)</h2>
        <div class="tag">Whole shares only · O(nW)</div>
        <div class="big blue" id="dProfit">—</div>
        <div class="meta">
          <div><span>Spent</span><b id="dSpent">—</b></div>
          <div><span>Runtime</span><b id="dMs">—</b></div>
          <div><span>Picks</span><b id="dCount">—</b></div>
          <div><span>Fractional?</span><b>never</b></div>
        </div>
      </div>
    </div>

    <div class="charts">
      <div class="panel chart-box">
        <h3>Profit & spend side by side</h3>
        <canvas id="cmpChart"></canvas>
      </div>
      <div class="panel chart-box">
        <h3>Runtime (ms)</h3>
        <canvas id="timeChart"></canvas>
      </div>
    </div>

    <div class="two-tables">
      <div class="panel">
        <h3 style="margin:0 0 8px;font-size:.92rem" class="gold">What greedy bought</h3>
        <table>
          <thead><tr><th>Ticker</th><th>Type</th><th>Qty</th><th>Spent</th><th>Profit</th></tr></thead>
          <tbody id="gBody"></tbody>
        </table>
      </div>
      <div class="panel">
        <h3 style="margin:0 0 8px;font-size:.92rem" class="blue">What DP bought</h3>
        <table>
          <thead><tr><th>Ticker</th><th>Type</th><th>Qty</th><th>Spent</th><th>Profit</th></tr></thead>
          <tbody id="dBody"></tbody>
        </table>
      </div>
    </div>

    <div class="panel" style="margin-top:12px">
      <h3 style="margin:0 0 8px;font-size:.92rem">Where they disagree</h3>
      <div id="diffBox" class="why">Run a compare to see which tickers only one algorithm took.</div>
    </div>
  </section>

  <!-- ===================== PROJECT 2 ===================== -->
  <section id="tab-p2" class="hidden">
    <p class="sub">
      Fake road network (directed, sparse, E ≈ 3·V). Same graph for all three algorithms —
      Dijkstra array, Dijkstra heap, Bellman-Ford. Tap a size preset to re-run.
    </p>
    <div class="panel controls">
      <div class="row">
        <span class="lbl">Preset</span>
        <button type="button" class="chip on" data-rpreset="small">Small</button>
        <button type="button" class="chip" data-rpreset="medium">Medium</button>
        <button type="button" class="chip" data-rpreset="large">Large</button>
        <button type="button" class="go" id="go2">Run routing benchmark</button>
      </div>
      <div class="status" id="status2">Showing results for: <b>—</b></div>
      <div class="err" id="err2"></div>
    </div>

    <div class="three">
      <div class="panel card">
        <h2 class="gold">Dijkstra (array)</h2>
        <div class="tag">O(V² + E) · scan for min each time</div>
        <div class="big gold" id="rArray">—</div>
        <div class="meta"><div><span>Last size mean</span><b id="rArrayNote">ms</b></div></div>
      </div>
      <div class="panel card">
        <h2 class="blue">Dijkstra (heap)</h2>
        <div class="tag">O((V+E) log V) · binary heap</div>
        <div class="big blue" id="rHeap">—</div>
        <div class="meta"><div><span>Last size mean</span><b id="rHeapNote">ms</b></div></div>
      </div>
      <div class="panel card">
        <h2 class="violet">Bellman-Ford</h2>
        <div class="tag">O(V·E) · neg-cycle check</div>
        <div class="big violet" id="rBf">—</div>
        <div class="meta"><div><span>Last size mean</span><b id="rBfNote">ms</b></div></div>
      </div>
    </div>

    <div class="charts">
      <div class="panel chart-box">
        <h3>Runtime vs vertices</h3>
        <canvas id="routeChart"></canvas>
      </div>
      <div class="panel chart-box">
        <h3>Winner at largest V</h3>
        <canvas id="routeBar"></canvas>
      </div>
    </div>

    <div class="panel">
      <h3 style="margin:0 0 8px;font-size:.92rem">Benchmark table</h3>
      <table>
        <thead>
          <tr>
            <th>V</th><th>E</th>
            <th>Dijkstra array (ms)</th>
            <th>Dijkstra heap (ms)</th>
            <th>Bellman-Ford (ms)</th>
            <th>Fastest</th>
          </tr>
        </thead>
        <tbody id="rBody"></tbody>
      </table>
      <div class="why" id="rWhy" style="margin-top:10px"></div>
    </div>
  </section>
</div>

<script>
const presets = {
  quick:  { budget: 1500, n: 20 },
  class:  { budget: 3000, n: 35 },
  tight:  { budget: 800,  n: 12 },
};
const rPresets = {
  small:  { sizes: [40, 70, 100], trials: 1 },
  medium: { sizes: [50, 100, 200], trials: 2 },
  large:  { sizes: [50, 100, 200, 350], trials: 2 },
};

let cmpChart, timeChart, routeChart, routeBar;
let runId1 = 0, runId2 = 0;
let currentR = rPresets.small;
let p2Loaded = false;

function money(x){ return "$" + Number(x).toLocaleString(undefined,{maximumFractionDigits:2}); }
function setOn(group, el){
  document.querySelectorAll(group).forEach(b => b.classList.remove("on"));
  el.classList.add("on");
}
function selectedP1(){
  return {
    budget: Number(document.querySelector(".bud.on").dataset.b),
    n: Number(document.querySelector(".stk.on").dataset.n),
    seed: 42,
  };
}
function syncChips(budget, n){
  document.querySelectorAll(".bud").forEach(b => b.classList.toggle("on", Number(b.dataset.b) === budget));
  document.querySelectorAll(".stk").forEach(b => b.classList.toggle("on", Number(b.dataset.n) === n));
}

/* tabs */
document.querySelectorAll(".tab").forEach(btn => {
  btn.addEventListener("click", () => {
    setOn(".tab", btn);
    const id = btn.dataset.tab;
    document.getElementById("tab-p1").classList.toggle("hidden", id !== "p1");
    document.getElementById("tab-p2").classList.toggle("hidden", id !== "p2");
    if(id === "p2" && !p2Loaded){ run2(); }
  });
});

/* ---------- Project 1 ---------- */
document.querySelectorAll("[data-preset]").forEach(btn => {
  btn.addEventListener("click", () => {
    setOn("[data-preset]", btn);
    const p = presets[btn.dataset.preset];
    syncChips(p.budget, p.n);
    run1();
  });
});
document.querySelectorAll(".bud").forEach(btn => {
  btn.addEventListener("click", () => {
    setOn(".bud", btn);
    document.querySelectorAll("[data-preset]").forEach(b => b.classList.remove("on"));
    run1();
  });
});
document.querySelectorAll(".stk").forEach(btn => {
  btn.addEventListener("click", () => {
    setOn(".stk", btn);
    document.querySelectorAll("[data-preset]").forEach(b => b.classList.remove("on"));
    run1();
  });
});

function mkCharts1(){
  const axis = {
    plugins:{ legend:{ labels:{ color:"#c9d4ca" } } },
    scales:{
      x:{ ticks:{ color:"#9aab9c" }, grid:{ color:"rgba(47,61,51,.55)" } },
      y:{ ticks:{ color:"#9aab9c" }, grid:{ color:"rgba(47,61,51,.55)" } },
    }
  };
  cmpChart = new Chart(document.getElementById("cmpChart"), {
    type:"bar",
    data:{
      labels:["Expected profit","Cash spent"],
      datasets:[
        { label:"Greedy", data:[0,0], backgroundColor:"#d4a54a" },
        { label:"DP", data:[0,0], backgroundColor:"#6ea8d8" },
      ]
    },
    options: axis
  });
  timeChart = new Chart(document.getElementById("timeChart"), {
    type:"bar",
    data:{
      labels:["Greedy","DP"],
      datasets:[{ label:"ms", data:[0,0], backgroundColor:["#d4a54a","#6ea8d8"] }]
    },
    options:{ ...axis, plugins:{ legend:{ display:false } } }
  });
}

function rows(list){
  if(!list.length) return `<tr><td colspan="5">nothing picked</td></tr>`;
  return list.map(p => `
    <tr>
      <td>${p.ticker}</td>
      <td class="${p.frac ? "frac" : "whole"}">${p.frac ? "fraction" : "whole"}</td>
      <td>${p.qty}</td>
      <td>${money(p.spent)}</td>
      <td>${money(p.got)}</td>
    </tr>`).join("");
}

function paint1(d){
  document.getElementById("status1").innerHTML =
    `Showing results for: <b>${money(d.budget)}</b> budget · <b>${d.n}</b> stocks · ` +
    `<b>${d.greedy.picks.length}</b> greedy picks · <b>${d.dp.picks.length}</b> DP picks`;
  document.getElementById("gProfit").textContent = money(d.greedy.profit);
  document.getElementById("dProfit").textContent = money(d.dp.profit);
  document.getElementById("gSpent").textContent = money(d.greedy.spent);
  document.getElementById("dSpent").textContent = money(d.dp.spent);
  document.getElementById("gMs").textContent = d.greedy.ms.toFixed(3) + " ms";
  document.getElementById("dMs").textContent = d.dp.ms.toFixed(2) + " ms";
  document.getElementById("gCount").textContent = d.greedy.picks.length;
  document.getElementById("dCount").textContent = d.dp.picks.length;
  document.getElementById("gFrac").textContent = d.greedy.has_frac ? "yes — last pick sliced" : "no";

  const gap = d.greedy.profit - d.dp.profit;
  const el = document.getElementById("delta");
  if (Math.abs(gap) < 0.01) { el.textContent = "≈ same $"; el.className = "delta green"; }
  else if (gap > 0) { el.textContent = "+" + money(gap); el.className = "delta gold"; }
  else { el.textContent = money(gap); el.className = "delta blue"; }
  document.getElementById("deltaHint").textContent = gap >= 0 ? "greedy profit ahead" : "DP profit ahead";
  document.getElementById("why").innerHTML = d.blurb;

  cmpChart.data.datasets[0].data = [d.greedy.profit, d.greedy.spent];
  cmpChart.data.datasets[1].data = [d.dp.profit, d.dp.spent];
  cmpChart.update();
  timeChart.data.datasets[0].data = [d.greedy.ms, d.dp.ms];
  timeChart.update();
  document.getElementById("gBody").innerHTML = rows(d.greedy.picks);
  document.getElementById("dBody").innerHTML = rows(d.dp.picks);

  const onlyG = d.diff.only_greedy, onlyD = d.diff.only_dp, both = d.diff.both;
  document.getElementById("diffBox").innerHTML = `
    <b class="green">${both.length}</b> tickers in both ·
    <b class="gold">${onlyG.length}</b> only greedy (${onlyG.join(", ") || "—"}) ·
    <b class="blue">${onlyD.length}</b> only DP (${onlyD.join(", ") || "—"})
    <br><br>${d.diff.note}`;
}

async function run1(){
  const btn = document.getElementById("go1");
  const err = document.getElementById("err1");
  const opts = selectedP1();
  const myId = ++runId1;
  err.textContent = "";
  btn.disabled = true;
  btn.textContent = "Comparing…";
  document.getElementById("status1").innerHTML = `Running <b>${money(opts.budget)}</b> · <b>${opts.n}</b> stocks…`;
  try{
    const res = await fetch("/api/compare?t=" + Date.now(), {
      method:"POST",
      headers:{ "Content-Type":"application/json", "Cache-Control":"no-store" },
      cache:"no-store",
      body: JSON.stringify(opts)
    });
    const data = await res.json();
    if(!res.ok) throw new Error(data.error || "failed");
    if(myId !== runId1) return;
    paint1(data);
  }catch(e){
    if(myId === runId1) err.textContent = e.message;
  }finally{
    if(myId === runId1){ btn.disabled = false; btn.textContent = "Compare greedy vs DP"; }
  }
}

/* ---------- Project 2 ---------- */
document.querySelectorAll("[data-rpreset]").forEach(btn => {
  btn.addEventListener("click", () => {
    setOn("[data-rpreset]", btn);
    currentR = rPresets[btn.dataset.rpreset];
    run2();
  });
});

function mkCharts2(){
  const axis = {
    plugins:{ legend:{ labels:{ color:"#c9d4ca" } } },
    scales:{
      x:{ ticks:{ color:"#9aab9c" }, grid:{ color:"rgba(47,61,51,.55)" } },
      y:{ ticks:{ color:"#9aab9c" }, grid:{ color:"rgba(47,61,51,.55)" } },
    }
  };
  routeChart = new Chart(document.getElementById("routeChart"), {
    type:"line",
    data:{
      labels:[],
      datasets:[
        { label:"Dijkstra array", data:[], borderColor:"#d4a54a", tension:.25, pointRadius:4 },
        { label:"Dijkstra heap", data:[], borderColor:"#6ea8d8", tension:.25, pointRadius:4 },
        { label:"Bellman-Ford", data:[], borderColor:"#a78bfa", tension:.25, pointRadius:4 },
      ]
    },
    options:{ ...axis, scales:{ ...axis.scales, y:{ ...axis.scales.y, title:{ display:true, text:"ms", color:"#9aab9c" } } } }
  });
  routeBar = new Chart(document.getElementById("routeBar"), {
    type:"bar",
    data:{
      labels:["Array","Heap","Bellman-Ford"],
      datasets:[{ data:[0,0,0], backgroundColor:["#d4a54a","#6ea8d8","#a78bfa"] }]
    },
    options:{ ...axis, plugins:{ legend:{ display:false } } }
  });
}

function paint2(d){
  p2Loaded = true;
  const last = d.rows[d.rows.length - 1];
  document.getElementById("status2").innerHTML =
    `Showing results for: V up to <b>${last.V}</b> · E ≈ <b>${last.E}</b> · trials <b>${d.trials}</b>`;
  document.getElementById("rArray").textContent = last.array_ms.toFixed(2) + " ms";
  document.getElementById("rHeap").textContent = last.heap_ms.toFixed(2) + " ms";
  document.getElementById("rBf").textContent = last.bf_ms.toFixed(2) + " ms";
  document.getElementById("rArrayNote").textContent = "at V=" + last.V;
  document.getElementById("rHeapNote").textContent = "at V=" + last.V;
  document.getElementById("rBfNote").textContent = "at V=" + last.V;

  routeChart.data.labels = d.rows.map(r => r.V);
  routeChart.data.datasets[0].data = d.rows.map(r => r.array_ms);
  routeChart.data.datasets[1].data = d.rows.map(r => r.heap_ms);
  routeChart.data.datasets[2].data = d.rows.map(r => r.bf_ms);
  routeChart.update();
  routeBar.data.datasets[0].data = [last.array_ms, last.heap_ms, last.bf_ms];
  routeBar.update();

  document.getElementById("rBody").innerHTML = d.rows.map(r => {
    const times = { array: r.array_ms, heap: r.heap_ms, bf: r.bf_ms };
    const best = Object.entries(times).sort((a,b)=>a[1]-b[1])[0][0];
    const label = best === "array" ? "array" : best === "heap" ? "heap" : "Bellman-Ford";
    return `<tr>
      <td>${r.V}</td><td>${r.E}</td>
      <td>${r.array_ms.toFixed(3)}</td>
      <td>${r.heap_ms.toFixed(3)}</td>
      <td>${r.bf_ms.toFixed(3)}</td>
      <td>${label}</td>
    </tr>`;
  }).join("");

  document.getElementById("rWhy").innerHTML = d.blurb;
}

async function run2(){
  const btn = document.getElementById("go2");
  const err = document.getElementById("err2");
  const myId = ++runId2;
  err.textContent = "";
  btn.disabled = true;
  btn.textContent = "Benchmarking…";
  document.getElementById("status2").innerHTML = `Running sizes <b>${currentR.sizes.join(", ")}</b>…`;
  try{
    const res = await fetch("/api/routing?t=" + Date.now(), {
      method:"POST",
      headers:{ "Content-Type":"application/json", "Cache-Control":"no-store" },
      cache:"no-store",
      body: JSON.stringify(currentR)
    });
    const data = await res.json();
    if(!res.ok) throw new Error(data.error || "failed");
    if(myId !== runId2) return;
    paint2(data);
  }catch(e){
    if(myId === runId2) err.textContent = e.message;
  }finally{
    if(myId === runId2){ btn.disabled = false; btn.textContent = "Run routing benchmark"; }
  }
}

mkCharts1();
mkCharts2();
document.getElementById("go1").addEventListener("click", run1);
document.getElementById("go2").addEventListener("click", run2);
run1();
</script>
</body>
</html>
"""


@app.after_request
def no_cache(resp):
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    return resp


@app.get("/")
def home():
    return render_template_string(PAGE)


@app.post("/api/compare")
def compare():
    data = request.get_json(force=True) or {}
    try:
        budget = float(data.get("budget", 1500))
        n = int(data.get("n", 20))
        seed = int(data.get("seed", 42))
    except Exception:
        return jsonify({"error": "bad inputs"}), 400

    if budget < 100 or n < 5 or n > 80:
        return jsonify({"error": "use budget >= 100 and stocks between 5 and 80"}), 400

    stocks = make_stocks(n, seed)
    g_ms, g_pack = timed(lambda: greedy_pick(stocks, budget), runs=1)
    d_ms, d_pack = timed(lambda: dp_pick(stocks, budget), runs=1)
    g_profit, g_picks, g_spent = g_pack
    d_profit, d_picks, d_spent = d_pack

    g_set = {p["ticker"] for p in g_picks}
    d_set = {p["ticker"] for p in d_picks}
    only_g = sorted(g_set - d_set)
    only_d = sorted(d_set - g_set)
    both = sorted(g_set & d_set)
    has_frac = any(p["frac"] for p in g_picks)
    gap = round(g_profit - d_profit, 4)

    if has_frac and gap > 0.01:
        blurb = (
            f"Greedy edged ahead by {gap:.2f} because it sliced a share "
            f"({[p['ticker'] for p in g_picks if p['frac']][0]}). "
            "DP couldn’t take that leftover cash as a partial share."
        )
    elif abs(gap) <= 0.01:
        blurb = (
            "Profits landed nearly the same this round — still different rules: "
            "greedy is allowed fractions, DP is not."
        )
    else:
        blurb = f"Gap is {gap:.2f}. Different pick sets can show up even when totals look close."

    note = (
        "Greedy sorts by profit-per-dollar and fills fast. "
        "DP searches whole-share combos for the best total under the budget."
    )
    if only_g or only_d:
        note += " The ticker lists below show where the portfolios actually diverge."

    return jsonify({
        "budget": budget,
        "n": n,
        "seed": seed,
        "greedy": {
            "profit": g_profit, "spent": g_spent, "ms": round(g_ms, 4),
            "picks": g_picks, "has_frac": has_frac,
        },
        "dp": {
            "profit": d_profit, "spent": d_spent, "ms": round(d_ms, 4),
            "picks": d_picks,
        },
        "diff": {
            "only_greedy": only_g, "only_dp": only_d, "both": both, "note": note,
        },
        "blurb": blurb,
    })


@app.post("/api/routing")
def routing():
    data = request.get_json(force=True) or {}
    try:
        sizes = [int(x) for x in data.get("sizes", [40, 70, 100])]
        trials = int(data.get("trials", 1))
        edge_factor = int(data.get("edge_factor", 3))
        seed = int(data.get("seed", 42))
    except Exception:
        return jsonify({"error": "bad inputs"}), 400

    if not sizes or min(sizes) < 5 or max(sizes) > 500 or trials < 1 or trials > 5:
        return jsonify({"error": "keep V in 5..500 and trials in 1..5"}), 400

    # quiet console spam from nr.run_benchmarks by calling pieces ourselves
    rows = []
    source = 0
    for idx, V in enumerate(sizes):
        E = edge_factor * V
        graph = nr.generate_random_directed_graph(V, E, seed=seed + idx)
        array_times, heap_times, bf_times = [], [], []
        for _ in range(trials):
            t, dist_a = nr._time_call(nr.dijkstra_array, graph, source)
            array_times.append(t)
            t, dist_h = nr._time_call(nr.dijkstra_heap, graph, source)
            heap_times.append(t)
            t, (dist_b, neg) = nr._time_call(nr.bellman_ford, graph, source)
            bf_times.append(t)
            if neg:
                return jsonify({"error": "negative cycle on positive graph — bug"}), 500
            if dist_a != dist_h or dist_a != dist_b:
                return jsonify({"error": "algorithms disagreed on distances"}), 500

        rows.append({
            "V": V,
            "E": E,
            "array_ms": round(sum(array_times) / trials, 4),
            "heap_ms": round(sum(heap_times) / trials, 4),
            "bf_ms": round(sum(bf_times) / trials, 4),
        })

    last = rows[-1]
    order = sorted(
        [("array", last["array_ms"]), ("heap", last["heap_ms"]), ("bf", last["bf_ms"])],
        key=lambda x: x[1],
    )
    winner = {"array": "Dijkstra (array)", "heap": "Dijkstra (heap)", "bf": "Bellman-Ford"}[order[0][0]]
    blurb = (
        f"At V={last['V']} the fastest was <b>{winner}</b> "
        f"({order[0][1]:.2f} ms). Heap Dijkstra usually wins on sparse roads; "
        "Bellman-Ford grows roughly with V·E; array Dijkstra pays O(V²)."
    )

    return jsonify({"trials": trials, "edge_factor": edge_factor, "rows": rows, "blurb": blurb})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8742, debug=False)
