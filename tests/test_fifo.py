"""Unit tests for Smart-Freeze First-In, First-Out (FIFO) fund-tracing engine (engine.fifo).

Tests:
1. Direct suspected-source transfer without commingling.
2. Two source lots consumed in strict FIFO chronological order.
3. Partial consumption of the oldest lot leaving newer suspected funds untouched.
4. Multiple sequential outgoing transfers from the same account.
5. Multi-hop transfers across multiple accounts (B -> C -> D).
6. Multiple distinct suspected-source lots tracked separately under FIFO.
7. Opening balances with unknown provenance (history_complete=False).
8. Equal timestamps and deterministic tie-breaking.
9. External withdrawals from a commingled account.
10. Insufficient available funds rejection (overdraft protection).
11. Strict conservation of value across internal transfers and active lot balances.
12. Incomplete account histories explicitly flagged and surfaced.
13. Strict isolation from hidden ground-truth labels.
14. End-to-end tracing on real synthetic Case 1 with exact integer-paise conservation.
"""

import inspect
from pathlib import Path
import pytest

from engine.fifo import FIFOTracer, OPENING_BALANCE_TIMESTAMP
from engine.tracing_models import (
    CATEGORY_LEGITIMATE,
    CATEGORY_UNKNOWN,
    FIFOLot,
    make_suspected_category,
)
from pipeline.adapters.synthetic_adapter import SyntheticAdapter

WORKSPACE_DIR = Path(__file__).resolve().parent.parent
REAL_SYNTHETIC_DIR = WORKSPACE_DIR / "data" / "synthetic"


# ==============================================================================
# 1. Direct Suspected-Source Transfer
# ==============================================================================

def test_direct_suspected_source_transfer():
    """Test 1: Direct transfer of suspected funds from victim to mule, then mule to layer 2."""
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

    tracer = FIFOTracer(accounts, transactions)
    result = tracer.trace_source_transaction("TXN_SRC", source_case_id="CASE-1")

    assert result.retained_suspected_paise.get("ACC_MULE", 0) == 0
    assert result.retained_suspected_paise.get("ACC_LAYER2", 0) == 500000
    assert result.total_retained_suspected() == 500000
    assert result.total_withdrawn_suspected() == 0
    assert len(result.transfer_hops) == 2


# ==============================================================================
# 2. Two Source Lots Consumed in FIFO Order
# ==============================================================================

def test_two_source_lots_consumed_in_fifo_order():
    """Test 2: Account has clean opening balance, then receives suspected funds.
    Outgoing transfer spans both lots: oldest (clean) lot is exhausted first,
    and remaining amount is drawn from the suspected lot.
    """
    accounts = [
        {"account_id": "ACC_VICTIM", "opening_balance_paise": 1000000, "history_complete": True},
        # Mule starts with 10,000 paise clean opening balance
        {"account_id": "ACC_MULE", "opening_balance_paise": 10000, "history_complete": True},
        {"account_id": "ACC_LAYER2", "opening_balance_paise": 0, "history_complete": True},
    ]
    transactions = [
        # Mule receives 20,000 paise suspected at 10:00:00Z
        {
            "transaction_id": "TXN_SRC",
            "timestamp": "2026-01-15T10:00:00Z",
            "from_account": "ACC_VICTIM",
            "to_account": "ACC_MULE",
            "amount_paise": 20000,
            "transaction_type": "transfer",
            "case_id": "CASE-1",
        },
        # Mule sends 15,000 paise at 12:00:00Z
        # FIFO order:
        # 1. 10,000 paise clean opening balance (exhausted, remaining: 0)
        # 2. 5,000 paise suspected (remaining in Mule: 15,000)
        {
            "transaction_id": "TXN_OUT",
            "timestamp": "2026-01-15T12:00:00Z",
            "from_account": "ACC_MULE",
            "to_account": "ACC_LAYER2",
            "amount_paise": 15000,
            "transaction_type": "transfer",
            "case_id": "CASE-1",
        },
    ]

    tracer = FIFOTracer(accounts, transactions)
    result = tracer.trace_source_transaction("TXN_SRC", source_case_id="CASE-1")

    # Mule retains 15,000 paise suspected
    assert result.retained_suspected_paise["ACC_MULE"] == 15000
    # Layer 2 received 5,000 paise suspected (and 10,000 clean)
    assert result.retained_suspected_paise["ACC_LAYER2"] == 5000
    assert result.total_retained_suspected() == 20000


