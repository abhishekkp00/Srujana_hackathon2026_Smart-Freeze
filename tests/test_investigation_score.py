"""Unit and Integration Tests for Investigation Priority Scoring.

Tests component weighting, missing component coverage, deterministic ranking,
evidence-backed explanations, temporal cutoff isolation, and ground-truth isolation.
"""

from __future__ import annotations

import math
from pathlib import Path
import pytest
import pandas as pd

from engine.behavioural_features import CaseFeatures
from engine.investigation_score import (
    GOVERNANCE_DISCLAIMER,
    CasePriorityScore,
    ComponentScore,
    InvestigationScoringEngine,
    ScoringConfig,
)


def test_correct_weighted_score_all_components():
    """Verify exact prototype formula S = 0.40*B + 0.40*T + 0.20*H with hand-calculated inputs."""
    config = ScoringConfig(weight_b=0.40, weight_t=0.40, weight_h=0.20)
    engine = InvestigationScoringEngine(config=config)

    # Hand-crafted features: B=80.0, T=60.0, H=50.0
    # Expected: 0.40*80 + 0.40*60 + 0.20*50 = 32 + 24 + 10 = 66.0
    case = {"case_id": "CASE-HAND", "reported_amount_paise": 10000000, "reported_date": "2026-01-15T00:00:00Z"}
    
    # Create synthetic transactions yielding known features
    # B: 1 rapid hop (40pts) + amount_dev=1.0 (0pts) + drain=1.0 (25pts) = 65.0
    # T: depth=2 (35pts) + fan_out=1 (5pts) + cash=True (20pts) = 60.0
    # H: suspected=1.0 (50pts) + amount=10M/20M (25pts) = 75.0
    # S = 0.40*65 + 0.40*60 + 0.20*75 = 26 + 24 + 15 = 65.0
    txs = [
        {
            "transaction_id": "TXN_H1",
            "timestamp": "2026-01-10T10:00:00Z",
            "from_account": "ACC_V",
            "to_account": "ACC_M",
            "amount_paise": 10000000,
            "transaction_type": "transfer",
            "case_id": "CASE-HAND",
            "evidence_status": "suspected_fraud",
        },
        {
            "transaction_id": "TXN_H2",
            "timestamp": "2026-01-10T10:45:00Z",  # 45 mins: rapid hop
            "from_account": "ACC_M",
            "to_account": "EXT_CASH_ATM",
            "amount_paise": 10000000,
            "transaction_type": "withdrawal",
            "case_id": "CASE-HAND",
            "evidence_status": "suspected_fraud",
        },
    ]
    accounts = [
        {"account_id": "ACC_V", "opening_balance_paise": 10000000, "history_complete": True},
        {"account_id": "ACC_M", "opening_balance_paise": 0, "history_complete": True},
    ]

    res = engine.score_case(case=case, transactions=txs, accounts=accounts)
    assert res.case_id == "CASE-HAND"
    assert res.evidence_coverage == 1.0
    assert res.status == "SCORED"
    assert res.component_b.is_available is True
    assert res.component_t.is_available is True
    assert res.component_h.is_available is True

    expected_score = round(
        config.weight_b * res.component_b.score
        + config.weight_t * res.component_t.score
        + config.weight_h * res.component_h.score,
        2,
    )
    assert math.isclose(res.final_score, expected_score, abs_tol=0.01)
    assert res.priority_band in {"CRITICAL", "HIGH", "MEDIUM", "LOW"}


def test_missing_components_and_coverage_renormalization():
    """Test handling of missing components and re-normalization of available weights."""
    config = ScoringConfig(weight_b=0.40, weight_t=0.40, weight_h=0.20, min_evidence_coverage=0.50)
    engine = InvestigationScoringEngine(config=config)

    # Empty transactions -> B and T unavailable; only H available from reported amount (coverage = 0.20)
    case = {"case_id": "CASE-NO-TX", "reported_amount_paise": 5000000, "reported_date": "2026-01-15T00:00:00Z"}
    res = engine.score_case(case=case, transactions=[], accounts=[])

    # Coverage is 0.20, which is below min_evidence_coverage (0.50)
    assert res.evidence_coverage == 0.20
    assert res.final_score is None
    assert res.priority_band == "UNSCORED"
    assert res.status == "INSUFFICIENT_COVERAGE"
    assert "B (Behavioural)" in res.missing_components
    assert "T (Transaction-Trail)" in res.missing_components
    assert "H (Historical/Contextual)" not in res.missing_components


