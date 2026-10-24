"""Smart-Freeze Fund-Tracing Data Models.

Defines domain models, source-lot pool tracking, and structured tracing result types
for proportional, FIFO, and LIBR tracing algorithms. All amounts are strictly
represented as integer paise (1 INR = 100 paise).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional
import pandas as pd

CATEGORY_LEGITIMATE = "LEGITIMATE"
CATEGORY_UNKNOWN = "UNKNOWN_ORIGIN"


def make_suspected_category(source_tx_id: str, case_id: str = "") -> str:
    """Generate a canonical category identifier for a suspected source transaction."""
    cid = case_id.strip() if case_id else "UNKNOWN_CASE"
    return f"SUSPECTED:{cid}:{source_tx_id.strip()}"


# ==============================================================================
# Proportional Models
# ==============================================================================

@dataclass
class AccountSourcePool:
    """Tracks funds in an account partitioned into distinct source categories."""
    account_id: str
    history_complete: bool = True
    pools: Dict[str, int] = field(default_factory=dict)

    def total_balance_paise(self) -> int:
        return sum(self.pools.values())

    def get_balance(self, category: str) -> int:
        return self.pools.get(category, 0)

    def credit(self, category: str, amount_paise: int) -> None:
        if amount_paise < 0:
            raise ValueError(f"Cannot credit negative amount: {amount_paise}")
        if amount_paise == 0:
            return
        self.pools[category] = self.pools.get(category, 0) + amount_paise

    def debit(self, category: str, amount_paise: int) -> None:
        if amount_paise < 0:
            raise ValueError(f"Cannot debit negative amount: {amount_paise}")
        if amount_paise == 0:
            return
        current = self.pools.get(category, 0)
        if amount_paise > current:
            raise ValueError(
                f"Account '{self.account_id}' pool '{category}' has insufficient funds: "
                f"requested debit {amount_paise} paise, available {current} paise"
            )
        new_val = current - amount_paise
        if new_val == 0:
            del self.pools[category]
        else:
            self.pools[category] = new_val

    def snapshot(self) -> Dict[str, int]:
        return dict(self.pools)

    def copy(self) -> AccountSourcePool:
        return AccountSourcePool(
            account_id=self.account_id,
            history_complete=self.history_complete,
            pools=dict(self.pools),
        )


@dataclass(frozen=True)
class TracingHop:
    """Record of an internal transfer hop along a fund-tracing path."""
    hop_index: int
    transaction_id: str
    timestamp: str
    from_account: str
    to_account: str
    total_amount_paise: int
    suspected_amount_paise: int
    allocated_by_category: Dict[str, int]
    case_id: str
    evidence_status: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AllocationExplanation:
    """Step-by-step mathematical explanation of a proportional allocation."""
    transaction_id: str
    timestamp: str
    account_id: str
    counterparty_account: str
    transaction_type: str
    total_amount_paise: int
    balance_before_paise: int
    pools_before: Dict[str, int]
    exact_shares: Dict[str, str]
    base_allocations: Dict[str, int]
    remainders: Dict[str, int]
    remainder_paise_awarded: Dict[str, int]
    final_allocations: Dict[str, int]
    pools_after: Dict[str, int]
    explanation_text: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ProportionalTraceResult:
    """Structured output of a proportional fund-tracing run."""
    source_transaction_id: str
    source_case_id: str
    initial_suspected_amount_paise: int
    account_pools: Dict[str, Dict[str, int]]
    retained_suspected_paise: Dict[str, int]
    withdrawn_suspected_paise: Dict[str, int]
    transfer_hops: List[TracingHop] = field(default_factory=list)
    explanations: List[AllocationExplanation] = field(default_factory=list)
    incomplete_history_accounts: List[str] = field(default_factory=list)
    assumptions_and_limitations: List[str] = field(default_factory=list)

    def total_retained_suspected(self) -> int:
        return sum(self.retained_suspected_paise.values())

    def total_withdrawn_suspected(self) -> int:
        return sum(self.withdrawn_suspected_paise.values())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_transaction_id": self.source_transaction_id,
            "source_case_id": self.source_case_id,
            "initial_suspected_amount_paise": self.initial_suspected_amount_paise,
            "total_retained_suspected_paise": self.total_retained_suspected(),
            "total_withdrawn_suspected_paise": self.total_withdrawn_suspected(),
            "account_pools": self.account_pools,
            "retained_suspected_paise": self.retained_suspected_paise,
            "withdrawn_suspected_paise": self.withdrawn_suspected_paise,
            "transfer_hops": [h.to_dict() for h in self.transfer_hops],
            "explanations": [e.to_dict() for e in self.explanations],
            "incomplete_history_accounts": self.incomplete_history_accounts,
            "assumptions_and_limitations": self.assumptions_and_limitations,
        }

    def summary_dataframe(self) -> pd.DataFrame:
        """Tabular summary of suspected fund retention per account."""
        rows = []
        for acc_id, amt in sorted(self.retained_suspected_paise.items(), key=lambda x: x[1], reverse=True):
            if amt > 0:
                is_inc = acc_id in self.incomplete_history_accounts
                rows.append({
                    "account_id": acc_id,
                    "retained_suspected_paise": amt,
                    "retained_suspected_inr": round(amt / 100.0, 2),
                    "history_complete": not is_inc,
                })
        return pd.DataFrame(rows)


# ==============================================================================
# FIFO Models
# ==============================================================================

@dataclass
class FIFOLot:
    """Represents an ordered source lot in an account under FIFO rules."""
    lot_id: str
    account_id: str
    origin_transaction_id: str
    origin_timestamp: str
    origin_sequence: int
    original_amount_paise: int
    remaining_amount_paise: int
    source_classification: str
    source_case_id: str = ""
    parent_lot_id: Optional[str] = None
    history_complete: bool = True

    def consume(self, amount: int) -> int:
        """Consume up to amount from this lot. Returns actual consumed amount."""
        if amount <= 0:
            return 0
        consumed = min(amount, self.remaining_amount_paise)
        self.remaining_amount_paise -= consumed
        return consumed

    def is_exhausted(self) -> bool:
        return self.remaining_amount_paise <= 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class FIFOConsumptionEvent:
    """Record of a lot consumption during a FIFO outgoing transaction."""
    transaction_id: str
    timestamp: str
    account_id: str
    lot_id: str
    origin_transaction_id: str
    source_classification: str
    source_case_id: str
    amount_consumed_paise: int
    lot_balance_before_paise: int
    lot_balance_after_paise: int

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class FIFOAllocationExplanation:
    """Step-by-step explanation of lots consumed during a FIFO transaction."""
    transaction_id: str
    timestamp: str
    account_id: str
    counterparty_account: str
    total_amount_paise: int
    consumptions: List[FIFOConsumptionEvent]
    explanation_text: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "transaction_id": self.transaction_id,
            "timestamp": self.timestamp,
            "account_id": self.account_id,
            "counterparty_account": self.counterparty_account,
            "total_amount_paise": self.total_amount_paise,
            "consumptions": [c.to_dict() for c in self.consumptions],
            "explanation_text": self.explanation_text,
        }


@dataclass
class FIFOTraceResult:
    """Structured output of a First-In, First-Out (FIFO) fund-tracing run."""
    source_transaction_id: str
    source_case_id: str
    initial_suspected_amount_paise: int
    retained_suspected_paise: Dict[str, int]
    withdrawn_suspected_paise: Dict[str, int]
    active_lots_by_account: Dict[str, List[Dict[str, Any]]]
    transfer_hops: List[TracingHop] = field(default_factory=list)
    consumption_events: List[FIFOConsumptionEvent] = field(default_factory=list)
    explanations: List[FIFOAllocationExplanation] = field(default_factory=list)
    incomplete_history_accounts: List[str] = field(default_factory=list)
    assumptions_and_limitations: List[str] = field(default_factory=list)

    def total_retained_suspected(self) -> int:
        return sum(self.retained_suspected_paise.values())

    def total_withdrawn_suspected(self) -> int:
        return sum(self.withdrawn_suspected_paise.values())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_transaction_id": self.source_transaction_id,
            "source_case_id": self.source_case_id,
            "initial_suspected_amount_paise": self.initial_suspected_amount_paise,
            "total_retained_suspected_paise": self.total_retained_suspected(),
            "total_withdrawn_suspected_paise": self.total_withdrawn_suspected(),
            "retained_suspected_paise": self.retained_suspected_paise,
            "withdrawn_suspected_paise": self.withdrawn_suspected_paise,
            "active_lots_by_account": self.active_lots_by_account,
            "transfer_hops": [h.to_dict() for h in self.transfer_hops],
            "consumption_events": [c.to_dict() for c in self.consumption_events],
            "explanations": [e.to_dict() for e in self.explanations],
            "incomplete_history_accounts": self.incomplete_history_accounts,
            "assumptions_and_limitations": self.assumptions_and_limitations,
        }

    def summary_dataframe(self) -> pd.DataFrame:
        """Tabular summary of suspected fund retention per account under FIFO."""
        rows = []
        for acc_id, amt in sorted(self.retained_suspected_paise.items(), key=lambda x: x[1], reverse=True):
            if amt > 0:
                is_inc = acc_id in self.incomplete_history_accounts
                rows.append({
                    "account_id": acc_id,
                    "retained_suspected_paise": amt,
                    "retained_suspected_inr": round(amt / 100.0, 2),
                    "history_complete": not is_inc,
                })
        return pd.DataFrame(rows)


# ==============================================================================
# LIBR Models
# ==============================================================================

@dataclass
class LIBRAttributionEvent:
    """Record of balance and attribution changes under LIBR convention."""
    transaction_id: str
    timestamp: str
    account_id: str
    counterparty_account: str
    transaction_type: str
    total_amount_paise: int
    balance_before_paise: int
    balance_after_paise: int
    attributed_before_paise: int
    attributed_after_paise: int
    lowest_intermediate_balance_paise: int
    attribution_reduction_paise: int
    propagated_amount_paise: int
    explanation_text: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class LIBRTraceResult:
    """Structured output of a Lowest Intermediate Balance Rule (LIBR) fund-tracing run."""
    source_transaction_id: str
    source_case_id: str
    initial_suspected_amount_paise: int
    retained_suspected_paise: Dict[str, int]
    withdrawn_suspected_paise: Dict[str, int]
    lowest_intermediate_balances: Dict[str, int]
    transfer_hops: List[TracingHop] = field(default_factory=list)
    events: List[LIBRAttributionEvent] = field(default_factory=list)
    incomplete_history_accounts: List[str] = field(default_factory=list)
    assumptions_and_limitations: List[str] = field(default_factory=list)

    def total_retained_suspected(self) -> int:
        return sum(self.retained_suspected_paise.values())

    def total_withdrawn_suspected(self) -> int:
        return sum(self.withdrawn_suspected_paise.values())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_transaction_id": self.source_transaction_id,
            "source_case_id": self.source_case_id,
            "initial_suspected_amount_paise": self.initial_suspected_amount_paise,
            "total_retained_suspected_paise": self.total_retained_suspected(),
            "total_withdrawn_suspected_paise": self.total_withdrawn_suspected(),
            "retained_suspected_paise": self.retained_suspected_paise,
            "withdrawn_suspected_paise": self.withdrawn_suspected_paise,
            "lowest_intermediate_balances": self.lowest_intermediate_balances,
            "transfer_hops": [h.to_dict() for h in self.transfer_hops],
            "events": [e.to_dict() for e in self.events],
            "incomplete_history_accounts": self.incomplete_history_accounts,
            "assumptions_and_limitations": self.assumptions_and_limitations,
        }

    def summary_dataframe(self) -> pd.DataFrame:
        """Tabular summary of suspected fund retention per account under LIBR."""
        rows = []
        for acc_id, amt in sorted(self.retained_suspected_paise.items(), key=lambda x: x[1], reverse=True):
            if amt > 0:
                is_inc = acc_id in self.incomplete_history_accounts
                rows.append({
                    "account_id": acc_id,
                    "retained_suspected_paise": amt,
                    "retained_suspected_inr": round(amt / 100.0, 2),
                    "history_complete": not is_inc,
                })
        return pd.DataFrame(rows)

