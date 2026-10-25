"""ML pipeline and API tests that adapt to optional local data/model artifacts."""

import hashlib
import json
from pathlib import Path

import joblib
import pandas as pd
import pytest
from sklearn.ensemble import RandomForestClassifier
from sklearn.pipeline import Pipeline
from fastapi.testclient import TestClient

from app.main import app
from ml.dataset import DatasetValidationError, load_and_validate_dataset
from ml.schemas import FEATURE_NAMES
from ml.service import MLService

ROOT = Path(__file__).resolve().parents[1]
CREDITCARD_PATH = ROOT / "data" / "raw" / "creditcard.csv"


@pytest.fixture
def client() -> TestClient:
    test_client = TestClient(app)
    test_client.headers["Authorization"] = "Bearer dev_token_admin"
    return test_client


@pytest.fixture
def ml_service() -> MLService:
    service = MLService.get_instance()
    service.reload()
    return service


def require_model(service: MLService) -> None:
    if not service.is_loaded:
        pytest.skip("No valid trained model artifact is installed: " + str(service.get_status().get("message", "unavailable")))


def test_feature_schema_and_ordering():
    """Validate the exact supported card-fraud feature schema."""
    assert len(FEATURE_NAMES) == 30
    assert FEATURE_NAMES[0] == "Time"
    assert FEATURE_NAMES[-1] == "Amount"
    assert FEATURE_NAMES[1:29] == [f"V{i}" for i in range(1, 29)]


@pytest.mark.skipif(not CREDITCARD_PATH.is_file(), reason="Optional Kaggle dataset is not installed in this checkout")
def test_dataset_validation_on_real_data():
    """Validate the downloaded credit-card dataset when it is available locally."""
    df = load_and_validate_dataset(str(CREDITCARD_PATH))
    assert set(FEATURE_NAMES).issubset(set(df.columns))
    assert "Class" in df.columns
    assert set(df["Class"].unique()).issubset({0, 1})
    assert int(df["Class"].sum()) > 0
    assert len(df) == int(df["Class"].sum()) + int((df["Class"] == 0).sum())


def test_dataset_validation_rejects_missing_columns(tmp_path: Path):
    bad_csv = tmp_path / "bad.csv"
    bad_csv.write_text("Time,V1,Class\n0.0,1.2,0\n", encoding="utf-8")
    with pytest.raises(DatasetValidationError, match="Missing required columns"):
        load_and_validate_dataset(str(bad_csv))


def test_dataset_validation_rejects_invalid_classes(tmp_path: Path):
    columns = ",".join(FEATURE_NAMES + ["Class"])
    row = ",".join(["0.0"] * len(FEATURE_NAMES) + ["2"])
    bad_csv = tmp_path / "bad_class.csv"
    bad_csv.write_text(f"{columns}\n{row}\n", encoding="utf-8")
    with pytest.raises(DatasetValidationError, match="Unexpected target classes"):
        load_and_validate_dataset(str(bad_csv))


def test_ml_service_reloads_artifacts_created_after_startup(tmp_path: Path):
    """A running API process must discover a newly trained local artifact on the next status request."""
    artifact_path = tmp_path / "fraud_detector_v1.joblib"
    metadata_path = tmp_path / "model_metadata.json"
    demo_path = tmp_path / "demo_samples.json"

    service = MLService(artifact_path=artifact_path, metadata_path=metadata_path, demo_path=demo_path)
    assert service.get_status()["status"] == "UNAVAILABLE"

    # Small deterministic fixture proves service lifecycle behaviour; it is not reported as training data.
    rows = [
        {feature: 0.0 for feature in FEATURE_NAMES},
        {feature: float(index + 1) for index, feature in enumerate(FEATURE_NAMES)},
    ]
    x = pd.DataFrame(rows, columns=FEATURE_NAMES)
    y = [0, 1]
    pipeline = Pipeline([
        ("preprocessor", "passthrough"),
        ("classifier", RandomForestClassifier(n_estimators=2, random_state=7)),
    ])
    pipeline.fit(x, y)
    joblib.dump(pipeline, artifact_path)

    digest = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
    metadata_path.write_text(json.dumps({
        "features": FEATURE_NAMES,
        "artifact_sha256": digest,
        "model_version": "test-fixture-only",
        "model_algorithm": "RandomForestClassifier",
        "selected_threshold": 0.5,
        "dataset_source": "unit-test fixture only",
        "dataset_rows": 2,
        "train_size": 2,
        "val_size": 0,
        "test_size": 0,
        "primary_model_metrics": {},
    }), encoding="utf-8")
    demo_path.write_text("[]", encoding="utf-8")

    loaded_status = service.get_status()
    assert loaded_status["status"] == "LOADED"
    assert loaded_status["model_version"] == "test-fixture-only"
    assert loaded_status["artifact_sha256_verified"] is True
    assert loaded_status["dataset_source"] == "unit-test fixture only"

def test_model_artifact_loading_and_status(ml_service: MLService):
    require_model(ml_service)
    status = ml_service.get_status()
    assert status["status"] == "LOADED"
    assert status["artifact_sha256_verified"] is True
    assert status["model_version"] == ml_service.version
    assert status["selected_threshold"] == ml_service.threshold
    assert status["feature_count"] == len(FEATURE_NAMES)


def test_prediction_consistency_after_reload(ml_service: MLService):
    require_model(ml_service)
    samples = ml_service.get_demo_samples()
    if not samples:
        pytest.skip("The trained model has no generated demo_samples.json; rerun the training script")
    sample = samples[0]["features"]
    first = ml_service.predict(sample)
    ml_service.reload()
    require_model(ml_service)
    second = ml_service.predict(sample)
    assert first.model_score == second.model_score
    assert first.predicted_class == second.predicted_class
    assert first.threshold_used == second.threshold_used


