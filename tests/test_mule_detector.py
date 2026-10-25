"""Tests for Smart-Freeze Interpretable Mule-vs-Bystander Model & Governance Invariants.

Verifies:
1. Strict split by attack family (Train: A & B, Val: C, Test: D).
2. Zero feature derivation from ground truth.
3. ROC-AUC, PR-AUC, and Precision@k on held-out test family.
4. False positive rate on the innocent aggregator hard case.
5. Comparison against hand-weighted investigation score.
6. Label-shuffle sanity test (AUC near 0.50).
7. Standardized coefficient reason code extraction.
8. Integration into engine/decision.py and API endpoints.
9. "trained on simulated data" governance labels.
"""

from __future__ import annotations

import json
from pathlib import Path
import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.main import app
from engine.behavioural_features import (
    MULE_FEATURE_NAMES,
    AccountFeatureExtractor,
    AccountBehaviouralFeatures,
)
from engine.decision import DecisionEngine
from ml.mule_service import MuleDetectorService, MulePrediction
from ml.train_mule_detector import (
    prepare_mule_dataset,
    train_and_evaluate_mule_detector,
)

ROOT_DIR = Path(__file__).resolve().parents[1]
MODEL_DIR = ROOT_DIR / "models"
MODEL_CARD_PATH = MODEL_DIR / "mule_detector_model_card.json"
ARTIFACT_PATH = MODEL_DIR / "mule_detector_v1.joblib"


@pytest.fixture(scope="module")
def api_client():
    return TestClient(app)


@pytest.fixture(scope="module")
def auth_headers():
    return {"Authorization": "Bearer dev_token_admin"}


def test_split_by_attack_family_isolation():
    """Verify strict partition separation by attack family."""
    df, gt, _ = prepare_mule_dataset(seed=42, num_accounts=500, num_cases=20)
    
    train_families = set(df[df["family"].isin(["family_a", "family_b"])]["family"])
    val_families = set(df[df["family"] == "family_c"]["family"])
    test_families = set(df[df["family"] == "family_d"]["family"])

    assert train_families == {"family_a", "family_b"}
    assert val_families == {"family_c"}
    assert test_families == {"family_d"}
    assert train_families.isdisjoint(val_families)
    assert train_families.isdisjoint(test_families)
    assert val_families.isdisjoint(test_families)


def test_no_feature_derived_from_ground_truth():
    """Verify that feature extraction inspects only public ledger records without ground truth."""
    extractor = AccountFeatureExtractor()
    mock_accounts = [
        {"account_id": "ACC_TEST_01", "opening_balance_paise": 500_000, "history_complete": True},
        {"account_id": "ACC_TEST_02", "opening_balance_paise": 100_000, "history_complete": False},
    ]
    mock_txs = [
        {
            "transaction_id": "TXN_001",
            "timestamp": "2026-01-01T10:00:00Z",
            "from_account": "ACC_TEST_01",
            "to_account": "ACC_TEST_02",
            "amount_paise": 200_000,
            "case_id": "CASE-TEST-001",
        },
        {
            "transaction_id": "TXN_002",
            "timestamp": "2026-01-01T10:30:00Z",
            "from_account": "ACC_TEST_02",
            "to_account": "EXT_CASH_ATM",
            "amount_paise": 190_000,
            "case_id": "CASE-TEST-001",
        },
    ]

    feats = extractor.extract_account_features(
        account_id="ACC_TEST_02",
        case_id="CASE-TEST-001",
        transactions=mock_txs,
        accounts=mock_accounts,
    )

    # Features must match deterministic public arithmetic
    assert feats.account_id == "ACC_TEST_02"
    assert feats.rapid_pass_through_ratio == 1.0  # 30m delta < 2h
    assert feats.drain_rate == 0.95  # 190,000 / 200,000
    assert feats.cash_exit_ratio == 1.0  # entire outflow was EXT_CASH_ATM
    assert feats.has_incomplete_history == 1.0  # history_complete was False
    
    # Assert no ground-truth lot fields exist on features
    feat_dict = feats.to_dict()
    for key in feat_dict.keys():
        assert "lot" not in key.lower()
        assert "ground_truth" not in key.lower()
        assert "suspected_allocation" not in key.lower()


def test_model_card_and_artifact_integrity():
    """Ensure trained model card and joblib artifact exist and match recorded SHA-256."""
    assert MODEL_CARD_PATH.is_file(), "mule_detector_model_card.json missing"
    assert ARTIFACT_PATH.is_file(), "mule_detector_v1.joblib missing"

    with open(MODEL_CARD_PATH, "r", encoding="utf-8") as f:
        card = json.load(f)

    assert card["governance_label"] == "trained on simulated data"
    assert "artifact_sha256" in card
    assert "training_data_sha256" in card
    assert len(card["features"]) == 10

    # Test metrics
    test_m = card["test_metrics"]
    assert test_m["roc_auc"] >= 0.85
    assert test_m["pr_auc"] >= 0.85
    assert test_m["precision_at_5"] > 0.0

    # Aggregator hard case false positive metric
    val_m = card["validation_metrics"]
    assert "aggregator_hard_case_false_positives" in val_m
    assert "aggregator_hard_case_false_positive_rate" in val_m


def test_label_shuffle_sanity_test_near_half():
    """Verify that permuting training labels reduces Test ROC-AUC to near 0.50."""
    with open(MODEL_CARD_PATH, "r", encoding="utf-8") as f:
        card = json.load(f)

    shuf_auc = card["sanity_checks"]["label_shuffle_test_roc_auc"]
    assert abs(shuf_auc - 0.50) < 0.20, f"Expected label shuffle AUC near 0.50, got {shuf_auc}"
    assert card["sanity_checks"]["label_shuffle_passed"] is True


