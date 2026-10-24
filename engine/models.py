"""Smart-Freeze Financial Engine Data Models.

Defines domain models for ledger reconstruction, balance events,
validation reports, and graph summaries. All monetary amounts are
represented strictly as integer paise (1 INR = 100 paise).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class AccountState:
    """State of an internal ledger account throughout reconstruction."""
    account_id: str
    account_type: str
    opening_balance_paise: int
    current_balance_paise: int
    history_complete: bool
    total_credits_paise: int = 0
    total_debits_paise: int = 0
    internal_credits_paise: int = 0
    internal_debits_paise: int = 0
    external_deposits_paise: int = 0
    external_withdrawals_paise: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BalanceEvent:
    """Immutable audit record of an account balance change."""
    account_id: str
    timestamp: str
    transaction_id: str
    counterparty_account: str
    balance_before_paise: int
    amount_change_paise: int  # Signed: positive for inflow/credit, negative for outflow/debit
    balance_after_paise: int
    direction: str            # 'CREDIT' or 'DEBIT'
    transaction_type: str
    case_id: str
    evidence_status: str
    history_complete: bool

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class LedgerValidationReport:
    """Audit report for ledger reconstruction and balance conservation."""
    is_valid: bool
    accounts_count: int
    transactions_count: int
    internal_transfers_count: int
    external_deposits_count: int
    external_withdrawals_count: int
    total_turnover_paise: int
    total_opening_balance_paise: int
    total_final_balance_paise: int
    total_external_deposits_paise: int
    total_external_withdrawals_paise: int
    conservation_verified: bool
    incomplete_history_accounts: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class GraphSummary:
    """Descriptive topological summary of the transaction graph."""
    internal_account_nodes: int
    internal_transfer_edges: int
    weakly_connected_components: int
    isolated_accounts: List[str] = field(default_factory=list)
    top_senders_by_volume: List[Dict[str, Any]] = field(default_factory=list)
    top_receivers_by_volume: List[Dict[str, Any]] = field(default_factory=list)
    top_senders_by_count: List[Dict[str, Any]] = field(default_factory=list)
    top_receivers_by_count: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
