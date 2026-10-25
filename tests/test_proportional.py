"""Unit tests for Smart-Freeze proportional fund-tracing engine (engine.proportional).

Tests:
1. Direct transfer of suspected funds without commingling.
2. Partial transfer leaving suspected funds in the sender account.
3. Proportional allocation from a commingled balance (clean + suspected).
4. Fan-out split transfers across multiple destination accounts.
5. Multiple distinct suspected-source transactions tracked separately.
6. External withdrawal from a commingled account.
7. Independent legitimate account with zero suspected funds.
8. Deterministic integer-paise rounding with remainder allocation.
9. Strict conservation of suspected funds across internal and external paths.
10. Insufficient balance / invalid state rejection.
11. Incomplete history accounts explicitly surfaced.
12. Strict isolation from hidden ground truth.
13. End-to-end tracing on real synthetic Case 1 with exact paise validation.
"""

import os
from pathlib import Path
import pytest

from engine.proportional import ProportionalTracer
from engine.tracing_models import (
    CATEGORY_LEGITIMATE,
    CATEGORY_UNKNOWN,
    AccountSourcePool,
    make_suspected_category,
)
from pipeline.adapters.synthetic_adapter import SyntheticAdapter

WORKSPACE_DIR = Path(__file__).resolve().parent.parent
REAL_SYNTHETIC_DIR = Path(os.environ.get("SMART_FREEZE_DATA_DIR", str(WORKSPACE_DIR / "data" / "fixtures" / "demo_3case")))


# ==============================================================================
# 1. Direct Transfer of Suspected Funds
# ==============================================================================

def test_direct_transfer_of_suspected_funds():
    accounts = [
        {"account_id": "ACC_VICTIM", "opening_balance_paise": 1000000, "history_complete": True},
        {"account_id": "ACC_MULE", "opening_balance_paise": 0, "history_complete": True},
        {"account_id": "ACC_LAYER2", "opening_balance_paise": 0, "history_complete": True},
    ]
    transactions = [
        # Source fraud transaction
        {
            "transaction_id": "TXN_SRC",
            "timestamp": "2026-01-15T10:00:00Z",
            "from_account": "ACC_VICTIM",
            "to_account": "ACC_MULE",
            "amount_paise": 500000,
            "transaction_type": "transfer",
            "case_id": "CASE-1",
        },
        # Direct onward transfer: 500,000 paise to Layer 2
        {
            "transaction_id": "TXN_FWD",
            "timestamp": "2026-01-15T11:00:00Z",
            "from_account": "ACC_MULE",
            "to_account": "ACC_LAYER2",
            "amount_paise": 500000,
            "transaction_type": "transfer",
            "case_id": "CASE-1",
        },
    ]

    tracer = ProportionalTracer(accounts, transactions)
    result = tracer.trace_source_transaction("TXN_SRC", source_case_id="CASE-1")

    assert result.retained_suspected_paise.get("ACC_MULE", 0) == 0
    assert result.retained_suspected_paise.get("ACC_LAYER2", 0) == 500000
    assert result.total_retained_suspected() == 500000
    assert result.total_withdrawn_suspected() == 0
    assert len(result.transfer_hops) == 2


# ==============================================================================
# 2. Partial Transfer Leaving Suspected Funds Behind
# ==============================================================================

def test_partial_transfer_leaves_funds_behind():
    accounts = [
        {"account_id": "ACC_VICTIM", "opening_balance_paise": 1000000, "history_complete": True},
        {"account_id": "ACC_MULE", "opening_balance_paise": 0, "history_complete": True},
        {"account_id": "ACC_LAYER2", "opening_balance_paise": 0, "history_complete": True},
    ]
    transactions = [
        {
            "transaction_id": "TXN_SRC",
            "timestamp": "2026-01-15T10:00:00Z",
            "from_account": "ACC_VICTIM",
            "to_account": "ACC_MULE",
            "amount_paise": 500000,
            "transaction_type": "transfer",
            "case_id": "CASE-1",
        },
        # Mule only forwards 200,000 paise out of 500,000 paise
        {
            "transaction_id": "TXN_FWD",
            "timestamp": "2026-01-15T11:00:00Z",
            "from_account": "ACC_MULE",
            "to_account": "ACC_LAYER2",
            "amount_paise": 200000,
            "transaction_type": "transfer",
            "case_id": "CASE-1",
        },
    ]

    tracer = ProportionalTracer(accounts, transactions)
    result = tracer.trace_source_transaction("TXN_SRC", source_case_id="CASE-1")

    assert result.retained_suspected_paise["ACC_MULE"] == 300000
    assert result.retained_suspected_paise["ACC_LAYER2"] == 200000
    assert result.total_retained_suspected() == 500000


