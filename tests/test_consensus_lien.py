"""Unit tests for Smart-Freeze Consensus Lien Engine (engine.consensus_lien).

Tests:
1. Correct lower and upper estimates: min(P, F, L) and max(P, F, L).
2. Correct disagreement range calculation: (upper - lower).
3. All three methods agreeing (zero disagreement).
4. Each method producing a different value (three-way method divergence).
5. Invalid or missing method outputs rejected.
6. Non-comparable source transactions, case references, or initial amounts surfaced.
7. Strict integer-paise arithmetic throughout.
8. Negative or malformed outputs identified and rejected.
9. Structured explanations match computed bounds.
10. End-to-end Consensus Lien on real synthetic Case 1 with tabular output.
"""

import os
from pathlib import Path
import pytest

from engine.consensus_lien import (
    AccountConsensusLien,
    ConsensusLienEngine,
    ConsensusLienResult,
)
from engine.tracing_models import (
    FIFOTraceResult,
    LIBRTraceResult,
    ProportionalTraceResult,
)
from pipeline.adapters.synthetic_adapter import SyntheticAdapter

WORKSPACE_DIR = Path(__file__).resolve().parent.parent
REAL_SYNTHETIC_DIR = Path(os.environ.get("SMART_FREEZE_DATA_DIR", str(WORKSPACE_DIR / "data" / "fixtures" / "demo_3case")))


def _create_mock_results(
    prop_retained: dict,
    fifo_retained: dict,
    libr_retained: dict,
    src_tx: str = "TXN_SRC",
    src_case: str = "CASE-1",
    init_amt: int = 100000,
):
    """Helper to create comparable mock tracing results for unit tests."""
    p_res = ProportionalTraceResult(
        source_transaction_id=src_tx,
        source_case_id=src_case,
        initial_suspected_amount_paise=init_amt,
        account_pools={},
        retained_suspected_paise=prop_retained,
        withdrawn_suspected_paise={},
    )
    f_res = FIFOTraceResult(
        source_transaction_id=src_tx,
        source_case_id=src_case,
        initial_suspected_amount_paise=init_amt,
        retained_suspected_paise=fifo_retained,
        withdrawn_suspected_paise={},
        active_lots_by_account={},
    )
    l_res = LIBRTraceResult(
        source_transaction_id=src_tx,
        source_case_id=src_case,
        initial_suspected_amount_paise=init_amt,
        retained_suspected_paise=libr_retained,
        withdrawn_suspected_paise={},
        lowest_intermediate_balances={},
    )
    return p_res, f_res, l_res


# ==============================================================================
# 1. Correct Lower and Upper Estimates
# ==============================================================================

def test_correct_lower_and_upper_estimates():
    """Test 1: Verify lower = min(P, F, L) and upper = max(P, F, L)."""
    p, f, l = _create_mock_results(
        prop_retained={"ACC_A": 35000},
        fifo_retained={"ACC_A": 40000},
        libr_retained={"ACC_A": 75000},
    )
    result = ConsensusLienEngine.compare_results(p, f, l)
    lien = result.account_liens["ACC_A"]

    assert lien.lower_estimate_paise == 35000
    assert lien.upper_estimate_paise == 75000
    assert lien.lower_method == "Proportional"
    assert lien.upper_method == "LIBR"


# ==============================================================================
# 2. Correct Disagreement Range
# ==============================================================================

def test_correct_disagreement_range():
    """Test 2: Verify disagreement = upper - lower."""
    p, f, l = _create_mock_results(
        prop_retained={"ACC_A": 30000},
        fifo_retained={"ACC_A": 50000},
        libr_retained={"ACC_A": 70000},
    )
    result = ConsensusLienEngine.compare_results(p, f, l)
    lien = result.account_liens["ACC_A"]

    assert lien.disagreement_paise == 40000  # 70,000 - 30,000
    assert result.overall_disagreement_paise == 40000


# ==============================================================================
# 3. All Three Methods Agreeing
# ==============================================================================

def test_all_three_methods_agreeing():
    """Test 3: When all three methods produce identical values, disagreement is 0."""
    p, f, l = _create_mock_results(
        prop_retained={"ACC_MULE": 50000},
        fifo_retained={"ACC_MULE": 50000},
        libr_retained={"ACC_MULE": 50000},
    )
    result = ConsensusLienEngine.compare_results(p, f, l)
    lien = result.account_liens["ACC_MULE"]

    assert lien.lower_estimate_paise == 50000
    assert lien.upper_estimate_paise == 50000
    assert lien.disagreement_paise == 0
    assert "Proportional" in lien.lower_method
    assert "FIFO" in lien.lower_method
    assert "LIBR" in lien.lower_method


