import heapq
import math
import os
import sys
import random
import time
from collections import deque
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


def rebuild_path(parent, target):
    if target < 0 or target >= len(parent):
        return []
    path = []
    cur = target
    seen = set()
    while cur != -1 and cur not in seen:
        seen.add(cur)
        path.append(cur)
        cur = parent[cur]
    path.reverse()
    return path


def path_cost(graph, path):
    if len(path) < 2:
        return 0
    total = 0
    for a, b in zip(path, path[1:]):
        options = [w for v, w in graph[a] if v == b]
        if not options:
            return None
        total += min(options)
    return total


_DISTRICTS = [
    "Harbor", "Midtown", "Heights", "Market", "Campus",
    "Airport", "Oldtown", "Riverside", "Parkside", "Station",
]


def generate_city_map(side, seed):
    """
    Build a block-grid city:
      - local streets (cheap per block, many hops)
      - highways (one hop, but pricey) so BFS loves them and Dijkstra often doesn't
    """
    rng = random.Random(seed)
    side = max(3, int(side))
    V = side * side
    graph = {i: [] for i in range(V)}

    def idx(r, c):
        return r * side + c

    def add_edge(u, v, w):
        graph[u].append((v, w))
        graph[v].append((u, w))

    # city streets along the grid
    for r in range(side):
        for c in range(side):
            u = idx(r, c)
            if c + 1 < side:
                add_edge(u, idx(r, c + 1), rng.randint(2, 4))
            if r + 1 < side:
                add_edge(u, idx(r + 1, c), rng.randint(2, 4))

    # arterial highways: skip blocks in one hop, but cost more than the street detour
    jumps = [(0, 2), (0, 3), (2, 0), (3, 0), (2, 2), (3, 1), (1, 3)]
    for _ in range(side + 2):
        r = rng.randrange(side)
        c = rng.randrange(side)
        dr, dc = rng.choice(jumps)
        r2, c2 = r + dr, c + dc
        if 0 <= r2 < side and 0 <= c2 < side:
            hops = abs(dr) + abs(dc)
            # pricier than walking the blocks → Dijkstra prefers streets; BFS prefers 1 hop
            hwy = hops * 3 + rng.randint(5, 10)
            add_edge(idx(r, c), idx(r2, c2), hwy)

    nodes = []
    for i in range(V):
        r, c = divmod(i, side)
        # slight lane jitter so it feels like a real street grid
        nodes.append({
            "id": i,
            "name": f"{_DISTRICTS[(r + c) % len(_DISTRICTS)]} {chr(65+c)}{r+1}",
            "x": (c + 0.5 + rng.uniform(-0.08, 0.08)) / side,
            "y": (r + 0.5 + rng.uniform(-0.08, 0.08)) / side,
            "row": r,
            "col": c,
        })

    source, target = 0, V - 1
    return graph, nodes, source, target, side


def dijkstra_trace(graph, source):
    V = len(graph)
    dist = [float("inf")] * V
    parent = [-1] * V
    order = []
    seen = set()
    dist[source] = 0.0
    pq = [(0.0, source)]
    while pq:
        d, u = heapq.heappop(pq)
        if u in seen:
            continue
        seen.add(u)
        order.append(u)
        for v, w in graph[u]:
            nd = d + w
            if nd < dist[v]:
                dist[v] = nd
                parent[v] = u
                heapq.heappush(pq, (nd, v))
    return dist, parent, order


def bfs_trace(graph, source, target):
    """Fewest streets (hops), ignores road lengths — often a different route."""
    V = len(graph)
    parent = [-1] * V
    order = []
    q = deque([source])
    seen = {source}
    while q:
        u = q.popleft()
        order.append(u)
        if u == target:
            break
        # light edges first only for stable animation; hop count still BFS
        nbrs = sorted(graph[u], key=lambda vw: vw[1])
        for v, _w in nbrs:
            if v not in seen:
                seen.add(v)
                parent[v] = u
                q.append(v)
    for i in range(V):
        if i not in seen:
            continue
        if i not in order:
            order.append(i)
    return parent, order


def greedy_geo_trace(graph, source, target, nodes):
    """Greedy best-first: head toward the destination geographically (can be suboptimal)."""
    parent = [-1] * len(graph)
    order = []
    seen = set()
    pos = {n["id"]: (n["x"], n["y"]) for n in nodes}

    def h(i):
        x, y = pos[i]
        tx, ty = pos[target]
        return (x - tx) ** 2 + (y - ty) ** 2

    pq = [(h(source), source)]
    while pq:
        _, u = heapq.heappop(pq)
        if u in seen:
            continue
        seen.add(u)
        order.append(u)
        if u == target:
            break
        for v, _w in sorted(graph[u], key=lambda vw: h(vw[0])):
            if v in seen:
                continue
            if parent[v] == -1 and v != source:
                parent[v] = u
            heapq.heappush(pq, (h(v), v))
    return parent, order