# ==============================================================================
# 3. Proportional Allocation from Commingled Balance
# ==============================================================================

def test_commingled_balance_proportional_allocation():
    accounts = [
        {"account_id": "ACC_VICTIM", "opening_balance_paise": 1000000, "history_complete": True},
        # Mule already has 100,000 paise legitimate opening balance!
        {"account_id": "ACC_MULE", "opening_balance_paise": 100000, "history_complete": True},
        {"account_id": "ACC_RECIPIENT", "opening_balance_paise": 0, "history_complete": True},
    ]
    transactions = [
        # Mule receives 100,000 paise suspected (Total balance: 200,000: 50% clean, 50% suspected)
        {
            "transaction_id": "TXN_SRC",
            "timestamp": "2026-01-15T10:00:00Z",
            "from_account": "ACC_VICTIM",
            "to_account": "ACC_MULE",
            "amount_paise": 100000,
            "transaction_type": "transfer",
            "case_id": "CASE-1",
        },
        # Mule transfers 60,000 paise onward
        # Under proportional rule: 50% of 60,000 = 30,000 suspected, 30,000 clean!
        {
            "transaction_id": "TXN_FWD",
            "timestamp": "2026-01-15T12:00:00Z",
            "from_account": "ACC_MULE",
            "to_account": "ACC_RECIPIENT",
            "amount_paise": 60000,
            "transaction_type": "transfer",
            "case_id": "CASE-1",
        },
    ]

    tracer = ProportionalTracer(accounts, transactions)
    result = tracer.trace_source_transaction("TXN_SRC", source_case_id="CASE-1")

    # Mule retained: 70,000 clean, 70,000 suspected
    assert result.retained_suspected_paise["ACC_MULE"] == 70000
    # Recipient received: 30,000 clean, 30,000 suspected
    assert result.retained_suspected_paise["ACC_RECIPIENT"] == 30000
    assert result.total_retained_suspected() == 100000


# ==============================================================================
# 4. Split Transfers (Smurfing / Fan-Out)
# ==============================================================================

def test_split_transfers_smurfing():
    accounts = [
        {"account_id": "ACC_VICTIM", "opening_balance_paise": 1000000, "history_complete": True},
        {"account_id": "ACC_SPLITTER", "opening_balance_paise": 0, "history_complete": True},
        {"account_id": "ACC_MULE_1", "opening_balance_paise": 0, "history_complete": True},
        {"account_id": "ACC_MULE_2", "opening_balance_paise": 0, "history_complete": True},
        {"account_id": "ACC_MULE_3", "opening_balance_paise": 0, "history_complete": True},
    ]
    transactions = [
        {
            "transaction_id": "TXN_SRC",
            "timestamp": "2026-01-15T10:00:00Z",
            "from_account": "ACC_VICTIM",
            "to_account": "ACC_SPLITTER",
            "amount_paise": 900000,
            "transaction_type": "transfer",
            "case_id": "CASE-2",
        },
        # Split 3 ways: 300,000 each
        {"transaction_id": "TXN_S1", "timestamp": "2026-01-15T11:00:00Z", "from_account": "ACC_SPLITTER", "to_account": "ACC_MULE_1", "amount_paise": 300000, "transaction_type": "transfer"},
        {"transaction_id": "TXN_S2", "timestamp": "2026-01-15T11:05:00Z", "from_account": "ACC_SPLITTER", "to_account": "ACC_MULE_2", "amount_paise": 300000, "transaction_type": "transfer"},
        {"transaction_id": "TXN_S3", "timestamp": "2026-01-15T11:10:00Z", "from_account": "ACC_SPLITTER", "to_account": "ACC_MULE_3", "amount_paise": 300000, "transaction_type": "transfer"},
    ]

    tracer = ProportionalTracer(accounts, transactions)
    result = tracer.trace_source_transaction("TXN_SRC", source_case_id="CASE-2")

    assert result.retained_suspected_paise.get("ACC_SPLITTER", 0) == 0
    assert result.retained_suspected_paise["ACC_MULE_1"] == 300000
    assert result.retained_suspected_paise["ACC_MULE_2"] == 300000
    assert result.retained_suspected_paise["ACC_MULE_3"] == 300000
    assert result.total_retained_suspected() == 900000