# ==============================================================================
# 3. Partial Consumption of Oldest Lot
# ==============================================================================

def test_partial_consumption_of_oldest_lot():
    """Test 3: Oldest lot has 50,000 paise clean funds. Suspected deposit is 30,000 paise.
    Outgoing transfer is 20,000 paise. Under FIFO, only the oldest (clean) lot is drawn;
    the suspected lot is completely untouched.
    """
    accounts = [
        {"account_id": "ACC_VICTIM", "opening_balance_paise": 1000000, "history_complete": True},
        {"account_id": "ACC_MULE", "opening_balance_paise": 50000, "history_complete": True},
        {"account_id": "ACC_LAYER2", "opening_balance_paise": 0, "history_complete": True},
    ]
    transactions = [
        {
            "transaction_id": "TXN_SRC",
            "timestamp": "2026-01-15T10:00:00Z",
            "from_account": "ACC_VICTIM",
            "to_account": "ACC_MULE",
            "amount_paise": 30000,
            "transaction_type": "transfer",
            "case_id": "CASE-1",
        },
        # Mule sends 20,000 paise. Under FIFO, drawn entirely from 50,000 clean opening lot.
        {
            "transaction_id": "TXN_OUT",
            "timestamp": "2026-01-15T12:00:00Z",
            "from_account": "ACC_MULE",
            "to_account": "ACC_LAYER2",
            "amount_paise": 20000,
            "transaction_type": "transfer",
            "case_id": "CASE-1",
        },
    ]

    tracer = FIFOTracer(accounts, transactions)
    result = tracer.trace_source_transaction("TXN_SRC", source_case_id="CASE-1")

    # Mule retains 100% of suspected funds: 30,000 paise!
    assert result.retained_suspected_paise["ACC_MULE"] == 30000
    assert "ACC_LAYER2" not in result.retained_suspected_paise
    assert result.total_retained_suspected() == 30000


# ==============================================================================
# 4. Multiple Outgoing Transfers from Same Account
# ==============================================================================

def test_multiple_outgoing_transfers_from_same_account():
    """Test 4: Account executes multiple sequential transfers exhausting lots one by one."""
    accounts = [
        {"account_id": "ACC_VICTIM", "opening_balance_paise": 1000000, "history_complete": True},
        {"account_id": "ACC_MULE", "opening_balance_paise": 10000, "history_complete": True},
        {"account_id": "ACC_DEST_1", "opening_balance_paise": 0, "history_complete": True},
        {"account_id": "ACC_DEST_2", "opening_balance_paise": 0, "history_complete": True},
    ]
    transactions = [
        # Mule receives 40,000 paise suspected
        {
            "transaction_id": "TXN_SRC",
            "timestamp": "2026-01-15T10:00:00Z",
            "from_account": "ACC_VICTIM",
            "to_account": "ACC_MULE",
            "amount_paise": 40000,
            "transaction_type": "transfer",
            "case_id": "CASE-1",
        },
        # Tx 1: 5,000 paise to DEST_1 at 11:00:00Z (consumes 5,000 from clean lot)
        {
            "transaction_id": "TXN_OUT_1",
            "timestamp": "2026-01-15T11:00:00Z",
            "from_account": "ACC_MULE",
            "to_account": "ACC_DEST_1",
            "amount_paise": 5000,
            "transaction_type": "transfer",
            "case_id": "CASE-1",
        },
        # Tx 2: 25,000 paise to DEST_2 at 12:00:00Z
        # Consumes remaining 5,000 clean, and 20,000 suspected!
        {
            "transaction_id": "TXN_OUT_2",
            "timestamp": "2026-01-15T12:00:00Z",
            "from_account": "ACC_MULE",
            "to_account": "ACC_DEST_2",
            "amount_paise": 25000,
            "transaction_type": "transfer",
            "case_id": "CASE-1",
        },
    ]

    tracer = FIFOTracer(accounts, transactions)
    result = tracer.trace_source_transaction("TXN_SRC", source_case_id="CASE-1")

    assert "ACC_DEST_1" not in result.retained_suspected_paise  # Received only clean funds
    assert result.retained_suspected_paise["ACC_DEST_2"] == 20000  # Received 20,000 suspected
    assert result.retained_suspected_paise["ACC_MULE"] == 20000   # Retains remaining 20,000 suspected
    assert result.total_retained_suspected() == 40000


# ==============================================================================
# 5. Transfers Across Multiple Accounts (Multi-Hop)
# ==============================================================================

