#!/usr/bin/env python3
"""Smart-Freeze Synthetic Data Profiler.

Analyzes and profiles the generated synthetic financial ledger:
- Row counts, account archetypes, case breakdowns
- Evidence status distribution and case-linked vs legitimate proportions
- Amount distribution percentiles (p10, p25, p50, p75, p90, p99) in paise and INR
- Temporal span and daily/monthly volumes across 12 months
- Network graph topology (degrees, hubs, connected components, path lengths)
- Scenario coverage across all 18 families
- Double-entry balance conservation and financial integrity verification

Outputs:
- Machine-readable JSON: data/processed/synthetic_data_profile.json
- Formatted tabular terminal summary
"""

from __future__ import annotations

import argparse
import csv
import datetime
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import networkx as nx
except ImportError:
    nx = None


def format_inr(paise: int) -> str:
    """Format integer paise as human-readable INR string."""
    rupees = paise / 100.0
    if abs(rupees) >= 10_000_000:
        return f"₹{rupees / 10_000_000:.2f} Cr ({paise:,} paise)"
    if abs(rupees) >= 100_000:
        return f"₹{rupees / 100_000:.2f} Lakh ({paise:,} paise)"
    return f"₹{rupees:,.2f} ({paise:,} paise)"


def compute_percentiles(values: List[int]) -> Dict[str, Any]:
    """Compute exact empirical percentiles from a list of integer values."""
    if not values:
        return {}
    s = sorted(values)
    n = len(s)

    def get_p(p: float) -> int:
        idx = int(round((n - 1) * p))
        return s[max(0, min(n - 1, idx))]

    mean_val = sum(s) / n
    variance = sum((x - mean_val) ** 2 for x in s) / n if n > 1 else 0.0
    std_val = math.sqrt(variance)

    return {
        "count": n,
        "min_paise": s[0],
        "p10_paise": get_p(0.10),
        "p25_paise": get_p(0.25),
        "p50_median_paise": get_p(0.50),
        "p75_paise": get_p(0.75),
        "p90_paise": get_p(0.90),
        "p95_paise": get_p(0.95),
        "p99_paise": get_p(0.99),
        "max_paise": s[-1],
        "mean_paise": round(mean_val, 2),
        "std_paise": round(std_val, 2),
        "min_inr": s[0] / 100.0,
        "p50_median_inr": get_p(0.50) / 100.0,
        "p90_inr": get_p(0.90) / 100.0,
        "p99_inr": get_p(0.99) / 100.0,
        "max_inr": s[-1] / 100.0,
        "mean_inr": round(mean_val / 100.0, 2),
    }


