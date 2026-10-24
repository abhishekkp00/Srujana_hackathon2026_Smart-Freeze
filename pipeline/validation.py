"""FairHold Data Validation Module.

Performs structural and semantic validation for financial ledgers, transaction journals,
and external datasets. Distinguishes fatal validation errors from non-fatal quality warnings.
Never silently modifies, repairs, or drops invalid records.
"""

from __future__ import annotations

import csv
import datetime
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
import pandas as pd

from pipeline.schemas import (
    ALLOWED_ACCOUNT_TYPES,
    ALLOWED_TRANSACTION_TYPES,
    CANONICAL_ACCOUNT_COLUMNS,
    CANONICAL_CASE_COLUMNS,
    CANONICAL_TRANSACTION_COLUMNS,
    CASE_ID_PREFIX,
    ELLIPTIC_CLASS_LABELS,
    ELLIPTIC_CLASSES_COLUMNS,
    ELLIPTIC_EDGELIST_COLUMNS,
    EXTERNAL_ACCOUNT_PREFIX,
    INTERNAL_ACCOUNT_PREFIX,
    SYNTHAML_ALERTS_COLUMNS,
    SYNTHAML_ALERTS_OUTCOMES,
)


@dataclass
class ValidationResult:
    """Outcome of dataset validation."""
    dataset_name: str
    is_valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    records_checked: int = 0
    details: Dict[str, Any] = field(default_factory=dict)

    def add_error(self, message: str) -> None:
        self.errors.append(message)
        self.is_valid = False

    def add_warning(self, message: str) -> None:
        self.warnings.append(message)


def validate_iso_timestamp(timestamp_str: str) -> bool:
    """Validate whether string is valid ISO 8601."""
    if not isinstance(timestamp_str, str) or not timestamp_str.strip():
        return False
    try:
        clean_ts = timestamp_str.strip().replace("Z", "+00:00")
        datetime.datetime.fromisoformat(clean_ts)
        return True
    except (ValueError, TypeError):
        return False


def validate_date_string(date_str: str, fmt: str = "%Y-%m-%d") -> bool:
    """Validate whether string matches expected date format."""
    if not isinstance(date_str, str) or not date_str.strip():
        return False
    try:
        datetime.datetime.strptime(date_str.strip(), fmt)
        return True
    except (ValueError, TypeError):
        return False


def validate_synthetic_accounts(
    df: pd.DataFrame,
) -> ValidationResult:
    """Validate accounts table against FairHold canonical schema."""
    result = ValidationResult(dataset_name="synthetic_accounts", is_valid=True)
    result.records_checked = len(df)

    # 1. Column layout
    missing_cols = [c for c in CANONICAL_ACCOUNT_COLUMNS if c not in df.columns]
    if missing_cols:
        result.add_error(f"Missing required columns: {missing_cols}")
        return result

    # 2. Duplicate or empty account_id
    acc_ids = df["account_id"].astype(str).str.strip()
    if (acc_ids == "").any():
        result.add_error("Found empty account_id entries.")

    duplicates = acc_ids[acc_ids.duplicated(keep=False)].unique().tolist()
    if duplicates:
        result.add_error(f"Found {len(duplicates)} duplicate account_ids: {duplicates[:5]}")

    # 3. Account types
    for acc_type in df["account_type"].dropna().unique():
        if str(acc_type).strip() not in ALLOWED_ACCOUNT_TYPES:
            result.add_warning(f"Unrecognized account_type '{acc_type}'")

    # 4. Opening balance integer paise and non-negative
    for idx, val in df["opening_balance_paise"].items():
        if pd.isna(val):
            result.add_error(f"Row {idx}: missing opening_balance_paise.")
            continue
        try:
            val_int = int(val)
            if float(val) != float(val_int):
                result.add_error(f"Row {idx}: non-integer opening_balance_paise {val}")
            elif val_int < 0:
                result.add_error(f"Row {idx}: negative opening_balance_paise {val_int}")
        except (ValueError, TypeError):
            result.add_error(f"Row {idx}: invalid opening_balance_paise '{val}'")

    # 5. History complete boolean
    if "history_complete" in df.columns:
        incomplete_count = 0
        for val in df["history_complete"]:
            val_str = str(val).strip().lower()
            if val_str not in ("true", "false", "1", "0"):
                result.add_warning(f"Non-boolean history_complete value '{val}'")
            elif val_str in ("false", "0"):
                incomplete_count += 1
        if incomplete_count > 0:
            result.add_warning(
                f"Ledger contains {incomplete_count} accounts with incomplete statement history."
            )

    return result


