"""
Stock Market Investment Portfolio Maximizer
==========================================
A Design and Analysis of Algorithms (DAA) demonstration that allocates a
fixed capital budget across mock stock assets using two classic knapsack
approaches:

  Algorithm A — Greedy Fractional Knapsack
      Allows buying fractional shares. Assets are sorted by expected profit
      per unit of cost and capital is allocated greedily. Time O(n log n),
      auxiliary space O(n).

  Algorithm B — 0/1 Knapsack Dynamic Programming
      Allows whole shares only. A bottom-up one-dimensional DP table finds
      the maximum expected profit without reconstructing the portfolio.
      Time O(nW), auxiliary space O(W), where W is the integer-scaled budget.

Important notes
---------------
* Synthetic data is for teaching algorithms only — it is NOT real market
  prediction or investment advice.
* The two algorithms solve different problem variants (fractional vs 0/1),
  so their reported profits are NOT directly comparable under identical
  constraints.
"""

from __future__ import annotations

import random
import time
from typing import Dict, List, Tuple

import matplotlib

# Prefer a non-interactive backend so headless runs never hang on display.
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402  (must follow matplotlib.use)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
RISK_FREE_RATE = 0.02          # annual risk-free rate used in Sharpe ratio
RANDOM_SEED = 42               # fixed seed for reproducible mock data
BUDGET = 10_000.0              # fixed capital budget for every benchmark
BENCHMARK_RUNS = 5             # number of timed runs averaged per size
DATASET_SIZES = (10, 50, 100, 500)
GRAPH_FILENAME = "portfolio_runtime_comparison.png"


# ---------------------------------------------------------------------------
# 1. Stock Data Generation
# ---------------------------------------------------------------------------
def generate_stock_assets(num_stocks: int, seed: int = RANDOM_SEED) -> List[Dict]:
    """
    Generate a list of mock stock assets with reproducible random values.

    Each asset dictionary contains:
        ticker, cost, expected_return_rate, volatility, sharpe_ratio,
        expected_profit  (cost × expected_return_rate)

    Parameters
    ----------
    num_stocks : int
        Number of assets to create. Must be a positive integer.
    seed : int
        Random seed so results are reproducible across runs.

    Returns
    -------
    list of dict
        Mock stock assets ready for the knapsack algorithms.
    """
    if not isinstance(num_stocks, int) or num_stocks <= 0:
        raise ValueError("num_stocks must be a positive integer.")

    rng = random.Random(seed)
    assets: List[Dict] = []

    for i in range(num_stocks):
        ticker = f"STK{i + 1:03d}"
        # Share price between $10 and $250
        cost = round(rng.uniform(10.0, 250.0), 2)
        # Expected return rate between 2% and 25%
        expected_return_rate = round(rng.uniform(0.02, 0.25), 4)
        # Volatility between 5% and 40% (never zero — avoids division by zero)
        volatility = round(rng.uniform(0.05, 0.40), 4)

        sharpe_ratio = (expected_return_rate - RISK_FREE_RATE) / volatility
        expected_profit = cost * expected_return_rate

        assets.append(
            {
                "ticker": ticker,
                "cost": cost,
                "expected_return_rate": expected_return_rate,
                "volatility": volatility,
                "sharpe_ratio": round(sharpe_ratio, 4),
                "expected_profit": round(expected_profit, 4),
            }
        )

    return assets


