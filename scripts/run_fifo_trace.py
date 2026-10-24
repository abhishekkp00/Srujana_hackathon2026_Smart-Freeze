#!/usr/bin/env python3
"""Smart-Freeze First-In, First-Out (FIFO) Fund-Tracing CLI Tool.

Executes deterministic FIFO fund tracing from a designated suspected fraud origin
transaction, tracking ordered source-lot consumption across internal accounts
and external withdrawals using exact integer-paise arithmetic.

Usage:
    python3 scripts/run_fifo_trace.py --tx-id TXN_0009 --case-id CASE-2026-001
    python3 scripts/run_fifo_trace.py --tx-id TXN_0009 --verbose
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Ensure repository root is on sys.path
WORKSPACE_DIR = Path(__file__).resolve().parent.parent
if str(WORKSPACE_DIR) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_DIR))

from engine.fifo import FIFOTracer
from pipeline.adapters.synthetic_adapter import SyntheticAdapter


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Smart-Freeze FIFO Fund-Tracing CLI"
    )
    parser.add_argument(
        "--tx-id",
        type=str,
        default="TXN_0009",
        help="Designated suspected source transaction ID (default: TXN_0009)",
    )
    parser.add_argument(
        "--case-id",
        type=str,
        default="CASE-2026-001",
        help="Associated fraud case ID (default: CASE-2026-001)",
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
        help="Optional path to write full JSON trace result",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print detailed allocation explanations for all hops",
    )

    args = parser.parse_args()

    print("=" * 70)
    print("SMART-FREEZE: FIRST-IN, FIRST-OUT (FIFO) FUND-TRACING RUN")
    print("=" * 70)
    print(f"Source Transaction:  {args.tx_id}")
    print(f"Source Case:         {args.case_id}")
    print(f"Data Directory:      {args.synthetic_dir}\n")

    try:
        adapter = SyntheticAdapter(args.synthetic_dir)
        accounts, txns, cases = adapter.load_dataset()

        tracer = FIFOTracer(accounts, txns)
        result = tracer.trace_source_transaction(
            source_transaction_id=args.tx_id,
            source_case_id=args.case_id,
        )

        init_amt = result.initial_suspected_amount_paise
        tot_retained = result.total_retained_suspected()
        tot_withdrawn = result.total_withdrawn_suspected()

        print("--- Tracing Overview ---")
        print(f"Initial Suspected Amount: ₹{init_amt / 100:,.2f} ({init_amt:,} paise)")
        print(f"Retained in Internal Accounts: ₹{tot_retained / 100:,.2f} ({tot_retained:,} paise)")
        print(f"Attributed to External Outflows: ₹{tot_withdrawn / 100:,.2f} ({tot_withdrawn:,} paise)")
        print(
            f"Conservation Check:       "
            f"{'CONSERVED [PASS]' if (tot_retained + tot_withdrawn == init_amt) else 'VIOLATED [FAIL]'}"
        )

        print(f"\n--- Transfer Hops Traversed ({len(result.transfer_hops)}) ---")
        for hop in result.transfer_hops:
            print(
                f"  Hop {hop.hop_index:02d} | {hop.transaction_id} | {hop.from_account} -> {hop.to_account} "
                f"| Suspected Flow: ₹{hop.suspected_amount_paise / 100:,.2f} ({hop.suspected_amount_paise:,} paise) "
                f"| Total Tx: ₹{hop.total_amount_paise / 100:,.2f}"
            )

        print("\n--- Downstream Accounts Retaining Suspected Funds (FIFO) ---")
        for acc_id, amt in sorted(
            result.retained_suspected_paise.items(), key=lambda x: x[1], reverse=True
        ):
            pct = (amt / init_amt * 100.0) if init_amt > 0 else 0.0
            is_inc = acc_id in result.incomplete_history_accounts
            flag_str = " [!] INCOMPLETE HISTORY" if is_inc else ""
            print(
                f"  {acc_id:<22}: ₹{amt / 100:>10,.2f} ({amt:>10,} paise) [{pct:>5.1f}% of source]{flag_str}"
            )

        if result.withdrawn_suspected_paise:
            print("\n--- External Outflows Attributed to Suspected Funds (FIFO) ---")
            for ext_acc, amt in sorted(
                result.withdrawn_suspected_paise.items(), key=lambda x: x[1], reverse=True
            ):
                pct = (amt / init_amt * 100.0) if init_amt > 0 else 0.0
                print(
                    f"  {ext_acc:<22}: ₹{amt / 100:>10,.2f} ({amt:>10,} paise) [{pct:>5.1f}% of source]"
                )

        if args.verbose and result.explanations:
            print("\n--- Step-by-Step Mathematical Explanations (FIFO) ---")
            for exp in result.explanations:
                print(
                    f"\n[Transaction {exp.transaction_id} - {exp.account_id} -> {exp.counterparty_account}]"
                )
                print(exp.explanation_text)

        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with open(args.output, "w", encoding="utf-8") as f:
                json.dump(result.to_dict(), f, indent=2)
            print(f"\n[+] Full trace result saved to: {args.output}")

        print("\n" + "=" * 70)
        print("Tracing complete. Decision-support estimate only; not a legal conclusion.")
        print("=" * 70)
        return 0

    except Exception as exc:
        print(f"\n[ERROR] FIFO tracing failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
