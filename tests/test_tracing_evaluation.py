"""Unit tests for Smart-Freeze Tracing Ground-Truth Evaluation (evaluation.tracing_metrics).

Tests:
1. Exact calculation of absolute error (in paise and INR) against ground truth.
2. Graceful zero-ground-truth denominator handling for relative error.
3. Accurate exact-match rate and summary metrics calculation.
4. Evaluation-only access to ground truth.
5. Strict isolation: operational tracing engines never access ground truth.
6. End-to-end evaluation runner executes and outputs valid schema to data/processed.
"""

import inspect
import json
from pathlib import Path
import tempfile
import pytest

from engine.consensus_lien import ConsensusLienEngine
import engine.fifo as fifo_mod
import engine.libr as libr_mod
import engine.proportional as prop_mod
from evaluation.run_tracing_evaluation import evaluate_cases
from evaluation.tracing_metrics import TracingMetricsCalculator

WORKSPACE_DIR = Path(__file__).resolve().parent.parent
REAL_SYNTHETIC_DIR = WORKSPACE_DIR / "data" / "synthetic"


# ==============================================================================
# 1. Calculation of Absolute Error in Paise and INR
# ==============================================================================

def test_absolute_error_calculation():
    """Test 1: Verify absolute error is calculated exactly in integer paise and INR."""
    # Estimated: 40,000 paise (₹400), Ground Truth: 35,000 paise (₹350)
    metric = TracingMetricsCalculator.calculate_account_metric(
        account_id="ACC_01",
        estimated_paise=40000,
        ground_truth_paise=35000,
    )

    assert metric.absolute_error_paise == 5000
    assert metric.absolute_error_inr == 50.00
    assert metric.exact_match is False
    assert metric.relative_error == round(5000 / 35000.0, 4)
    assert metric.relative_error_status == "VALID"


# ==============================================================================
# 2. Zero-Ground-Truth Denominator Handling
# ==============================================================================

def test_zero_ground_truth_denominator_handling():
    """Test 2: When ground truth is zero, relative error handles both exact and erroneous cases without crashing."""
    # Case A: Both estimated and ground truth are 0 -> Exact match (0.0 relative error)
    m_exact = TracingMetricsCalculator.calculate_account_metric(
        account_id="ACC_CLEAN",
        estimated_paise=0,
        ground_truth_paise=0,
    )
    assert m_exact.exact_match is True
    assert m_exact.absolute_error_paise == 0
    assert m_exact.relative_error == 0.0
    assert m_exact.relative_error_status == "ZERO_DENOMINATOR_EXACT"

    # Case B: Ground truth is 0, but estimated is 10,000 -> Cannot divide by 0
    m_error = TracingMetricsCalculator.calculate_account_metric(
        account_id="ACC_INNOCENT",
        estimated_paise=10000,
        ground_truth_paise=0,
    )
    assert m_error.exact_match is False
    assert m_error.absolute_error_paise == 10000
    assert m_error.relative_error is None  # Handled safely, no ZeroDivisionError!
    assert m_error.relative_error_status == "ZERO_DENOMINATOR_ERROR"


# ==============================================================================
# 3. Method Summary Evaluation Metrics
# ==============================================================================

def test_method_summary_evaluation():
    """Test 3: Verify aggregate evaluation report metrics across multiple accounts."""
    estimated = {
        "ACC_1": 100000,  # GT: 100000 -> Exact match
        "ACC_2": 80000,   # GT: 50000  -> Error: 30000
        "ACC_3": 0,       # GT: 0      -> Exact match
    }
    ground_truth = {
        "ACC_1": 100000,
        "ACC_2": 50000,
        "ACC_3": 0,
    }

    report = TracingMetricsCalculator.evaluate_method_allocations(
        method_name="FIFO",
        case_id="CASE-TEST",
        estimated_allocations=estimated,
        ground_truth_allocations=ground_truth,
    )

    assert report.total_accounts == 3
    assert report.exact_match_count == 2
    assert report.exact_match_rate == round(2 / 3.0, 4)
    assert report.total_absolute_error_paise == 30000
    assert report.mean_absolute_error_paise == 10000.0
    assert report.mean_absolute_error_inr == 100.0


# ==============================================================================
# 4. Evaluation-Only Ground-Truth Access
# ==============================================================================

def test_evaluation_runner_loads_ground_truth():
    """Test 4: Verify evaluation runner successfully loads ground truth and scenarios."""
    from evaluation.run_tracing_evaluation import load_ground_truth

    gt = load_ground_truth(REAL_SYNTHETIC_DIR)
    assert "_metadata" in gt
    assert "cases" in gt
    assert "scenarios" in gt
    assert len(gt["cases"]) >= 3


# ==============================================================================
# 5. Strict Operational Tracing Isolation from Ground Truth
# ==============================================================================

def test_operational_modules_isolated_from_ground_truth():
    """Test 5: Operational tracing engines must NEVER reference or load ground truth."""
    for mod in [prop_mod, fifo_mod, libr_mod]:
        src = inspect.getsource(mod)
        assert "ground_truth" not in src.lower()


# ==============================================================================
# 6. End-to-End Evaluation Report Generation
# ==============================================================================

def test_end_to_end_evaluation_report_generation():
    """Test 6: Run full evaluation runner and verify output JSON structure."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        out_path = Path(tmp_dir) / "test_report.json"
        report = evaluate_cases(REAL_SYNTHETIC_DIR, out_path)

        assert out_path.exists()
        assert "evaluation_metadata" in report
        assert "cases" in report
        assert report["evaluation_metadata"]["total_cases_evaluated"] == 3

        # Check CASE-2026-001 has benchmark accuracy
        case1 = next(c for c in report["cases"] if c["case_id"] == "CASE-2026-001")
        assert case1["evaluation_available"] is True
        assert "method_evaluations" in case1
        assert "proportional" in case1["method_evaluations"]
        assert "fifo" in case1["method_evaluations"]
        assert "libr" in case1["method_evaluations"]
        assert "consensus_lower" in case1["method_evaluations"]
        assert "consensus_upper" in case1["method_evaluations"]