def test_transfers_across_multiple_accounts():
    """Test 5: Multi-hop propagation: Victim -> Mule -> Layer 2 -> Layer 3."""
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

    tracer = FIFOTracer(accounts, transactions)
    result = tracer.trace_source_transaction("TXN_SRC", source_case_id="CASE-1")

    assert result.retained_suspected_paise["ACC_MULE"] == 30000
    assert result.retained_suspected_paise["ACC_L2"] == 30000
    assert result.retained_suspected_paise["ACC_L3"] == 40000
    assert result.total_retained_suspected() == 100000
    assert len(result.transfer_hops) == 3


# ==============================================================================
# 6. Multiple Suspected-Source Lots
# ==============================================================================

def test_multiple_suspected_source_lots():
    """Test 6: Account receives two distinct suspected-source lots.
    Under FIFO, the earlier suspected lot is consumed first.
    """
    accounts = [
        {"account_id": "ACC_VICTIM_1", "opening_balance_paise": 500000, "history_complete": True},
        {"account_id": "ACC_VICTIM_2", "opening_balance_paise": 500000, "history_complete": True},
        {"account_id": "ACC_MULE", "opening_balance_paise": 0, "history_complete": True},
        {"account_id": "ACC_LAYER2", "opening_balance_paise": 0, "history_complete": True},
    ]
    transactions = [
        # Source 1: 30,000 paise at 10:00:00Z
        {
            "transaction_id": "TXN_SRC_1",
            "timestamp": "2026-01-15T10:00:00Z",
            "from_account": "ACC_VICTIM_1",
            "to_account": "ACC_MULE",
            "amount_paise": 30000,
            "transaction_type": "transfer",
            "case_id": "CASE-A",
        },
        # Source 2: 50,000 paise at 11:00:00Z
        {
            "transaction_id": "TXN_SRC_2",
            "timestamp": "2026-01-15T11:00:00Z",
            "from_account": "ACC_VICTIM_2",
            "to_account": "ACC_MULE",
            "amount_paise": 50000,
            "transaction_type": "transfer",
            "case_id": "CASE-B",
        },
        # Outflow: 40,000 paise at 12:00:00Z to Layer 2
        # FIFO consumes: all 30,000 of Source 1, and 10,000 of Source 2.
        {
            "transaction_id": "TXN_OUT",
            "timestamp": "2026-01-15T12:00:00Z",
            "from_account": "ACC_MULE",
            "to_account": "ACC_LAYER2",
            "amount_paise": 40000,
            "transaction_type": "transfer",
            "case_id": "CASE-A",
        },
    ]

    tracer = FIFOTracer(accounts, transactions)
    # Trace with both designated sources
    result = tracer.trace_sources([
        {"transaction_id": "TXN_SRC_1", "case_id": "CASE-A", "amount_paise": 30000},
        {"transaction_id": "TXN_SRC_2", "case_id": "CASE-B", "amount_paise": 50000},
    ])

    # Mule retains 40,000 paise of Source 2 (Source 1 exhausted)
    assert result.retained_suspected_paise["ACC_MULE"] == 40000
    # Layer 2 received 30,000 of Source 1 + 10,000 of Source 2 = 40,000
    assert result.retained_suspected_paise["ACC_LAYER2"] == 40000
    assert result.total_retained_suspected() == 80000


# ==============================================================================
# 7. Opening Balances with Unknown Provenance
# ==============================================================================

def test_opening_balances_with_unknown_provenance():
    """Test 7: Opening balance for account with history_complete=False is classified as CATEGORY_UNKNOWN."""
    accounts = [
        {"account_id": "ACC_MULE", "opening_balance_paise": 50000, "history_complete": False},
        {"account_id": "ACC_LAYER2", "opening_balance_paise": 0, "history_complete": True},
    ]
    transactions = [
        {
            "transaction_id": "TXN_OUT",
            "timestamp": "2026-01-15T12:00:00Z",
            "from_account": "ACC_MULE",
            "to_account": "ACC_LAYER2",
            "amount_paise": 30000,
            "transaction_type": "transfer",
        },
    ]

    tracer = FIFOTracer(accounts, transactions)
    initial_lots = tracer._initialize_lots()
    mule_lots = initial_lots["ACC_MULE"]

    assert len(mule_lots) == 1
    assert mule_lots[0].source_classification == CATEGORY_UNKNOWN
    assert mule_lots[0].history_complete is False


# ==============================================================================
# 8. Equal Timestamps and Deterministic Tie-Breaking
# ==============================================================================

