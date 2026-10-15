#!/usr/bin/env python3
"""
Network Routing and Map Navigation — DAA Project

Generates random directed road networks and empirically compares three
shortest-path algorithms:

  1. Dijkstra (array / O(V^2) min-scan)
  2. Dijkstra (binary heap via heapq)
  3. Bellman-Ford (with negative-cycle detection)

Run:
    python network_routing.py

Produces a console timing table and saves benchmark_results.png.
"""

from __future__ import annotations

import heapq
import math
import os
import random
import sys
import time
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Graph representation
# ---------------------------------------------------------------------------
# Adjacency list: graph[u] = [(v, weight), ...] for each directed edge u -> v.
# Vertices are integers in [0, V).
Graph = Dict[int, List[Tuple[int, int]]]

INF = math.inf


# ===========================================================================
# 1. Graph Generation Module
# ===========================================================================

def generate_random_directed_graph(
    V: int,
    E: int,
    min_weight: int = 1,
    max_weight: int = 100,
    seed: Optional[int] = None,
) -> Graph:
    """
    Generate a random directed graph with V vertices and exactly E edges.

    Edge weights are positive integers in [min_weight, max_weight], modeling
    road distances. Self-loops are forbidden. Duplicate (u, v) pairs are
    avoided so the final edge count is exactly E (raises ValueError if E
    exceeds the maximum possible directed edges without self-loops).

    Time complexity:  O(E) expected for unique-edge sampling; worst case
                      degrades if E approaches V*(V-1).
    Space complexity: O(V + E) for the adjacency list.
    """
    if V < 1:
        raise ValueError("V must be at least 1")
    max_edges = V * (V - 1)
    if E < 0 or E > max_edges:
        raise ValueError(f"E must be in [0, {max_edges}] for V={V}")
    if min_weight < 1:
        raise ValueError("min_weight must be a positive integer (>= 1)")
    if max_weight < min_weight:
        raise ValueError("max_weight must be >= min_weight")

    if seed is not None:
        random.seed(seed)

    graph: Graph = {i: [] for i in range(V)}
    used: set = set()

    while len(used) < E:
        u = random.randrange(V)
        v = random.randrange(V)
        if u == v or (u, v) in used:
            continue
        used.add((u, v))
        w = random.randint(min_weight, max_weight)
        graph[u].append((v, w))

    return graph


# ===========================================================================
# 2. Algorithmic Implementations
# ===========================================================================

def dijkstra_array(graph: Graph, source: int) -> List[float]:
    """
    Dijkstra's shortest-path algorithm using an unsorted array/list to select
    the unsettled node with the smallest distance (classic O(V^2) form).

    Assumes all edge weights are non-negative. Suitable for dense graphs or
    pedagogical comparison against the heap-based variant.

    Time complexity:  O(V^2 + E)  — each of V extract-min scans costs O(V);
                      edge relaxation over all adjacency lists is O(E).
    Space complexity: O(V) for distance and visited arrays.
    """
    V = len(graph)
    dist: List[float] = [INF] * V
    visited = [False] * V
    dist[source] = 0.0

    for _ in range(V):
        # Extract unsettled node with minimum distance — O(V) scan.
        u = -1
        best = INF
        for i in range(V):
            if not visited[i] and dist[i] < best:
                best = dist[i]
                u = i

        if u == -1 or best == INF:
            # Remaining nodes are unreachable.
            break

        visited[u] = True

        for v, weight in graph[u]:
            if not visited[v] and dist[u] + weight < dist[v]:
                dist[v] = dist[u] + weight

    return dist


def dijkstra_heap(graph: Graph, source: int) -> List[float]:
    """
    Dijkstra's shortest-path algorithm optimized with a binary min-heap
    (Python's heapq) for extract-min / decrease-key via lazy re-insertion.

    Assumes all edge weights are non-negative. Preferred for sparse graphs
    such as road networks where E = O(V).

    Time complexity:  O((V + E) log V) with a binary heap; each edge may
                      push an entry, and each pop is O(log V).
    Space complexity: O(V + E) for the distance array and heap entries
                      (lazy duplicates may grow to O(E) in the worst case).
    """
    V = len(graph)
    dist: List[float] = [INF] * V
    dist[source] = 0.0
    # Heap entries: (distance, vertex)
    pq: List[Tuple[float, int]] = [(0.0, source)]

    while pq:
        d, u = heapq.heappop(pq)
        if d > dist[u]:
            # Stale entry from lazy decrease-key; skip.
            continue
        for v, weight in graph[u]:
            nd = d + weight
            if nd < dist[v]:
                dist[v] = nd
                heapq.heappush(pq, (nd, v))

    return dist


