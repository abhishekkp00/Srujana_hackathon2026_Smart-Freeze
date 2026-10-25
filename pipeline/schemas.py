"""Smart-Freeze Canonical Schemas and Field Definitions.

Defines the canonical schema models, constants, and field semantics
for the Smart-Freeze financial investigation decision-support platform.
Preserves strict integer-paise representation for internal ledgers and
documents schemas and limitations of external datasets.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set


# ==============================================================================
# Smart-Freeze Canonical Internal Ledger Schema (Step 1 & Step 2)
# ==============================================================================

# Required column names for CSV validation
CANONICAL_ACCOUNT_COLUMNS = [
    "account_id",
    "account_type",
    "opening_balance_paise",
    "history_complete",
]

CANONICAL_TRANSACTION_COLUMNS = [
    "transaction_id",
    "timestamp",
    "from_account",
    "to_account",
    "amount_paise",
    "transaction_type",
    "case_id",
    "evidence_status",
]

CANONICAL_CASE_COLUMNS = [
    "case_id",
    "reported_date",
    "reported_amount_paise",
    "status",
]

ALLOWED_ACCOUNT_TYPES = {
    "savings",
    "current",
    "corporate",
    "merchant",
    "salary",
}

ALLOWED_TRANSACTION_TYPES = {
    "transfer",
    "deposit",
    "withdrawal",
    "salary_credit",
    "merchant_payment",
}

EXTERNAL_ACCOUNT_PREFIX = "EXT_"
INTERNAL_ACCOUNT_PREFIX = "ACC_"
CASE_ID_PREFIX = "CASE-"


@dataclass(frozen=True)
class CanonicalAccount:
    """Canonical representation of an internal financial account."""
    account_id: str
    account_type: str
    opening_balance_paise: int
    history_complete: bool

    def to_dict(self) -> Dict[str, Any]:
        return {
            "account_id": self.account_id,
            "account_type": self.account_type,
            "opening_balance_paise": self.opening_balance_paise,
            "history_complete": self.history_complete,
        }


@dataclass(frozen=True)
class CanonicalTransaction:
    """Canonical representation of a financial ledger journal entry."""
    transaction_id: str
    timestamp: str
    from_account: str
    to_account: str
    amount_paise: int
    transaction_type: str
    case_id: str = ""
    evidence_status: str = "unflagged"

    @property
    def is_internal_transfer(self) -> bool:
        return (
            not self.from_account.startswith(EXTERNAL_ACCOUNT_PREFIX)
            and not self.to_account.startswith(EXTERNAL_ACCOUNT_PREFIX)
        )

    @property
    def is_deposit(self) -> bool:
        return (
            self.from_account.startswith(EXTERNAL_ACCOUNT_PREFIX)
            and not self.to_account.startswith(EXTERNAL_ACCOUNT_PREFIX)
        )

    @property
    def is_withdrawal(self) -> bool:
        return (
            not self.from_account.startswith(EXTERNAL_ACCOUNT_PREFIX)
            and self.to_account.startswith(EXTERNAL_ACCOUNT_PREFIX)
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "transaction_id": self.transaction_id,
            "timestamp": self.timestamp,
            "from_account": self.from_account,
            "to_account": self.to_account,
            "amount_paise": self.amount_paise,
            "transaction_type": self.transaction_type,
            "case_id": self.case_id,
            "evidence_status": self.evidence_status,
        }


@dataclass(frozen=True)
class CanonicalCase:
    """Canonical representation of a reported fraud complaint."""
    case_id: str
    reported_date: str
    reported_amount_paise: int
    status: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "case_id": self.case_id,
            "reported_date": self.reported_date,
            "reported_amount_paise": self.reported_amount_paise,
            "status": self.status,
        }


# ==============================================================================
# External Dataset Schemas and Documentation
# ==============================================================================

# Elliptic Bitcoin Dataset
ELLIPTIC_CLASSES_COLUMNS = ["txId", "class"]
ELLIPTIC_EDGELIST_COLUMNS = ["txId1", "txId2"]
# Features file is headerless, with 167 numeric columns (col 0: txId, col 1: time_step, cols 2-166: features)
ELLIPTIC_CLASS_LABELS = {
    "1": "illicit",
    "2": "licit",
    "unknown": "unknown",
}

# SynthAML Alerts Dataset
SYNTHAML_ALERTS_COLUMNS = ["AlertID", "Date", "Outcome"]
SYNTHAML_ALERTS_OUTCOMES = {"Report", "Dismiss"}

# AMLNet Dataset (Australian synthetic AML benchmark)
AMLNET_COLUMNS = [
    "step",
    "type",
    "amount",
    "category",
    "nameOrig",
    "nameDest",
    "oldbalanceOrg",
    "newbalanceOrig",
    "isFraud",
    "isMoneyLaundering",
    "laundering_typology",
    "metadata",
    "fraud_probability",
    "hour",
    "day_of_week",
    "day_of_month",
    "month",
]


class DatasetType(str, Enum):
    """Categorization of supported datasets."""
    SMART_FREEZE_SYNTHETIC = "smartfreeze_synthetic"
    SMARTFREEZE_SYNTHETIC = "smartfreeze_synthetic"
    ELLIPTIC_BITCOIN = "elliptic_bitcoin"
    SYNTHAML_ALERTS = "synthaml_alerts"
    AMLNET = "amlnet"