def test_partial_coverage_above_minimum_threshold():
    """Test that when coverage >= min_coverage, score is re-normalized without artificial deflation."""
    # Custom config where H has weight 0.60
    config = ScoringConfig(weight_b=0.20, weight_t=0.20, weight_h=0.60, min_evidence_coverage=0.50)
    engine = InvestigationScoringEngine(config=config)

    case = {"case_id": "CASE-PARTIAL", "reported_amount_paise": 10000000, "reported_date": "2026-01-15T00:00:00Z"}
    # No transactions -> only H is available (coverage = 0.60 >= 0.50)
    res = engine.score_case(case=case, transactions=[], accounts=[])

    assert res.evidence_coverage == 0.60
    assert res.status == "SCORED_PARTIAL"
    assert res.final_score is not None
    # Re-normalized over H alone (weight 0.60 / 0.60 = 1.0) -> final_score should equal H score!
    assert math.isclose(res.final_score, res.component_h.score, abs_tol=0.01)


def test_component_boundaries_clamping():
    """Verify that all component scores and final scores are strictly clamped to [0.0, 100.0]."""
    engine = InvestigationScoringEngine()
    case = {"case_id": "CASE-EXTREME", "reported_amount_paise": 1000000000, "reported_date": "2026-01-15T00:00:00Z"}
    res = engine.score_case(case=case, transactions=[], accounts=[])

    if res.component_b.score is not None:
        assert 0.0 <= res.component_b.score <= 100.0
    if res.component_t.score is not None:
        assert 0.0 <= res.component_t.score <= 100.0
    if res.component_h.score is not None:
        assert 0.0 <= res.component_h.score <= 100.0
    if res.final_score is not None:
        assert 0.0 <= res.final_score <= 100.0


def test_deterministic_ranking_and_tie_breaking():
    """Verify deterministic ranking with documented 4-level tie-breaking hierarchy."""
    # Case A: score 85.0
    # Case B: score 70.0, coverage 1.0, amount 100
    # Case C: score 70.0, coverage 1.0, amount 200 (higher amount beats Case B)
    # Case D: score 70.0, coverage 1.0, amount 200, case_id "CASE-01" vs "CASE-02"
    # Case E: score None (unscored, should be last)

    dummy_comp = ComponentScore("dummy", 50.0, 1.0, True, "ok")
    scores = [
        CasePriorityScore(
            case_id="CASE-02",
            final_score=70.0,
            priority_band="HIGH",
            status="SCORED",
            evidence_coverage=1.0,
            reported_amount_paise=20000,
            reported_date="",
            component_b=dummy_comp,
            component_t=dummy_comp,
            component_h=dummy_comp,
            missing_components=[],
            positive_factors=[],
            mitigating_factors=[],
            data_quality_warnings=[],
            supporting_transaction_ids=[],
            supporting_account_ids=[],
            scoring_config_version="1.0",
            config_weights={},
        ),
        CasePriorityScore(
            case_id="CASE-01",
            final_score=70.0,
            priority_band="HIGH",
            status="SCORED",
            evidence_coverage=1.0,
            reported_amount_paise=20000,
            reported_date="",
            component_b=dummy_comp,
            component_t=dummy_comp,
            component_h=dummy_comp,
            missing_components=[],
            positive_factors=[],
            mitigating_factors=[],
            data_quality_warnings=[],
            supporting_transaction_ids=[],
            supporting_account_ids=[],
            scoring_config_version="1.0",
            config_weights={},
        ),
        CasePriorityScore(
            case_id="CASE-A",
            final_score=85.0,
            priority_band="CRITICAL",
            status="SCORED",
            evidence_coverage=1.0,
            reported_amount_paise=10000,
            reported_date="",
            component_b=dummy_comp,
            component_t=dummy_comp,
            component_h=dummy_comp,
            missing_components=[],
            positive_factors=[],
            mitigating_factors=[],
            data_quality_warnings=[],
            supporting_transaction_ids=[],
            supporting_account_ids=[],
            scoring_config_version="1.0",
            config_weights={},
        ),
        CasePriorityScore(
            case_id="CASE-UNSCORED",
            final_score=None,
            priority_band="UNSCORED",
            status="INSUFFICIENT_COVERAGE",
            evidence_coverage=0.2,
            reported_amount_paise=50000,
            reported_date="",
            component_b=dummy_comp,
            component_t=dummy_comp,
            component_h=dummy_comp,
            missing_components=[],
            positive_factors=[],
            mitigating_factors=[],
            data_quality_warnings=[],
            supporting_transaction_ids=[],
            supporting_account_ids=[],
            scoring_config_version="1.0",
            config_weights={},
        ),
    ]

    ranked = InvestigationScoringEngine.rank_cases(scores)
    # Expected ranking:
    # 1. CASE-A (score 85.0)
    # 2. CASE-01 (score 70.0, amount 20000, case_id "CASE-01" < "CASE-02")
    # 3. CASE-02 (score 70.0, amount 20000)
    # 4. CASE-UNSCORED (score None)
    assert [r.case_id for r in ranked] == ["CASE-A", "CASE-01", "CASE-02", "CASE-UNSCORED"]