def bellman_ford(
    graph: Graph, source: int
) -> Tuple[Optional[List[float]], bool]:
    """
    Standard Bellman-Ford single-source shortest paths.

    Performs |V|-1 full relaxation passes, then one extra pass to detect
    negative-weight cycles reachable from the source.

    Behavior on negative cycle:
        If a further relaxation is still possible after |V|-1 passes, a
        negative-weight cycle reachable from `source` exists. In that case
        this function returns (None, True). Callers should treat the distance
        array as undefined / invalid when the flag is True.

    Note: the graphs generated by this project use positive weights only, so
    the negative-cycle flag will normally be False. The check is retained for
    correctness and completeness of the algorithm.

    Returns:
        (distances, has_negative_cycle)
        - distances: list of length V, or None if a negative cycle is found.
        - has_negative_cycle: True iff a reachable negative cycle was detected.

    Time complexity:  O(V * E) — |V|-1 passes over all edges, plus one
                      detection pass.
    Space complexity: O(V + E) to hold distances and to iterate edges
                      (edge list materialization is O(E)).
    """
    V = len(graph)
    dist: List[float] = [INF] * V
    dist[source] = 0.0

    # Flatten adjacency list once for clean O(E) iteration per pass.
    edges: List[Tuple[int, int, int]] = [
        (u, v, w) for u in range(V) for (v, w) in graph[u]
    ]

    for _ in range(V - 1):
        updated = False
        for u, v, w in edges:
            if dist[u] != INF and dist[u] + w < dist[v]:
                dist[v] = dist[u] + w
                updated = True
        if not updated:
            # Early exit: no further improvements possible.
            break

    # Explicit negative-cycle check (Nth relaxation pass).
    for u, v, w in edges:
        if dist[u] != INF and dist[u] + w < dist[v]:
            return None, True

    return dist, False


# ===========================================================================
# 3. Empirical Benchmarking Module
# ===========================================================================

def _time_call(fn, *args, **kwargs) -> Tuple[float, object]:
    """Return (elapsed_ms, result) for a single call to fn."""
    t0 = time.perf_counter()
    result = fn(*args, **kwargs)
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    return elapsed_ms, result


def run_benchmarks(
    vertex_sizes: Optional[List[int]] = None,
    edge_factor: int = 3,
    source: int = 0,
    seed: int = 42,
    trials: int = 3,
) -> Dict[str, List[float]]:
    """
    Benchmark all three shortest-path implementations across scaling graph
    sizes that mimic a sparse road network (E ≈ edge_factor * V).

    For each V in vertex_sizes a fresh graph is generated (seeded for
    reproducibility). Each algorithm is timed `trials` times; the mean
    wall-clock time in milliseconds is recorded.

    Time complexity:  Dominated by the algorithms under test; orchestration
                      itself is O(len(vertex_sizes) * trials).
    Space complexity: O(V + E) for the largest graph held in memory, plus
                      O(len(vertex_sizes)) for the result lists.

    Returns:
        dict with keys 'V', 'dijkstra_array_ms', 'dijkstra_heap_ms',
        'bellman_ford_ms' — parallel lists suitable for plotting.
    """
    if vertex_sizes is None:
        vertex_sizes = [50, 100, 200, 400]

    results: Dict[str, List[float]] = {
        "V": [],
        "dijkstra_array_ms": [],
        "dijkstra_heap_ms": [],
        "bellman_ford_ms": [],
    }

    print("=" * 72)
    print("Network Routing Benchmark — Sparse Directed Graphs (E ≈ 3·V)")
    print("=" * 72)
    header = (
        f"{'V':>6}  {'E':>7}  "
        f"{'Dijkstra(array) ms':>20}  "
        f"{'Dijkstra(heap) ms':>18}  "
        f"{'Bellman-Ford ms':>16}"
    )
    print(header)
    print("-" * 72)

    for idx, V in enumerate(vertex_sizes):
        E = edge_factor * V
        # Distinct seed per size so graphs differ but remain reproducible.
        graph = generate_random_directed_graph(V, E, seed=seed + idx)

        array_times: List[float] = []
        heap_times: List[float] = []
        bf_times: List[float] = []

        for _ in range(trials):
            t, dist_a = _time_call(dijkstra_array, graph, source)
            array_times.append(t)

            t, dist_h = _time_call(dijkstra_heap, graph, source)
            heap_times.append(t)

            t, (dist_b, neg) = _time_call(bellman_ford, graph, source)
            bf_times.append(t)
            if neg:
                raise RuntimeError(
                    "Unexpected negative cycle on a positive-weight graph"
                )

            # Sanity: all three algorithms must agree on distances.
            if dist_a != dist_h or dist_a != dist_b:
                raise AssertionError(
                    f"Algorithm disagreement at V={V}: "
                    "distances differ between implementations"
                )

        mean_array = sum(array_times) / trials
        mean_heap = sum(heap_times) / trials
        mean_bf = sum(bf_times) / trials

        results["V"].append(float(V))
        results["dijkstra_array_ms"].append(mean_array)
        results["dijkstra_heap_ms"].append(mean_heap)
        results["bellman_ford_ms"].append(mean_bf)

        print(
            f"{V:6d}  {E:7d}  "
            f"{mean_array:20.3f}  "
            f"{mean_heap:18.3f}  "
            f"{mean_bf:16.3f}"
        )

    print("=" * 72)
    return results


