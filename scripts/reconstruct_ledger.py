#!/usr/bin/env python3
"""Smart-Freeze Ledger Reconstruction and Transaction Graph CLI.

Validates the operational synthetic financial ledger, calculates chronological
balance histories with exact integer-paise arithmetic, builds the directed transaction
graph, verifies value conservation, and outputs processed artifacts to data/processed/.

Usage:
    python3 scripts/reconstruct_ledger.py
    python3 scripts/reconstruct_ledger.py --synthetic-dir data/synthetic --output-dir data/processed
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Ensure repository root is on sys.path
WORKSPACE_DIR = Path(__file__).resolve().parent.parent
if str(WORKSPACE_DIR) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_DIR))

from engine.ledger import LedgerReconstructionEngine
from engine.transaction_graph import TransactionGraphEngine


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Smart-Freeze Ledger Reconstruction and Transaction Graph Generator"
    )
    parser.add_argument(
        "--synthetic-dir",
        type=Path,
        default=WORKSPACE_DIR / "data" / "synthetic",
        help="Input synthetic data directory (default: data/synthetic)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=WORKSPACE_DIR / "data" / "processed",
        help="Directory to write processed ledger artifacts (default: data/processed)",
    )

    args = parser.parse_args()

    print("=" * 70)
    print("SMART-FREEZE: LEDGER RECONSTRUCTION & TRANSACTION GRAPH")
    print("=" * 70)
    print(f"Input Directory:  {args.synthetic_dir}")
    print(f"Output Directory: {args.output_dir}\n")

    try:
        engine = LedgerReconstructionEngine(data_dir=args.synthetic_dir)
        tracker, graph, report = engine.reconstruct()
        artifacts = engine.export_processed_artifacts(
            output_dir=args.output_dir,
            tracker=tracker,
            graph=graph,
            report=report,
        )
        graph_summary = TransactionGraphEngine.summarize_graph(graph)

        print("--- Ledger Validation & Reconstruction Summary ---")
        print(f"Accounts Processed:       {report.accounts_count}")
        print(f"Transactions Processed:   {report.transactions_count}")
        print(f"  - Internal Transfers:   {report.internal_transfers_count}")
        print(f"  - External Deposits:    {report.external_deposits_count}")
        print(f"  - External Withdrawals: {report.external_withdrawals_count}")
        print(f"Total Turnover:           ₹{report.total_turnover_paise / 100:,.2f} ({report.total_turnover_paise:,} paise)")
        print(f"Total Opening Balance:    ₹{report.total_opening_balance_paise / 100:,.2f} ({report.total_opening_balance_paise:,} paise)")
        print(f"Total Final Balance:      ₹{report.total_final_balance_paise / 100:,.2f} ({report.total_final_balance_paise:,} paise)")
        print(f"Balance Conservation:     {'VERIFIED [PASS]' if report.conservation_verified else 'VIOLATED [FAIL]'}")

        if report.incomplete_history_accounts:
            print(f"\nIncomplete History Accounts ({len(report.incomplete_history_accounts)}):")
            for acc in report.incomplete_history_accounts:
                print(f"  [!] {acc} (balance history flagged as incomplete)")

        print("\n--- Directed Transaction Graph Summary ---")
        print(f"Internal Account Nodes:   {graph_summary.internal_account_nodes}")
        print(f"Internal Transfer Edges:  {graph_summary.internal_transfer_edges}")
        print(f"Weakly Connected Comps:   {graph_summary.weakly_connected_components}")
        print(f"Isolated Accounts:        {len(graph_summary.isolated_accounts)}")

        print("\n--- Processed Artifacts Generated ---")
        for key, path in artifacts.items():
            print(f"  [+] {key}: {path}")

        print("\n" + "=" * 70)
        print("Reconstruction complete and audit-ready.")
        print("=" * 70)
        return 0

    except Exception as exc:
        print(f"\n[ERROR] Ledger reconstruction failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
