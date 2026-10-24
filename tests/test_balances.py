"""Unit tests for FairHold balance tracking and reconstruction (engine.balances).

Tests:
1. Opening balances are loaded accurately.
2. Internal transfer debits sender and credits recipient by exactly the same amount.
3. Balance conservation across internal accounts.
4. External deposits increase account balance.
5. External withdrawals decrease account balance.
6. Unsupported negative balances (overdrafts) are rejected.
7. Negative opening balances are rejected.
8. Incomplete account history flag is preserved.
9. Every balance event has complete transaction provenance.
"""

import pytest

from engine.balances import (
    BalanceConservationError,
    BalanceReconstructionError,
    BalanceTracker,
    NegativeBalanceError,
)


@pytest.fixture
def sample_accounts():
    return [
        {"account_id": "ACC_A", "account_type": "savings", "opening_balance_paise": 100000, "history_complete": True},
        {"account_id": "ACC_B", "account_type": "current", "opening_balance_paise": 200000, "history_complete": True},
        {"account_id": "ACC_INCOMPLETE", "account_type": "savings", "opening_balance_paise": 50000, "history_complete": False},
    ]


def test_opening_balances_initialized(sample_accounts):
    tracker = BalanceTracker(sample_accounts)
    assert tracker.get_account_balance("ACC_A") == 100000
    assert tracker.get_account_balance("ACC_B") == 200000
    assert tracker.get_account_balance("ACC_INCOMPLETE") == 50000
    assert tracker.get_total_opening_balance() == 350000
    assert tracker.get_total_ledger_balance() == 350000


def test_internal_transfer_debits_and_credits_conserved(sample_accounts):
    tracker = BalanceTracker(sample_accounts)
    tx = {
        "transaction_id": "TXN_001",
        "timestamp": "2026-01-15T10:00:00Z",
        "from_account": "ACC_A",
        "to_account": "ACC_B",
        "amount_paise": 40000,
        "transaction_type": "transfer",
        "case_id": "CASE-2026-001",
        "evidence_status": "suspected_fraud",
    }
    events = tracker.apply_transaction(tx)
    assert len(events) == 2

    # Sender: debited 40,000 paise
    ev_sender = events[0]
    assert ev_sender.account_id == "ACC_A"
    assert ev_sender.direction == "DEBIT"
    assert ev_sender.balance_before_paise == 100000
    assert ev_sender.amount_change_paise == -40000
    assert ev_sender.balance_after_paise == 60000
    assert ev_sender.counterparty_account == "ACC_B"
    assert ev_sender.transaction_id == "TXN_001"
    assert tracker.get_account_balance("ACC_A") == 60000

    # Receiver: credited 40,000 paise
    ev_receiver = events[1]
    assert ev_receiver.account_id == "ACC_B"
    assert ev_receiver.direction == "CREDIT"
    assert ev_receiver.balance_before_paise == 200000
    assert ev_receiver.amount_change_paise == 40000
    assert ev_receiver.balance_after_paise == 240000
    assert ev_receiver.counterparty_account == "ACC_A"
    assert tracker.get_account_balance("ACC_B") == 240000

    # Strict conservation
    assert ev_sender.amount_change_paise + ev_receiver.amount_change_paise == 0
    assert tracker.get_total_ledger_balance() == 350000


def test_external_deposit_increases_balance(sample_accounts):
    tracker = BalanceTracker(sample_accounts)
    tx = {
        "transaction_id": "TXN_DEP_01",
        "timestamp": "2026-01-15T11:00:00Z",
        "from_account": "EXT_SALARY_ORIGIN",
        "to_account": "ACC_A",
        "amount_paise": 75000,
        "transaction_type": "deposit",
        "case_id": "",
        "evidence_status": "verified_legitimate",
    }
    events = tracker.apply_transaction(tx)
    assert len(events) == 1
    ev = events[0]
    assert ev.account_id == "ACC_A"
    assert ev.direction == "CREDIT"
    assert ev.balance_before_paise == 100000
    assert ev.amount_change_paise == 75000
    assert ev.balance_after_paise == 175000
    assert tracker.get_account_balance("ACC_A") == 175000
    assert tracker.get_total_ledger_balance() == 425000


def test_external_withdrawal_decreases_balance(sample_accounts):
    tracker = BalanceTracker(sample_accounts)
    tx = {
        "transaction_id": "TXN_WTH_01",
        "timestamp": "2026-01-15T12:00:00Z",
        "from_account": "ACC_B",
        "to_account": "EXT_CASH_ATM",
        "amount_paise": 50000,
        "transaction_type": "withdrawal",
        "case_id": "",
        "evidence_status": "verified_legitimate",
    }
    events = tracker.apply_transaction(tx)
    assert len(events) == 1
    ev = events[0]
    assert ev.account_id == "ACC_B"
    assert ev.direction == "DEBIT"
    assert ev.balance_before_paise == 200000
    assert ev.amount_change_paise == -50000
    assert ev.balance_after_paise == 150000
    assert tracker.get_account_balance("ACC_B") == 150000
    assert tracker.get_total_ledger_balance() == 300000


def test_overdraft_raises_negative_balance_error(sample_accounts):
    tracker = BalanceTracker(sample_accounts)
    tx = {
        "transaction_id": "TXN_OVERDRAFT",
        "timestamp": "2026-01-15T13:00:00Z",
        "from_account": "ACC_A",
        "to_account": "EXT_MERCHANT",
        "amount_paise": 150000,  # Balance is only 100,000
        "transaction_type": "withdrawal",
    }
    with pytest.raises(NegativeBalanceError) as exc:
        tracker.apply_transaction(tx)
    assert "overdraft" in str(exc.value).lower()
    assert "ACC_A" in str(exc.value)


def test_negative_opening_balance_rejected():
    invalid_accounts = [
        {"account_id": "ACC_NEG", "opening_balance_paise": -1000, "history_complete": True}
    ]
    with pytest.raises(NegativeBalanceError):
        BalanceTracker(invalid_accounts)


def test_incomplete_history_flag_preserved(sample_accounts):
    tracker = BalanceTracker(sample_accounts)
    tx = {
        "transaction_id": "TXN_INC_01",
        "timestamp": "2026-01-15T14:00:00Z",
        "from_account": "EXT_BANK",
        "to_account": "ACC_INCOMPLETE",
        "amount_paise": 20000,
        "transaction_type": "deposit",
    }
    events = tracker.apply_transaction(tx)
    assert events[0].history_complete is False


def test_provenance_and_dataframe_export(sample_accounts):
    tracker = BalanceTracker(sample_accounts)
    tx = {
        "transaction_id": "TXN_PROV_01",
        "timestamp": "2026-01-15T15:00:00Z",
        "from_account": "ACC_A",
        "to_account": "ACC_B",
        "amount_paise": 10000,
        "transaction_type": "transfer",
        "case_id": "CASE-2026-999",
        "evidence_status": "suspected_fraud",
    }
    tracker.apply_transaction(tx)
    df = tracker.get_balance_history_dataframe()
    assert len(df) == 2
    assert "case_id" in df.columns
    assert "transaction_id" in df.columns
    assert df["case_id"].iloc[0] == "CASE-2026-999"
    assert df["transaction_id"].iloc[0] == "TXN_PROV_01"