def validate_synthetic_cases(
    df: pd.DataFrame,
) -> ValidationResult:
    """Validate cases table against FairHold canonical schema."""
    result = ValidationResult(dataset_name="synthetic_cases", is_valid=True)
    result.records_checked = len(df)

    # 1. Columns
    missing_cols = [c for c in CANONICAL_CASE_COLUMNS if c not in df.columns]
    if missing_cols:
        result.add_error(f"Missing required columns: {missing_cols}")
        return result

    # 2. Case IDs
    case_ids = df["case_id"].astype(str).str.strip()
    if (case_ids == "").any():
        result.add_error("Found empty case_id entries.")

    dups = case_ids[case_ids.duplicated(keep=False)].unique().tolist()
    if dups:
        result.add_error(f"Found {len(dups)} duplicate case_ids: {dups[:5]}")

    # 3. Reported date ISO
    for idx, r_date in df["reported_date"].items():
        if not validate_iso_timestamp(str(r_date)):
            result.add_error(f"Row {idx}: invalid ISO reported_date '{r_date}'")

    # 4. Reported amount positive integer paise
    for idx, val in df["reported_amount_paise"].items():
        if pd.isna(val):
            result.add_error(f"Row {idx}: missing reported_amount_paise.")
            continue
        try:
            val_int = int(val)
            if float(val) != float(val_int):
                result.add_error(f"Row {idx}: non-integer reported_amount_paise {val}")
            elif val_int <= 0:
                result.add_error(f"Row {idx}: non-positive reported_amount_paise {val_int}")
        except (ValueError, TypeError):
            result.add_error(f"Row {idx}: invalid reported_amount_paise '{val}'")

    return result


def validate_synthetic_transactions(
    df: pd.DataFrame,
    valid_accounts: Optional[Set[str]] = None,
    valid_cases: Optional[Set[str]] = None,
) -> ValidationResult:
    """Validate transactions table against FairHold canonical schema and references."""
    result = ValidationResult(dataset_name="synthetic_transactions", is_valid=True)
    result.records_checked = len(df)

    # 1. Column layout
    missing_cols = [c for c in CANONICAL_TRANSACTION_COLUMNS if c not in df.columns]
    if missing_cols:
        result.add_error(f"Missing required columns: {missing_cols}")
        return result

    # 2. Duplicate or empty transaction_id
    tx_ids = df["transaction_id"].astype(str).str.strip()
    if (tx_ids == "").any():
        result.add_error("Found empty transaction_id entries.")

    duplicates = tx_ids[tx_ids.duplicated(keep=False)].unique().tolist()
    if duplicates:
        result.add_error(f"Found {len(duplicates)} duplicate transaction_ids: {duplicates[:5]}")

    # 3. Timestamps
    for idx, ts in df["timestamp"].items():
        if not validate_iso_timestamp(str(ts)):
            result.add_error(f"Row {idx}: invalid ISO 8601 timestamp '{ts}'")

    # 4. Amounts positive integer paise
    for idx, val in df["amount_paise"].items():
        if pd.isna(val):
            result.add_error(f"Row {idx}: missing amount_paise.")
            continue
        try:
            val_int = int(val)
            if float(val) != float(val_int):
                result.add_error(f"Row {idx}: non-integer amount_paise {val}")
            elif val_int <= 0:
                result.add_error(f"Row {idx}: non-positive amount_paise {val_int}")
        except (ValueError, TypeError):
            result.add_error(f"Row {idx}: invalid amount_paise '{val}'")

    # 5. Account counterparties and references
    for idx, row in df.iterrows():
        from_acc = str(row["from_account"]).strip()
        to_acc = str(row["to_account"]).strip()

        if not from_acc or not to_acc:
            result.add_error(f"Row {idx}: empty from/to account reference")
            continue

        if from_acc == to_acc:
            result.add_error(f"Row {idx}: self-transfer prohibited ({from_acc} -> {to_acc})")

        # Prohibit dual external counterparties
        if from_acc.startswith(EXTERNAL_ACCOUNT_PREFIX) and to_acc.startswith(EXTERNAL_ACCOUNT_PREFIX):
            result.add_error(f"Row {idx}: both counterparties external ({from_acc} -> {to_acc})")

        if valid_accounts is not None:
            if not from_acc.startswith(EXTERNAL_ACCOUNT_PREFIX) and from_acc not in valid_accounts:
                result.add_error(f"Row {idx}: unknown internal from_account '{from_acc}'")
            if not to_acc.startswith(EXTERNAL_ACCOUNT_PREFIX) and to_acc not in valid_accounts:
                result.add_error(f"Row {idx}: unknown internal to_account '{to_acc}'")

        # Case reference check (case_id is optional; empty string or NaN for legitimate transactions)
        case_raw = row.get("case_id", "")
        if pd.notna(case_raw):
            case_val = str(case_raw).strip()
            if case_val and case_val.lower() != "nan":
                if valid_cases is not None and case_val not in valid_cases:
                    result.add_error(f"Row {idx}: unreferenced case_id '{case_val}'")

    # 6. Transaction types warning
    for t_type in df["transaction_type"].dropna().unique():
        if str(t_type).strip() not in ALLOWED_TRANSACTION_TYPES:
            result.add_warning(f"Unrecognized transaction_type '{t_type}'")

    return result


