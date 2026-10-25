#!/usr/bin/env python3
"""Smart-Freeze Scaled Benchmark Suite.

Benchmarks Smart-Freeze's bounded-subgraph extraction, multi-method tracing,
Consensus Lien decision engine, and federated passport coordination across
1k, 5k, and 20k account ledgers.

Outputs:
1. benchmarks/benchmark_results.json: Raw measured metrics (p50/p95 latency, passports per case).
2. benchmarks/benchmark_chart.png: Dual-panel visualization of measured latencies and passports.

Strictly follows project rules: No extrapolated claims, exact measured numbers only.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple
import numpy as np

# Ensure repository root is on sys.path
WORKSPACE_DIR = Path(__file__).resolve().parent.parent
if str(WORKSPACE_DIR) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_DIR))

from scripts.generate_synthetic_data import generate_scaled_dataset
from engine.subgraph import BoundedSubgraphExtractor
from engine.decision import DecisionEngine
from federated.coordinator import FederatedCoordinator


def run_tier_benchmark(
    num_accounts: int,
    num_cases: int = 15,
    seed: int = 42,
    max_hops: int = 4,
    time_window_hours: float = 72.0,
) -> Dict[str, Any]:
    """Run full case evaluations on a generated dataset tier and record actual metrics."""
    print(f"\n--- Benchmarking Scale Tier: {num_accounts:,} accounts ({num_cases} cases) ---")
    
    # 1. Dataset Generation
    t_gen_start = time.perf_counter()
    accounts, transactions, cases, ground_truth = generate_scaled_dataset(
        num_accounts=num_accounts,
        num_cases=num_cases,
        seed=seed,
    )
    t_gen_end = time.perf_counter()
    gen_time_s = t_gen_end - t_gen_start
    print(f"  Generated {len(accounts):,} accounts, {len(transactions):,} txns in {gen_time_s:.3f}s")

    # Map transactions by case_id to locate origin
    tx_by_case: Dict[str, List[Dict[str, Any]]] = {}
    for tx in transactions:
        cid = str(tx.get("case_id", "")).strip()
        if cid:
            tx_by_case.setdefault(cid, []).append(tx)

    case_latencies_ms: List[float] = []
    case_passports: List[int] = []
    subgraph_nodes: List[int] = []
    subgraph_edges: List[int] = []

    decision_engine = DecisionEngine()

    # Warm up ML model service so cold imports do not distort latency measurements
    try:
        from ml.mule_service import MuleDetectorService
        MuleDetectorService.get_instance()
    except Exception:
        pass

    for idx, c in enumerate(cases):
        case_id = str(c["case_id"])
        c_txs = tx_by_case.get(case_id, [])
        if not c_txs:
            continue

        # Sort by timestamp to find root transaction
        c_txs_sorted = sorted(c_txs, key=lambda t: str(t.get("timestamp", "")))
        source_tx_id = str(c_txs_sorted[0]["transaction_id"])

        # Start timer for full case workflow
        t0 = time.perf_counter()

        # Step A: Bounded-subgraph extraction
        subgraph = BoundedSubgraphExtractor.extract(
            accounts=accounts,
            transactions=transactions,
            source_transaction_id=source_tx_id,
            max_hops=max_hops,
            time_window_hours=time_window_hours,
            max_edges=500,
            include_account_context=True,
        )

        # Step B: Multi-method tracing & decision evaluation
        rec_result = decision_engine.evaluate_case(
            case_id=case_id,
            accounts=subgraph.accounts,
            transactions=subgraph.transactions,
            source_transaction_id=source_tx_id,
            policy_name="balanced",
        )

        # Step C: Federated cross-institution passport issuance & verification
        coordinator = FederatedCoordinator()
        fed_result = coordinator.run_trace(
            accounts=subgraph.accounts,
            transactions=subgraph.transactions,
            source_transaction_id=source_tx_id,
            case_id=case_id,
        )

        t1 = time.perf_counter()
        elapsed_ms = (t1 - t0) * 1000.0

        num_passports = len(fed_result.passports)

        case_latencies_ms.append(elapsed_ms)
        case_passports.append(num_passports)
        subgraph_nodes.append(subgraph.node_count)
        subgraph_edges.append(subgraph.edge_count)

    lat_arr = np.array(case_latencies_ms)
    pass_arr = np.array(case_passports)
    nodes_arr = np.array(subgraph_nodes)
    edges_arr = np.array(subgraph_edges)

    p50_lat = float(np.percentile(lat_arr, 50))
    p95_lat = float(np.percentile(lat_arr, 95))
    mean_lat = float(np.mean(lat_arr))
    min_lat = float(np.min(lat_arr))
    max_lat = float(np.max(lat_arr))

    p50_pass = float(np.percentile(pass_arr, 50))
    p95_pass = float(np.percentile(pass_arr, 95))
    mean_pass = float(np.mean(pass_arr))
    max_pass = int(np.max(pass_arr))

    print(f"  Evaluated {len(case_latencies_ms)} cases:")
    print(f"    Latency: p50={p50_lat:.2f}ms, p95={p95_lat:.2f}ms, mean={mean_lat:.2f}ms")
    print(f"    Passports: mean={mean_pass:.2f}, p50={p50_pass:.1f}, p95={p95_pass:.1f}, max={max_pass}")
    print(f"    Subgraph: avg_nodes={np.mean(nodes_arr):.1f}, avg_edges={np.mean(edges_arr):.1f}")

    return {
        "tier_name": f"{num_accounts // 1000}k",
        "num_accounts": num_accounts,
        "total_transactions": len(transactions),
        "cases_evaluated": len(case_latencies_ms),
        "data_generation_time_s": round(gen_time_s, 4),
        "latency_ms": {
            "p50": round(p50_lat, 2),
            "p95": round(p95_lat, 2),
            "mean": round(mean_lat, 2),
            "min": round(min_lat, 2),
            "max": round(max_lat, 2),
            "samples": [round(x, 2) for x in case_latencies_ms],
        },
        "passports_per_case": {
            "mean": round(mean_pass, 2),
            "p50": round(p50_pass, 2),
            "p95": round(p95_pass, 2),
            "max": max_pass,
            "samples": [int(x) for x in case_passports],
        },
        "subgraph_stats": {
            "avg_nodes": round(float(np.mean(nodes_arr)), 1),
            "avg_edges": round(float(np.mean(edges_arr)), 1),
        },
    }


def generate_benchmark_chart(results: Dict[str, Any], output_path: Path):
    """Generate dual-panel benchmark visualization chart using matplotlib."""
    import matplotlib.pyplot as plt

    tiers = list(results["tiers"].keys())
    x = np.arange(len(tiers))
    width = 0.35

    p50_vals = [results["tiers"][t]["latency_ms"]["p50"] for t in tiers]
    p95_vals = [results["tiers"][t]["latency_ms"]["p95"] for t in tiers]
    mean_pass = [results["tiers"][t]["passports_per_case"]["mean"] for t in tiers]
    p95_pass = [results["tiers"][t]["passports_per_case"]["p95"] for t in tiers]

    plt.style.use("seaborn-v0_8-whitegrid" if "seaborn-v0_8-whitegrid" in plt.style.available else "default")
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5.5), dpi=300)
    fig.patch.set_facecolor("#ffffff")

    # Panel 1: Latency per Case (p50 and p95)
    rects1 = ax1.bar(x - width/2, p50_vals, width, label="p50 Latency (ms)", color="#2563eb", alpha=0.9)
    rects2 = ax1.bar(x + width/2, p95_vals, width, label="p95 Latency (ms)", color="#dc2626", alpha=0.9)

    ax1.set_title("Measured Case Latency (ms)\n(Bounded Subgraph + Tracing + Consensus + Federated)", fontsize=11, fontweight="bold", pad=12)
    ax1.set_xlabel("Account Scale Tier", fontsize=10, fontweight="bold")
    ax1.set_ylabel("Latency per Case (ms)", fontsize=10, fontweight="bold")
    ax1.set_xticks(x)
    ax1.set_xticklabels([f"{t.upper()} Accounts" for t in tiers], fontsize=10)
    ax1.legend(loc="upper left", frameon=True)
    ax1.grid(axis="y", linestyle="--", alpha=0.7)

    # Add data labels
    for rect in rects1:
        height = rect.get_height()
        ax1.annotate(f"{height:.1f}ms",
                    xy=(rect.get_x() + rect.get_width() / 2, height),
                    xytext=(0, 4), textcoords="offset points",
                    ha="center", va="bottom", fontsize=8, fontweight="bold")
    for rect in rects2:
        height = rect.get_height()
        ax1.annotate(f"{height:.1f}ms",
                    xy=(rect.get_x() + rect.get_width() / 2, height),
                    xytext=(0, 4), textcoords="offset points",
                    ha="center", va="bottom", fontsize=8, fontweight="bold", color="#991b1b")

    # Panel 2: Federated Passports per Case
    rects3 = ax2.bar(x - width/2, mean_pass, width, label="Mean Passports", color="#059669", alpha=0.9)
    rects4 = ax2.bar(x + width/2, p95_pass, width, label="p95 Passports", color="#d97706", alpha=0.9)

    ax2.set_title("Federated Passports Issued per Case\n(Ed25519-Signed Cross-Institution Transfers)", fontsize=11, fontweight="bold", pad=12)
    ax2.set_xlabel("Account Scale Tier", fontsize=10, fontweight="bold")
    ax2.set_ylabel("Passports Issued per Case", fontsize=10, fontweight="bold")
    ax2.set_xticks(x)
    ax2.set_xticklabels([f"{t.upper()} Accounts" for t in tiers], fontsize=10)
    ax2.legend(loc="upper left", frameon=True)
    ax2.grid(axis="y", linestyle="--", alpha=0.7)

    for rect in rects3:
        height = rect.get_height()
        ax2.annotate(f"{height:.1f}",
                    xy=(rect.get_x() + rect.get_width() / 2, height),
                    xytext=(0, 4), textcoords="offset points",
                    ha="center", va="bottom", fontsize=8, fontweight="bold")
    for rect in rects4:
        height = rect.get_height()
        ax2.annotate(f"{height:.1f}",
                    xy=(rect.get_x() + rect.get_width() / 2, height),
                    xytext=(0, 4), textcoords="offset points",
                    ha="center", va="bottom", fontsize=8, fontweight="bold", color="#92400e")

    plt.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_path, dpi=300)
    plt.close()
    print(f"\nSaved benchmark chart to: {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Smart-Freeze Scale Benchmark")
    parser.add_argument("--cases-per-tier", type=int, default=15, help="Number of cases per scale tier (default: 15)")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for deterministic data generation")
    args = parser.parse_args()

    scale_tiers = [1_000, 5_000, 20_000]
    results: Dict[str, Any] = {
        "benchmark_metadata": {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "python_version": sys.version.split()[0],
            "seed": args.seed,
            "cases_per_tier": args.cases_per_tier,
            "workflow": "BoundedSubgraphExtractor -> ConsensusLien (FIFO, Proportional, LIBR) -> DecisionEngine -> FederatedCoordinator",
            "claim_statement": "All figures are measured directly on the host machine without theoretical extrapolation.",
        },
        "tiers": {},
    }

    total_start = time.perf_counter()
    for scale in scale_tiers:
        tier_key = f"{scale // 1000}k"
        tier_res = run_tier_benchmark(
            num_accounts=scale,
            num_cases=args.cases_per_tier,
            seed=args.seed,
        )
        results["tiers"][tier_key] = tier_res

    total_time = time.perf_counter() - total_start
    results["benchmark_metadata"]["total_benchmark_time_s"] = round(total_time, 2)

    # Save JSON results
    output_json = WORKSPACE_DIR / "benchmarks" / "benchmark_results.json"
    output_json.parent.mkdir(parents=True, exist_ok=True)
    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"\nSaved benchmark metrics to: {output_json}")

    # Generate Chart
    output_png = WORKSPACE_DIR / "benchmarks" / "benchmark_chart.png"
    generate_benchmark_chart(results, output_png)

    # Print Summary Table
    print("\n" + "="*80)
    print("SMART-FREEZE BENCHMARK SUMMARY (MEASURED VALUES ONLY)")
    print("="*80)
    header = f"{'Tier':<8} | {'Accounts':<10} | {'Txs':<10} | {'p50 Lat (ms)':<14} | {'p95 Lat (ms)':<14} | {'Mean Passports':<16} | {'p95 Passports':<14}"
    print(header)
    print("-" * len(header))
    for t_key, t_data in results["tiers"].items():
        print(
            f"{t_key:<8} | "
            f"{t_data['num_accounts']:<10,d} | "
            f"{t_data['total_transactions']:<10,d} | "
            f"{t_data['latency_ms']['p50']:<14.2f} | "
            f"{t_data['latency_ms']['p95']:<14.2f} | "
            f"{t_data['passports_per_case']['mean']:<16.2f} | "
            f"{t_data['passports_per_case']['p95']:<14.2f}"
        )
    print("="*80)


if __name__ == "__main__":
    main()