# ==============================================================================
# 4. Each Method Producing a Different Value
# ==============================================================================

def test_each_method_producing_different_value():
    """Test 4: Three-way method divergence with different winners."""
    p, f, l = _create_mock_results(
        prop_retained={"ACC_X": 25000, "ACC_Y": 45000},
        fifo_retained={"ACC_X": 10000, "ACC_Y": 60000},
        libr_retained={"ACC_X": 50000, "ACC_Y": 20000},
    )
    result = ConsensusLienEngine.compare_results(p, f, l)

    # ACC_X: FIFO (10,000) < Prop (25,000) < LIBR (50,000)
    lien_x = result.account_liens["ACC_X"]
    assert lien_x.lower_estimate_paise == 10000
    assert lien_x.upper_estimate_paise == 50000
    assert lien_x.disagreement_paise == 40000
    assert lien_x.lower_method == "FIFO"
    assert lien_x.upper_method == "LIBR"

    # ACC_Y: LIBR (20,000) < Prop (45,000) < FIFO (60,000)
    lien_y = result.account_liens["ACC_Y"]
    assert lien_y.lower_estimate_paise == 20000
    assert lien_y.upper_estimate_paise == 60000
    assert lien_y.disagreement_paise == 40000
    assert lien_y.lower_method == "LIBR"
    assert lien_y.upper_method == "FIFO"


# ==============================================================================
# 5. Invalid or Missing Method Outputs Rejected
# ==============================================================================

def test_missing_method_outputs_rejected():
    """Test 5: Passing None for any method raises ValueError."""
    p, f, l = _create_mock_results({"ACC_A": 1000}, {"ACC_A": 1000}, {"ACC_A": 1000})
    with pytest.raises(ValueError, match="All three method results"):
        ConsensusLienEngine.compare_results(p, None, l)  # type: ignore


# ==============================================================================
# 6. Non-Comparable Sources or Scopes
# ==============================================================================

def test_non_comparable_sources_surfaced():
    """Test 6: Comparing results with different source transaction IDs marks status INCOMPARABLE."""
    p, f, _ = _create_mock_results({"ACC_A": 1000}, {"ACC_A": 1000}, {"ACC_A": 1000}, src_tx="TXN_001")
    _, _, l = _create_mock_results({"ACC_A": 1000}, {"ACC_A": 1000}, {"ACC_A": 1000}, src_tx="TXN_002")

    result = ConsensusLienEngine.compare_results(p, f, l)
    assert result.status == "INCOMPARABLE"
    assert len(result.errors) > 0
    assert "Incomparable source transactions" in result.errors[0]


# ==============================================================================
# 7. Strict Integer-Paise Arithmetic
# ==============================================================================

def test_strict_integer_paise_arithmetic():
    """Test 7: All outputs, bounds, and differences are exact python integers."""
    p, f, l = _create_mock_results(
        prop_retained={"ACC_A": 12345},
        fifo_retained={"ACC_A": 23456},
        libr_retained={"ACC_A": 34567},
    )
    result = ConsensusLienEngine.compare_results(p, f, l)
    lien = result.account_liens["ACC_A"]

    assert isinstance(lien.lower_estimate_paise, int)
    assert isinstance(lien.upper_estimate_paise, int)
    assert isinstance(lien.disagreement_paise, int)
    assert lien.lower_estimate_paise == 12345
    assert lien.upper_estimate_paise == 34567
    assert lien.disagreement_paise == 22222


# ==============================================================================
# 8. Negative or Malformed Outputs Rejected
# ==============================================================================

def test_negative_outputs_rejected():
    """Test 8: Negative retained amounts trigger validation errors."""
    p, f, l = _create_mock_results(
        prop_retained={"ACC_A": -500},
        fifo_retained={"ACC_A": 1000},
        libr_retained={"ACC_A": 1000},
    )
    result = ConsensusLienEngine.compare_results(p, f, l)
    assert result.status == "INCOMPARABLE"
    assert any("negative retained amount" in err for err in result.errors)


# ==============================================================================
# 9. Structured Explanations Match Computed Bounds
# ==============================================================================

def test_explanation_matches_computed_bounds():
    """Test 9: Narrative explanation text contains exact calculated paise and INR figures."""
    p, f, l = _create_mock_results(
        prop_retained={"ACC_A": 20000},
        fifo_retained={"ACC_A": 30000},
        libr_retained={"ACC_A": 50000},
    )
    result = ConsensusLienEngine.compare_results(p, f, l)
    lien = result.account_liens["ACC_A"]

    assert "20,000 paise" in lien.explanation_text
    assert "50,000 paise" in lien.explanation_text
    assert "30,000 paise" in lien.explanation_text
    assert "Lower = ₹200.00 | Upper = ₹500.00" in lien.explanation_text