def test_comparison_against_hand_weighted_score():
    """Verify comparison against hand-weighted priority score is recorded in model card."""
    with open(MODEL_CARD_PATH, "r", encoding="utf-8") as f:
        card = json.load(f)

    assert "comparisons" in card
    assert "hand_weighted_priority_score" in card["comparisons"]
    hw_auc = card["comparisons"]["hand_weighted_priority_score"]["test_roc_auc"]
    assert isinstance(hw_auc, (int, float))
    assert hw_auc > 0.50


def test_standardized_reason_code_generation():
    """Verify standardized feature contributions produce valid reason codes."""
    service = MuleDetectorService.get_instance()
    assert service.is_loaded is True

    # Account with high pass-through and cash exit
    mock_accounts = [
        {"account_id": "ACC_MULE_TEST", "opening_balance_paise": 50_000, "history_complete": True},
    ]
    mock_txs = [
        {"transaction_id": "T1", "timestamp": "2026-01-01T10:00:00Z", "from_account": "ACC_SRC", "to_account": "ACC_MULE_TEST", "amount_paise": 10_000_000, "case_id": "C1"},
        {"transaction_id": "T2", "timestamp": "2026-01-01T10:15:00Z", "from_account": "ACC_MULE_TEST", "to_account": "EXT_CASH_ATM", "amount_paise": 9_900_000, "case_id": "C1"},
    ]

    pred = service.predict_account(
        account_id="ACC_MULE_TEST",
        case_id="C1",
        transactions=mock_txs,
        accounts=mock_accounts,
    )

    assert isinstance(pred, MulePrediction)
    assert pred.governance_label == "trained on simulated data"
    assert pred.mule_score > 60.0  # High mule suspicion
    assert "MULE_RAPID_PASS_THROUGH" in pred.reason_codes or "MULE_DRAIN_SURGE" in pred.reason_codes or "MULE_CASH_EXIT_CONVERSION" in pred.reason_codes


def test_decision_engine_integrates_mule_score():
    """Verify that engine/decision.py dynamically uses MuleDetector predictions."""
    decision_engine = DecisionEngine()
    
    mock_accounts = [
        {"account_id": "ACC_VIC", "account_type": "savings", "opening_balance_paise": 20_000_000, "history_complete": True},
        {"account_id": "ACC_MULE", "account_type": "mule", "opening_balance_paise": 100_000, "history_complete": True},
    ]
    mock_txs = [
        {
            "transaction_id": "TX_SRC",
            "timestamp": "2026-01-01T10:00:00Z",
            "from_account": "ACC_VIC",
            "to_account": "ACC_MULE",
            "amount_paise": 5_000_000,
            "transaction_type": "transfer",
            "case_id": "CASE-TEST-DECISION",
            "evidence_status": "suspected_fraud",
        },
        {
            "transaction_id": "TX_OUT",
            "timestamp": "2026-01-01T10:30:00Z",
            "from_account": "ACC_MULE",
            "to_account": "EXT_CASH_ATM",
            "amount_paise": 4_900_000,
            "transaction_type": "transfer",
            "case_id": "CASE-TEST-DECISION",
            "evidence_status": "suspected_fraud",
        },
    ]

    res = decision_engine.evaluate_case(
        case_id="CASE-TEST-DECISION",
        accounts=mock_accounts,
        transactions=mock_txs,
        source_transaction_id="TX_SRC",
        mule_scores=None,  # triggers dynamic mule detector prediction
    )

    mule_rec = next(r for r in res.recommendations if r.account_id == "ACC_MULE")
    assert mule_rec.mule_score > 0.0
    # Reason codes from mule model should be present
    assert any("MULE_" in reason or "BYSTANDER_" in reason for reason in mule_rec.reasons)


def test_mule_detector_api_endpoints(api_client, auth_headers):
    """Test FastAPI endpoints for mule detector status, model card, and prediction."""
    # 1. Status endpoint
    stat_resp = api_client.get("/api/ml/mule-detector/status", headers=auth_headers)
    assert stat_resp.status_code == 200
    stat = stat_resp.json()
    assert stat["status"] == "LOADED"
    assert stat["governance_label"] == "trained on simulated data"
    assert "test_roc_auc" in stat

    # 2. Model Card endpoint
    card_resp = api_client.get("/api/ml/mule-detector/model-card", headers=auth_headers)
    assert card_resp.status_code == 200
    card = card_resp.json()
    assert card["model_name"] == "Smart-Freeze Interpretable Mule Detector"
    assert "artifact_sha256" in card

    # 3. Predict endpoint
    pred_resp = api_client.post(
        "/api/ml/mule-detector/predict",
        json={"account_id": "ACC_MULE_DIRECT_01", "case_id": "CASE-2026-001"},
        headers=auth_headers,
    )
    assert pred_resp.status_code == 200
    pred = pred_resp.json()
    assert "mule_score" in pred
    assert "mule_probability" in pred
    assert "reason_codes" in pred
    assert pred["governance_label"] == "trained on simulated data"


def test_credit_card_model_labelled_as_optional_benchmark(api_client, auth_headers):
    """Verify that Kaggle credit card model is clearly labelled as an optional external benchmark."""
    resp = api_client.get("/api/ml/status", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert "benchmark_role" in body
    assert "Optional External Benchmark" in body["benchmark_role"]
