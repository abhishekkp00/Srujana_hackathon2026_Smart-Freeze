#!/usr/bin/env python3
"""Smart-Freeze Tracing Evaluation Runner.

Executes post-hoc benchmarking and evaluation of fund-tracing algorithms
(Proportional, FIFO, LIBR, Consensus Lien) against synthetic ground-truth
allocations.

CRITICAL ARCHITECTURAL ISOLATION RULE:
Operational tracing and consensus modules never import or access ground truth.
Only this post-hoc evaluation runner reads `data/synthetic/ground_truth.json`
to evaluate errors, match rates, and empirical divergence.

Usage:
    python3 evaluation/run_tracing_evaluation.py
    python3 evaluation/run_tracing_evaluation.py --output data/processed/tracing_evaluation_report.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Ensure repository root is on sys.path
WORKSPACE_DIR = Path(__file__).resolve().parent.parent
if str(WORKSPACE_DIR) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_DIR))

from engine.consensus_lien import ConsensusLienEngine
from evaluation.tracing_metrics import TracingMetricsCalculator
from pipeline.adapters.synthetic_adapter import SyntheticAdapter

DEFAULT_DATA_DIR = WORKSPACE_DIR / "data" / "synthetic"
DEFAULT_OUTPUT_FILE = WORKSPACE_DIR / "data" / "processed" / "tracing_evaluation_report.json"

CASE_ORIGINS = {
    "CASE-2026-001": "TXN_0009",
    "CASE-2026-002": "TXN_0038",
    "CASE-2026-003": "TXN_0067",
}


def load_ground_truth(data_dir: Path) -> Dict[str, Any]:
    """Load ground-truth labels strictly for evaluation purposes."""
    gt_file = data_dir / "ground_truth.json"
    if not gt_file.exists():
        raise FileNotFoundError(f"Evaluation ground-truth file not found: {gt_file}")
    with open(gt_file, "r", encoding="utf-8") as f:
        return json.load(f)


def evaluate_cases(
    data_dir: Path,
    output_file: Optional[Path] = None,
) -> Dict[str, Any]:
    """Execute evaluation across synthetic cases and compute structured metrics."""
    gt_data = load_ground_truth(data_dir)
    adapter = SyntheticAdapter(data_dir)
    accounts, txns, cases = adapter.load_dataset()

    case_evaluations: List[Dict[str, Any]] = []
    scenarios_summary: Dict[str, Any] = {}

    for case_id, origin_tx in CASE_ORIGINS.items():
        case_gt = gt_data["cases"].get(case_id, {})
        expected_alloc = case_gt.get("expected_allocations")

        # Run Consensus Lien (which runs Proportional, FIFO, and LIBR independently)
        consensus_res = ConsensusLienEngine.run_all_methods(
            accounts=accounts,
            transactions=txns,
            source_transaction_id=origin_tx,
            source_case_id=case_id,
        )

        case_entry: Dict[str, Any] = {
            "case_id": case_id,
            "origin_transaction_id": origin_tx,
            "initial_suspected_amount_paise": consensus_res.initial_suspected_amount_paise,
            "consensus_status": consensus_res.status,
            "total_lower_retained_paise": consensus_res.total_lower_retained_paise,
            "total_upper_retained_paise": consensus_res.total_upper_retained_paise,
            "overall_disagreement_paise": consensus_res.overall_disagreement_paise,
            "account_liens": {k: v.to_dict() for k, v in consensus_res.account_liens.items()},
            "evaluation_available": expected_alloc is not None,
        }

        # If ground-truth allocations are defined for this case, compute benchmark metrics
        if expected_alloc is not None:
            gt_retained: Dict[str, int] = {}
            for acc, details in expected_alloc.items():
                if "retained_suspected_paise" in details:
                    gt_retained[acc] = int(details["retained_suspected_paise"])

            prop_retained = consensus_res.proportional_result.retained_suspected_paise if consensus_res.proportional_result else {}
            fifo_retained = consensus_res.fifo_result.retained_suspected_paise if consensus_res.fifo_result else {}
            libr_retained = consensus_res.libr_result.retained_suspected_paise if consensus_res.libr_result else {}

            # Consensus Lower & Upper bounds as estimates
            lower_retained = {acc: lien.lower_estimate_paise for acc, lien in consensus_res.account_liens.items()}
            upper_retained = {acc: lien.upper_estimate_paise for acc, lien in consensus_res.account_liens.items()}

            method_reports = {
                "proportional": TracingMetricsCalculator.evaluate_method_allocations(
                    "Proportional", case_id, prop_retained, gt_retained
                ).to_dict(),
                "fifo": TracingMetricsCalculator.evaluate_method_allocations(
                    "FIFO", case_id, fifo_retained, gt_retained
                ).to_dict(),
                "libr": TracingMetricsCalculator.evaluate_method_allocations(
                    "LIBR", case_id, libr_retained, gt_retained
                ).to_dict(),
                "consensus_lower": TracingMetricsCalculator.evaluate_method_allocations(
                    "Consensus_Lower", case_id, lower_retained, gt_retained
                ).to_dict(),
                "consensus_upper": TracingMetricsCalculator.evaluate_method_allocations(
                    "Consensus_Upper", case_id, upper_retained, gt_retained
                ).to_dict(),
            }
            case_entry["method_evaluations"] = method_reports

        case_evaluations.append(case_entry)

    # Scenarios breakdown
    scenario_tx_counts = {scen: len(tx_list) for scen, tx_list in gt_data.get("scenarios", {}).items()}

    final_report = {
        "evaluation_metadata": {
            "title": "Smart-Freeze Tracing Algorithm Evaluation Report",
            "generator_seed": gt_data.get("_metadata", {}).get("random_seed", 42),
            "total_cases_evaluated": len(case_evaluations),
            "cases_with_ground_truth": sum(1 for c in case_evaluations if c["evaluation_available"]),
            "scenario_coverage": scenario_tx_counts,
            "disclaimer": "Empirical evaluation on controlled synthetic data. Performance on synthetic scenarios "
                          "does not represent production bank accuracy claims. Consensus bounds are investigative estimates.",
        },
        "cases": case_evaluations,
    }

    if output_file:
        output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(final_report, f, indent=2)
        print(f"[+] Evaluation report successfully saved to: {output_file}")

    return final_report


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Smart-Freeze Fund-Tracing Ground-Truth Evaluation Runner"
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=DEFAULT_DATA_DIR,
        help=f"Path to synthetic data directory (default: {DEFAULT_DATA_DIR})",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_FILE,
        help=f"Path to write evaluation JSON report (default: {DEFAULT_OUTPUT_FILE})",
    )

    args = parser.parse_args()

    print("=" * 70)
    print("SMART-FREEZE: FUND-TRACING GROUND-TRUTH EVALUATION")
    print("=" * 70)
    print(f"Data Directory:  {args.data_dir}")
    print(f"Output Report:   {args.output}\n")

    report = evaluate_cases(args.data_dir, args.output)

    print("\n--- Consensus Lien & Method Divergence Summary ---")
    for c in report["cases"]:
        cid = c["case_id"]
        init = c["initial_suspected_amount_paise"]
        disagree = c["overall_disagreement_paise"]
        print(f"\nCase: {cid} (Origin: {c['origin_transaction_id']} | ₹{init / 100:,.2f})")
        print(f"  Consensus Status: {c['consensus_status']}")
        print(f"  Total Lower Bound: ₹{c['total_lower_retained_paise'] / 100:,.2f}")
        print(f"  Total Upper Bound: ₹{c['total_upper_retained_paise'] / 100:,.2f}")
        print(f"  Total Disagreement: ₹{disagree / 100:,.2f} ({disagree:,} paise)")

        print("  Accounts Evaluated:")
        for acc_id, lien in c["account_liens"].items():
            print(
                f"    {acc_id:<20} | Prop: ₹{lien['proportional_paise']/100:>9,.2f} | "
                f"FIFO: ₹{lien['fifo_paise']/100:>9,.2f} | LIBR: ₹{lien['libr_paise']/100:>9,.2f} | "
                f"Range: [₹{lien['lower_estimate_paise']/100:,.2f} - ₹{lien['upper_estimate_paise']/100:,.2f}] "
                f"(Δ ₹{lien['disagreement_paise']/100:,.2f})"
            )

        if c.get("method_evaluations"):
            print("  Benchmark Accuracy against Ground Truth:")
            for m_name, m_rep in c["method_evaluations"].items():
                print(
                    f"    {m_name:<16}: Exact Matches={m_rep['exact_match_count']}/{m_rep['total_accounts']} "
                    f"({m_rep['exact_match_rate']*100:.1f}%) | MAE=₹{m_rep['mean_absolute_error_inr']:,.2f}"
                )

    print("\n" + "=" * 70)
    print("Evaluation completed. Empirical metrics for decision support; not a production accuracy claim.")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
