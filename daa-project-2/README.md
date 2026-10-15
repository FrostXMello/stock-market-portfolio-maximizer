# DAA Project 2 — Network Routing and Map Navigation

Shortest-path algorithms (Dijkstra array / heap, Bellman-Ford) with empirical benchmarks on sparse directed road networks (E ≈ 3·V).

See [HANDOFF.md](./HANDOFF.md) if you are merging this into the combined DAA app.

## Run

```bash
pip install -r requirements.txt
python network_routing.py
```

Writes `benchmark_results.png` (runtime ms vs vertices for all three algorithms).