# ===========================================================================
# 4. Visualization
# ===========================================================================

def plot_benchmark_results(
    results: Dict[str, List[float]],
    output_path: str = "benchmark_results.png",
    show: bool = True,
) -> str:
    """
    Render a professional line chart of runtime (ms) vs number of vertices V
    for all three algorithmic variants and save it to disk.

    When a display is unavailable (common on headless / cloud VMs), the figure
    is saved only and plt.show() is skipped so the process exits cleanly.

    Time complexity:  O(n) where n = number of benchmarked sizes (plot points).
    Space complexity: O(n) for the figure artists and data series.
    """
    import matplotlib

    # Prefer a non-interactive backend when no usable DISPLAY is set so
    # savefig works and the script never blocks on a GUI event loop.
    display = os.environ.get("DISPLAY", "").strip()
    headless = (not display) and sys.platform != "darwin"
    if headless:
        matplotlib.use("Agg")

    import matplotlib.pyplot as plt

    backend = matplotlib.get_backend().lower()
    interactive = (not headless) and ("agg" not in backend)

    V = results["V"]
    fig, ax = plt.subplots(figsize=(10, 6))

    ax.plot(
        V,
        results["dijkstra_array_ms"],
        marker="o",
        linewidth=2,
        label="Dijkstra (array / O(V²))",
    )
    ax.plot(
        V,
        results["dijkstra_heap_ms"],
        marker="s",
        linewidth=2,
        label="Dijkstra (binary heap / O((V+E) log V))",
    )
    ax.plot(
        V,
        results["bellman_ford_ms"],
        marker="^",
        linewidth=2,
        label="Bellman-Ford (O(V·E))",
    )

    ax.set_xlabel("Number of Vertices (V)", fontsize=12)
    ax.set_ylabel("Execution Time (ms)", fontsize=12)
    ax.set_title(
        "Shortest-Path Runtime Comparison\n"
        "Sparse Directed Road Network (E ≈ 3·V)",
        fontsize=14,
    )
    ax.legend(loc="upper left", fontsize=10)
    ax.grid(True, linestyle="--", alpha=0.5)
    ax.set_xticks(V)

    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    print(f"Saved plot → {os.path.abspath(output_path)}")

    if show and interactive:
        # Non-blocking show so the script exits cleanly on interactive backends.
        try:
            plt.show(block=False)
            plt.pause(0.5)
        except Exception:
            pass

    plt.close(fig)
    return output_path


# ===========================================================================
# Entry point
# ===========================================================================

def main() -> None:
    """
    Run the full empirical study and emit the comparison plot.

    Time complexity:  Dominated by run_benchmarks over the chosen sizes.
    Space complexity: O(V + E) for the largest graph under test.
    """
    sizes = [50, 100, 200, 400]
    results = run_benchmarks(vertex_sizes=sizes, edge_factor=3, seed=42, trials=3)
    plot_benchmark_results(results, output_path="benchmark_results.png", show=True)


if __name__ == "__main__":
    main()
