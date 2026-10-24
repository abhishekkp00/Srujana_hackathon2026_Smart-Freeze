"""Smart-Freeze Synthetic Dataset Adapter.

Loads and normalizes the operational synthetic accounts, transactions, and cases.
Enforces integer-paise representation and strict ground-truth isolation.
Operational adapters MUST NEVER access hidden ground truth.
"""

from __future__ import annotations

import csv
import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
import pandas as pd

from pipeline.schemas import (
    CANONICAL_ACCOUNT_COLUMNS,
    CANONICAL_CASE_COLUMNS,
    CANONICAL_TRANSACTION_COLUMNS,
    CanonicalAccount,
    CanonicalCase,
    CanonicalTransaction,
)
from pipeline.validation import (
    validate_synthetic_accounts,
    validate_synthetic_cases,
    validate_synthetic_transactions,
)


class GroundTruthAccessViolationError(PermissionError):
    """Raised when operational components attempt to access hidden ground truth."""
    pass


class SyntheticAdapter:
    """Adapter for Smart-Freeze synthetic operational financial records."""

    def __init__(self, data_dir: Path | str):
        self.data_dir = Path(data_dir)
        self.accounts_path = self.data_dir / "accounts.csv"
        self.transactions_path = self.data_dir / "transactions.csv"
        self.cases_path = self.data_dir / "cases.csv"

    def exists(self) -> bool:
        """Check if all 3 operational CSV files are present."""
        return (
            self.accounts_path.exists()
            and self.transactions_path.exists()
            and self.cases_path.exists()
        )

    def verify_ground_truth_isolation(self, target_path: Path | str) -> None:
        """Verify that the target path does not attempt to access ground_truth.json."""
        name = Path(target_path).name.lower()
        if "ground_truth" in name:
            raise GroundTruthAccessViolationError(
                f"Access Denied: Operational adapter cannot load hidden ground truth '{target_path}'. "
                "Ground truth is strictly isolated for post-hoc evaluation."
            )

    def load_accounts(self) -> pd.DataFrame:
        """Load and validate operational accounts DataFrame."""
        if not self.accounts_path.exists():
            raise FileNotFoundError(f"Accounts file not found: {self.accounts_path}")

        df = pd.read_csv(self.accounts_path)
        v_res = validate_synthetic_accounts(df)
        if not v_res.is_valid:
            raise ValueError(f"Accounts validation failed: {v_res.errors}")

        # Enforce canonical types
        df["account_id"] = df["account_id"].astype(str)
        df["account_type"] = df["account_type"].astype(str)
        df["opening_balance_paise"] = df["opening_balance_paise"].astype("int64")
        df["history_complete"] = df["history_complete"].astype(bool)
        return df

    def load_cases(self) -> pd.DataFrame:
        """Load and validate operational cases DataFrame."""
        if not self.cases_path.exists():
            raise FileNotFoundError(f"Cases file not found: {self.cases_path}")

        df = pd.read_csv(self.cases_path)
        v_res = validate_synthetic_cases(df)
        if not v_res.is_valid:
            raise ValueError(f"Cases validation failed: {v_res.errors}")

        df["case_id"] = df["case_id"].astype(str)
        df["reported_date"] = df["reported_date"].astype(str)
        df["reported_amount_paise"] = df["reported_amount_paise"].astype("int64")
        df["status"] = df["status"].astype(str)
        return df

    def load_transactions(
        self,
        valid_accounts: Optional[Set[str]] = None,
        valid_cases: Optional[Set[str]] = None,
    ) -> pd.DataFrame:
        """Load and validate operational transactions DataFrame."""
        if not self.transactions_path.exists():
            raise FileNotFoundError(f"Transactions file not found: {self.transactions_path}")

        df = pd.read_csv(self.transactions_path)
        v_res = validate_synthetic_transactions(
            df, valid_accounts=valid_accounts, valid_cases=valid_cases
        )
        if not v_res.is_valid:
            raise ValueError(f"Transactions validation failed: {v_res.errors}")

        df["transaction_id"] = df["transaction_id"].astype(str)
        df["timestamp"] = df["timestamp"].astype(str)
        df["from_account"] = df["from_account"].astype(str)
        df["to_account"] = df["to_account"].astype(str)
        df["amount_paise"] = df["amount_paise"].astype("int64")
        df["transaction_type"] = df["transaction_type"].astype(str)
        df["case_id"] = df["case_id"].fillna("").astype(str)
        df["evidence_status"] = df["evidence_status"].astype(str)
        return df

    def load_dataset(self) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        """Load and cross-validate all 3 operational synthetic tables."""
        df_acc = self.load_accounts()
        df_case = self.load_cases()

        acc_ids = set(df_acc["account_id"].unique())
        case_ids = set(df_case["case_id"].unique())

        df_tx = self.load_transactions(valid_accounts=acc_ids, valid_cases=case_ids)
        return df_acc, df_tx, df_case