def build_map_view(side, seed):
    """
    Same city for 3 routing rules that intentionally pick different paths:
      - Dijkstra: cheapest total distance
      - BFS: fewest road segments
      - Greedy: always aim straight at the destination
    """
    graph, nodes, source, target, side = generate_city_map(side, seed)
    dist, p_dijk, ord_dijk = dijkstra_trace(graph, source)
    p_bfs, ord_bfs = bfs_trace(graph, source, target)
    p_greed, ord_greed = greedy_geo_trace(graph, source, target, nodes)

    path_d = rebuild_path(p_dijk, target)
    path_b = rebuild_path(p_bfs, target)
    path_g = rebuild_path(p_greed, target)

    edges = []
    for u in range(len(graph)):
        for v, w in graph[u]:
            if u < v:  # draw once; still directed? city is bidirectional — store both for viz arrows one way
                edges.append({"u": u, "v": v, "w": w})

    # for animation arrows keep both directions as separate edges
    edges = []
    for u in range(len(graph)):
        for v, w in graph[u]:
            edges.append({"u": u, "v": v, "w": w})

    return {
        "V": len(graph),
        "E": len(edges),
        "side": side,
        "source": source,
        "target": target,
        "dist": None if dist[target] == float("inf") else round(dist[target], 2),
        "path": path_d,
        "nodes": nodes,
        "edges": edges,
        "algos": {
            "array": {
                "label": "Dijkstra · shortest distance",
                "visit_order": ord_dijk,
                "path": path_d,
                "metric": f"cost {path_cost(graph, path_d)} · {max(0,len(path_d)-1)} hops",
            },
            "heap": {
                "label": "BFS · fewest streets",
                "visit_order": ord_bfs,
                "path": path_b,
                "metric": f"cost {path_cost(graph, path_b)} · {max(0,len(path_b)-1)} hops",
            },
            "bf": {
                "label": "Greedy · head for destination",
                "visit_order": ord_greed,
                "path": path_g,
                "metric": f"cost {path_cost(graph, path_g)} · {max(0,len(path_g)-1)} hops",
            },
        },
    }