# ==============================================================================
# 5. Multiple Suspected Sources Kept Distinct
# ==============================================================================

def test_multiple_sources_distinct():
    cat1 = make_suspected_category("TXN_SRC_1", "CASE-A")
    cat2 = make_suspected_category("TXN_SRC_2", "CASE-B")
    assert cat1 != cat2
    assert "CASE-A" in cat1
    assert "CASE-B" in cat2


# ==============================================================================
# 6. External Withdrawal from Commingled Account
# ==============================================================================

def test_external_withdrawal_from_commingled_account():
    accounts = [
        {"account_id": "ACC_VICTIM", "opening_balance_paise": 1000000, "history_complete": True},
        {"account_id": "ACC_MULE", "opening_balance_paise": 50000, "history_complete": True},
    ]
    transactions = [
        # Mule receives 50,000 suspected. Total balance: 100,000 (50% clean, 50% suspected)
        {
            "transaction_id": "TXN_SRC",
            "timestamp": "2026-01-15T10:00:00Z",
            "from_account": "ACC_VICTIM",
            "to_account": "ACC_MULE",
            "amount_paise": 50000,
            "transaction_type": "transfer",
            "case_id": "CASE-1",
        },
        # Mule withdraws 40,000 paise to EXT_ATM
        # Proportional: 50% of 40,000 = 20,000 clean, 20,000 suspected withdrawn!
        {
            "transaction_id": "TXN_WTH",
            "timestamp": "2026-01-15T12:00:00Z",
            "from_account": "ACC_MULE",
            "to_account": "EXT_CASH_ATM",
            "amount_paise": 40000,
            "transaction_type": "withdrawal",
            "case_id": "CASE-1",
        },
    ]

    tracer = ProportionalTracer(accounts, transactions)
    result = tracer.trace_source_transaction("TXN_SRC", source_case_id="CASE-1")

    # Retained in Mule: 30,000 paise suspected (plus 30,000 clean)
    assert result.retained_suspected_paise["ACC_MULE"] == 30000
    # Withdrawn via ATM: 20,000 paise suspected
    assert result.withdrawn_suspected_paise["EXT_CASH_ATM"] == 20000
    # Strict conservation: 30,000 retained + 20,000 withdrawn == 50,000 initial suspected
    assert result.total_retained_suspected() + result.total_withdrawn_suspected() == 50000


# ==============================================================================
# 7. Independent Legitimate Account
# ==============================================================================

def test_independent_account_zero_attribution():
    accounts = [
        {"account_id": "ACC_VICTIM", "opening_balance_paise": 1000000, "history_complete": True},
        {"account_id": "ACC_MULE", "opening_balance_paise": 0, "history_complete": True},
        {"account_id": "ACC_INNOCENT_BIZ", "opening_balance_paise": 500000, "history_complete": True},
    ]
    transactions = [
        {
            "transaction_id": "TXN_SRC",
            "timestamp": "2026-01-15T10:00:00Z",
            "from_account": "ACC_VICTIM",
            "to_account": "ACC_MULE",
            "amount_paise": 500000,
            "transaction_type": "transfer",
            "case_id": "CASE-1",
        },
    ]

    tracer = ProportionalTracer(accounts, transactions)
    result = tracer.trace_source_transaction("TXN_SRC", source_case_id="CASE-1")

    assert "ACC_INNOCENT_BIZ" not in result.retained_suspected_paise
    assert result.retained_suspected_paise.get("ACC_INNOCENT_BIZ", 0) == 0


# ==============================================================================
# 8. Deterministic Integer-Paise Rounding with Remainder
# ==============================================================================