# ---------------------------------------------------------------------------
# 2. Algorithm A: Greedy Fractional Knapsack
# ---------------------------------------------------------------------------
def greedy_fractional_knapsack(assets: List[Dict], budget: float) -> float:
    """
    Maximize expected profit allowing fractional shares (fractional knapsack).

    Strategy
    --------
    1. Sort assets by expected profit per unit of cost (descending).
    2. Buy as much of each asset as the remaining budget allows.
    3. Stop when the budget is exhausted.

    Complexity
    ----------
    Time     : O(n log n)  — dominated by sorting
    Aux space: O(n)        — sorted copy of the asset list

    Parameters
    ----------
    assets : list of dict
        Stock assets with 'cost' and 'expected_profit' fields.
    budget : float
        Available capital. Must be non-negative.

    Returns
    -------
    float
        Maximum expected profit under the fractional-share model.
    """
    if budget < 0:
        raise ValueError("budget must be non-negative.")
    if not assets:
        return 0.0

    # Sort by profit density (expected profit / cost), highest first.
    # O(n log n) time; the sorted list uses O(n) auxiliary space.
    sorted_assets = sorted(
        assets,
        key=lambda a: a["expected_profit"] / a["cost"],
        reverse=True,
    )

    remaining = budget
    total_profit = 0.0

    for asset in sorted_assets:
        cost = asset["cost"]
        profit = asset["expected_profit"]

        if remaining <= 0:
            break

        if cost <= remaining:
            # Buy one full share
            total_profit += profit
            remaining -= cost
        else:
            # Buy a fraction of one share with whatever capital is left
            fraction = remaining / cost
            total_profit += profit * fraction
            remaining = 0.0

    return total_profit


# ---------------------------------------------------------------------------
# 3. Algorithm B: 0/1 Knapsack DP (1-D, O(W) auxiliary space)
# ---------------------------------------------------------------------------
def zero_one_knapsack_dp(assets: List[Dict], budget: float) -> float:
    """
    Maximize expected profit with whole shares only (0/1 knapsack).

    Uses a classic bottom-up DP with a single one-dimensional array so that
    auxiliary space is O(W), where W is the integer-scaled budget.
    Capacities are iterated in descending order so each asset is used at
    most once. Portfolio reconstruction is intentionally omitted; only the
    maximum expected profit is returned.

    Complexity
    ----------
    Time     : O(nW)
    Aux space: O(W)   — single DP array of length W+1

    Parameters
    ----------
    assets : list of dict
        Stock assets with 'cost' and 'expected_profit' fields.
    budget : float
        Available capital. Must be non-negative.

    Returns
    -------
    float
        Maximum expected profit under the whole-share (0/1) model.
    """
    if budget < 0:
        raise ValueError("budget must be non-negative.")
    if not assets:
        return 0.0

    # Scale dollars to cents so weights are integers (W = integer budget).
    scale = 100
    W = int(budget * scale)

    # One-dimensional DP array — auxiliary space O(W).
    # dp[w] = best expected profit achievable with capacity w (in cents).
    dp = [0.0] * (W + 1)

    for asset in assets:
        weight = int(round(asset["cost"] * scale))
        value = asset["expected_profit"]

        if weight <= 0 or weight > W:
            continue

        # Descend so this asset is considered at most once (0/1).
        for w in range(W, weight - 1, -1):
            candidate = dp[w - weight] + value
            if candidate > dp[w]:
                dp[w] = candidate

    return dp[W]


# ---------------------------------------------------------------------------
# 4. Benchmarking
# ---------------------------------------------------------------------------
def measure_average_runtime_ms(
    func,
    assets: List[Dict],
    budget: float,
    runs: int = BENCHMARK_RUNS,
) -> Tuple[float, float]:
    """
    Time a knapsack function over several runs and return (avg_ms, profit).

    Uses time.perf_counter() for high-resolution wall-clock timing.
    The profit returned is from the last run (deterministic for fixed seed).
    """
    if runs <= 0:
        raise ValueError("runs must be a positive integer.")

    total_seconds = 0.0
    profit = 0.0

    for _ in range(runs):
        start = time.perf_counter()
        profit = func(assets, budget)
        end = time.perf_counter()
        total_seconds += end - start

    avg_ms = (total_seconds / runs) * 1000.0
    return avg_ms, profit


def run_benchmarks(
    sizes: Tuple[int, ...] = DATASET_SIZES,
    budget: float = BUDGET,
    runs: int = BENCHMARK_RUNS,
) -> List[Dict]:
    """
    Benchmark both algorithms on each dataset size with the same budget.

    Both algorithms receive the identical generated dataset and the same
    fixed capital budget for a fair runtime comparison. Reported profits
    still solve different variants (fractional vs 0/1) and are therefore
    not necessarily directly comparable.
    """
    results: List[Dict] = []

    for n in sizes:
        assets = generate_stock_assets(n)

        greedy_ms, greedy_profit = measure_average_runtime_ms(
            greedy_fractional_knapsack, assets, budget, runs
        )
        dp_ms, dp_profit = measure_average_runtime_ms(
            zero_one_knapsack_dp, assets, budget, runs
        )

        results.append(
            {
                "n": n,
                "greedy_ms": greedy_ms,
                "greedy_profit": greedy_profit,
                "dp_ms": dp_ms,
                "dp_profit": dp_profit,
            }
        )

    return results