@pytest.mark.parametrize("mutator, message", [
    (lambda features: features.pop("Amount"), "Missing required feature"),
    (lambda features: features.update({"SuspiciousFlag": 1.0}), "Unexpected extra feature"),
    (lambda features: features.update({"V1": float("nan")}), "finite numeric"),
])
def test_prediction_rejects_invalid_features(ml_service: MLService, mutator, message):
    require_model(ml_service)
    samples = ml_service.get_demo_samples()
    if not samples:
        pytest.skip("The trained model has no generated demo samples")
    invalid = dict(samples[0]["features"])
    mutator(invalid)
    with pytest.raises(ValueError, match=message):
        ml_service.predict(invalid)


def test_api_ml_status_is_truthful(client: TestClient):
    response = client.get("/api/ml/status")
    assert response.status_code == 200
    status = response.json()
    assert status["feature_count"] == len(FEATURE_NAMES)

    service = MLService.get_instance()
    if service.is_loaded:
        assert status["status"] == "LOADED"
        assert status["artifact_sha256_verified"] is True
        assert status["selected_threshold"] == service.threshold
    else:
        assert status["status"] == "UNAVAILABLE"
        assert status["artifact_sha256_verified"] is False
        assert status["selected_threshold"] is None


def test_api_ml_evaluation_is_available_only_with_a_loaded_model(client: TestClient):
    response = client.get("/api/ml/evaluation")
    service = MLService.get_instance()

    if not service.is_loaded:
        assert response.status_code == 503
        return

    assert response.status_code == 200
    report = response.json()
    assert report["dataset_rows"] == report["train_size"] + report["val_size"] + report["test_size"]
    assert report["selected_threshold"] == report["primary_model_metrics"]["threshold_used"]
    assert report["primary_model_metrics"]["model_name"]
    assert report["baseline_model_metrics"]["model_name"]
    for key in ("precision", "recall", "f1_score", "pr_auc", "roc_auc", "accuracy"):
        assert 0.0 <= report["primary_model_metrics"][key] <= 1.0
    cm = report["primary_model_metrics"]["confusion_matrix"]
    assert sum(cm.values()) == report["test_size"]


def test_api_ml_demo_samples_match_model_availability(client: TestClient):
    status = client.get("/api/ml/status").json()
    response = client.get("/api/ml/demo-samples")
    assert response.status_code == 200
    samples = response.json()

    if status["status"] != "LOADED":
        assert samples == []
        return

    # Demo sample count comes from the training artifact; don't assume a fixed count.
    assert len(samples) > 0
    for sample in samples:
        assert set(sample["features"]) == set(FEATURE_NAMES)
        assert sample["ground_truth_class"] in (0, 1)


def test_api_ml_predict_success_or_unavailable(client: TestClient):
    status = client.get("/api/ml/status").json()
    samples = client.get("/api/ml/demo-samples").json()

    if status["status"] != "LOADED":
        features = {name: 0.0 for name in FEATURE_NAMES}
        response = client.post("/api/ml/predict", json={"features": features})
        assert response.status_code == 503
        return

    assert samples, "Loaded model should have generated demo samples for the interactive workflow"
    response = client.post("/api/ml/predict", json={"features": samples[0]["features"]})
    assert response.status_code == 200
    result = response.json()
    assert result["predicted_class"] in (0, 1)
    assert result["predicted_label"] in ("FRAUD", "NON_FRAUD")
    assert 0.0 <= result["model_score"] <= 1.0
    assert result["threshold_used"] == status["selected_threshold"]
    assert result["model_version"] == status["model_version"]
    assert result["governance_notice"]


def test_api_ml_predict_validates_features_even_when_model_is_unavailable(client: TestClient):
    response = client.post("/api/ml/predict", json={"features": {"Time": 100.0}})
    assert response.status_code == 422
    assert "Missing required feature" in str(response.json()["detail"])


def test_ml_predictions_do_not_change_tracing_results(client: TestClient):
    service = MLService.get_instance()
    require_model(service)
    samples = service.get_demo_samples()
    if not samples:
        pytest.skip("No generated model demo samples are installed")

    before = client.get("/api/consensus-lien/CASE-2026-001")
    assert before.status_code == 200
    before_data = before.json()

    for sample in samples[:3]:
        prediction = client.post("/api/ml/predict", json={"features": sample["features"]})
        assert prediction.status_code == 200

    after = client.get("/api/consensus-lien/CASE-2026-001")
    assert after.status_code == 200
    after_data = after.json()
    assert before_data["total_lower_bound_paise"] == after_data["total_lower_bound_paise"]
    assert before_data["total_upper_bound_paise"] == after_data["total_upper_bound_paise"]
    assert before_data["total_disagreement_paise"] == after_data["total_disagreement_paise"]


def test_smart_freeze_model_dir_env_var(monkeypatch, tmp_path):
    """Verify SMART_FREEZE_MODEL_DIR overrides default model directory."""
    custom_dir = tmp_path / "custom_models"
    custom_dir.mkdir()
    monkeypatch.setenv("SMART_FREEZE_MODEL_DIR", str(custom_dir))

    # Import/instantiate service with custom model dir
    service = MLService(
        artifact_path=custom_dir / "fraud_detector_v1.joblib",
        metadata_path=custom_dir / "model_metadata.json",
        demo_path=custom_dir / "demo_samples.json",
    )
    status = service.get_status()
    assert status["status"] == "UNAVAILABLE"
    assert not service.is_loaded

