"""FairHold Dataset Profiling Module.

Generates deterministic profiling summaries for supported datasets:
- Row and column counts
- Missing-value counts and percentages
- Duplicate counts
- Amount statistics (with documented currency units)
- Timestamp ranges
- Class/label distributions
- Graph node and edge counts
- Validation errors and warnings
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
import pandas as pd

from pipeline.schemas import (
    CANONICAL_ACCOUNT_COLUMNS,
    CANONICAL_CASE_COLUMNS,
    CANONICAL_TRANSACTION_COLUMNS,
    ELLIPTIC_CLASS_LABELS,
)
from pipeline.validation import (
    validate_elliptic_dataset,
    validate_synthaml_alerts,
    validate_synthetic_accounts,
    validate_synthetic_cases,
    validate_synthetic_transactions,
)


@dataclass
class DatasetProfile:
    """Summary profile of an ingested dataset."""
    dataset_name: str
    source_files: Dict[str, str] = field(default_factory=dict)
    status: str = "success"  # "success", "skipped", "error"
    row_counts: Dict[str, int] = field(default_factory=dict)
    column_counts: Dict[str, int] = field(default_factory=dict)
    column_types: Dict[str, Dict[str, str]] = field(default_factory=dict)
    missing_counts: Dict[str, Dict[str, int]] = field(default_factory=dict)
    missing_pcts: Dict[str, Dict[str, float]] = field(default_factory=dict)
    duplicate_counts: Dict[str, int] = field(default_factory=dict)
    amount_statistics: Dict[str, Any] = field(default_factory=dict)
    timestamp_ranges: Dict[str, str] = field(default_factory=dict)
    label_distribution: Dict[str, int] = field(default_factory=dict)
    graph_statistics: Dict[str, int] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def format_text(self) -> str:
        """Render a readable text profile report."""
        lines = [
            f"=" * 70,
            f"FAIRHOLD DATASET PROFILE: {self.dataset_name.upper()}",
            f"=" * 70,
            f"Status: {self.status.upper()}",
        ]

        if self.source_files:
            lines.append("Source Files:")
            for k, v in sorted(self.source_files.items()):
                lines.append(f"  - {k}: {v}")

        if self.status == "skipped":
            lines.append("Reason: Dataset files not found on filesystem.")
            return "\n".join(lines)

        if self.row_counts:
            lines.append("\nDimensions & Row Counts:")
            for k, count in sorted(self.row_counts.items()):
                cols = self.column_counts.get(k, 0)
                lines.append(f"  - {k}: {count:,} rows, {cols} columns")

        if self.duplicate_counts:
            lines.append("\nDuplicate Key Counts:")
            for k, count in sorted(self.duplicate_counts.items()):
                lines.append(f"  - {k}: {count}")

        if self.timestamp_ranges:
            lines.append("\nTimestamp Ranges:")
            for k, v in sorted(self.timestamp_ranges.items()):
                lines.append(f"  - {k}: {v}")

        if self.amount_statistics:
            lines.append("\nMonetary Amount Statistics:")
            for k, v in self.amount_statistics.items():
                lines.append(f"  - {k}: {v}")

        if self.label_distribution:
            lines.append("\nClass / Label Distribution:")
            for k, v in sorted(self.label_distribution.items()):
                lines.append(f"  - {k}: {v:,}")

        if self.graph_statistics:
            lines.append("\nGraph Structure:")
            for k, v in sorted(self.graph_statistics.items()):
                lines.append(f"  - {k}: {v:,}")

        # Missing values (only report if any missing)
        any_missing = any(
            any(cnt > 0 for cnt in col_map.values())
            for col_map in self.missing_counts.values()
        )
        if any_missing:
            lines.append("\nMissing Values:")
            for table, col_map in sorted(self.missing_counts.items()):
                for col, cnt in sorted(col_map.items()):
                    if cnt > 0:
                        pct = self.missing_pcts.get(table, {}).get(col, 0.0)
                        lines.append(f"  - {table}.{col}: {cnt:,} ({pct:.2f}%)")

        if self.warnings:
            lines.append(f"\nData Quality Warnings ({len(self.warnings)}):")
            for w in self.warnings:
                lines.append(f"  [!] {w}")

        if self.errors:
            lines.append(f"\nValidation Errors ({len(self.errors)}):")
            for e in self.errors:
                lines.append(f"  [ERROR] {e}")

        lines.append("=" * 70)
        return "\n".join(lines)


def profile_synthetic_dataset(data_dir: Path | str) -> DatasetProfile:
    """Profile FairHold synthetic financial dataset (accounts, transactions, cases)."""
    p_dir = Path(data_dir)
    profile = DatasetProfile(dataset_name="fairhold_synthetic")

    acc_path = p_dir / "accounts.csv"
    tx_path = p_dir / "transactions.csv"
    case_path = p_dir / "cases.csv"

    profile.source_files = {
        "accounts": str(acc_path),
        "transactions": str(tx_path),
        "cases": str(case_path),
    }

    if not (acc_path.exists() and tx_path.exists() and case_path.exists()):
        profile.status = "skipped"
        profile.warnings.append("One or more synthetic CSV files are missing.")
        return profile

    try:
        df_acc = pd.read_csv(acc_path)
        df_tx = pd.read_csv(tx_path)
        df_case = pd.read_csv(case_path)
    except Exception as exc:
        profile.status = "error"
        profile.errors.append(f"Failed to read CSV files: {exc}")
        return profile

    # Row & column counts
    profile.row_counts = {
        "accounts": len(df_acc),
        "transactions": len(df_tx),
        "cases": len(df_case),
    }
    profile.column_counts = {
        "accounts": len(df_acc.columns),
        "transactions": len(df_tx.columns),
        "cases": len(df_case.columns),
    }

    # Columns & types
    profile.column_types = {
        "accounts": {col: str(dtype) for col, dtype in df_acc.dtypes.items()},
        "transactions": {col: str(dtype) for col, dtype in df_tx.dtypes.items()},
        "cases": {col: str(dtype) for col, dtype in df_case.dtypes.items()},
    }

    # Missing counts
    profile.missing_counts = {
        "accounts": df_acc.isnull().sum().to_dict(),
        "transactions": df_tx.isnull().sum().to_dict(),
        "cases": df_case.isnull().sum().to_dict(),
    }
    profile.missing_pcts = {
        "accounts": (df_acc.isnull().mean() * 100.0).round(2).to_dict(),
        "transactions": (df_tx.isnull().mean() * 100.0).round(2).to_dict(),
        "cases": (df_case.isnull().mean() * 100.0).round(2).to_dict(),
    }

    # Duplicates
    dup_acc = int(df_acc["account_id"].duplicated().sum()) if "account_id" in df_acc.columns else 0
    dup_tx = int(df_tx["transaction_id"].duplicated().sum()) if "transaction_id" in df_tx.columns else 0
    dup_case = int(df_case["case_id"].duplicated().sum()) if "case_id" in df_case.columns else 0
    profile.duplicate_counts = {
        "accounts.account_id": dup_acc,
        "transactions.transaction_id": dup_tx,
        "cases.case_id": dup_case,
    }

    # Amounts
    if "amount_paise" in df_tx.columns and pd.api.types.is_numeric_dtype(df_tx["amount_paise"]):
        amt_col = df_tx["amount_paise"]
        profile.amount_statistics = {
            "unit": "paise (integer, 1 INR = 100 paise)",
            "min_amount_paise": int(amt_col.min()),
            "max_amount_paise": int(amt_col.max()),
            "total_turnover_paise": int(amt_col.sum()),
            "mean_amount_paise": round(float(amt_col.mean()), 2),
            "total_turnover_inr": round(float(amt_col.sum()) / 100.0, 2),
        }

    # Timestamp ranges
    if "timestamp" in df_tx.columns and len(df_tx) > 0:
        profile.timestamp_ranges["transactions"] = (
            f"{df_tx['timestamp'].min()} to {df_tx['timestamp'].max()}"
        )
    if "reported_date" in df_case.columns and len(df_case) > 0:
        profile.timestamp_ranges["cases"] = (
            f"{df_case['reported_date'].min()} to {df_case['reported_date'].max()}"
        )

    # Validate
    v_acc = validate_synthetic_accounts(df_acc)
    v_case = validate_synthetic_cases(df_case)
    valid_accs = set(df_acc["account_id"].dropna().unique()) if "account_id" in df_acc.columns else None
    valid_cases = set(df_case["case_id"].dropna().unique()) if "case_id" in df_case.columns else None
    v_tx = validate_synthetic_transactions(df_tx, valid_accounts=valid_accs, valid_cases=valid_cases)

    profile.warnings.extend(v_acc.warnings + v_case.warnings + v_tx.warnings)
    profile.errors.extend(v_acc.errors + v_case.errors + v_tx.errors)

    if profile.errors:
        profile.status = "error"

    return profile


def profile_elliptic_dataset(dataset_dir: Path | str) -> DatasetProfile:
    """Profile Elliptic Bitcoin transaction graph dataset."""
    p_dir = Path(dataset_dir)
    profile = DatasetProfile(dataset_name="elliptic_bitcoin")

    classes_path = p_dir / "elliptic_txs_classes.csv"
    edges_path = p_dir / "elliptic_txs_edgelist.csv"
    features_path = p_dir / "elliptic_txs_features.csv"

    profile.source_files = {
        "classes": str(classes_path),
        "edgelist": str(edges_path),
        "features": str(features_path),
    }

    if not (classes_path.exists() and edges_path.exists()):
        profile.status = "skipped"
        profile.warnings.append("Elliptic classes or edgelist CSV file missing.")
        return profile

    try:
        df_classes = pd.read_csv(classes_path)
        df_edges = pd.read_csv(edges_path)
    except Exception as exc:
        profile.status = "error"
        profile.errors.append(f"Failed to read Elliptic CSV files: {exc}")
        return profile

    profile.row_counts = {
        "classes": len(df_classes),
        "edgelist": len(df_edges),
    }
    profile.column_counts = {
        "classes": len(df_classes.columns),
        "edgelist": len(df_edges.columns),
    }

    profile.missing_counts = {
        "classes": df_classes.isnull().sum().to_dict(),
        "edgelist": df_edges.isnull().sum().to_dict(),
    }
    profile.missing_pcts = {
        "classes": (df_classes.isnull().mean() * 100.0).round(2).to_dict(),
        "edgelist": (df_edges.isnull().mean() * 100.0).round(2).to_dict(),
    }

    # Labels
    raw_counts = df_classes["class"].astype(str).value_counts().to_dict()
    profile.label_distribution = {
        f"class_{k} ({ELLIPTIC_CLASS_LABELS.get(k, 'unknown')})": v
        for k, v in raw_counts.items()
    }

    # Graph structure
    edge_nodes = set(df_edges["txId1"]).union(set(df_edges["txId2"]))
    profile.graph_statistics = {
        "total_nodes_in_classes": len(df_classes),
        "nodes_participating_in_edges": len(edge_nodes),
        "directed_edges": len(df_edges),
    }

    # Validate
    v_res = validate_elliptic_dataset(df_classes, df_edges)
    profile.warnings.extend(v_res.warnings)
    profile.errors.extend(v_res.errors)

    if profile.errors:
        profile.status = "error"

    return profile


def profile_synthaml_dataset(data_dir: Path | str) -> DatasetProfile:
    """Profile SynthAML alerts dataset and document missing transactions companion."""
    p_dir = Path(data_dir)
    profile = DatasetProfile(dataset_name="synthaml_alerts")

    alerts_path = p_dir / "synthetic_alerts.csv"
    txns_path = p_dir / "synthetic_transactions.csv"

    profile.source_files = {
        "alerts": str(alerts_path),
        "transactions": str(txns_path),
    }

    if not alerts_path.exists():
        profile.status = "skipped"
        profile.warnings.append("SynthAML synthetic_alerts.csv not found.")
        return profile

    try:
        df_alerts = pd.read_csv(alerts_path)
    except Exception as exc:
        profile.status = "error"
        profile.errors.append(f"Failed to read synthetic_alerts.csv: {exc}")
        return profile

    profile.row_counts = {"alerts": len(df_alerts)}
    profile.column_counts = {"alerts": len(df_alerts.columns)}
    profile.missing_counts = {"alerts": df_alerts.isnull().sum().to_dict()}
    profile.missing_pcts = {"alerts": (df_alerts.isnull().mean() * 100.0).round(2).to_dict()}

    if "AlertID" in df_alerts.columns:
        profile.duplicate_counts = {
            "alerts.AlertID": int(df_alerts["AlertID"].duplicated().sum())
        }

    if "Outcome" in df_alerts.columns:
        profile.label_distribution = df_alerts["Outcome"].value_counts().to_dict()

    if "Date" in df_alerts.columns and len(df_alerts) > 0:
        profile.timestamp_ranges["alerts"] = (
            f"{df_alerts['Date'].min()} to {df_alerts['Date'].max()}"
        )

    # Validate
    v_res = validate_synthaml_alerts(df_alerts, transactions_file_present=txns_path.exists())
    profile.warnings.extend(v_res.warnings)
    profile.errors.extend(v_res.errors)

    if profile.errors:
        profile.status = "error"

    return profile


def profile_amlnet_dataset(file_path: Path | str, sample_size: Optional[int] = None) -> DatasetProfile:
    """Profile AMLNet August 2025 multi-channel banking transaction dataset."""
    p_file = Path(file_path)
    profile = DatasetProfile(dataset_name="amlnet")
    profile.source_files = {"transactions": str(p_file)}

    if not p_file.exists():
        profile.status = "skipped"
        profile.warnings.append(f"AMLNet file '{p_file}' not found.")
        return profile

    try:
        df = pd.read_csv(p_file, nrows=sample_size)
    except Exception as exc:
        profile.status = "error"
        profile.errors.append(f"Failed to load AMLNet CSV: {exc}")
        return profile

    profile.row_counts = {"transactions": len(df)}
    profile.column_counts = {"transactions": len(df.columns)}
    profile.missing_counts = {"transactions": df.isnull().sum().to_dict()}
    profile.missing_pcts = {"transactions": (df.isnull().mean() * 100.0).round(2).to_dict()}

    if "laundering_typology" in df.columns:
        profile.label_distribution = df["laundering_typology"].value_counts().to_dict()

    if "amount" in df.columns and pd.api.types.is_numeric_dtype(df["amount"]):
        amt_col = df["amount"]
        profile.amount_statistics = {
            "unit": "AUD (floating-point dollar values in raw source)",
            "min_amount": round(float(amt_col.min()), 2),
            "max_amount": round(float(amt_col.max()), 2),
            "mean_amount": round(float(amt_col.mean()), 2),
            "total_sum": round(float(amt_col.sum()), 2),
        }

    # Known schema observation: fraud_probability has missing values
    if "fraud_probability" in df.columns and df["fraud_probability"].isnull().sum() > 0:
        missing_cnt = int(df["fraud_probability"].isnull().sum())
        profile.warnings.append(
            f"Provenance: fraud_probability has {missing_cnt:,} null values in raw dataset."
        )

    profile.warnings.append(
        "AMLNet is an Australian multi-channel banking transaction dataset with typologies; "
        "it is NOT a SynthAML transaction companion."
    )

    return profile
