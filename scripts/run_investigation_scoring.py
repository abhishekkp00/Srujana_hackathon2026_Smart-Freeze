#!/usr/bin/env python3
"""Smart-Freeze Explainable Investigation Priority Scoring CLI Tool.

Executes deterministic, explainable priority scoring across cases in the synthetic
operational ledger, producing component breakdowns (B, T, H), evidence coverage,
supporting transaction references, and ranked triage summaries for authorized human review.

Usage:
    python3 scripts/run_investigation_scoring.py
    python3 scripts/run_investigation_scoring.py --case-id CASE-2026-001 --verbose
    python3 scripts/run_investigation_scoring.py --output data/processed/investigation_scores.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import pandas as pd

# Ensure repository root is on sys.path
WORKSPACE_DIR = Path(__file__).resolve().parent.parent
if str(WORKSPACE_DIR) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_DIR))

from engine.investigation_score import (
    GOVERNANCE_DISCLAIMER,
    InvestigationScoringEngine,
    ScoringConfig,
)
from pipeline.adapters.synthetic_adapter import SyntheticAdapter


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Smart-Freeze Investigation Priority Scoring CLI"
    )
    parser.add_argument(
        "--case-id",
        type=str,
        default=None,
        help="Specific case ID to score (default: score and rank all cases)",
    )
    parser.add_argument(
        "--synthetic-dir",
        type=Path,
        default=WORKSPACE_DIR / "data" / "synthetic",
        help="Synthetic data directory (default: data/synthetic)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional path to write JSON scoring results",
    )
    parser.add_argument(
        "--cutoff",
        type=str,
        default=None,
        help="Optional ISO 8601 UTC temporal cutoff (e.g. 2026-01-16T10:00:00Z)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print detailed component subfactors, supporting transaction IDs, and factors",
    )

    args = parser.parse_args()

    adapter = SyntheticAdapter(args.synthetic_dir)
    if not adapter.exists():
        print(f"[-] Error: Synthetic dataset files missing in {args.synthetic_dir}", file=sys.stderr)
        return 1

    cases_df = pd.read_csv(adapter.cases_path)
    txs_df = pd.read_csv(adapter.transactions_path)
    accs_df = pd.read_csv(adapter.accounts_path)

    config = ScoringConfig()
    engine = InvestigationScoringEngine(config=config)

    if args.case_id:
        target_case = cases_df[cases_df["case_id"] == args.case_id]
        if target_case.empty:
            print(f"[-] Error: Case '{args.case_id}' not found in {adapter.cases_path}", file=sys.stderr)
            return 1
        scored = [
            engine.score_case(
                case=target_case.iloc[0].to_dict(),
                transactions=txs_df,
                accounts=accs_df,
                cutoff_timestamp=args.cutoff,
                baseline_transactions=txs_df,
            )
        ]
    else:
        scored = engine.score_all_cases(
            cases=cases_df,
            transactions=txs_df,
            accounts=accs_df,
            cutoff_timestamp=args.cutoff,
        )

    ranked = engine.rank_cases(scored)

    print("=" * 80)
    print("SMART-FREEZE: INVESTIGATION PRIORITY SCORING REPORT")
    print("=" * 80)
    print(f"Configuration Version: {config.version}")
    print(f"Provisional Weights:   B={config.weight_b:.2f}, T={config.weight_t:.2f}, H={config.weight_h:.2f}")
    print(f"Min Evidence Coverage: {config.min_evidence_coverage:.0%}")
    print(f"Cases Evaluated:       {len(ranked)}")
    print("-" * 80)

    for rank_idx, s in enumerate(ranked, start=1):
        score_str = f"{s.final_score:.2f}/100" if s.final_score is not None else "UNSCORED"
        rep_amt_inr = s.reported_amount_paise / 100.0
        print(f"\n[Rank #{rank_idx}] Case: {s.case_id}")
        print(f"  Priority Band:     {s.priority_band} (Score: {score_str})")
        print(f"  Evaluation Status: {s.status} (Coverage: {s.evidence_coverage:.1%})")
        print(f"  Reported Amount:   ₹{rep_amt_inr:,.2f} | Date: {s.reported_date}")
        print("  Component Scores:")
        print(f"    • {s.component_b.component_name:24}: {s.component_b.score if s.component_b.score is not None else 'N/A'} (Weight {s.component_b.weight:.2f})")
        print(f"    • {s.component_t.component_name:24}: {s.component_t.score if s.component_t.score is not None else 'N/A'} (Weight {s.component_t.weight:.2f})")
        print(f"    • {s.component_h.component_name:24}: {s.component_h.score if s.component_h.score is not None else 'N/A'} (Weight {s.component_h.weight:.2f})")

        if s.positive_factors:
            print("  Priority Escalating Factors:")
            for pf in s.positive_factors:
                print(f"    [+] {pf}")

        if s.mitigating_factors:
            print("  Mitigating Indicators:")
            for mf in s.mitigating_factors:
                print(f"    [-] {mf}")

        if s.data_quality_warnings:
            print("  Data Quality & Uncertainty Warnings:")
            for w in s.data_quality_warnings:
                print(f"    [!] {w}")

        if args.verbose:
            print("  Supporting Evidence Provenance:")
            print(f"    Transactions ({len(s.supporting_transaction_ids)}): {', '.join(s.supporting_transaction_ids)}")
            print(f"    Accounts     ({len(s.supporting_account_ids)}): {', '.join(s.supporting_account_ids)}")
            print("    Component Subfactors:")
            print(f"      B Subfactors: {json.dumps(s.component_b.subfactors)}")
            print(f"      T Subfactors: {json.dumps(s.component_t.subfactors)}")
            print(f"      H Subfactors: {json.dumps(s.component_h.subfactors)}")

    print("\n" + "=" * 80)
    print("LEGAL & GOVERNANCE NOTICE:")
    print(GOVERNANCE_DISCLAIMER)
    print("=" * 80)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        out_data = {
            "config": {
                "version": config.version,
                "weights": {"B": config.weight_b, "T": config.weight_t, "H": config.weight_h},
                "min_coverage": config.min_evidence_coverage,
            },
            "cases_count": len(ranked),
            "ranked_cases": [s.to_dict() for s in ranked],
            "disclaimer": GOVERNANCE_DISCLAIMER,
        }
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(out_data, f, indent=2)
        print(f"[+] Full JSON scoring report saved to: {args.output}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