def test_equal_timestamps_deterministic_tie_breaking():
    """Test 8: Simultaneous transactions with identical timestamps are stably sorted by transaction ID."""
    accounts = [
        {"account_id": "ACC_VICTIM", "opening_balance_paise": 1000000, "history_complete": True},
        {"account_id": "ACC_MULE", "opening_balance_paise": 0, "history_complete": True},
        {"account_id": "ACC_DEST_A", "opening_balance_paise": 0, "history_complete": True},
        {"account_id": "ACC_DEST_B", "opening_balance_paise": 0, "history_complete": True},
    ]
    # Two identical timestamp transactions
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

    # Pass in order [tx_a, tx_b, tx_src]
    tracer1 = FIFOTracer(accounts, [tx_a, tx_b, tx_src])
    # Pass in reverse order [tx_b, tx_a, tx_src]
    tracer2 = FIFOTracer(accounts, [tx_b, tx_a, tx_src])

    res1 = tracer1.trace_source_transaction("TXN_SRC", "CASE-1")
    res2 = tracer2.trace_source_transaction("TXN_SRC", "CASE-1")

    assert res1.retained_suspected_paise == res2.retained_suspected_paise
    # TXN_001_B must be processed before TXN_002_A due to alphanumeric tie-breaker
    assert tracer1.transactions[1]["transaction_id"] == "TXN_001_B"
    assert tracer1.transactions[2]["transaction_id"] == "TXN_002_A"


# ==============================================================================
# 9. External Withdrawals
# ==============================================================================

def test_external_withdrawals():
    """Test 9: External withdrawal consumes lots via FIFO and records outflow to external account."""
    accounts = [
        {"account_id": "ACC_VICTIM", "opening_balance_paise": 1000000, "history_complete": True},
        {"account_id": "ACC_MULE", "opening_balance_paise": 10000, "history_complete": True},
    ]
    transactions = [
        # Mule receives 50,000 paise suspected
        {
            "transaction_id": "TXN_SRC",
            "timestamp": "2026-01-15T10:00:00Z",
            "from_account": "ACC_VICTIM",
            "to_account": "ACC_MULE",
            "amount_paise": 50000,
            "transaction_type": "transfer",
            "case_id": "CASE-1",
        },
        # Mule withdraws 35,000 paise to EXT_ATM at 12:00:00Z
        # Under FIFO:
        # 1. 10,000 clean opening lot (exhausted)
        # 2. 25,000 suspected lot (remaining in Mule: 25,000 suspected)
        {
            "transaction_id": "TXN_WTH",
            "timestamp": "2026-01-15T12:00:00Z",
            "from_account": "ACC_MULE",
            "to_account": "EXT_ATM_01",
            "amount_paise": 35000,
            "transaction_type": "withdrawal",
            "case_id": "CASE-1",
        },
    ]

    tracer = FIFOTracer(accounts, transactions)
    result = tracer.trace_source_transaction("TXN_SRC", "CASE-1")

    assert result.retained_suspected_paise["ACC_MULE"] == 25000
    assert result.withdrawn_suspected_paise["EXT_ATM_01"] == 25000
    assert result.total_retained_suspected() == 25000
    assert result.total_withdrawn_suspected() == 25000
    assert result.total_retained_suspected() + result.total_withdrawn_suspected() == 50000


# ==============================================================================
# 10. Insufficient Available Funds Rejection
# ==============================================================================

def test_insufficient_available_funds_rejected():
    """Test 10: Outgoing transaction exceeding available balance raises ValueError."""
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
            "amount_paise": 20000,  # Exceeds 10,000 paise
            "transaction_type": "transfer",
        },
    ]

    tracer = FIFOTracer(accounts, transactions)
    with pytest.raises(ValueError, match="insufficient balance"):
        tracer.trace_source_transaction("TXN_OVERDRAFT")


# ==============================================================================
# 11. Conservation of Value Across Internal Transfers
# ==============================================================================