# ==============================================================================
# 10. End-to-End Consensus Lien on Real Synthetic Case 1
# ==============================================================================

def test_real_synthetic_case_1_consensus_lien():
    """Test 10: Run all three methods on real Case 1 (TXN_0009) and verify Consensus bounds."""
    assert REAL_SYNTHETIC_DIR.exists()
    adapter = SyntheticAdapter(REAL_SYNTHETIC_DIR)
    accounts, txns, cases = adapter.load_dataset()

    result = ConsensusLienEngine.run_all_methods(
        accounts=accounts,
        transactions=txns,
        source_transaction_id="TXN_0009",
        source_case_id="CASE-2026-001",
    )

    assert result.status == "COMPARABLE"
    assert result.initial_suspected_amount_paise == 10000000  # 10,000,000 paise (₹100,000)

    # ACC_COMMINGLED_01 bounds:
    # Proportional: 3,585,434 paise
    # FIFO:         4,000,000 paise
    # LIBR:         7,500,000 paise
    commingled_lien = result.account_liens["ACC_COMMINGLED_01"]
    assert commingled_lien.lower_estimate_paise == 3585434
    assert commingled_lien.upper_estimate_paise == 7500000
    assert commingled_lien.disagreement_paise == 3914566
    assert commingled_lien.lower_method == "Proportional"
    assert commingled_lien.upper_method == "LIBR"

    # Tabular summary export
    df_summary = result.summary_dataframe()
    assert len(df_summary) >= 4
    assert "account_id" in df_summary.columns
    assert "lower_bound_inr" in df_summary.columns
    assert "upper_bound_inr" in df_summary.columns


# ==============================================================================
# 11. Acceptance Test 3: Joint Total <= Suspected Amount for All Synthetic Cases
# ==============================================================================

def test_joint_total_le_suspected_amount_all_synthetic_cases():
    """Acceptance Test 3: Joint total <= suspected amount for every case in data/synthetic.

    Verifies that while per-account maximums can sum to more than the stolen amount
    (e.g., CASE-2026-001 sum of per-account max is 15,189,076 paise / ₹151,890.76 on 10,000,000 paise / ₹100,000.00),
    the joint-feasible total never exceeds initial suspected amount minus money confirmed to have left the system.
    """
    assert REAL_SYNTHETIC_DIR.exists()
    adapter = SyntheticAdapter(REAL_SYNTHETIC_DIR)
    accounts, txns, cases = adapter.load_dataset()

    case_origins = {
        "CASE-2026-001": "TXN_0009",
        "CASE-2026-002": "TXN_0038",
        "CASE-2026-003": "TXN_0067",
    }

    for case_id, origin_tx in case_origins.items():
        res = ConsensusLienEngine.run_all_methods(
            accounts=accounts,
            transactions=txns,
            source_transaction_id=origin_tx,
            source_case_id=case_id,
        )
        assert res.status == "COMPARABLE"
        suspected = res.initial_suspected_amount_paise
        confirmed_outflows = res.confirmed_withdrawn_paise
        joint_upper = res.joint_feasible_upper_paise

        # Strict invariant: joint_upper <= suspected - confirmed_outflows <= suspected
        assert joint_upper <= suspected - confirmed_outflows
        assert joint_upper <= suspected
        assert res.joint_total_paise <= suspected
        assert res.joint_total <= suspected / 100.0
        assert res.joint_feasible_lower_paise <= joint_upper

    # Specific check for CASE-2026-001 demonstrating the exact requirement:
    res_case1 = ConsensusLienEngine.run_all_methods(
        accounts=accounts,
        transactions=txns,
        source_transaction_id="TXN_0009",
        source_case_id="CASE-2026-001",
    )
    # Per-account unconstrained sum exceeds 100,000 INR (151,890.76)
    assert res_case1.total_upper_retained_paise == 15189076
    # Confirmed withdrawn via external ATM is 476,190 paise
    assert res_case1.confirmed_withdrawn_paise == 476190
    # Joint-feasible upper bound is exactly min(15,189,076, 10,000,000 - 476,190) = 9,523,810 paise (₹95,238.10)
    assert res_case1.joint_feasible_upper_paise == 9523810
    assert res_case1.joint_total_paise == 9523810
    assert res_case1.joint_total_paise <= 10000000
    assert res_case1.joint_total <= 100000.00