PAGE = r"""
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>DAA Projects</title>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=Fraunces:opsz,wght@9..144,600;9..144,700&display=swap" rel="stylesheet"/>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/cytoscape@3.30.4/dist/cytoscape.min.js"></script>
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
  .howto{
    display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin:0 0 16px
  }
  @media(max-width:800px){.howto{grid-template-columns:1fr}}
  .howto .step{
    background:#141b16;border:1px solid var(--line);border-radius:12px;padding:12px 14px
  }
  .howto .num{
    display:inline-block;width:22px;height:22px;border-radius:50%;
    background:var(--gold);color:#1a1408;font-size:.75rem;font-weight:700;
    text-align:center;line-height:22px;margin-right:6px
  }
  .howto strong{display:block;margin:6px 0 4px}
  .howto p{margin:0;color:var(--muted);font-size:.82rem;line-height:1.4}
  .explain{
    display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:16px
  }
  .explain.three-col{grid-template-columns:1fr 1fr 1fr}
  @media(max-width:900px){.explain,.explain.three-col{grid-template-columns:1fr}}
  .explain .box{background:#141b16;border:1px solid var(--line);border-radius:12px;padding:12px 14px}
  .explain h3{margin:0 0 6px;font-size:.95rem}
  .explain p{margin:0;color:var(--muted);font-size:.84rem;line-height:1.45}
  .tip{
    margin:0 0 14px;padding:12px 14px;border-radius:12px;
    background:rgba(212,165,74,.08);border:1px solid rgba(212,165,74,.35);
    color:var(--text);font-size:.88rem;line-height:1.45
  }
  .tip b{color:var(--gold)}
  .legend-note{color:var(--muted);font-size:.8rem;margin:6px 0 0;line-height:1.4}
  .map-wrap{margin-bottom:14px}
  .map-top{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin-bottom:10px}
  .map-top h3{margin:0;font-size:1rem;flex:1}
  .map-grid{
    display:grid;grid-template-columns:repeat(3,1fr);gap:10px
  }
  @media(max-width:1000px){.map-grid{grid-template-columns:1fr}}
  .map-card{background:#0e1512;border:1px solid var(--line);border-radius:12px;padding:8px}
  .map-card h4{margin:0 0 6px;font-size:.88rem}
  .map-card .cy{
    width:100%;height:min(340px,55vw);border-radius:10px;
    background:linear-gradient(160deg,#0b1220 0%,#101a14 55%,#0d1518 100%);
    border:1px solid var(--line); overflow:hidden
  }
  .map-legend{display:flex;flex-wrap:wrap;gap:12px;margin-top:10px;font-size:.8rem;color:var(--muted)}
  .map-legend i{
    display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:5px;vertical-align:middle
  }
  .swatch{display:inline-block;width:18px;height:3px;margin-right:5px;vertical-align:middle;border-radius:2px}
  .lib-credit{font-size:.72rem;color:#6f7f72;margin-top:6px}
</style>
</head>
<body>
<div class="wrap">
  <h1>DAA Projects</h1>
  <p class="sub">
    Two algorithm demos you can click through. Pick a project tab, tap a simple option,
    and watch the results update — no coding needed.
  </p>

  <div class="tabs">
    <button type="button" class="tab on" data-tab="p1">
      Project 1 · Investing
      <small>Which stocks to buy with a budget?</small>
    </button>
    <button type="button" class="tab" data-tab="p2">
      Project 2 · Maps / Roads
      <small>Which route-finding method is fastest?</small>
    </button>
  </div>

  <!-- ===================== PROJECT 1 ===================== -->
  <section id="tab-p1">
    <div class="tip">
      <b>What this shows:</b> You have fake money and a list of fake stocks.
      Two algorithms try to earn the most expected profit. They use <b>different rules</b>,
      so their answers can differ — that’s the point.
    </div>

    <div class="howto">
      <div class="step"><span class="num">1</span><strong>Pick how hard it is</strong><p>Start with “Quick look”. Change money or stock count if you want.</p></div>
      <div class="step"><span class="num">2</span><strong>It runs by itself</strong><p>Every tap re-runs both algorithms on the same data.</p></div>
      <div class="step"><span class="num">3</span><strong>Read the cards</strong><p>Gold = Greedy. Blue = Dynamic Programming. Middle number = profit gap.</p></div>
    </div>

    <div class="explain">
      <div class="box">
        <h3 class="gold">Greedy (fast &amp; flexible)</h3>
        <p>Sorts stocks by “profit per dollar”, then buys the best ones first.
        Allowed to buy a <b>fraction</b> of the last share if money runs out mid-buy.
        Usually very fast.</p>
      </div>
      <div class="box">
        <h3 class="blue">Dynamic Programming (strict)</h3>
        <p>Only buys <b>whole</b> shares — all or nothing for each stock.
        Checks combinations carefully for the best total under the budget.
        Slower, but follows the stricter rule.</p>
      </div>
    </div>

    <div class="panel controls">
      <div class="row">
        <span class="lbl">Try this</span>
        <button type="button" class="chip on" data-preset="quick">Quick look</button>
        <button type="button" class="chip" data-preset="class">Classroom demo</button>
        <button type="button" class="chip" data-preset="tight">Tight money</button>
      </div>
      <div class="row">
        <span class="lbl">Your money</span>
        <button type="button" class="chip bud" data-b="800">$800</button>
        <button type="button" class="chip bud on" data-b="1500">$1,500</button>
        <button type="button" class="chip bud" data-b="3000">$3,000</button>
        <button type="button" class="chip bud" data-b="8000">$8,000</button>
      </div>
      <div class="row">
        <span class="lbl"># of stocks</span>
        <button type="button" class="chip stk" data-n="12">12</button>
        <button type="button" class="chip stk on" data-n="20">20</button>
        <button type="button" class="chip stk" data-n="35">35</button>
        <button type="button" class="chip stk" data-n="50">50</button>
        <button type="button" class="go" id="go1">Run comparison</button>
      </div>
      <p class="legend-note">Tip: “Tight money” makes the difference easier to see, because leftover cash matters more.</p>
      <div class="status" id="status1">Waiting to run…</div>
      <div class="err" id="err1"></div>
    </div>

    <div class="vs">
      <div class="panel card">
        <h2 class="gold">Greedy result</h2>
        <div class="tag">Can buy partial shares · usually fastest</div>
        <div class="big gold" id="gProfit">—</div>
        <div class="meta">
          <div><span>Money used</span><b id="gSpent">—</b></div>
          <div><span>Time taken</span><b id="gMs">—</b></div>
          <div><span>Stocks chosen</span><b id="gCount">—</b></div>
          <div><span>Used a fraction?</span><b id="gFrac">—</b></div>
        </div>
      </div>
      <div class="mid">
        <div class="delta" id="delta">vs</div>
        <div class="hint" id="deltaHint">difference in expected profit</div>
        <div class="why" id="why"></div>
      </div>
      <div class="panel card">
        <h2 class="blue">DP result</h2>
        <div class="tag">Whole shares only · slower but strict</div>
        <div class="big blue" id="dProfit">—</div>
        <div class="meta">
          <div><span>Money used</span><b id="dSpent">—</b></div>
          <div><span>Time taken</span><b id="dMs">—</b></div>
          <div><span>Stocks chosen</span><b id="dCount">—</b></div>
          <div><span>Used a fraction?</span><b>no (not allowed)</b></div>
        </div>
      </div>
    </div>

    <div class="charts">
      <div class="panel chart-box">
        <h3>How much profit &amp; cash each used</h3>
        <canvas id="cmpChart"></canvas>
        <p class="legend-note">Taller profit bar = better expected return under that algorithm’s rules.</p>
      </div>
      <div class="panel chart-box">
        <h3>How long each took</h3>
        <canvas id="timeChart"></canvas>
        <p class="legend-note">Lower is faster. Greedy is almost always quicker.</p>
      </div>
    </div>

    <div class="two-tables">
      <div class="panel">
        <h3 style="margin:0 0 8px;font-size:.92rem" class="gold">Greedy shopping list</h3>
        <p class="legend-note" style="margin-top:0;margin-bottom:8px">“fraction” means it bought only part of that share.</p>
        <table>
          <thead><tr><th>Stock</th><th>Buy type</th><th>Amount</th><th>Paid</th><th>Expected profit</th></tr></thead>
          <tbody id="gBody"></tbody>
        </table>
      </div>
      <div class="panel">
        <h3 style="margin:0 0 8px;font-size:.92rem" class="blue">DP shopping list</h3>
        <p class="legend-note" style="margin-top:0;margin-bottom:8px">Every row is a full share (no partial buys).</p>
        <table>
          <thead><tr><th>Stock</th><th>Buy type</th><th>Amount</th><th>Paid</th><th>Expected profit</th></tr></thead>
          <tbody id="dBody"></tbody>
        </table>
      </div>
    </div>

    <div class="panel" style="margin-top:12px">
      <h3 style="margin:0 0 8px;font-size:.92rem">Did they pick the same stocks?</h3>
      <div id="diffBox" class="why">Run a comparison to see overlaps and differences.</div>
    </div>
  </section>

  <!-- ===================== PROJECT 2 ===================== -->
  <section id="tab-p2" class="hidden">
    <div class="tip">
      <b>What this shows:</b> A real-looking <b>city street grid</b> (cheap local streets + pricey highway shortcuts).
      Three routing rules run on that <b>same city</b> and usually pick <b>different cyan routes</b>:
      Dijkstra minimizes distance, BFS minimizes number of streets, Greedy aims straight at the destination.
      Timing cards below still race Array/Heap Dijkstra vs Bellman-Ford on speed.
    </div>

    <div class="howto">
      <div class="step"><span class="num">1</span><strong>Pick a city size</strong><p>Small / Medium / Large grows the street grid.</p></div>
      <div class="step"><span class="num">2</span><strong>Compare the three routes</strong><p>Same START→END. Cyan paths often differ — that’s intentional.</p></div>
      <div class="step"><span class="num">3</span><strong>Read the speed race</strong><p>Charts still show which shortest-path code runs fastest.</p></div>
    </div>

    <div class="explain three-col">
      <div class="box">
        <h3 class="gold">Dijkstra · array</h3>
        <p>Each step searches the whole list for the next closest city. Simple idea, gets slower as the map grows (about V²).</p>
      </div>
      <div class="box">
        <h3 class="blue">Dijkstra · heap</h3>
        <p>Same Dijkstra idea, but uses a priority queue so “who’s next?” is cheap. Great for road-like sparse maps.</p>
      </div>
      <div class="box">
        <h3 class="violet">Bellman-Ford</h3>
        <p>Relaxes every road many times. Can handle weird negative weights (we don’t use those here). Usually slower on big maps.</p>
      </div>
    </div>

    <div class="panel controls">
      <div class="row">
        <span class="lbl">Map size</span>
        <button type="button" class="chip on" data-rpreset="small">Small (fast)</button>
        <button type="button" class="chip" data-rpreset="medium">Medium</button>
        <button type="button" class="chip" data-rpreset="large">Large (slower)</button>
        <button type="button" class="go" id="go2">Run speed test</button>
      </div>
      <p class="legend-note">V = number of cities/junctions. E = number of one-way roads (about 3×V here).</p>
      <div class="status" id="status2">Waiting to run…</div>
      <div class="err" id="err2"></div>
    </div>

    <div class="panel map-wrap">
      <div class="map-top">
        <h3>Same city map · three algorithms exploring it</h3>
        <button type="button" class="chip" id="mapPrev">◀ smaller</button>
        <button type="button" class="chip on" id="mapPlay">▶ play growth</button>
        <button type="button" class="chip" id="mapNext">bigger ▶</button>
      </div>
      <div class="map-grid">
        <div class="map-card">
          <h4 class="gold">Dijkstra · shortest distance</h4>
          <div class="cy" id="cyArray"></div>
          <p class="legend-note" id="metricArray" style="margin-top:6px">—</p>
        </div>
        <div class="map-card">
          <h4 class="blue">BFS · fewest streets</h4>
          <div class="cy" id="cyHeap"></div>
          <p class="legend-note" id="metricHeap" style="margin-top:6px">—</p>
        </div>
        <div class="map-card">
          <h4 class="violet">Greedy · head for destination</h4>
          <div class="cy" id="cyBf"></div>
          <p class="legend-note" id="metricBf" style="margin-top:6px">—</p>
        </div>
      </div>
      <div class="map-legend">
        <span><i style="background:#3dd68c"></i>Start (NW)</span>
        <span><i style="background:#ff6b6b"></i>Destination (SE)</span>
        <span><span class="swatch" style="background:#3d4f5f"></span>City streets / highways</span>
        <span><span class="swatch" style="background:#f0c14b"></span>Explored</span>
        <span><span class="swatch" style="background:#4cc9f0"></span>Chosen route (often different!)</span>
      </div>
      <p class="legend-note" id="mapCaption">Run a speed test — one city, three routing rules.</p>
      <p class="lib-credit">City maps via <b>Cytoscape.js</b>. Highways are short hops but expensive, so BFS and Dijkstra disagree on purpose.</p>
    </div>

    <div class="three">
      <div class="panel card">
        <h2 class="gold">Array Dijkstra</h2>
        <div class="tag">Simple scan · slower on big maps</div>
        <div class="big gold" id="rArray">—</div>
        <div class="meta"><div><span>Time on biggest map</span><b id="rArrayNote">—</b></div></div>
      </div>
      <div class="panel card">
        <h2 class="blue">Heap Dijkstra</h2>
        <div class="tag">Priority queue · usually the winner</div>
        <div class="big blue" id="rHeap">—</div>
        <div class="meta"><div><span>Time on biggest map</span><b id="rHeapNote">—</b></div></div>
      </div>
      <div class="panel card">
        <h2 class="violet">Bellman-Ford</h2>
        <div class="tag">Checks all roads repeatedly</div>
        <div class="big violet" id="rBf">—</div>
        <div class="meta"><div><span>Time on biggest map</span><b id="rBfNote">—</b></div></div>
      </div>
    </div>

    <div class="charts">
      <div class="panel chart-box">
        <h3>Time as the map gets bigger</h3>
        <canvas id="routeChart"></canvas>
        <p class="legend-note">X-axis = cities (V). Y-axis = milliseconds. Steeper line = slows down faster.</p>
      </div>
      <div class="panel chart-box">
        <h3>Final race (biggest map only)</h3>
        <canvas id="routeBar"></canvas>
        <p class="legend-note">Shortest bar wins that round.</p>
      </div>
    </div>

    <div class="panel">
      <h3 style="margin:0 0 8px;font-size:.92rem">Results table</h3>
      <table>
        <thead>
          <tr>
            <th>Cities (V)</th><th>Roads (E)</th>
            <th>Array (ms)</th>
            <th>Heap (ms)</th>
            <th>Bellman-Ford (ms)</th>
            <th>Winner</th>
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
  small:  { sizes: [40, 70, 100], sides: [4, 5, 6], trials: 1 },
  medium: { sizes: [50, 100, 160], sides: [5, 6, 7], trials: 1 },
  large:  { sizes: [60, 120, 200], sides: [6, 7, 8, 9], trials: 1 },
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
      labels:["Expected profit ($)","Money spent ($)"],
      datasets:[
        { label:"Greedy", data:[0,0], backgroundColor:"#d4a54a" },
        { label:"DP (whole shares)", data:[0,0], backgroundColor:"#6ea8d8" },
      ]
    },
    options: axis
  });
  timeChart = new Chart(document.getElementById("timeChart"), {
    type:"bar",
    data:{
      labels:["Greedy","DP"],
      datasets:[{ label:"milliseconds", data:[0,0], backgroundColor:["#d4a54a","#6ea8d8"] }]
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
    `Now showing: <b>${money(d.budget)}</b> to spend on <b>${d.n}</b> stocks. ` +
    `Greedy bought <b>${d.greedy.picks.length}</b> · DP bought <b>${d.dp.picks.length}</b>.`;
  document.getElementById("gProfit").textContent = money(d.greedy.profit);
  document.getElementById("dProfit").textContent = money(d.dp.profit);
  document.getElementById("gSpent").textContent = money(d.greedy.spent);
  document.getElementById("dSpent").textContent = money(d.dp.spent);
  document.getElementById("gMs").textContent = d.greedy.ms.toFixed(3) + " ms";
  document.getElementById("dMs").textContent = d.dp.ms.toFixed(2) + " ms";
  document.getElementById("gCount").textContent = d.greedy.picks.length;
  document.getElementById("dCount").textContent = d.dp.picks.length;
  document.getElementById("gFrac").textContent = d.greedy.has_frac ? "yes — last buy was partial" : "no — all full shares";

  const gap = d.greedy.profit - d.dp.profit;
  const el = document.getElementById("delta");
  if (Math.abs(gap) < 0.01) { el.textContent = "≈ same"; el.className = "delta green"; }
  else if (gap > 0) { el.textContent = "+" + money(gap); el.className = "delta gold"; }
  else { el.textContent = money(gap); el.className = "delta blue"; }
  document.getElementById("deltaHint").textContent = gap >= 0
    ? "Greedy earned more expected profit"
    : "DP earned more expected profit";
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
    <b class="green">${both.length}</b> stocks appear on both lists.
    <b class="gold">${onlyG.length}</b> only on Greedy (${onlyG.join(", ") || "none"}).
    <b class="blue">${onlyD.length}</b> only on DP (${onlyD.join(", ") || "none"}).
    <br><br>${d.diff.note}`;
}

async function run1(){
  const btn = document.getElementById("go1");
  const err = document.getElementById("err1");
  const opts = selectedP1();
  const myId = ++runId1;
  err.textContent = "";
  btn.disabled = true;
  btn.textContent = "Working…";
  document.getElementById("status1").innerHTML = `Running with <b>${money(opts.budget)}</b> and <b>${opts.n}</b> stocks…`;
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
    if(myId === runId1){ btn.disabled = false; btn.textContent = "Run comparison"; }
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
        { label:"Array Dijkstra", data:[], borderColor:"#d4a54a", tension:.25, pointRadius:4 },
        { label:"Heap Dijkstra", data:[], borderColor:"#6ea8d8", tension:.25, pointRadius:4 },
        { label:"Bellman-Ford", data:[], borderColor:"#a78bfa", tension:.25, pointRadius:4 },
      ]
    },
    options:{ ...axis, scales:{ ...axis.scales, y:{ ...axis.scales.y, title:{ display:true, text:"time (ms)", color:"#9aab9c" } } } }
  });
  routeBar = new Chart(document.getElementById("routeBar"), {
    type:"bar",
    data:{
      labels:["Array","Heap","Bellman-Ford"],
      datasets:[{ label:"ms", data:[0,0,0], backgroundColor:["#d4a54a","#6ea8d8","#a78bfa"] }]
    },
    options:{ ...axis, plugins:{ legend:{ display:false } } }
  });
}

let maps = [];
let mapIndex = 0;
let mapTimer = null;
let animTimer = null;
let animStep = 0;
let cyMaps = { array: null, heap: null, bf: null };
const ALGO_KEYS = ["array", "heap", "bf"];
const ALGO_BOX = { array: "cyArray", heap: "cyHeap", bf: "cyBf" };
const MAP_W = 420, MAP_H = 300;

function stopMapPlay(){
  if(mapTimer){ clearInterval(mapTimer); mapTimer = null; }
  const b = document.getElementById("mapPlay");
  if(b){ b.textContent = "▶ play growth"; b.classList.add("on"); }
}
function stopAnim(){
  if(animTimer){ clearInterval(animTimer); animTimer = null; }
}

function cityElements(m){
  const els = [];
  m.nodes.forEach(n => {
    els.push({
      group: "nodes",
      data: {
        id: "n" + n.id,
        label: m.V <= 28 ? (n.name || ("City " + n.id)) : String(n.id),
        raw: n.id,
      },
      position: { x: 24 + n.x * (MAP_W - 48), y: 24 + n.y * (MAP_H - 48) },
    });
  });
  m.edges.forEach((e, i) => {
    els.push({
      group: "edges",
      data: {
        id: "e" + i,
        source: "n" + e.u,
        target: "n" + e.v,
        weight: e.w,
        key: e.u + ">" + e.v,
      },
    });
  });
  return els;
}

function cyStyle(m){
  const nsize = m.V > 60 ? 8 : m.V > 35 ? 12 : 18;
  return [
    {
      selector: "node",
      style: {
        "background-color": "#2a3a48",
        "border-width": 2,
        "border-color": "#6f8799",
        "label": "data(label)",
        "color": "#d7e0e8",
        "font-size": m.V > 40 ? 0 : 9,
        "font-family": "IBM Plex Sans, sans-serif",
        "text-valign": "top",
        "text-margin-y": -4,
        "width": nsize,
        "height": nsize,
        "overlay-opacity": 0,
      }
    },
    {
      selector: "edge",
      style: {
        "width": 1.2,
        "line-color": "#3d4f5f",
        "target-arrow-color": "#3d4f5f",
        "target-arrow-shape": "triangle",
        "curve-style": "bezier",
        "arrow-scale": 0.6,
        "opacity": 0.7,
      }
    },
    { selector: "node.explored", style: { "background-color": "#f0c14b", "border-color": "#ffe08a" } },
    { selector: "edge.explored", style: { "line-color": "#c9a227", "target-arrow-color": "#c9a227", "width": 2, "opacity": 0.9 } },
    { selector: "node.path", style: { "background-color": "#4cc9f0", "border-color": "#9be7ff", "width": nsize+6, "height": nsize+6 } },
    { selector: "edge.path", style: { "line-color": "#4cc9f0", "target-arrow-color": "#4cc9f0", "width": 4, "opacity": 1, "z-index": 99 } },
    {
      selector: "node.start",
      style: {
        "background-color": "#3dd68c", "border-color": "#b6f5d3",
        "width": nsize+10, "height": nsize+10,
        "label": "START", "font-size": 9, "font-weight": 700, "color": "#3dd68c",
      }
    },
    {
      selector: "node.end",
      style: {
        "background-color": "#ff6b6b", "border-color": "#ffc2c2",
        "width": nsize+10, "height": nsize+10,
        "label": "END", "font-size": 9, "font-weight": 700, "color": "#ff6b6b",
      }
    },
  ];
}

function ensureAllCy(m){
  const els = cityElements(m);
  const style = cyStyle(m);
  ALGO_KEYS.forEach(key => {
    if(cyMaps[key]){ cyMaps[key].destroy(); cyMaps[key] = null; }
    cyMaps[key] = cytoscape({
      container: document.getElementById(ALGO_BOX[key]),
      elements: els,
      layout: { name: "preset", fit: true, padding: 16 },
      minZoom: 0.35,
      maxZoom: 2.2,
      wheelSensitivity: 0.2,
      style,
      userZoomingEnabled: true,
      userPanningEnabled: true,
    });
  });
}

function styleOne(cy, m, algoKey, exploredCount){
  if(!cy || !m.algos || !m.algos[algoKey]) return;
  const order = m.algos[algoKey].visit_order || [];
  const path = m.algos[algoKey].path || m.path || [];
  const explored = new Set(order.slice(0, exploredCount));
  const showPath = exploredCount >= order.length;
  const pathSet = new Set(path);
  const pathEdges = new Set();
  for(let i=1;i<path.length;i++) pathEdges.add(path[i-1] + ">" + path[i]);

  cy.batch(() => {
    cy.nodes().forEach(n => {
      const id = n.data("raw");
      n.removeClass("explored path start end");
      if(id === m.source) n.addClass("start");
      else if(id === m.target) n.addClass("end");
      else if(showPath && pathSet.has(id)) n.addClass("path");
      else if(explored.has(id)) n.addClass("explored");
    });
    cy.edges().forEach(e => {
      e.removeClass("explored path");
      const key = e.data("key");
      const u = Number(e.data("source").slice(1));
      const v = Number(e.data("target").slice(1));
      if(showPath && pathEdges.has(key)) e.addClass("path");
      else if(explored.has(u) && explored.has(v)) e.addClass("explored");
    });
  });
}

function styleAll(m, frac){
  // frac 0..1 progress; each algo may have different order lengths
  ALGO_KEYS.forEach(key => {
    const order = (m.algos && m.algos[key] && m.algos[key].visit_order) || [];
    const count = Math.floor(frac * order.length);
    styleOne(cyMaps[key], m, key, count);
  });
  const startName = (m.nodes.find(n => n.id === m.source) || {}).name || ("City " + m.source);
  const endName = (m.nodes.find(n => n.id === m.target) || {}).name || ("City " + m.target);
  const done = frac >= 1;
  const paths = ALGO_KEYS.map(k => JSON.stringify((m.algos[k]||{}).path||[]));
  const allSame = paths[0]===paths[1] && paths[1]===paths[2];
  document.getElementById("metricArray").textContent = (m.algos.array && m.algos.array.metric) || "—";
  document.getElementById("metricHeap").textContent = (m.algos.heap && m.algos.heap.metric) || "—";
  document.getElementById("metricBf").textContent = (m.algos.bf && m.algos.bf.metric) || "—";
  document.getElementById("mapCaption").innerHTML =
    `<b>${m.side}×${m.side}</b> city blocks · <b>${m.V}</b> junctions · ` +
    `<b>${startName}</b> → <b>${endName}</b> · ` +
    (done
      ? (allSame
          ? "routes matched this round (try another size)"
          : "<b class='coral'>routes differ</b> — different rules, different paths")
      : "exploring…");
}

function playExplore(m){
  stopAnim();
  ensureAllCy(m);
  animStep = 0;
  const frames = 42;
  const stepEvery = 40;
  styleAll(m, 0);
  animTimer = setInterval(() => {
    animStep += 1;
    const frac = Math.min(1, animStep / frames);
    styleAll(m, frac);
    if(frac >= 1) stopAnim();
  }, stepEvery);
}

function showMapAt(i, animate=true){
  if(!maps.length) return;
  mapIndex = Math.max(0, Math.min(maps.length-1, i));
  const m = maps[mapIndex];
  if(animate) playExplore(m);
  else {
    stopAnim();
    ensureAllCy(m);
    styleAll(m, 1);
  }
}

function paint2(d){
  p2Loaded = true;
  const last = d.rows[d.rows.length - 1];
  document.getElementById("status2").innerHTML =
    `Now showing maps up to <b>${last.V}</b> cities and about <b>${last.E}</b> roads ` +
    `(averaged over <b>${d.trials}</b> run${d.trials>1?"s":""}).`;
  document.getElementById("rArray").textContent = last.array_ms.toFixed(2) + " ms";
  document.getElementById("rHeap").textContent = last.heap_ms.toFixed(2) + " ms";
  document.getElementById("rBf").textContent = last.bf_ms.toFixed(2) + " ms";
  document.getElementById("rArrayNote").textContent = last.V + " cities";
  document.getElementById("rHeapNote").textContent = last.V + " cities";
  document.getElementById("rBfNote").textContent = last.V + " cities";

  routeChart.data.labels = d.rows.map(r => r.V + " cities");
  routeChart.data.datasets[0].data = d.rows.map(r => r.array_ms);
  routeChart.data.datasets[1].data = d.rows.map(r => r.heap_ms);
  routeChart.data.datasets[2].data = d.rows.map(r => r.bf_ms);
  routeChart.update();
  routeBar.data.datasets[0].data = [last.array_ms, last.heap_ms, last.bf_ms];
  routeBar.update();

  document.getElementById("rBody").innerHTML = d.rows.map(r => {
    const times = { array: r.array_ms, heap: r.heap_ms, bf: r.bf_ms };
    const best = Object.entries(times).sort((a,b)=>a[1]-b[1])[0][0];
    const label = best === "array" ? "Array" : best === "heap" ? "Heap" : "Bellman-Ford";
    return `<tr>
      <td>${r.V}</td><td>${r.E}</td>
      <td>${r.array_ms.toFixed(3)}</td>
      <td>${r.heap_ms.toFixed(3)}</td>
      <td>${r.bf_ms.toFixed(3)}</td>
      <td>${label}</td>
    </tr>`;
  }).join("");

  document.getElementById("rWhy").innerHTML = d.blurb;

  maps = d.maps || [];
  stopMapPlay();
  showMapAt(0, true);
}

async function run2(){
  const btn = document.getElementById("go2");
  const err = document.getElementById("err2");
  const myId = ++runId2;
  err.textContent = "";
  btn.disabled = true;
  btn.textContent = "Working…";
  document.getElementById("status2").innerHTML =
    `Testing maps with <b>${currentR.sizes.join(", ")}</b> cities…`;
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
    if(myId === runId2){ btn.disabled = false; btn.textContent = "Run speed test"; }
  }
}

document.getElementById("mapPrev").addEventListener("click", () => {
  stopMapPlay();
  showMapAt(mapIndex - 1, true);
});
document.getElementById("mapNext").addEventListener("click", () => {
  stopMapPlay();
  showMapAt(mapIndex + 1, true);
});
document.getElementById("mapPlay").addEventListener("click", () => {
  if(mapTimer){ stopMapPlay(); return; }
  if(!maps.length) return;
  const btn = document.getElementById("mapPlay");
  btn.textContent = "■ stop";
  btn.classList.remove("on");
  showMapAt(0, true);
  mapTimer = setInterval(() => {
    if(mapIndex >= maps.length - 1){
      stopMapPlay();
      return;
    }
    showMapAt(mapIndex + 1, true);
  }, 2600);
});

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
        frac_ticker = [p["ticker"] for p in g_picks if p["frac"]][0]
        blurb = (
            f"In plain English: Greedy won by ${gap:.2f} because it bought a "
            f"<b>slice</b> of {frac_ticker} with leftover cash. "
            "DP refused that partial buy, so some money sat unused."
        )
    elif abs(gap) <= 0.01:
        blurb = (
            "In plain English: profits came out almost the same this time — "
            "but the rules are still different (fractions vs whole shares only)."
        )
    else:
        blurb = (
            f"In plain English: the profit gap is ${abs(gap):.2f}. "
            "Look at the shopping lists below to see which stocks each method chose."
        )

    note = (
        "Remember: this is fake market data for learning algorithms — not real investing advice. "
        "Greedy = buy best value-per-dollar first (fractions OK). "
        "DP = only whole shares, searching for the best combo."
    )
    if only_g or only_d:
        note += " The lists below highlight where their baskets differ."

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

    try:
        sides = [int(x) for x in data.get("sides", [4, 5, 6])]
    except Exception:
        sides = [4, 5, 6]
    sides = [max(3, min(10, s)) for s in sides] or [4, 5, 6]

    rows = []
    maps = []
    source = 0
    for idx, V in enumerate(sizes):
        E = edge_factor * V
        gseed = seed + idx
        graph = nr.generate_random_directed_graph(V, E, seed=gseed)
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

    # visual city maps (separate from timing graphs) — grow block by block
    for i, side in enumerate(sides):
        maps.append(build_map_view(side, seed + 100 + i))

    last = rows[-1]
    order = sorted(
        [("array", last["array_ms"]), ("heap", last["heap_ms"]), ("bf", last["bf_ms"])],
        key=lambda x: x[1],
    )
    winner = {
        "array": "Array Dijkstra",
        "heap": "Heap Dijkstra",
        "bf": "Bellman-Ford",
    }[order[0][0]]
    blurb = (
        f"In plain English: on the biggest map ({last['V']} cities), "
        f"<b>{winner}</b> finished first at {order[0][1]:.2f} ms. "
        "Same shortest-path answers — only the speed differs. "
        "On the map above: gold cities are explored, blue line is the route chosen."
    )

    return jsonify({
        "trials": trials,
        "edge_factor": edge_factor,
        "rows": rows,
        "maps": maps,
        "blurb": blurb,
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8742, debug=False)
