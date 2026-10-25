"""Unit tests for Smart-Freeze Lowest Intermediate Balance Rule (LIBR) fund-tracing engine (engine.libr).

Tests:
1. Direct source inflow.
2. Source inflow followed by partial withdrawal (clean funds spend first).
3. Balance reduction followed by later deposit (LIBR no-replenishment rule).
4. Source inflow followed by multiple withdrawals.
5. Internal transfer to another account (propagation of suspected funds).
6. Multi-hop transfers across multiple accounts (Victim -> Mule -> L2 -> L3).
7. Multiple distinct suspected-source transactions.
8. Equal timestamps and deterministic tie-breaking.
9. Outgoing transaction exceeding available balance (overdraft protection).
10. Incomplete historical information explicitly surfaced.
11. Exact integer-paise calculations.
12. Preservation of provenance and transfer hops.
13. Strict isolation from hidden ground-truth labels.
14. End-to-end tracing on real synthetic Case 1 with exact integer-paise conservation.
"""

import inspect
import os
from pathlib import Path
import pytest

from engine.libr import LIBRTracer
from engine.tracing_models import make_suspected_category
from pipeline.adapters.synthetic_adapter import SyntheticAdapter

WORKSPACE_DIR = Path(__file__).resolve().parent.parent
REAL_SYNTHETIC_DIR = Path(os.environ.get("SMART_FREEZE_DATA_DIR", str(WORKSPACE_DIR / "data" / "fixtures" / "demo_3case")))


# ==============================================================================
# 1. Direct Source Inflow
# ==============================================================================