def test_future_transactions_temporal_exclusion():
    """Verify that transactions occurring strictly after the cutoff timestamp are excluded."""
    engine = InvestigationScoringEngine()
    case = {"case_id": "CASE-TEMP", "reported_amount_paise": 1000000, "reported_date": "2026-01-10T00:00:00Z"}
    txs = [
        # Past transaction (valid)
        {
            "transaction_id": "TXN_PAST",
            "timestamp": "2026-01-09T12:00:00Z",
            "from_account": "ACC_A",
            "to_account": "ACC_B",
            "amount_paise": 500000,
            "case_id": "CASE-TEMP",
            "evidence_status": "suspected_fraud",
        },
        # Future transaction (should be excluded)
        {
            "transaction_id": "TXN_FUTURE",
            "timestamp": "2026-01-11T12:00:00Z",
            "from_account": "ACC_B",
            "to_account": "ACC_C",
            "amount_paise": 500000,
            "case_id": "CASE-TEMP",
            "evidence_status": "suspected_fraud",
        },
    ]

    res = engine.score_case(
        case=case,
        transactions=txs,
        accounts=[],
        cutoff_timestamp="2026-01-10T00:00:00Z",
    )

    assert "TXN_PAST" in res.supporting_transaction_ids
    assert "TXN_FUTURE" not in res.supporting_transaction_ids
    assert len(res.supporting_transaction_ids) == 1


def test_operational_modules_isolated_from_ground_truth():
    """Verify that scoring and behavioural feature modules do NOT access ground_truth.json."""
    scoring_file = Path("engine/investigation_score.py").read_text(encoding="utf-8")
    features_file = Path("engine/behavioural_features.py").read_text(encoding="utf-8")

    assert "ground_truth.json" not in scoring_file
    assert "ground_truth" not in scoring_file.lower()
    assert "ground_truth.json" not in features_file
    assert "ground_truth" not in features_file.lower()


def test_governance_disclaimer_present():
    """Verify mandatory governance disclaimer is present on all scored outputs."""
    engine = InvestigationScoringEngine()
    case = {"case_id": "CASE-DISCLAIM", "reported_amount_paise": 1000000, "reported_date": "2026-01-10T00:00:00Z"}
    res = engine.score_case(case=case, transactions=[], accounts=[])

    assert res.disclaimer == GOVERNANCE_DISCLAIMER
    assert "NOT a calibrated probability of fraud" in res.disclaimer
    assert "Automatic account freezes" in res.disclaimer


def test_real_synthetic_dataset_scoring():
    """End-to-end integration test scoring the three real synthetic cases."""
    cases_df = pd.read_csv("data/synthetic/cases.csv")
    txs_df = pd.read_csv("data/synthetic/transactions.csv")
    accs_df = pd.read_csv("data/synthetic/accounts.csv")

    engine = InvestigationScoringEngine()
    scored_cases = engine.score_all_cases(
        cases=cases_df,
        transactions=txs_df,
        accounts=accs_df,
    )

    assert len(scored_cases) == 3

    ranked = engine.rank_cases(scored_cases)
    assert len(ranked) == 3

    # Check each case scored successfully
    for sc in ranked:
        assert sc.status == "SCORED"
        assert sc.evidence_coverage == 1.0
        assert sc.final_score is not None
        assert 0.0 <= sc.final_score <= 100.0
        assert sc.priority_band in {"CRITICAL", "HIGH", "MEDIUM", "LOW"}
        assert len(sc.supporting_transaction_ids) > 0
        assert len(sc.supporting_account_ids) > 0

    df_summary = engine.to_dataframe(ranked)
    assert len(df_summary) == 3
    assert "final_score" in df_summary.columns
    assert "priority_band" in df_summary.columns