def test_conservation_of_value_across_internal_transfers():
    """Test 11: Value is strictly conserved across multiple complex splits and transfers."""
    accounts = [
        {"account_id": "ACC_VICTIM", "opening_balance_paise": 1000000, "history_complete": True},
        {"account_id": "ACC_MULE", "opening_balance_paise": 20000, "history_complete": True},
        {"account_id": "ACC_L2_A", "opening_balance_paise": 0, "history_complete": True},
        {"account_id": "ACC_L2_B", "opening_balance_paise": 0, "history_complete": True},
    ]
    transactions = [
        # Inflow: 80,000 suspected
        {
            "transaction_id": "TXN_SRC",
            "timestamp": "2026-01-15T10:00:00Z",
            "from_account": "ACC_VICTIM",
            "to_account": "ACC_MULE",
            "amount_paise": 80000,
            "transaction_type": "transfer",
            "case_id": "CASE-1",
        },
        # Mule sends 50,000 to L2_A
        # FIFO: 20,000 clean + 30,000 suspected. Mule has 50,000 suspected remaining.
        {
            "transaction_id": "TXN_SPLIT_1",
            "timestamp": "2026-01-15T11:00:00Z",
            "from_account": "ACC_MULE",
            "to_account": "ACC_L2_A",
            "amount_paise": 50000,
            "transaction_type": "transfer",
            "case_id": "CASE-1",
        },
        # Mule sends 20,000 to L2_B
        # FIFO: draws 20,000 suspected. Mule has 30,000 suspected remaining.
        {
            "transaction_id": "TXN_SPLIT_2",
            "timestamp": "2026-01-15T12:00:00Z",
            "from_account": "ACC_MULE",
            "to_account": "ACC_L2_B",
            "amount_paise": 20000,
            "transaction_type": "transfer",
            "case_id": "CASE-1",
        },
    ]

    tracer = FIFOTracer(accounts, transactions)
    result = tracer.trace_source_transaction("TXN_SRC", "CASE-1")

    assert result.retained_suspected_paise["ACC_MULE"] == 30000
    assert result.retained_suspected_paise["ACC_L2_A"] == 30000
    assert result.retained_suspected_paise["ACC_L2_B"] == 20000
    assert result.total_retained_suspected() == 80000
    assert result.total_withdrawn_suspected() == 0


# ==============================================================================
# 12. Incomplete Account Histories Explicitly Flagged
# ==============================================================================

def test_incomplete_account_histories_flagged():
    """Test 12: Account with incomplete history retaining suspected funds is explicitly flagged."""
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

    tracer = FIFOTracer(accounts, transactions)
    result = tracer.trace_source_transaction("TXN_SRC", "CASE-1")

    assert "ACC_INCOMPLETE" in result.incomplete_history_accounts
    df_summary = result.summary_dataframe()
    assert bool(df_summary.loc[df_summary["account_id"] == "ACC_INCOMPLETE", "history_complete"].iloc[0]) is False


# ==============================================================================
# 13. Strict Isolation from Hidden Ground Truth
# ==============================================================================

def test_ground_truth_isolation():
    """Test 13: FIFOTracer never references or reads ground_truth.json."""
    import engine.fifo as fifo_mod

    source_code = inspect.getsource(fifo_mod)
    assert "ground_truth" not in source_code.lower()

    adapter = SyntheticAdapter(REAL_SYNTHETIC_DIR)
    accounts, txns, cases = adapter.load_dataset()
    tracer = FIFOTracer(accounts, txns)
    result = tracer.trace_source_transaction("TXN_0009")
    res_dict = result.to_dict()
    assert "_scenario" not in str(res_dict)


# ==============================================================================
# 14. Real Synthetic Case 1 Tracing
# ==============================================================================

def test_real_synthetic_case_1_tracing():
    """Test 14: Trace real synthetic Case 1 origin TXN_0009 (₹100,000 / 10,000,000 paise).
    Validates complete integer-paise conservation and non-negative lot balances.
    """
    assert REAL_SYNTHETIC_DIR.exists()
    adapter = SyntheticAdapter(REAL_SYNTHETIC_DIR)
    accounts, txns, cases = adapter.load_dataset()

    tracer = FIFOTracer(accounts, txns)
    result = tracer.trace_source_transaction("TXN_0009", source_case_id="CASE-2026-001")

    init_amt = result.initial_suspected_amount_paise
    assert init_amt == 10000000  # 10,000,000 paise (₹100,000)

    tot_retained = result.total_retained_suspected()
    tot_withdrawn = result.total_withdrawn_suspected()

    # Exact conservation: every single paise of the initial 10,000,000 is accounted for
    assert tot_retained + tot_withdrawn == init_amt


    # Verify no lot balance in any account is negative
    for acc_id, lots in result.active_lots_by_account.items():
        for lot in lots:
            assert lot["remaining_amount_paise"] > 0
            assert lot["remaining_amount_paise"] <= lot["original_amount_paise"]

    # Verify transfer hops exist
    assert len(result.transfer_hops) > 0