def validate_elliptic_dataset(
    df_classes: pd.DataFrame,
    df_edges: pd.DataFrame,
) -> ValidationResult:
    """Validate Elliptic Bitcoin transaction graph schemas and edge integrity."""
    result = ValidationResult(dataset_name="elliptic_bitcoin", is_valid=True)
    result.records_checked = len(df_classes)

    # 1. Classes columns
    for col in ELLIPTIC_CLASSES_COLUMNS:
        if col not in df_classes.columns:
            result.add_error(f"Classes table missing column '{col}'")

    # 2. Edges columns
    for col in ELLIPTIC_EDGELIST_COLUMNS:
        if col not in df_edges.columns:
            result.add_error(f"Edgelist table missing column '{col}'")

    if not result.is_valid:
        return result

    # 3. Label values
    unique_classes = set(df_classes["class"].astype(str).unique())
    unknown_labels = unique_classes - set(ELLIPTIC_CLASS_LABELS.keys())
    if unknown_labels:
        result.add_warning(f"Unrecognized class labels found: {unknown_labels}")

    # 4. Check duplicate txIds
    dup_txs = df_classes["txId"][df_classes["txId"].duplicated()].tolist()
    if dup_txs:
        result.add_error(f"Found {len(dup_txs)} duplicate txIds in classes table.")

    # 5. Edge reference coverage check (nodes in edgelist present in classes)
    node_set = set(df_classes["txId"].unique())
    edge_srcs = set(df_edges["txId1"].unique())
    edge_dsts = set(df_edges["txId2"].unique())
    all_edge_nodes = edge_srcs.union(edge_dsts)

    unobserved = all_edge_nodes - node_set
    if unobserved:
        result.add_warning(
            f"Edgelist contains {len(unobserved)} transaction nodes without explicit class labels."
        )

    return result


def validate_synthaml_alerts(
    df_alerts: pd.DataFrame,
    transactions_file_present: bool = False,
) -> ValidationResult:
    """Validate SynthAML alerts dataset and document missing transactions companion."""
    result = ValidationResult(dataset_name="synthaml_alerts", is_valid=True)
    result.records_checked = len(df_alerts)

    # 1. Columns
    missing_cols = [c for c in SYNTHAML_ALERTS_COLUMNS if c not in df_alerts.columns]
    if missing_cols:
        result.add_error(f"Missing required alert columns: {missing_cols}")
        return result

    # 2. Duplicate AlertIDs
    dup_alerts = df_alerts["AlertID"][df_alerts["AlertID"].duplicated()].tolist()
    if dup_alerts:
        result.add_error(f"Found {len(dup_alerts)} duplicate AlertIDs: {dup_alerts[:5]}")

    # 3. Date format (YYYY-MM-DD)
    for idx, d_val in df_alerts["Date"].items():
        if not validate_date_string(str(d_val)):
            result.add_error(f"Row {idx}: invalid date format '{d_val}' (expected YYYY-MM-DD)")

    # 4. Outcomes
    unique_outcomes = set(df_alerts["Outcome"].astype(str).unique())
    invalid_outcomes = unique_outcomes - SYNTHAML_ALERTS_OUTCOMES
    if invalid_outcomes:
        result.add_warning(f"Unrecognized alert outcomes: {invalid_outcomes}")

    # 5. Missing companion check
    if not transactions_file_present:
        result.add_warning(
            "Provenance Warning: 'synthetic_transactions.csv' companion file is missing. "
            "Alerts cannot be joined with transaction journals and are retained as orphan alerts."
        )

    return result
