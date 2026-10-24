"""FairHold Ledger Reconstruction Coordinator.

Orchestrates loading, validation, deterministic chronological sorting, balance
reconstruction, and transaction graph generation for FairHold's synthetic financial ledger.
Verifies global balance conservation and exports audit-ready processed artifacts.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
import networkx as nx
import pandas as pd

from engine.balances import (
    BalanceConservationError,
    BalanceReconstructionError,
    BalanceTracker,
    NegativeBalanceError,
)
from engine.models import GraphSummary, LedgerValidationReport
from engine.transaction_graph import TransactionGraphEngine
from pipeline.adapters.synthetic_adapter import SyntheticAdapter
from pipeline.schemas import (
    CANONICAL_ACCOUNT_COLUMNS,
    CANONICAL_TRANSACTION_COLUMNS,
    EXTERNAL_ACCOUNT_PREFIX,
)
from pipeline.validation import (
    validate_iso_timestamp,
    validate_synthetic_accounts,
    validate_synthetic_transactions,
)


class LedgerReconstructionEngine:
    """End-to-end ledger validation, balance reconstruction, and graph builder."""

    def __init__(self, data_dir: Path | str):
        self.data_dir = Path(data_dir)
        self.adapter = SyntheticAdapter(self.data_dir)

    def load_and_validate_inputs(
        self,
    ) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        """Load accounts, transactions, and cases using the Step 2 synthetic adapter."""
        if not self.adapter.exists():
            raise FileNotFoundError(
                f"Synthetic operational files missing in directory: {self.data_dir}"
            )
        return self.adapter.load_dataset()

    @staticmethod
    def sort_transactions_deterministically(
        transactions: List[Dict[str, Any]] | pd.DataFrame,
    ) -> List[Dict[str, Any]]:
        """Sort transactions deterministically using (timestamp, transaction_id).

        Tie-breaking rule: If two transactions share the identical timestamp,
        they are ordered lexicographically by unique transaction_id.
        """
        if isinstance(transactions, pd.DataFrame):
            tx_list = transactions.to_dict(orient="records")
        else:
            tx_list = list(transactions)

        return sorted(tx_list, key=lambda t: (str(t["timestamp"]), str(t["transaction_id"])))

    def reconstruct(
        self,
        accounts_df: Optional[pd.DataFrame] = None,
        transactions_df: Optional[pd.DataFrame] = None,
    ) -> Tuple[BalanceTracker, nx.MultiDiGraph, LedgerValidationReport]:
        """Perform deterministic ledger reconstruction and balance conservation audit.

        Returns:
            Tuple of (BalanceTracker, MultiDiGraph, LedgerValidationReport).
        """
        if accounts_df is None or transactions_df is None:
            loaded_acc, loaded_tx, _ = self.load_and_validate_inputs()
            accounts_df = accounts_df if accounts_df is not None else loaded_acc
            transactions_df = transactions_df if transactions_df is not None else loaded_tx

        # Validate accounts
        v_acc = validate_synthetic_accounts(accounts_df)
        if not v_acc.is_valid:
            raise BalanceReconstructionError(f"Account validation failed: {v_acc.errors}")

        valid_acc_ids = set(accounts_df["account_id"].astype(str).str.strip().unique())

        # Validate transactions
        v_tx = validate_synthetic_transactions(transactions_df, valid_accounts=valid_acc_ids)
        if not v_tx.is_valid:
            raise BalanceReconstructionError(f"Transaction validation failed: {v_tx.errors}")

        # Deterministic chronological ordering
        sorted_txs = self.sort_transactions_deterministically(transactions_df)

        # Initialize BalanceTracker
        tracker = BalanceTracker(accounts_df)
        opening_total = tracker.get_total_opening_balance()

        # Track turnover and counts
        total_turnover = 0
        internal_count = 0
        deposit_count = 0
        withdrawal_count = 0
        ext_deposits_total = 0
        ext_withdrawals_total = 0

        # Sequentially apply transactions
        for tx in sorted_txs:
            amount = int(tx["amount_paise"])
            total_turnover += amount

            from_acc = str(tx["from_account"]).strip()
            to_acc = str(tx["to_account"]).strip()

            is_from_ext = from_acc.startswith(EXTERNAL_ACCOUNT_PREFIX)
            is_to_ext = to_acc.startswith(EXTERNAL_ACCOUNT_PREFIX)

            if is_from_ext:
                deposit_count += 1
                ext_deposits_total += amount
            elif is_to_ext:
                withdrawal_count += 1
                ext_withdrawals_total += amount
            else:
                internal_count += 1

            tracker.apply_transaction(tx)

        final_total = tracker.get_total_ledger_balance()

        # Global balance conservation formula check:
        # Final_Total = Opening_Total + External_Deposits - External_Withdrawals
        expected_final = opening_total + ext_deposits_total - ext_withdrawals_total
        conservation_verified = (final_total == expected_final)

        if not conservation_verified:
            raise BalanceConservationError(
                f"Global ledger conservation violation: Final balance ({final_total} paise) "
                f"!= Expected balance ({expected_final} paise) based on "
                f"Opening ({opening_total}) + Deposits ({ext_deposits_total}) - Withdrawals ({ext_withdrawals_total})"
            )

        # Build transaction graph
        final_balances_map = {
            acc_id: acc.current_balance_paise for acc_id, acc in tracker.accounts.items()
        }
        graph = TransactionGraphEngine.build_graph(
            accounts_df,
            sorted_txs,
            final_balances=final_balances_map,
        )

        # Identify accounts with incomplete history
        incomplete_accs = [
            acc_id for acc_id, acc in tracker.accounts.items() if not acc.history_complete
        ]

        warnings: List[str] = list(v_acc.warnings) + list(v_tx.warnings)
        if incomplete_accs:
            warnings.append(
                f"Reconstructed balances for {len(incomplete_accs)} account(s) have incomplete "
                f"historical context: {incomplete_accs}. Their balance histories must not be treated as complete."
            )

        report = LedgerValidationReport(
            is_valid=True,
            accounts_count=len(accounts_df),
            transactions_count=len(sorted_txs),
            internal_transfers_count=internal_count,
            external_deposits_count=deposit_count,
            external_withdrawals_count=withdrawal_count,
            total_turnover_paise=total_turnover,
            total_opening_balance_paise=opening_total,
            total_final_balance_paise=final_total,
            total_external_deposits_paise=ext_deposits_total,
            total_external_withdrawals_paise=ext_withdrawals_total,
            conservation_verified=conservation_verified,
            incomplete_history_accounts=incomplete_accs,
            errors=[],
            warnings=warnings,
        )

        return tracker, graph, report

    def export_processed_artifacts(
        self,
        output_dir: Path | str,
        tracker: BalanceTracker,
        graph: nx.MultiDiGraph,
        report: LedgerValidationReport,
    ) -> Dict[str, Path]:
        """Export balance_history.csv, ledger_validation_report.json, and transaction_graph_summary.json.

        Guarantees that no hidden ground truth fields are exposed in operational outputs.
        """
        out_p = Path(output_dir)
        out_p.mkdir(parents=True, exist_ok=True)

        # 1. balance_history.csv
        df_history = tracker.get_balance_history_dataframe()
        history_path = out_p / "balance_history.csv"
        df_history.to_csv(history_path, index=False)

        # 2. ledger_validation_report.json
        report_path = out_p / "ledger_validation_report.json"
        with open(report_path, mode="w", encoding="utf-8") as f:
            json.dump(report.to_dict(), f, indent=2)

        # 3. transaction_graph_summary.json
        summary = TransactionGraphEngine.summarize_graph(graph)
        graph_summary_path = out_p / "transaction_graph_summary.json"
        with open(graph_summary_path, mode="w", encoding="utf-8") as f:
            json.dump(summary.to_dict(), f, indent=2)

        return {
            "balance_history": history_path,
            "ledger_validation_report": report_path,
            "transaction_graph_summary": graph_summary_path,
        }
