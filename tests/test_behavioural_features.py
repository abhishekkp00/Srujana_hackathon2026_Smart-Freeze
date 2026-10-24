"""Unit and Integration Tests for Behavioural and Trail Feature Engineering.

Tests feature calculation, normalization, edge-case resilience, temporal cutoff enforcement,
and data-quality warnings.
"""

from __future__ import annotations

import datetime
from pathlib import Path
import pytest
import pandas as pd

from engine.behavioural_features import (
    BehaviouralFeatureExtractor,
    CaseFeatures,
)


@pytest.fixture
def sample_accounts():
    return [
        {"account_id": "ACC_VICTIM_01", "opening_balance_paise": 10000000, "history_complete": True},
        {"account_id": "ACC_MULE_01", "opening_balance_paise": 500000, "history_complete": True},
        {"account_id": "ACC_MULE_INCOMPLETE", "opening_balance_paise": 100000, "history_complete": False},
        {"account_id": "ACC_DEST_01", "opening_balance_paise": 0, "history_complete": True},
    ]


@pytest.fixture
def sample_transactions():
    return [
        # Case 101 trail
        {
            "transaction_id": "TXN_001",
            "timestamp": "2026-01-10T10:00:00Z",
            "from_account": "ACC_VICTIM_01",
            "to_account": "ACC_MULE_01",
            "amount_paise": 5000000,
            "transaction_type": "transfer",
            "case_id": "CASE-101",
            "evidence_status": "suspected_fraud",
        },
        {
            "transaction_id": "TXN_002",
            "timestamp": "2026-01-10T10:30:00Z",  # 30 mins later: rapid pass-through!
            "from_account": "ACC_MULE_01",
            "to_account": "ACC_DEST_01",
            "amount_paise": 4800000,
            "transaction_type": "transfer",
            "case_id": "CASE-101",
            "evidence_status": "suspected_fraud",
        },
        {
            "transaction_id": "TXN_003",
            "timestamp": "2026-01-10T11:00:00Z",
            "from_account": "ACC_MULE_01",
            "to_account": "EXT_CASH_ATM",
            "amount_paise": 200000,
            "transaction_type": "withdrawal",
            "case_id": "CASE-101",
            "evidence_status": "suspected_fraud",
        },
        # Future transaction (after cutoff)
        {
            "transaction_id": "TXN_FUTURE",
            "timestamp": "2026-01-15T12:00:00Z",
            "from_account": "ACC_DEST_01",
            "to_account": "EXT_MERCHANT",
            "amount_paise": 1000000,
            "transaction_type": "transfer",
            "case_id": "CASE-101",
            "evidence_status": "suspected_fraud",
        },
    ]


def test_rapid_movement_and_drain_detection(sample_accounts, sample_transactions):
    """Test rapid pass-through (<2h) and intermediary fund drain rate calculation."""
    extractor = BehaviouralFeatureExtractor(rapid_hop_seconds=7200)
    case = {
        "case_id": "CASE-101",
        "reported_date": "2026-01-11T00:00:00Z",
        "reported_amount_paise": 5000000,
    }

    # Cutoff at 2026-01-11 to exclude TXN_FUTURE
    features = extractor.extract_features(
        case=case,
        transactions=sample_transactions,
        accounts=sample_accounts,
        cutoff_timestamp="2026-01-11T00:00:00Z",
    )

    assert features.case_id == "CASE-101"
    assert features.b_available is True
    assert features.rapid_movement_ratio > 0.0  # TXN_001 -> TXN_002 was 30 mins
    assert features.drain_rate == 1.0  # 4.8M + 0.2M = 5.0M out of 5.0M in
    assert 0.0 <= features.b_score <= 100.0

    # Ensure TXN_FUTURE was not included in supporting transactions
    assert "TXN_FUTURE" not in features.supporting_transaction_ids
    assert len(features.supporting_transaction_ids) == 3


def test_trail_graph_depth_and_cash_withdrawal(sample_accounts, sample_transactions):
    """Test graph depth, fan-out, and cash withdrawal detection."""
    extractor = BehaviouralFeatureExtractor()
    case = {
        "case_id": "CASE-101",
        "reported_date": "2026-01-11T00:00:00Z",
        "reported_amount_paise": 5000000,
    }

    features = extractor.extract_features(
        case=case,
        transactions=sample_transactions,
        accounts=sample_accounts,
        cutoff_timestamp="2026-01-11T00:00:00Z",
    )

    assert features.t_available is True
    # VICTIM -> MULE -> DEST / ATM (depth is 2 hops)
    assert features.graph_depth == 2
    # MULE sends to DEST and EXT_CASH_ATM (fan_out is 2)
    assert features.fan_out_degree == 2
    assert features.has_cash_withdrawal is True
    assert 0.0 <= features.t_score <= 100.0
    assert any("Cash withdrawal identified" in f for f in features.positive_factors)


def test_incomplete_history_data_quality_warning(sample_accounts):
    """Test that incomplete accounts generate warnings without fabricating evidence."""
    extractor = BehaviouralFeatureExtractor()
    case = {
        "case_id": "CASE-INCOMPLETE",
        "reported_date": "2026-01-11T00:00:00Z",
        "reported_amount_paise": 2000000,
    }
    txs = [
        {
            "transaction_id": "TXN_INC_01",
            "timestamp": "2026-01-10T10:00:00Z",
            "from_account": "ACC_VICTIM_01",
            "to_account": "ACC_MULE_INCOMPLETE",
            "amount_paise": 2000000,
            "transaction_type": "transfer",
            "case_id": "CASE-INCOMPLETE",
            "evidence_status": "suspected_fraud",
        }
    ]

    features = extractor.extract_features(
        case=case,
        transactions=txs,
        accounts=sample_accounts,
    )

    assert features.has_incomplete_history is True
    assert features.incomplete_account_count == 1
    assert any("incomplete historical statement records" in w for w in features.data_quality_warnings)


def test_no_transactions_linked_to_case():
    """Test case where no transactions are yet tagged with the case_id."""
    extractor = BehaviouralFeatureExtractor()
    case = {
        "case_id": "CASE-EMPTY",
        "reported_date": "2026-01-11T00:00:00Z",
        "reported_amount_paise": 1000000,
    }

    features = extractor.extract_features(
        case=case,
        transactions=[],
        accounts=[],
    )

    assert features.b_available is False
    assert features.b_score is None
    assert features.t_available is False
    assert features.t_score is None
    # H is available from the reported amount
    assert features.h_available is True
    assert features.h_score is not None
    assert features.trail_transaction_count == 0


def test_invalid_and_out_of_range_inputs():
    """Test resilience against negative amounts, NaN/None, and malformed timestamps."""
    extractor = BehaviouralFeatureExtractor()
    case = {
        "case_id": "CASE-BAD",
        "reported_date": "invalid-timestamp",
        "reported_amount_paise": -50000,  # Negative amount
    }
    txs = [
        {
            "transaction_id": "TXN_BAD_01",
            "timestamp": "not-a-date",
            "from_account": "ACC_A",
            "to_account": "ACC_B",
            "amount_paise": "invalid_amt",
            "case_id": "CASE-BAD",
        }
    ]

    features = extractor.extract_features(
        case=case,
        transactions=txs,
        accounts=[],
    )

    # Clamped gracefully without crashing
    assert features.reported_amount_paise == 0
    assert any("Negative reported amount" in w for w in features.data_quality_warnings)