def profile_dataset(data_dir: Path) -> Dict[str, Any]:
    """Read CSV files and Ground Truth, computing comprehensive profile metrics."""
    acc_path = data_dir / "accounts.csv"
    txn_path = data_dir / "transactions.csv"
    cas_path = data_dir / "cases.csv"
    gt_path = data_dir / "ground_truth.json"

    if not acc_path.exists() or not txn_path.exists() or not cas_path.exists():
        raise FileNotFoundError(f"Missing required CSV files in {data_dir}")

    # 1. Accounts
    accounts: List[Dict[str, Any]] = []
    with open(acc_path, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            accounts.append({
                "account_id": r["account_id"],
                "account_type": r["account_type"],
                "opening_balance_paise": int(r["opening_balance_paise"]),
                "history_complete": r["history_complete"].lower() in ("true", "1"),
            })

    # 2. Transactions
    transactions: List[Dict[str, Any]] = []
    with open(txn_path, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            transactions.append({
                "transaction_id": r["transaction_id"],
                "timestamp": r["timestamp"],
                "from_account": r["from_account"],
                "to_account": r["to_account"],
                "amount_paise": int(r["amount_paise"]),
                "transaction_type": r["transaction_type"],
                "case_id": r["case_id"],
                "evidence_status": r["evidence_status"],
            })

    # 3. Cases
    cases: List[Dict[str, Any]] = []
    with open(cas_path, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            cases.append({
                "case_id": r["case_id"],
                "reported_date": r["reported_date"],
                "reported_amount_paise": int(r["reported_amount_paise"]),
                "status": r["status"],
            })

    # 4. Ground Truth
    ground_truth: Dict[str, Any] = {}
    if gt_path.exists():
        with open(gt_path, mode="r", encoding="utf-8") as f:
            ground_truth = json.load(f)

    # -------------------------------------------------------------
    # Metrics Computation
    # -------------------------------------------------------------
    # Accounts metrics
    acc_by_type = Counter(a["account_type"] for a in accounts)
    incomplete_hist_count = sum(1 for a in accounts if not a["history_complete"])
    acc_opening_balances = [a["opening_balance_paise"] for a in accounts]

    # Transactions metrics
    txn_by_type = Counter(t["transaction_type"] for t in transactions)
    txn_by_evidence = Counter(t["evidence_status"] for t in transactions)
    case_linked_txns = [t for t in transactions if t["case_id"]]
    non_case_txns = [t for t in transactions if not t["case_id"]]

    all_amts = [t["amount_paise"] for t in transactions]
    case_amts = [t["amount_paise"] for t in case_linked_txns]
    legit_amts = [t["amount_paise"] for t in non_case_txns]

    amt_profile_all = compute_percentiles(all_amts)
    amt_profile_case = compute_percentiles(case_amts)
    amt_profile_legit = compute_percentiles(legit_amts)

    # Temporal metrics
    timestamps = [t["timestamp"] for t in transactions]
    timestamps.sort()
    earliest_ts = timestamps[0] if timestamps else ""
    latest_ts = timestamps[-1] if timestamps else ""

    dt_start = datetime.datetime.fromisoformat(earliest_ts.replace("Z", "+00:00"))
    dt_end = datetime.datetime.fromisoformat(latest_ts.replace("Z", "+00:00"))
    timespan_days = (dt_end - dt_start).days + 1

    txns_by_month: Dict[str, int] = defaultdict(int)
    txns_by_day: Dict[str, int] = defaultdict(int)
    for t in transactions:
        month_str = t["timestamp"][:7]  # YYYY-MM
        day_str = t["timestamp"][:10]   # YYYY-MM-DD
        txns_by_month[month_str] += 1
        txns_by_day[day_str] += 1

    daily_counts = list(txns_by_day.values())
    daily_stats = {
        "active_days": len(daily_counts),
        "min_per_day": min(daily_counts) if daily_counts else 0,
        "p50_per_day": sorted(daily_counts)[len(daily_counts) // 2] if daily_counts else 0,
        "max_per_day": max(daily_counts) if daily_counts else 0,
        "mean_per_day": round(sum(daily_counts) / len(daily_counts), 2) if daily_counts else 0,
    }

    # Balance conservation & simulation
    sim_balances: Dict[str, int] = {a["account_id"]: a["opening_balance_paise"] for a in accounts}
    negative_balance_events = 0
    tot_opening = sum(acc_opening_balances)
    tot_ext_inflow = 0
    tot_ext_outflow = 0

    for t in transactions:
        fa = t["from_account"]
        ta = t["to_account"]
        amt = t["amount_paise"]

        if fa.startswith("EXT_"):
            tot_ext_inflow += amt
        else:
            sim_balances[fa] -= amt
            if sim_balances[fa] < 0:
                negative_balance_events += 1

        if ta.startswith("EXT_"):
            tot_ext_outflow += amt
        else:
            sim_balances[ta] += amt

    tot_final = sum(sim_balances.values())
    conservation_valid = (tot_opening + tot_ext_inflow - tot_ext_outflow == tot_final)

    # Graph Network Topology (using NetworkX if available)
    graph_metrics: Dict[str, Any] = {}
    if nx:
        G = nx.DiGraph()
        for a in accounts:
            G.add_node(a["account_id"], type=a["account_type"])
        for t in transactions:
            fa = t["from_account"]
            ta = t["to_account"]
            if not fa.startswith("EXT_") and not ta.startswith("EXT_"):
                G.add_edge(fa, ta)

        in_degrees = [d for _, d in G.in_degree()]
        out_degrees = [d for _, d in G.out_degree()]
        top_in = sorted(G.in_degree(), key=lambda x: x[1], reverse=True)[:5]
        top_out = sorted(G.out_degree(), key=lambda x: x[1], reverse=True)[:5]

        wcc = list(nx.weakly_connected_components(G))
        largest_wcc = max(len(c) for c in wcc) if wcc else 0

        graph_metrics = {
            "num_nodes": G.number_of_nodes(),
            "num_edges": G.number_of_edges(),
            "weakly_connected_components": len(wcc),
            "largest_wcc_size": largest_wcc,
            "max_in_degree": max(in_degrees) if in_degrees else 0,
            "mean_in_degree": round(sum(in_degrees) / len(in_degrees), 2) if in_degrees else 0,
            "max_out_degree": max(out_degrees) if out_degrees else 0,
            "mean_out_degree": round(sum(out_degrees) / len(out_degrees), 2) if out_degrees else 0,
            "top_in_degree_hubs": [{"account_id": a, "in_degree": d} for a, d in top_in],
            "top_out_degree_hubs": [{"account_id": a, "out_degree": d} for a, d in top_out],
        }

    # Case & Scenario metrics
    case_amounts = [c["reported_amount_paise"] for c in cases]
    case_amt_profile = compute_percentiles(case_amounts)

    scenarios_meta = ground_truth.get("scenarios", {})
    scenario_counts = {scen: len(txns) for scen, txns in scenarios_meta.items()}

    profile_report: Dict[str, Any] = {
        "_metadata": {
            "profiled_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "data_directory": str(data_dir.resolve()),
            "generator_seed": ground_truth.get("_metadata", {}).get("random_seed"),
            "generator_version": ground_truth.get("_metadata", {}).get("generator_version"),
        },
        "summary": {
            "total_accounts": len(accounts),
            "total_transactions": len(transactions),
            "total_cases": len(cases),
            "timespan_days": timespan_days,
            "date_range": f"{earliest_ts} to {latest_ts}",
            "case_linked_transactions": len(case_linked_txns),
            "case_linked_percentage": round(len(case_linked_txns) / len(transactions) * 100, 2),
            "non_case_transactions": len(non_case_txns),
            "non_case_percentage": round(len(non_case_txns) / len(transactions) * 100, 2),
        },
        "accounts": {
            "count": len(accounts),
            "by_archetype": dict(acc_by_type),
            "incomplete_history_accounts": incomplete_hist_count,
            "incomplete_history_percentage": round(incomplete_hist_count / len(accounts) * 100, 2),
            "opening_balances": compute_percentiles(acc_opening_balances),
        },
        "transactions": {
            "count": len(transactions),
            "by_type": dict(txn_by_type),
            "by_evidence_status": dict(txn_by_evidence),
            "amount_percentiles_all": amt_profile_all,
            "amount_percentiles_case_linked": amt_profile_case,
            "amount_percentiles_legitimate": amt_profile_legit,
        },
        "cases": {
            "count": len(cases),
            "reported_amount_percentiles": case_amt_profile,
            "total_reported_stolen_paise": sum(case_amounts),
            "total_reported_stolen_inr": sum(case_amounts) / 100.0,
        },
        "temporal_distribution": {
            "timespan_days": timespan_days,
            "daily_stats": daily_stats,
            "monthly_volume": dict(sorted(txns_by_month.items())),
        },
        "network_topology": graph_metrics,
        "scenario_coverage": scenario_counts,
        "financial_integrity": {
            "total_opening_paise": tot_opening,
            "total_ext_inflows_paise": tot_ext_inflow,
            "total_ext_outflows_paise": tot_ext_outflow,
            "total_final_paise": tot_final,
            "conservation_equation_holds": conservation_valid,
            "negative_balance_events": negative_balance_events,
            "zero_negative_balances_verified": (negative_balance_events == 0),
        },
    }

    return profile_report


def print_tabular_summary(report: Dict[str, Any]) -> None:
    """Print clean, structured terminal tables summarizing the dataset."""
    s = report["summary"]
    acc = report["accounts"]
    txn = report["transactions"]
    cas = report["cases"]
    temp = report["temporal_distribution"]
    fi = report["financial_integrity"]
    net = report.get("network_topology", {})

    print("\n" + "=" * 80)
    print("               SMART-FREEZE SYNTHETIC DATASET PROFILE REPORT               ")
    print("=" * 80)
    print(f"Directory:       {report['_metadata']['data_directory']}")
    print(f"Generator Seed:  {report['_metadata']['generator_seed']} ({report['_metadata']['generator_version']})")
    print(f"Date Range:      {s['date_range']} ({s['timespan_days']} days / 12 months)")
    print("-" * 80)
    print("OVERALL METRICS:")
    print(f"  • Total Accounts:      {s['total_accounts']:,} (with {acc['incomplete_history_accounts']} incomplete history = {acc['incomplete_history_percentage']}%)")
    print(f"  • Total Transactions:  {s['total_transactions']:,}")
    print(f"    - Legitimate:        {s['non_case_transactions']:,} ({s['non_case_percentage']}%)")
    print(f"    - Suspected/Case:    {s['case_linked_transactions']:,} ({s['case_linked_percentage']}%)")
    print(f"  • Total Cases:         {s['total_cases']:,} (Total Reported: ₹{cas['total_reported_stolen_inr']:,.2f})")
    print("-" * 80)

    print("ACCOUNT ARCHETYPES:")
    for atype, cnt in acc["by_archetype"].items():
        pct = (cnt / s['total_accounts']) * 100
        print(f"  • {atype:<24} {cnt:>6,} accounts ({pct:>5.1f}%)")
    print("-" * 80)

    print("TRANSACTION AMOUNTS (Empirical Percentiles):")
    p = txn["amount_percentiles_all"]
    print(f"  • Min:        ₹{p['min_inr']:>12,.2f}  ({p['min_paise']:,} paise)")
    print(f"  • p10:        ₹{p.get('p10_paise', 0) / 100:>12,.2f}")
    print(f"  • p25:        ₹{p.get('p25_paise', 0) / 100:>12,.2f}")
    print(f"  • p50 (Med):  ₹{p['p50_median_inr']:>12,.2f}  ({p['p50_median_paise']:,} paise)")
    print(f"  • p75:        ₹{p.get('p75_paise', 0) / 100:>12,.2f}")
    print(f"  • p90:        ₹{p['p90_inr']:>12,.2f}")
    print(f"  • p99:        ₹{p['p99_inr']:>12,.2f}")
    print(f"  • Max:        ₹{p['max_inr']:>12,.2f}  ({p['max_paise']:,} paise)")
    print(f"  • Mean ± Std: ₹{p['mean_inr']:>12,.2f} ± ₹{p['std_paise'] / 100:,.2f}")
    print("-" * 80)

    print("MONTHLY TRANSACTION VOLUME (12 Months):")
    for m, vol in temp["monthly_volume"].items():
        bar = "█" * int(vol / 200)
        print(f"  • {m}: {vol:>6,} txns  {bar}")
    print("-" * 80)

    if net:
        print("NETWORK TOPOLOGY (Directed Account Graph):")
        print(f"  • Internal Nodes: {net.get('num_nodes'):,} | Directed Edges: {net.get('num_edges'):,}")
        print(f"  • Weakly Connected Components: {net.get('weakly_connected_components')} (Largest: {net.get('largest_wcc_size'):,} accounts)")
        print(f"  • Max In-Degree (Hubs): {net.get('max_in_degree')} | Max Out-Degree: {net.get('max_out_degree')}")
        print("-" * 80)

    print("SCENARIO FAMILY COVERAGE (18 Families):")
    scen_cov = report.get("scenario_coverage", {})
    for scen_name, count in scen_cov.items():
        print(f"  • {scen_name:<46} {count:>5,} transactions")
    print("-" * 80)

    print("FINANCIAL CONSERVATION & INTEGRITY AUDIT:")
    print(f"  • Total Opening Balances:  ₹{fi['total_opening_paise'] / 100:>15,.2f}")
    print(f"  • Total External Inflows:  ₹{fi['total_ext_inflows_paise'] / 100:>15,.2f}")
    print(f"  • Total External Outflows: ₹{fi['total_ext_outflows_paise'] / 100:>15,.2f}")
    print(f"  • Net Final Balances:      ₹{fi['total_final_paise'] / 100:>15,.2f}")
    eq_status = "PASS (VERIFIED)" if fi["conservation_equation_holds"] else "FAIL (VIOLATION)"
    neg_status = "PASS (0 negative events)" if fi["zero_negative_balances_verified"] else f"FAIL ({fi['negative_balance_events']} events)"
    print(f"  • Conservation Equation:   {eq_status}")
    print(f"  • Negative Balance Check:  {neg_status}")
    print("=" * 80 + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Profile Smart-Freeze Synthetic Financial Dataset")
    parser.add_argument("--data-dir", type=str, default="data/synthetic", help="Path to synthetic dataset directory")
    parser.add_argument("--output-json", type=str, default="data/processed/synthetic_data_profile.json", help="Path to output JSON profile")
    parser.add_argument("--json-only", action="store_true", help="Output JSON only without terminal table")
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    profile = profile_dataset(data_dir)

    # Save to JSON
    out_json = Path(args.output_json)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    with open(out_json, mode="w", encoding="utf-8") as f:
        json.dump(profile, f, indent=2, sort_keys=True)

    if not args.json_only:
        print_tabular_summary(profile)

    print(f"Profile saved to: {out_json.resolve()}")


if __name__ == "__main__":
    main()