def print_results_table(results: List[Dict]) -> None:
    """Print a neat terminal table of benchmark results."""
    header = (
        f"{'Dataset Size':>12} | "
        f"{'Greedy (ms)':>12} | "
        f"{'Greedy Profit':>14} | "
        f"{'DP (ms)':>12} | "
        f"{'DP Profit':>14}"
    )
    separator = "-" * len(header)

    print()
    print("Benchmark Results")
    print("(Same dataset + same budget for both algorithms per row.)")
    print(
        "Note: Greedy allows fractional shares; DP allows whole shares only."
    )
    print(
        "Profits solve different variants and are NOT necessarily directly comparable."
    )
    print(separator)
    print(header)
    print(separator)

    for row in results:
        print(
            f"{row['n']:>12} | "
            f"{row['greedy_ms']:>12.4f} | "
            f"{row['greedy_profit']:>14.2f} | "
            f"{row['dp_ms']:>12.4f} | "
            f"{row['dp_profit']:>14.2f}"
        )

    print(separator)


# ---------------------------------------------------------------------------
# 5. Graph: runtime vs dataset size
# ---------------------------------------------------------------------------
def plot_runtime_comparison(results: List[Dict], filename: str = GRAPH_FILENAME) -> None:
    """
    Draw and save a line graph of average runtime vs dataset size.

    Saves to disk first (required for headless environments), then attempts
    plt.show(). With the Agg backend, show() will not open a window.
    """
    sizes = [row["n"] for row in results]
    greedy_times = [row["greedy_ms"] for row in results]
    dp_times = [row["dp_ms"] for row in results]

    plt.figure(figsize=(9, 5))
    plt.plot(
        sizes,
        greedy_times,
        marker="o",
        linestyle="-",
        label="Greedy Fractional Knapsack",
    )
    plt.plot(
        sizes,
        dp_times,
        marker="s",
        linestyle="-",
        label="0/1 Knapsack DP",
    )
    plt.title("Runtime vs Dataset Size — Portfolio Maximizer")
    plt.xlabel("Dataset Size (number of stocks)")
    plt.ylabel("Average Runtime (ms)")
    plt.legend()
    plt.grid(True, linestyle="--", alpha=0.6)
    plt.tight_layout()
    plt.savefig(filename, dpi=150)
    print(f"\nGraph saved to: {filename}")
    # Safe under Agg: no interactive window; still called for completeness.
    plt.show()
    plt.close()


# ---------------------------------------------------------------------------
# 6. main
# ---------------------------------------------------------------------------
def print_complexities() -> None:
    """Print theoretical time and space complexities for viva review."""
    print()
    print("Theoretical Complexities")
    print("-" * 40)
    print("Greedy Fractional Knapsack")
    print("  Time     : O(n log n)")
    print("  Aux space: O(n)")
    print()
    print("0/1 Knapsack DP (1-D)")
    print("  Time     : O(nW)   where W = integer-scaled budget")
    print("  Aux space: O(W)    single DP array — each asset used at most once")
    print("-" * 40)


def main() -> None:
    """Entry point: generate data, benchmark, print table, plot graph."""
    print("=" * 64)
    print("Stock Market Investment Portfolio Maximizer")
    print("=" * 64)
    print(f"Fixed capital budget : ${BUDGET:,.2f}")
    print(f"Risk-free rate       : {RISK_FREE_RATE:.2%}")
    print(f"Random seed          : {RANDOM_SEED}")
    print(f"Runs averaged        : {BENCHMARK_RUNS}")
    print()
    print(
        "Synthetic data is NOT real market prediction. "
        "Greedy (fractional) and DP (0/1) solve different variants — "
        "profits are not directly comparable."
    )

    results = run_benchmarks()
    print_results_table(results)
    plot_runtime_comparison(results)
    print_complexities()


if __name__ == "__main__":
    main()
