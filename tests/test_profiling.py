"""Unit tests for FairHold dataset profiling (pipeline.profiling).

Tests:
- Deterministic profiling output
- Accuracy of row/col dimensions, missing counts, duplicate counts
- Accurate monetary amount statistics in paise
- Skipped status for missing dataset directories
- Text and dictionary format representations
"""

from pathlib import Path
import tempfile
import pandas as pd
import pytest

from pipeline.profiling import (
    DatasetProfile,
    profile_elliptic_dataset,
    profile_synthaml_dataset,
    profile_synthetic_dataset,
)


@pytest.fixture
def synthetic_temp_dir():
    """Create a minimal synthetic dataset in a temporary directory."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        p = Path(tmp_dir)

        df_acc = pd.DataFrame([
            {"account_id": "ACC_A", "account_type": "savings", "opening_balance_paise": 10000, "history_complete": True},
            {"account_id": "ACC_B", "account_type": "current", "opening_balance_paise": 20000, "history_complete": True},
        ])
        df_acc.to_csv(p / "accounts.csv", index=False)

        df_case = pd.DataFrame([
            {"case_id": "CASE-2026-001", "reported_date": "2026-01-15T10:00:00Z", "reported_amount_paise": 50000, "status": "open"}
        ])
        df_case.to_csv(p / "cases.csv", index=False)

        df_tx = pd.DataFrame([
            {
                "transaction_id": "TXN_01",
                "timestamp": "2026-01-16T10:00:00Z",
                "from_account": "EXT_ATM",
                "to_account": "ACC_A",
                "amount_paise": 10000,
                "transaction_type": "deposit",
                "case_id": "",
                "evidence_status": "unflagged",
            },
            {
                "transaction_id": "TXN_02",
                "timestamp": "2026-01-16T12:00:00Z",
                "from_account": "ACC_A",
                "to_account": "ACC_B",
                "amount_paise": 4000,
                "transaction_type": "transfer",
                "case_id": "CASE-2026-001",
                "evidence_status": "suspected_fraud",
            },
        ])
        df_tx.to_csv(p / "transactions.csv", index=False)

        yield p


def test_synthetic_profiling_dimensions_and_amounts(synthetic_temp_dir):
    profile = profile_synthetic_dataset(synthetic_temp_dir)
    assert profile.status == "success"
    assert profile.row_counts["accounts"] == 2
    assert profile.row_counts["transactions"] == 2
    assert profile.row_counts["cases"] == 1

    assert profile.amount_statistics["min_amount_paise"] == 4000
    assert profile.amount_statistics["max_amount_paise"] == 10000
    assert profile.amount_statistics["total_turnover_paise"] == 14000
    assert profile.amount_statistics["total_turnover_inr"] == 140.0


def test_synthetic_profiling_missing_dataset():
    with tempfile.TemporaryDirectory() as empty_dir:
        profile = profile_synthetic_dataset(Path(empty_dir) / "non_existent")
        assert profile.status == "skipped"
        assert len(profile.warnings) > 0


def test_profiling_text_and_dict_representations(synthetic_temp_dir):
    profile = profile_synthetic_dataset(synthetic_temp_dir)
    txt = profile.format_text()
    assert "FAIRHOLD DATASET PROFILE: FAIRHOLD_SYNTHETIC" in txt
    assert "Status: SUCCESS" in txt
    assert "total_turnover_paise: 14000" in txt

    d = profile.to_dict()
    assert d["dataset_name"] == "fairhold_synthetic"
    assert d["status"] == "success"


def test_elliptic_profiling_skipped_when_missing():
    with tempfile.TemporaryDirectory() as empty_dir:
        profile = profile_elliptic_dataset(Path(empty_dir) / "no_elliptic")
        assert profile.status == "skipped"
        assert "missing" in profile.warnings[0].lower()


def test_synthaml_profiling_skipped_when_missing():
    with tempfile.TemporaryDirectory() as empty_dir:
        profile = profile_synthaml_dataset(Path(empty_dir) / "no_synthaml")
        assert profile.status == "skipped"
        assert "not found" in profile.warnings[0].lower()