def test_direct_source_inflow():
    """Test 1: Direct transfer from victim to mule establishes suspected attribution."""
    accounts = [
        {"account_id": "ACC_VICTIM", "opening_balance_paise": 1000000, "history_complete": True},
        {"account_id": "ACC_MULE", "opening_balance_paise": 0, "history_complete": True},
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

    tracer = LIBRTracer(accounts, transactions)
    result = tracer.trace_source_transaction("TXN_SRC", source_case_id="CASE-1")

    assert result.retained_suspected_paise["ACC_MULE"] == 500000
    assert result.total_retained_suspected() == 500000
    assert result.total_withdrawn_suspected() == 0
    assert result.lowest_intermediate_balances["ACC_MULE"] == 500000
    assert len(result.transfer_hops) == 1


# ==============================================================================
# 2. Source Inflow Followed by Partial Withdrawal
# ==============================================================================

def test_source_inflow_followed_by_partial_withdrawal():
    """Test 2: Account has clean funds + suspected funds.
    Clean funds are presumed spent first; suspected funds only dissipated after clean funds are exhausted.
    """
    accounts = [
        {"account_id": "ACC_VICTIM", "opening_balance_paise": 1000000, "history_complete": True},
        # Mule has 20,000 clean opening balance
        {"account_id": "ACC_MULE", "opening_balance_paise": 20000, "history_complete": True},
    ]
    transactions = [
        # Mule receives 50,000 paise suspected (Total balance = 70,000; clean = 20,000, suspected = 50,000)
        {
            "transaction_id": "TXN_SRC",
            "timestamp": "2026-01-15T10:00:00Z",
            "from_account": "ACC_VICTIM",
            "to_account": "ACC_MULE",
            "amount_paise": 50000,
            "transaction_type": "transfer",
            "case_id": "CASE-1",
        },
        # Withdrawal 1: 15,000 paise. Absorbed entirely by 20,000 clean funds!
        {
            "transaction_id": "TXN_WTH_1",
            "timestamp": "2026-01-15T11:00:00Z",
            "from_account": "ACC_MULE",
            "to_account": "EXT_ATM",
            "amount_paise": 15000,
            "transaction_type": "withdrawal",
            "case_id": "CASE-1",
        },
        # Withdrawal 2: 25,000 paise. Clean funds only have 5,000 left.
        # Excess 20,000 draws from suspected funds.
        {
            "transaction_id": "TXN_WTH_2",
            "timestamp": "2026-01-15T12:00:00Z",
            "from_account": "ACC_MULE",
            "to_account": "EXT_ATM",
            "amount_paise": 25000,
            "transaction_type": "withdrawal",
            "case_id": "CASE-1",
        },
    ]

    tracer = LIBRTracer(accounts, transactions)
    result = tracer.trace_source_transaction("TXN_SRC", source_case_id="CASE-1")

    # Mule retains 30,000 paise suspected
    assert result.retained_suspected_paise["ACC_MULE"] == 30000
    # EXT_ATM received 20,000 paise suspected
    assert result.withdrawn_suspected_paise["EXT_ATM"] == 20000
    assert result.total_retained_suspected() == 30000
    assert result.total_withdrawn_suspected() == 20000
    assert result.lowest_intermediate_balances["ACC_MULE"] == 30000


# ==============================================================================
# 3. Balance Reduction Followed by Later Deposit (No-Replenishment Rule)
# ==============================================================================

def test_balance_reduction_followed_by_later_deposit():
    """Test 3: LIBR No-Replenishment Rule.
    When an account balance falls, attributed suspected funds are permanently capped.
    Later deposits from legitimate third parties do NOT restore previously dissipated attribution.
    """
    accounts = [
        {"account_id": "ACC_VICTIM", "opening_balance_paise": 1000000, "history_complete": True},
        {"account_id": "ACC_MULE", "opening_balance_paise": 0, "history_complete": True},
    ]
    transactions = [
        # Inflow: 100,000 paise suspected. Balance = 100,000
        {
            "transaction_id": "TXN_SRC",
            "timestamp": "2026-01-15T10:00:00Z",
            "from_account": "ACC_VICTIM",
            "to_account": "ACC_MULE",
            "amount_paise": 100000,
            "transaction_type": "transfer",
            "case_id": "CASE-1",
        },
        # Withdrawal: 60,000 paise. Balance drops to 40,000 paise.
        # Attributed suspected is capped at 40,000 paise.
        {
            "transaction_id": "TXN_WTH",
            "timestamp": "2026-01-15T11:00:00Z",
            "from_account": "ACC_MULE",
            "to_account": "EXT_ATM",
            "amount_paise": 60000,
            "transaction_type": "withdrawal",
            "case_id": "CASE-1",
        },
        # Later independent deposit: 50,000 paise from third party.
        # Balance rises to 90,000 paise.
        # Under LIBR No-Replenishment: Attributed suspected remains capped at 40,000 paise!
        {
            "transaction_id": "TXN_DEP",
            "timestamp": "2026-01-15T12:00:00Z",
            "from_account": "EXT_CLIENT",
            "to_account": "ACC_MULE",
            "amount_paise": 50000,
            "transaction_type": "deposit",
        },
    ]

    tracer = LIBRTracer(accounts, transactions)
    result = tracer.trace_source_transaction("TXN_SRC", source_case_id="CASE-1")

    assert result.retained_suspected_paise["ACC_MULE"] == 40000
    assert result.withdrawn_suspected_paise["EXT_ATM"] == 60000
    assert result.lowest_intermediate_balances["ACC_MULE"] == 40000
    assert result.total_retained_suspected() == 40000


# ==============================================================================
# 4. Source Inflow Followed by Multiple Withdrawals
# ==============================================================================

def test_source_inflow_followed_by_multiple_withdrawals():
    """Test 4: Sequential withdrawals progressively reduce balance and track intermediate low."""
    accounts = [
        {"account_id": "ACC_VICTIM", "opening_balance_paise": 1000000, "history_complete": True},
        {"account_id": "ACC_MULE", "opening_balance_paise": 0, "history_complete": True},
    ]
    transactions = [
        {
            "transaction_id": "TXN_SRC",
            "timestamp": "2026-01-15T10:00:00Z",
            "from_account": "ACC_VICTIM",
            "to_account": "ACC_MULE",
            "amount_paise": 100000,
            "transaction_type": "transfer",
            "case_id": "CASE-1",
        },
        {
            "transaction_id": "TXN_W1",
            "timestamp": "2026-01-15T11:00:00Z",
            "from_account": "ACC_MULE",
            "to_account": "EXT_ATM",
            "amount_paise": 30000,
            "transaction_type": "withdrawal",
        },
        {
            "transaction_id": "TXN_W2",
            "timestamp": "2026-01-15T12:00:00Z",
            "from_account": "ACC_MULE",
            "to_account": "EXT_ATM",
            "amount_paise": 40000,
            "transaction_type": "withdrawal",
        },
        {
            "transaction_id": "TXN_W3",
            "timestamp": "2026-01-15T13:00:00Z",
            "from_account": "ACC_MULE",
            "to_account": "EXT_ATM",
            "amount_paise": 20000,
            "transaction_type": "withdrawal",
        },
    ]

    tracer = LIBRTracer(accounts, transactions)
    result = tracer.trace_source_transaction("TXN_SRC", source_case_id="CASE-1")

    assert result.retained_suspected_paise["ACC_MULE"] == 10000
    assert result.withdrawn_suspected_paise["EXT_ATM"] == 90000
    assert result.lowest_intermediate_balances["ACC_MULE"] == 10000


# ==============================================================================
# 5. Internal Transfer to Another Account
# ==============================================================================

def test_internal_transfer_to_another_account():
    """Test 5: Internal transfer propagates suspected attribution when clean funds are exhausted."""
    accounts = [
        {"account_id": "ACC_VICTIM", "opening_balance_paise": 1000000, "history_complete": True},
        # Mule starts with 10,000 clean opening balance
        {"account_id": "ACC_MULE", "opening_balance_paise": 10000, "history_complete": True},
        {"account_id": "ACC_LAYER2", "opening_balance_paise": 0, "history_complete": True},
    ]
    transactions = [
        # Mule receives 50,000 suspected. Balance = 60,000 (10,000 clean, 50,000 suspected)
        {
            "transaction_id": "TXN_SRC",
            "timestamp": "2026-01-15T10:00:00Z",
            "from_account": "ACC_VICTIM",
            "to_account": "ACC_MULE",
            "amount_paise": 50000,
            "transaction_type": "transfer",
            "case_id": "CASE-1",
        },
        # Mule sends 40,000 to Layer 2.
        # Clean funds absorb first 10,000. Suspected funds absorb remaining 30,000.
        {
            "transaction_id": "TXN_TRANSFER",
            "timestamp": "2026-01-15T12:00:00Z",
            "from_account": "ACC_MULE",
            "to_account": "ACC_LAYER2",
            "amount_paise": 40000,
            "transaction_type": "transfer",
            "case_id": "CASE-1",
        },
    ]

    tracer = LIBRTracer(accounts, transactions)
    result = tracer.trace_source_transaction("TXN_SRC", source_case_id="CASE-1")

    assert result.retained_suspected_paise["ACC_MULE"] == 20000
    assert result.retained_suspected_paise["ACC_LAYER2"] == 30000
    assert result.total_retained_suspected() == 50000
    assert len(result.transfer_hops) == 2


# ==============================================================================
# 6. Transfers Across Multiple Accounts (Multi-Hop)
# ==============================================================================

def test_transfers_across_multiple_accounts():
    """Test 6: Multi-hop propagation: Victim -> Mule -> L2 -> L3."""
    accounts = [
        {"account_id": "ACC_VICTIM", "opening_balance_paise": 1000000, "history_complete": True},
        {"account_id": "ACC_MULE", "opening_balance_paise": 0, "history_complete": True},
        {"account_id": "ACC_L2", "opening_balance_paise": 0, "history_complete": True},
        {"account_id": "ACC_L3", "opening_balance_paise": 0, "history_complete": True},
    ]
    transactions = [
        # Victim -> Mule: 100,000 paise suspected
        {
            "transaction_id": "TXN_SRC",
            "timestamp": "2026-01-15T10:00:00Z",
            "from_account": "ACC_VICTIM",
            "to_account": "ACC_MULE",
            "amount_paise": 100000,
            "transaction_type": "transfer",
            "case_id": "CASE-1",
        },
        # Mule -> L2: 70,000 paise (Mule retains 30,000)
        {
            "transaction_id": "TXN_HOP_1",
            "timestamp": "2026-01-15T11:00:00Z",
            "from_account": "ACC_MULE",
            "to_account": "ACC_L2",
            "amount_paise": 70000,
            "transaction_type": "transfer",
            "case_id": "CASE-1",
        },
        # L2 -> L3: 40,000 paise (L2 retains 30,000; L3 receives 40,000)
        {
            "transaction_id": "TXN_HOP_2",
            "timestamp": "2026-01-15T12:00:00Z",
            "from_account": "ACC_L2",
            "to_account": "ACC_L3",
            "amount_paise": 40000,
            "transaction_type": "transfer",
            "case_id": "CASE-1",
        },
    ]

    tracer = LIBRTracer(accounts, transactions)
    result = tracer.trace_source_transaction("TXN_SRC", source_case_id="CASE-1")

    assert result.retained_suspected_paise["ACC_MULE"] == 30000
    assert result.retained_suspected_paise["ACC_L2"] == 30000
    assert result.retained_suspected_paise["ACC_L3"] == 40000
    assert result.total_retained_suspected() == 100000
    assert len(result.transfer_hops) == 3


# ==============================================================================
# 7. Multiple Suspected-Source Transactions
# ==============================================================================

def test_multiple_suspected_source_transactions():
    """Test 7: Two distinct suspected-source transactions tracked separately."""
    accounts = [
        {"account_id": "ACC_VICTIM_1", "opening_balance_paise": 500000, "history_complete": True},
        {"account_id": "ACC_VICTIM_2", "opening_balance_paise": 500000, "history_complete": True},
        {"account_id": "ACC_MULE", "opening_balance_paise": 0, "history_complete": True},
        {"account_id": "ACC_LAYER2", "opening_balance_paise": 0, "history_complete": True},
    ]
    transactions = [
        # Source 1: 30,000 paise at 10:00
        {
            "transaction_id": "TXN_SRC_1",
            "timestamp": "2026-01-15T10:00:00Z",
            "from_account": "ACC_VICTIM_1",
            "to_account": "ACC_MULE",
            "amount_paise": 30000,
            "transaction_type": "transfer",
            "case_id": "CASE-A",
        },
        # Source 2: 50,000 paise at 11:00
        {
            "transaction_id": "TXN_SRC_2",
            "timestamp": "2026-01-15T11:00:00Z",
            "from_account": "ACC_VICTIM_2",
            "to_account": "ACC_MULE",
            "amount_paise": 50000,
            "transaction_type": "transfer",
            "case_id": "CASE-B",
        },
        # Outflow: 40,000 paise to Layer 2 at 12:00
        # FIFO priority between suspected sources: Source 1 (30,000) exhausted first;
        # Source 2 (10,000) drawn next.
        {
            "transaction_id": "TXN_OUT",
            "timestamp": "2026-01-15T12:00:00Z",
            "from_account": "ACC_MULE",
            "to_account": "ACC_LAYER2",
            "amount_paise": 40000,
            "transaction_type": "transfer",
        },
    ]

    tracer = LIBRTracer(accounts, transactions)
    result = tracer.trace_sources([
        {"transaction_id": "TXN_SRC_1", "case_id": "CASE-A", "amount_paise": 30000},
        {"transaction_id": "TXN_SRC_2", "case_id": "CASE-B", "amount_paise": 50000},
    ])

    assert result.retained_suspected_paise["ACC_MULE"] == 40000
    assert result.retained_suspected_paise["ACC_LAYER2"] == 40000
    assert result.total_retained_suspected() == 80000


# ==============================================================================
# 8. Equal Timestamps and Deterministic Ordering
# ==============================================================================

def test_equal_timestamps_deterministic_ordering():
    """Test 8: Simultaneous transactions with identical timestamps are stably sorted by transaction ID."""
    accounts = [
        {"account_id": "ACC_VICTIM", "opening_balance_paise": 1000000, "history_complete": True},
        {"account_id": "ACC_MULE", "opening_balance_paise": 0, "history_complete": True},
        {"account_id": "ACC_DEST_A", "opening_balance_paise": 0, "history_complete": True},
        {"account_id": "ACC_DEST_B", "opening_balance_paise": 0, "history_complete": True},
    ]
    tx_a = {
        "transaction_id": "TXN_002_A",
        "timestamp": "2026-01-15T12:00:00Z",
        "from_account": "ACC_MULE",
        "to_account": "ACC_DEST_A",
        "amount_paise": 10000,
        "transaction_type": "transfer",
    }
    tx_b = {
        "transaction_id": "TXN_001_B",
        "timestamp": "2026-01-15T12:00:00Z",
        "from_account": "ACC_MULE",
        "to_account": "ACC_DEST_B",
        "amount_paise": 10000,
        "transaction_type": "transfer",
    }
    tx_src = {
        "transaction_id": "TXN_SRC",
        "timestamp": "2026-01-15T10:00:00Z",
        "from_account": "ACC_VICTIM",
        "to_account": "ACC_MULE",
        "amount_paise": 20000,
        "transaction_type": "transfer",
        "case_id": "CASE-1",
    }

    tracer1 = LIBRTracer(accounts, [tx_a, tx_b, tx_src])
    tracer2 = LIBRTracer(accounts, [tx_b, tx_a, tx_src])

    res1 = tracer1.trace_source_transaction("TXN_SRC", "CASE-1")
    res2 = tracer2.trace_source_transaction("TXN_SRC", "CASE-1")

    assert res1.retained_suspected_paise == res2.retained_suspected_paise
    assert tracer1.transactions[1]["transaction_id"] == "TXN_001_B"
    assert tracer1.transactions[2]["transaction_id"] == "TXN_002_A"


# ==============================================================================
# 9. Outgoing Transaction Exceeding Available Balance
# ==============================================================================

def test_outgoing_transaction_exceeding_balance_rejected():
    """Test 9: Outgoing transaction exceeding available balance raises ValueError."""
    accounts = [
        {"account_id": "ACC_MULE", "opening_balance_paise": 10000, "history_complete": True},
        {"account_id": "ACC_DEST", "opening_balance_paise": 0, "history_complete": True},
    ]
    transactions = [
        {
            "transaction_id": "TXN_OVERDRAFT",
            "timestamp": "2026-01-15T10:00:00Z",
            "from_account": "ACC_MULE",
            "to_account": "ACC_DEST",
            "amount_paise": 20000,
            "transaction_type": "transfer",
        },
    ]

    tracer = LIBRTracer(accounts, transactions)
    with pytest.raises(ValueError, match="insufficient balance"):
        tracer.trace_source_transaction("TXN_OVERDRAFT")


# ==============================================================================
# 10. Incomplete Historical Information
# ==============================================================================

def test_incomplete_historical_information():
    """Test 10: Account with incomplete history retaining suspected funds is explicitly surfaced."""
    accounts = [
        {"account_id": "ACC_VICTIM", "opening_balance_paise": 500000, "history_complete": True},
        {"account_id": "ACC_INCOMPLETE", "opening_balance_paise": 0, "history_complete": False},
    ]
    transactions = [
        {
            "transaction_id": "TXN_SRC",
            "timestamp": "2026-01-15T10:00:00Z",
            "from_account": "ACC_VICTIM",
            "to_account": "ACC_INCOMPLETE",
            "amount_paise": 100000,
            "transaction_type": "transfer",
            "case_id": "CASE-1",
        },
    ]

    tracer = LIBRTracer(accounts, transactions)
    result = tracer.trace_source_transaction("TXN_SRC", "CASE-1")

    assert "ACC_INCOMPLETE" in result.incomplete_history_accounts
    df_summary = result.summary_dataframe()
    assert bool(df_summary.loc[df_summary["account_id"] == "ACC_INCOMPLETE", "history_complete"].iloc[0]) is False


# ==============================================================================
# 11. Exact Integer-Paise Calculations
# ==============================================================================

def test_exact_integer_paise_calculations():
    """Test 11: Assert all balances and attributions are exact python integers."""
    accounts = [
        {"account_id": "ACC_VICTIM", "opening_balance_paise": 1000000, "history_complete": True},
        {"account_id": "ACC_MULE", "opening_balance_paise": 33333, "history_complete": True},
    ]
    transactions = [
        {
            "transaction_id": "TXN_SRC",
            "timestamp": "2026-01-15T10:00:00Z",
            "from_account": "ACC_VICTIM",
            "to_account": "ACC_MULE",
            "amount_paise": 77777,
            "transaction_type": "transfer",
            "case_id": "CASE-1",
        },
        {
            "transaction_id": "TXN_WTH",
            "timestamp": "2026-01-15T11:00:00Z",
            "from_account": "ACC_MULE",
            "to_account": "EXT_ATM",
            "amount_paise": 50000,
            "transaction_type": "withdrawal",
        },
    ]

    tracer = LIBRTracer(accounts, transactions)
    result = tracer.trace_source_transaction("TXN_SRC", "CASE-1")

    # Clean was 33,333. Outflow is 50,000. Suspected spent = 50,000 - 33,333 = 16,667 paise.
    # Suspected remaining = 77,777 - 16,667 = 61,110 paise.
    assert isinstance(result.retained_suspected_paise["ACC_MULE"], int)
    assert result.retained_suspected_paise["ACC_MULE"] == 61110
    assert result.withdrawn_suspected_paise["EXT_ATM"] == 16667
    assert result.total_retained_suspected() + result.total_withdrawn_suspected() == 77777


# ==============================================================================
# 12. Preservation of Provenance
# ==============================================================================

def test_preservation_of_provenance():
    """Test 12: Verify hop details and event references are recorded."""
    accounts = [
        {"account_id": "ACC_VICTIM", "opening_balance_paise": 500000, "history_complete": True},
        {"account_id": "ACC_MULE", "opening_balance_paise": 0, "history_complete": True},
        {"account_id": "ACC_L2", "opening_balance_paise": 0, "history_complete": True},
    ]
    transactions = [
        {
            "transaction_id": "TXN_SRC",
            "timestamp": "2026-01-15T10:00:00Z",
            "from_account": "ACC_VICTIM",
            "to_account": "ACC_MULE",
            "amount_paise": 50000,
            "transaction_type": "transfer",
            "case_id": "CASE-1",
        },
        {
            "transaction_id": "TXN_HOP",
            "timestamp": "2026-01-15T11:00:00Z",
            "from_account": "ACC_MULE",
            "to_account": "ACC_L2",
            "amount_paise": 50000,
            "transaction_type": "transfer",
            "case_id": "CASE-1",
        },
    ]

    tracer = LIBRTracer(accounts, transactions)
    result = tracer.trace_source_transaction("TXN_SRC", "CASE-1")

    assert len(result.transfer_hops) == 2
    assert result.transfer_hops[1].transaction_id == "TXN_HOP"
    assert result.transfer_hops[1].from_account == "ACC_MULE"
    assert result.transfer_hops[1].to_account == "ACC_L2"
    assert len(result.events) > 0


# ==============================================================================
# 13. Strict Isolation from Hidden Ground Truth
# ==============================================================================

def test_ground_truth_isolation():
    """Test 13: LIBRTracer never references or reads ground_truth.json."""
    import engine.libr as libr_mod

    source_code = inspect.getsource(libr_mod)
    assert "ground_truth" not in source_code.lower()

    adapter = SyntheticAdapter(REAL_SYNTHETIC_DIR)
    accounts, txns, cases = adapter.load_dataset()
    tracer = LIBRTracer(accounts, txns)
    result = tracer.trace_source_transaction("TXN_0009")
    res_dict = result.to_dict()
    assert "_scenario" not in str(res_dict)


# ==============================================================================
# 14. Real Synthetic Case 1 Tracing
# ==============================================================================

def test_real_synthetic_case_1_tracing():
    """Test 14: Trace real synthetic Case 1 origin TXN_0009 (₹100,000 / 10,000,000 paise).
    Validates complete integer-paise conservation and lowest intermediate balance bounds.
    """
    assert REAL_SYNTHETIC_DIR.exists()
    adapter = SyntheticAdapter(REAL_SYNTHETIC_DIR)
    accounts, txns, cases = adapter.load_dataset()

    tracer = LIBRTracer(accounts, txns)
    result = tracer.trace_source_transaction("TXN_0009", source_case_id="CASE-2026-001")

    init_amt = result.initial_suspected_amount_paise
    assert init_amt == 10000000  # 10,000,000 paise

    tot_retained = result.total_retained_suspected()
    tot_withdrawn = result.total_withdrawn_suspected()

    # Exact conservation: every single paise of the initial 10,000,000 is accounted for
    assert tot_retained + tot_withdrawn == init_amt

    # Verify lowest intermediate balance is recorded for active accounts
    for acc_id, amt in result.retained_suspected_paise.items():
        assert acc_id in result.lowest_intermediate_balances
        # Retained suspected cannot exceed lowest intermediate balance
        assert amt <= result.lowest_intermediate_balances[acc_id]

    assert len(result.transfer_hops) > 0
    assert len(result.events) > 0
