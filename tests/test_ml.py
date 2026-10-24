"""Comprehensive automated tests for ML fraud detection pipeline and API endpoints."""

import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from app.main import app
from ml.dataset import DatasetValidationError, load_and_validate_dataset
from ml.schemas import FEATURE_NAMES, PredictRequest
from ml.service import MLService, ModelArtifactError


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def ml_service() -> MLService:
    service = MLService.get_instance()
    service.reload()
    return service


def test_feature_schema_and_ordering():
    """Verify feature names count and exact canonical ordering."""
    assert len(FEATURE_NAMES) == 30
    assert FEATURE_NAMES[0] == "Time"
    assert FEATURE_NAMES[-1] == "Amount"
    for i in range(1, 29):
        assert f"V{i}" in FEATURE_NAMES
        assert FEATURE_NAMES[i] == f"V{i}"


def test_dataset_validation_on_real_data():
    """Verify dataset loading and schema validation on creditcard.csv."""
    df = load_and_validate_dataset("data/raw/creditcard.csv")
    assert len(df) == 284807
    assert set(FEATURE_NAMES).issubset(set(df.columns))
    assert "Class" in df.columns
    assert df["Class"].sum() == 492


def test_dataset_validation_rejects_missing_columns(tmp_path: Path):
    """Verify validation fails if columns are missing."""
    bad_csv = tmp_path / "bad.csv"
    bad_csv.write_text("Time,V1,Class\n0.0,1.2,0\n")
    with pytest.raises(DatasetValidationError) as exc:
        load_and_validate_dataset(str(bad_csv))
    assert "Missing required columns" in str(exc.value)


def test_dataset_validation_rejects_invalid_classes(tmp_path: Path):
    """Verify validation fails if target contains invalid classes."""
    cols = ",".join(FEATURE_NAMES + ["Class"])
    row = ",".join(["0.0"] * 30 + ["2"])  # class 2 is invalid
    bad_csv = tmp_path / "bad_class.csv"
    bad_csv.write_text(f"{cols}\n{row}\n")
    with pytest.raises(DatasetValidationError) as exc:
        load_and_validate_dataset(str(bad_csv))
    assert "Unexpected target classes" in str(exc.value)


def test_model_artifact_loading_and_status(ml_service: MLService):
    """Verify MLService successfully loads the trained Random Forest artifact and metadata."""
    assert ml_service.is_loaded is True
    status = ml_service.get_status()
    assert status["status"] == "LOADED"
    assert status["model_version"] == "v1.0.0"
    assert status["selected_threshold"] == 0.63
    assert status["feature_count"] == 30


def test_prediction_consistency_after_reload(ml_service: MLService):
    """Verify prediction produces bit-identical scores before and after reloading from disk."""
    samples = ml_service.get_demo_samples()
    assert len(samples) > 0
    sample = samples[0]["features"]

    pred1 = ml_service.predict(sample)
    ml_service.reload()
    pred2 = ml_service.predict(sample)

    assert pred1.model_score == pred2.model_score
    assert pred1.predicted_class == pred2.predicted_class
    assert pred1.threshold_used == pred2.threshold_used


def test_prediction_rejects_missing_features(ml_service: MLService):
    """Verify predict rejects feature dictionaries with missing keys."""
    samples = ml_service.get_demo_samples()
    incomplete = dict(samples[0]["features"])
    del incomplete["Amount"]

    with pytest.raises(ValueError) as exc:
        ml_service.predict(incomplete)
    assert "Missing required feature(s): ['Amount']" in str(exc.value)


def test_prediction_rejects_extra_features(ml_service: MLService):
    """Verify predict rejects unexpected additional feature keys."""
    samples = ml_service.get_demo_samples()
    extra = dict(samples[0]["features"])
    extra["SuspiciousFlag"] = 1.0

    with pytest.raises(ValueError) as exc:
        ml_service.predict(extra)
    assert "Unexpected extra feature(s) provided: ['SuspiciousFlag']" in str(exc.value)


def test_prediction_rejects_non_numeric_values(ml_service: MLService):
    """Verify predict rejects non-numeric feature types."""
    samples = ml_service.get_demo_samples()
    bad_type = dict(samples[0]["features"])
    bad_type["V1"] = "invalid_string"

    with pytest.raises(ValueError) as exc:
        ml_service.predict(bad_type)
    assert "must be a numeric value" in str(exc.value)


def test_api_ml_status(client: TestClient):
    """Verify GET /api/ml/status endpoint."""
    resp = client.get("/api/ml/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "LOADED"
    assert data["feature_count"] == 30
    assert data["selected_threshold"] == 0.63
    assert "RandomForestClassifier" in data["algorithm"]


def test_api_ml_evaluation(client: TestClient):
    """Verify GET /api/ml/evaluation endpoint."""
    resp = client.get("/api/ml/evaluation")
    assert resp.status_code == 200
    data = resp.json()
    assert data["dataset_rows"] == 284807
    assert data["selected_threshold"] == 0.63
    assert "primary_model_metrics" in data
    assert "baseline_model_metrics" in data

    primary = data["primary_model_metrics"]
    assert primary["model_name"] == "Random Forest Classifier (Primary)"
    assert primary["f1_score"] > 0.75
    assert primary["roc_auc"] > 0.95
    assert "confusion_matrix" in primary


def test_api_ml_demo_samples(client: TestClient):
    """Verify GET /api/ml/demo-samples endpoint."""
    resp = client.get("/api/ml/demo-samples")
    assert resp.status_code == 200
    samples = resp.json()
    assert len(samples) == 10
    classes = {s["ground_truth_class"] for s in samples}
    assert classes == {0, 1}
    for s in samples:
        assert len(s["features"]) == 30


def test_api_ml_predict_success(client: TestClient):
    """Verify POST /api/ml/predict with valid payload."""
    demo_resp = client.get("/api/ml/demo-samples")
    sample = demo_resp.json()[0]

    resp = client.post("/api/ml/predict", json={"features": sample["features"]})
    assert resp.status_code == 200
    res = resp.json()
    assert res["predicted_class"] in (0, 1)
    assert res["predicted_label"] in ("FRAUD", "NON_FRAUD")
    assert 0.0 <= res["model_score"] <= 1.0
    assert res["threshold_used"] == 0.63
    assert "governance_notice" in res


def test_api_ml_predict_validation_error(client: TestClient):
    """Verify POST /api/ml/predict returns 422 for missing or invalid features."""
    resp = client.post("/api/ml/predict", json={"features": {"Time": 100.0}})
    assert resp.status_code == 422
    assert "Missing required feature" in resp.json()["detail"]


def test_ml_tracing_isolation(client: TestClient):
    """Verify ML predictions do NOT alter financial tracing or Consensus Lien results."""
    # 1. Fetch initial Consensus Lien
    lien_before = client.get("/api/consensus-lien/CASE-2026-001").json()

    # 2. Run several ML predictions
    samples = client.get("/api/ml/demo-samples").json()
    for s in samples[:3]:
        client.post("/api/ml/predict", json={"features": s["features"]})

    # 3. Fetch Consensus Lien again and verify identical values
    lien_after = client.get("/api/consensus-lien/CASE-2026-001").json()
    assert lien_before["total_lower_bound_paise"] == lien_after["total_lower_bound_paise"]
    assert lien_before["total_upper_bound_paise"] == lien_after["total_upper_bound_paise"]
    assert lien_before["total_disagreement_paise"] == lien_after["total_disagreement_paise"]
    assert len(lien_before["account_liens"]) == len(lien_after["account_liens"])