def test_deterministic_rounding_remainder_allocation():
    pool = AccountSourcePool(account_id="ACC_ROUNDING")
    # Pool with 33 paise in CAT_A and 67 paise in CAT_B (Total = 100 paise)
    pool.credit("CAT_A", 33)
    pool.credit("CAT_B", 67)

    # Spend 10 paise:
    # 10 * 33 / 100 = 3 rem 30
    # 10 * 67 / 100 = 6 rem 70
    # Remainder 1 awarded to CAT_B (rem 70 > 30)
    final_alloc, base, rems, awarded = ProportionalTracer.allocate_proportionally(pool, 10)

    assert final_alloc["CAT_A"] == 3
    assert final_alloc["CAT_B"] == 7
    assert sum(final_alloc.values()) == 10
    assert awarded["CAT_B"] == 1
    assert awarded["CAT_A"] == 0


# ==============================================================================
# 9. Insufficient Balance Rejection
# ==============================================================================

def test_insufficient_balance_rejected():
    pool = AccountSourcePool(account_id="ACC_EMPTY")
    pool.credit("CAT_A", 500)
    with pytest.raises(ValueError) as exc:
        ProportionalTracer.allocate_proportionally(pool, 600)
    assert "insufficient balance" in str(exc.value).lower()


# ==============================================================================
# 10. Incomplete History Surfaced
# ==============================================================================

def test_incomplete_history_flagged():
    accounts = [
        {"account_id": "ACC_VICTIM", "opening_balance_paise": 1000000, "history_complete": True},
        {"account_id": "ACC_INC", "opening_balance_paise": 100000, "history_complete": False},
    ]
    transactions = [
        {
            "transaction_id": "TXN_SRC",
            "timestamp": "2026-01-15T10:00:00Z",
            "from_account": "ACC_VICTIM",
            "to_account": "ACC_INC",
            "amount_paise": 200000,
            "transaction_type": "transfer",
            "case_id": "CASE-1",
        },
    ]

    tracer = ProportionalTracer(accounts, transactions)
    result = tracer.trace_source_transaction("TXN_SRC", source_case_id="CASE-1")

    assert "ACC_INC" in result.incomplete_history_accounts
    assert result.retained_suspected_paise["ACC_INC"] == 200000


# ==============================================================================
# 11. Strict Isolation from Hidden Ground Truth
# ==============================================================================

def test_ground_truth_isolation():
    adapter = SyntheticAdapter(REAL_SYNTHETIC_DIR)
    accounts, txns, cases = adapter.load_dataset()
    tracer = ProportionalTracer(accounts, txns)

    # Verify no hidden ground truth is loaded or exposed
    result = tracer.trace_source_transaction("TXN_0009")
    res_dict = result.to_dict()
    assert "_scenario" not in str(res_dict)
    assert "lot_id" not in str(res_dict)


# ==============================================================================
# 12. Real Synthetic Case 1 Tracing & Exact Conservation
# ==============================================================================

def test_real_synthetic_case_1_tracing():
    adapter = SyntheticAdapter(REAL_SYNTHETIC_DIR)
    accounts, txns, cases = adapter.load_dataset()
    tracer = ProportionalTracer(accounts, txns)

    # TXN_0009: 10,000,000 paise from ACC_VICTIM_01 to ACC_MULE_DIRECT_01 (Case 1)
    result = tracer.trace_source_transaction("TXN_0009", source_case_id="CASE-2026-001")

    assert result.source_transaction_id == "TXN_0009"
    assert result.initial_suspected_amount_paise == 10000000

    # Strict conservation invariant across the entire downstream graph:
    # Retained + Withdrawn == Initial Suspected Amount!
    total_retained = result.total_retained_suspected()
    total_withdrawn = result.total_withdrawn_suspected()
    assert total_retained + total_withdrawn == 10000000

    # Mule received 10,000,000 with 500,000 opening balance (Total 10,500,000: 95.24% suspected)
    # Then forwarded 8,000,000 and withdrew 500,000 to ATM
    assert result.withdrawn_suspected_paise.get("EXT_CASH_ATM", 0) > 0
    assert result.retained_suspected_paise["ACC_MULE_DIRECT_01"] > 0
    assert result.retained_suspected_paise["ACC_COMMINGLED_01"] > 0

    # Verify explanations exist and are detailed
    assert len(result.explanations) > 0
    assert len(result.transfer_hops) > 0
