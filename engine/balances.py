"""FairHold Balance Tracking and History Reconstruction Engine.

Tracks running balances per internal account, validates balance conservation,
verifies that accounts never enter negative balances (overdraft unsupported),
and generates audit-ready chronological balance events with complete provenance.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple
import pandas as pd

from engine.models import AccountState, BalanceEvent
from pipeline.schemas import EXTERNAL_ACCOUNT_PREFIX


class BalanceReconstructionError(ValueError):
    """Base error for balance reconstruction failures."""
    pass


class NegativeBalanceError(BalanceReconstructionError):
    """Raised when an account balance drops below zero without overdraft support."""
    pass


class BalanceConservationError(BalanceReconstructionError):
    """Raised when an internal transfer fails to conserve value across counterparties."""
    pass


class BalanceTracker:
    """Manages account states, applies transaction events, and records balance histories."""

    def __init__(self, accounts: List[Dict[str, any]] | pd.DataFrame):
        self.accounts: Dict[str, AccountState] = {}
        self.balance_events: List[BalanceEvent] = []
        self._initialize_accounts(accounts)

    def _initialize_accounts(self, accounts: List[Dict[str, any]] | pd.DataFrame) -> None:
        """Initialize account states from input records."""
        if isinstance(accounts, pd.DataFrame):
            records = accounts.to_dict(orient="records")
        else:
            records = accounts

        for row in records:
            acc_id = str(row["account_id"]).strip()
            opening = int(row["opening_balance_paise"])
            if opening < 0:
                raise NegativeBalanceError(
                    f"Account '{acc_id}' has negative opening balance: {opening} paise"
                )

            hist_comp = bool(row.get("history_complete", True))
            self.accounts[acc_id] = AccountState(
                account_id=acc_id,
                account_type=str(row.get("account_type", "savings")).strip(),
                opening_balance_paise=opening,
                current_balance_paise=opening,
                history_complete=hist_comp,
            )

    def apply_transaction(self, tx: Dict[str, any]) -> List[BalanceEvent]:
        """Apply a validated transaction to the internal ledger.

        Updates running balances, verifies conservation and non-negative constraints,
        and generates balance events for affected internal accounts.
        """
        tx_id = str(tx["transaction_id"]).strip()
        ts = str(tx["timestamp"]).strip()
        from_acc = str(tx["from_account"]).strip()
        to_acc = str(tx["to_account"]).strip()
        amount = int(tx["amount_paise"])
        tx_type = str(tx.get("transaction_type", "transfer")).strip()
        case_id = str(tx.get("case_id", "") or "").strip()
        evidence_status = str(tx.get("evidence_status", "unflagged")).strip()

        if amount <= 0:
            raise BalanceReconstructionError(
                f"Transaction '{tx_id}' has non-positive amount: {amount} paise"
            )

        events: List[BalanceEvent] = []

        is_from_external = from_acc.startswith(EXTERNAL_ACCOUNT_PREFIX)
        is_to_external = to_acc.startswith(EXTERNAL_ACCOUNT_PREFIX)

        if is_from_external and is_to_external:
            raise BalanceReconstructionError(
                f"Transaction '{tx_id}': Both counterparties external ({from_acc} -> {to_acc})"
            )

        # 1. External Deposit (EXT_ -> ACC_)
        if is_from_external and not is_to_external:
            if to_acc not in self.accounts:
                raise BalanceReconstructionError(
                    f"Transaction '{tx_id}': Unknown destination internal account '{to_acc}'"
                )
            acc_state = self.accounts[to_acc]
            bal_before = acc_state.current_balance_paise
            bal_after = bal_before + amount

            acc_state.current_balance_paise = bal_after
            acc_state.total_credits_paise += amount
            acc_state.external_deposits_paise += amount

            event = BalanceEvent(
                account_id=to_acc,
                timestamp=ts,
                transaction_id=tx_id,
                counterparty_account=from_acc,
                balance_before_paise=bal_before,
                amount_change_paise=amount,
                balance_after_paise=bal_after,
                direction="CREDIT",
                transaction_type=tx_type,
                case_id=case_id,
                evidence_status=evidence_status,
                history_complete=acc_state.history_complete,
            )
            events.append(event)
            self.balance_events.append(event)

        # 2. External Withdrawal (ACC_ -> EXT_)
        elif not is_from_external and is_to_external:
            if from_acc not in self.accounts:
                raise BalanceReconstructionError(
                    f"Transaction '{tx_id}': Unknown originating internal account '{from_acc}'"
                )
            acc_state = self.accounts[from_acc]
            bal_before = acc_state.current_balance_paise
            bal_after = bal_before - amount

            if bal_after < 0:
                raise NegativeBalanceError(
                    f"Account '{from_acc}' overdraft: balance drops to {bal_after} paise "
                    f"(required debit {amount} paise from balance {bal_before} paise) on transaction '{tx_id}'"
                )

            acc_state.current_balance_paise = bal_after
            acc_state.total_debits_paise += amount
            acc_state.external_withdrawals_paise += amount

            event = BalanceEvent(
                account_id=from_acc,
                timestamp=ts,
                transaction_id=tx_id,
                counterparty_account=to_acc,
                balance_before_paise=bal_before,
                amount_change_paise=-amount,
                balance_after_paise=bal_after,
                direction="DEBIT",
                transaction_type=tx_type,
                case_id=case_id,
                evidence_status=evidence_status,
                history_complete=acc_state.history_complete,
            )
            events.append(event)
            self.balance_events.append(event)

        # 3. Internal Transfer (ACC_ -> ACC_)
        else:
            if from_acc not in self.accounts:
                raise BalanceReconstructionError(
                    f"Transaction '{tx_id}': Unknown sender internal account '{from_acc}'"
                )
            if to_acc not in self.accounts:
                raise BalanceReconstructionError(
                    f"Transaction '{tx_id}': Unknown recipient internal account '{to_acc}'"
                )
            if from_acc == to_acc:
                raise BalanceReconstructionError(
                    f"Transaction '{tx_id}': Self-transfer prohibited ({from_acc})"
                )

            sender = self.accounts[from_acc]
            receiver = self.accounts[to_acc]

            sender_before = sender.current_balance_paise
            sender_after = sender_before - amount

            if sender_after < 0:
                raise NegativeBalanceError(
                    f"Account '{from_acc}' overdraft: balance drops to {sender_after} paise "
                    f"(required transfer {amount} paise from balance {sender_before} paise) on transaction '{tx_id}'"
                )

            receiver_before = receiver.current_balance_paise
            receiver_after = receiver_before + amount

            # Verify conservation of transfer across accounts
            if (sender_after - sender_before) + (receiver_after - receiver_before) != 0:
                raise BalanceConservationError(
                    f"Transaction '{tx_id}': Transfer value not conserved across '{from_acc}' and '{to_acc}'"
                )

            sender.current_balance_paise = sender_after
            sender.total_debits_paise += amount
            sender.internal_debits_paise += amount

            receiver.current_balance_paise = receiver_after
            receiver.total_credits_paise += amount
            receiver.internal_credits_paise += amount

            event_sender = BalanceEvent(
                account_id=from_acc,
                timestamp=ts,
                transaction_id=tx_id,
                counterparty_account=to_acc,
                balance_before_paise=sender_before,
                amount_change_paise=-amount,
                balance_after_paise=sender_after,
                direction="DEBIT",
                transaction_type=tx_type,
                case_id=case_id,
                evidence_status=evidence_status,
                history_complete=sender.history_complete,
            )
            event_receiver = BalanceEvent(
                account_id=to_acc,
                timestamp=ts,
                transaction_id=tx_id,
                counterparty_account=from_acc,
                balance_before_paise=receiver_before,
                amount_change_paise=amount,
                balance_after_paise=receiver_after,
                direction="CREDIT",
                transaction_type=tx_type,
                case_id=case_id,
                evidence_status=evidence_status,
                history_complete=receiver.history_complete,
            )

            events.extend([event_sender, event_receiver])
            self.balance_events.extend([event_sender, event_receiver])

        return events

    def get_balance_history_dataframe(self) -> pd.DataFrame:
        """Export balance history events as an audit-ready DataFrame."""
        if not self.balance_events:
            return pd.DataFrame(columns=[
                "account_id",
                "timestamp",
                "transaction_id",
                "counterparty_account",
                "balance_before_paise",
                "amount_change_paise",
                "balance_after_paise",
                "direction",
                "transaction_type",
                "case_id",
                "evidence_status",
                "history_complete",
            ])

        records = [e.to_dict() for e in self.balance_events]
        return pd.DataFrame(records)

    def get_account_balance(self, account_id: str) -> int:
        """Get the current balance of an account in paise."""
        if account_id not in self.accounts:
            raise KeyError(f"Unknown account_id: {account_id}")
        return self.accounts[account_id].current_balance_paise

    def get_total_ledger_balance(self) -> int:
        """Get the sum of current balances across all internal accounts."""
        return sum(acc.current_balance_paise for acc in self.accounts.values())

    def get_total_opening_balance(self) -> int:
        """Get the sum of opening balances across all internal accounts."""
        return sum(acc.opening_balance_paise for acc in self.accounts.values())
