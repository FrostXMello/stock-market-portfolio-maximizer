# Handoff — DAA Project 2 (Network Routing)

Picked up from Cursor Project **DAA Project 2**. Merge from here into the combined app.

## Location
All files live under `daa-project-2/`:
- `network_routing.py` — graph gen, Dijkstra array O(V²), Dijkstra heapq, Bellman-Ford + neg-cycle check, benchmarks, matplotlib plot
- `requirements.txt` — `matplotlib>=3.7.0`
- `benchmark_results.png` — sample run output
- `README.md` — how to run standalone

## Run standalone
```bash
pip install -r daa-project-2/requirements.txt
python daa-project-2/network_routing.py
```

## Intended merge (from DAA Project chat)
- Existing portfolio maximizer is on `main` (`main.py` Flask app).
- Build a **two-tab UI**: **DAA Project** (portfolio) | **DAA Project 2** (this routing work).
- Branch/PR: `daa-project-2` → https://github.com/FrostXMello/stock-market-portfolio-maximizer/pull/1

## Status
Complete and self-contained. No further work required in the DAA Project 2 Cursor chat.
