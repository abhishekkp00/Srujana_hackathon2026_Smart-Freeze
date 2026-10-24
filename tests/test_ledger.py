"""Unit tests for FairHold ledger reconstruction coordinator (engine.ledger).

Tests:
1. End-to-end ledger reconstruction on real operational synthetic data.
2. Global balance conservation equation holds strictly across all accounts.
3. Deterministic chronological sorting with transaction_id tie-breaking for equal timestamps.
4. Duplicate transaction IDs are rejected.
5. Broken account references are rejected.
6. Unsupported negative balances are rejected.
7. Incomplete history accounts are explicitly flagged in warnings.
8. Operational output files are generated and contain zero hidden ground-truth fields.
"""

import json
from pathlib import Path
import tempfile
import pandas as pd
import pytest

from engine.balances import (
    BalanceConservationError,
    BalanceReconstructionError,
    NegativeBalanceError,
)
from engine.ledger import LedgerReconstructionEngine

WORKSPACE_DIR = Path(__file__).resolve().parent.parent
REAL_SYNTHETIC_DIR = WORKSPACE_DIR / "data" / "synthetic"


def test_deterministic_sorting_with_equal_timestamps():
    """Verify deterministic tie-breaking by transaction_id when timestamps are identical."""
    unordered_txs = [
        {"transaction_id": "TXN_0003", "timestamp": "2026-01-15T10:00:00Z"},
        {"transaction_id": "TXN_0001", "timestamp": "2026-01-15T10:00:00Z"},
        {"transaction_id": "TXN_0002", "timestamp": "2026-01-15T10:00:00Z"},
        {"transaction_id": "TXN_0000", "timestamp": "2026-01-15T09:00:00Z"},
    ]
    sorted_txs = LedgerReconstructionEngine.sort_transactions_deterministically(unordered_txs)
    ids = [t["transaction_id"] for t in sorted_txs]
    assert ids == ["TXN_0000", "TXN_0001", "TXN_0002", "TXN_0003"]


def test_real_synthetic_ledger_reconstruction():
    """Verify reconstruction on the real generated synthetic dataset."""
    engine = LedgerReconstructionEngine(REAL_SYNTHETIC_DIR)
    tracker, graph, report = engine.reconstruct()

    assert report.is_valid is True
    assert report.accounts_count == 38
    assert report.transactions_count == 119
    assert report.conservation_verified is True

    # Check conservation: Final = Opening + Deposits - Withdrawals
    expected_final = (
        report.total_opening_balance_paise
        + report.total_external_deposits_paise
        - report.total_external_withdrawals_paise
    )
    assert report.total_final_balance_paise == expected_final

    # Incomplete history account is flagged
    assert "ACC_INCOMPLETE_01" in report.incomplete_history_accounts


def test_duplicate_transaction_id_rejected():
    accounts_df = pd.DataFrame([
        {"account_id": "ACC_1", "account_type": "savings", "opening_balance_paise": 100000, "history_complete": True},
        {"account_id": "ACC_2", "account_type": "savings", "opening_balance_paise": 100000, "history_complete": True},
    ])
    # Duplicate transaction_id TXN_01
    transactions_df = pd.DataFrame([
        {"transaction_id": "TXN_01", "timestamp": "2026-01-15T10:00:00Z", "from_account": "ACC_1", "to_account": "ACC_2", "amount_paise": 10000, "transaction_type": "transfer", "case_id": "", "evidence_status": "unflagged"},
        {"transaction_id": "TXN_01", "timestamp": "2026-01-15T11:00:00Z", "from_account": "ACC_1", "to_account": "ACC_2", "amount_paise": 10000, "transaction_type": "transfer", "case_id": "", "evidence_status": "unflagged"},
    ])

    engine = LedgerReconstructionEngine(REAL_SYNTHETIC_DIR)
    with pytest.raises(BalanceReconstructionError) as exc:
        engine.reconstruct(accounts_df=accounts_df, transactions_df=transactions_df)
    assert "duplicate transaction_id" in str(exc.value).lower()


def test_broken_account_reference_rejected():
    accounts_df = pd.DataFrame([
        {"account_id": "ACC_1", "account_type": "savings", "opening_balance_paise": 100000, "history_complete": True},
    ])
    # ACC_2 does not exist in accounts
    transactions_df = pd.DataFrame([
        {"transaction_id": "TXN_01", "timestamp": "2026-01-15T10:00:00Z", "from_account": "ACC_1", "to_account": "ACC_2", "amount_paise": 10000, "transaction_type": "transfer", "case_id": "", "evidence_status": "unflagged"},
    ])

    engine = LedgerReconstructionEngine(REAL_SYNTHETIC_DIR)
    with pytest.raises(BalanceReconstructionError) as exc:
        engine.reconstruct(accounts_df=accounts_df, transactions_df=transactions_df)
    assert "unknown internal to_account 'ACC_2'" in str(exc.value)


def test_negative_balance_overdraft_rejected():
    accounts_df = pd.DataFrame([
        {"account_id": "ACC_1", "account_type": "savings", "opening_balance_paise": 10000, "history_complete": True},
        {"account_id": "ACC_2", "account_type": "savings", "opening_balance_paise": 50000, "history_complete": True},
    ])
    # ACC_1 only has 10,000 paise, attempts to transfer 20,000 paise
    transactions_df = pd.DataFrame([
        {"transaction_id": "TXN_01", "timestamp": "2026-01-15T10:00:00Z", "from_account": "ACC_1", "to_account": "ACC_2", "amount_paise": 20000, "transaction_type": "transfer", "case_id": "", "evidence_status": "unflagged"},
    ])

    engine = LedgerReconstructionEngine(REAL_SYNTHETIC_DIR)
    with pytest.raises(NegativeBalanceError) as exc:
        engine.reconstruct(accounts_df=accounts_df, transactions_df=transactions_df)
    assert "overdraft" in str(exc.value).lower()


def test_artifacts_export_and_ground_truth_isolation():
    """Verify that export creates expected artifacts without hidden ground truth."""
    engine = LedgerReconstructionEngine(REAL_SYNTHETIC_DIR)
    tracker, graph, report = engine.reconstruct()

    with tempfile.TemporaryDirectory() as tmp_dir:
        artifacts = engine.export_processed_artifacts(
            output_dir=tmp_dir,
            tracker=tracker,
            graph=graph,
            report=report,
        )

        assert "balance_history" in artifacts
        assert "ledger_validation_report" in artifacts
        assert "transaction_graph_summary" in artifacts

        # Verify balance_history.csv contains no ground-truth fields
        df_history = pd.read_csv(artifacts["balance_history"])
        for col in df_history.columns:
            assert "ground_truth" not in col.lower()
            assert "lot_id" not in col.lower()
            assert "_scenario" not in col.lower()

        # Verify JSON report contains no ground truth
        with open(artifacts["ledger_validation_report"], "r", encoding="utf-8") as f:
            report_data = json.load(f)
            assert "ground_truth" not in str(report_data).lower()
