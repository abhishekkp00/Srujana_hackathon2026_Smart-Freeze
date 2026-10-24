"""Model inference service with cached loading, strict schema validation, and governance."""

import json
import hashlib
import math
import os
from pathlib import Path
from typing import Dict, Any, Optional
import joblib
import pandas as pd
from sklearn.pipeline import Pipeline

from ml.schemas import (
    FEATURE_NAMES,
    PredictRequest,
    PredictResponse,
    EvaluationReport,
    DemoSample,
)

ROOT_DIR = Path(__file__).resolve().parents[1]
MODEL_DIR = Path(os.getenv("FAIRHOLD_MODEL_DIR", str(ROOT_DIR / "models"))).resolve()
DEFAULT_ARTIFACT_PATH = MODEL_DIR / "fraud_detector_v1.joblib"
DEFAULT_METADATA_PATH = MODEL_DIR / "model_metadata.json"
DEFAULT_DEMO_PATH = MODEL_DIR / "demo_samples.json"


class ModelArtifactError(Exception):
    """Raised when the model artifact or metadata is invalid or missing."""
    pass


class MLService:
    """Singleton-style service managing model lifecycle and prediction inference."""

    _instance: Optional["MLService"] = None

    def __init__(
        self,
        artifact_path: Path = DEFAULT_ARTIFACT_PATH,
        metadata_path: Path = DEFAULT_METADATA_PATH,
        demo_path: Path = DEFAULT_DEMO_PATH,
    ):
        self.artifact_path = Path(artifact_path)
        self.metadata_path = Path(metadata_path)
        self.demo_path = Path(demo_path)

        self.pipeline: Optional[Pipeline] = None
        self.metadata: Optional[Dict[str, Any]] = None
        self.demo_samples: list[Dict[str, Any]] = []
        self.threshold: float = 0.50
        self.version: str = "unknown"
        self.algorithm: str = "RandomForestClassifier"

        self._load_artifacts()

    @classmethod
    def get_instance(cls) -> "MLService":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def reload(self) -> None:
        """Force reload of artifacts from disk."""
        self._load_artifacts()

    def _load_artifacts(self) -> None:
        """Load a locally trusted model only after validating metadata and its SHA-256 digest."""
        self.pipeline = None
        self.metadata = None
        self.demo_samples = []
        self.artifact_sha256_verified = False
        self.load_error = None

        if not self.artifact_path.is_file():
            self.load_error = "Model artifact is unavailable. Place creditcard.csv in data/raw and run the training script."
            return
        if not self.metadata_path.is_file():
            self.load_error = "Model metadata is missing. Re-run the training script to generate a matching artifact and metadata."
            return

        try:
            with self.metadata_path.open("r", encoding="utf-8") as metadata_file:
                metadata = json.load(metadata_file)

            file_size = self.artifact_path.stat().st_size
            if file_size <= 0 or file_size > 50 * 1024 * 1024:
                raise ModelArtifactError("Model artifact is empty or exceeds the configured size limit.")

            expected_sha = metadata.get("artifact_sha256")
            if not isinstance(expected_sha, str) or len(expected_sha) != 64:
                raise ModelArtifactError("Model metadata has no valid artifact SHA-256. Re-run the training script.")
            digest = hashlib.sha256()
            with self.artifact_path.open("rb") as artifact_file:
                for chunk in iter(lambda: artifact_file.read(1024 * 1024), b""):
                    digest.update(chunk)
            actual_sha = digest.hexdigest()
            if actual_sha.lower() != expected_sha.lower():
                raise ModelArtifactError("Model artifact integrity verification failed; loading was refused.")

            # Deserialization is permitted only for the configured local artifact after hash verification.
            loaded = joblib.load(self.artifact_path)
            if not isinstance(loaded, Pipeline):
                raise ModelArtifactError("The configured artifact is not a scikit-learn Pipeline.")

            stored_features = metadata.get("features")
            if stored_features != FEATURE_NAMES:
                raise ModelArtifactError("Model feature schema does not match the API feature schema.")

            demo_samples = []
            if self.demo_path.is_file():
                with self.demo_path.open("r", encoding="utf-8") as sample_file:
                    loaded_samples = json.load(sample_file)
                if not isinstance(loaded_samples, list):
                    raise ModelArtifactError("Demo sample artifact must contain a list.")
                expected = set(FEATURE_NAMES)
                for sample in loaded_samples:
                    if not isinstance(sample, dict) or not isinstance(sample.get("features"), dict):
                        raise ModelArtifactError("A demo sample has an invalid schema.")
                    if set(sample["features"]) != expected:
                        raise ModelArtifactError("A demo sample does not match the model feature schema.")
                demo_samples = loaded_samples

            self.pipeline = loaded
            self.metadata = metadata
            self.demo_samples = demo_samples
            self.threshold = float(metadata.get("selected_threshold", 0.5))
            self.version = str(metadata.get("model_version") or metadata.get("selected_model") or "unversioned")
            self.artifact_sha256_verified = True
        except Exception as exc:
            # Keep the API alive, but make inference unavailable and expose a sanitized status.
            self.pipeline = None
            self.metadata = None
            self.demo_samples = []
            self.artifact_sha256_verified = False
            self.load_error = str(exc) if isinstance(exc, ModelArtifactError) else "Model artifacts could not be safely loaded."
    @property
    def is_loaded(self) -> bool:
        return self.pipeline is not None and self.metadata is not None

    def get_status(self) -> Dict[str, Any]:
        """Return live model readiness based on loaded artifacts and their integrity check."""
        if not self.is_loaded or self.metadata is None:
            return {
                "status": "UNAVAILABLE",
                "message": self.load_error or "Model artifacts are unavailable.",
                "model_version": None,
                "algorithm": None,
                "selected_threshold": None,
                "artifact_sha256_verified": False,
                "feature_count": len(FEATURE_NAMES),
                "features": FEATURE_NAMES,
            }

        primary_metrics = self.metadata.get("primary_model_metrics", {})
        return {
            "status": "LOADED",
            "model_version": self.version,
            "algorithm": self.metadata.get("model_algorithm") or self.metadata.get("selected_model"),
            "selected_threshold": self.threshold,
            "artifact_sha256_verified": self.artifact_sha256_verified,
            "feature_count": len(FEATURE_NAMES),
            "features": FEATURE_NAMES,
            "training_timestamp": self.metadata.get("training_timestamp"),
            "dataset_source": self.metadata.get("dataset_source"),
            "dataset_rows": self.metadata.get("dataset_rows"),
            "train_size": self.metadata.get("train_size"),
            "validation_size": self.metadata.get("val_size"),
            "test_size": self.metadata.get("test_size"),
            "held_out_test_f1": primary_metrics.get("f1_score"),
            "held_out_test_pr_auc": primary_metrics.get("pr_auc"),
        }

    def get_evaluation_report(self) -> Dict[str, Any]:
        """Return the comprehensive held-out test evaluation report."""
        if not self.is_loaded or self.metadata is None:
            raise ModelArtifactError("Evaluation report is unavailable because model artifact is not loaded.")
        return self.metadata

    def get_demo_samples(self) -> list[Dict[str, Any]]:
        """Return real labelled demo feature vectors from the test partition."""
        return self.demo_samples

    def predict(self, feature_dict: Dict[str, Any]) -> PredictResponse:
        """Validate input features and compute fraud risk prediction."""
        if not self.is_loaded or self.pipeline is None:
            raise ModelArtifactError("ML model is not loaded. Train model or inspect /api/ml/status.")

        # Validate exact feature set
        provided_keys = set(feature_dict.keys())
        expected_keys = set(FEATURE_NAMES)

        missing = expected_keys - provided_keys
        if missing:
            raise ValueError(f"Missing required feature(s): {sorted(missing)}")

        extra = provided_keys - expected_keys
        if extra:
            raise ValueError(f"Unexpected extra feature(s) provided: {sorted(extra)}")

        # Reject booleans, NaN and infinities instead of silently coercing them.
        ordered_values = []
        for feat in FEATURE_NAMES:
            val = feature_dict[feat]
            if isinstance(val, bool) or not isinstance(val, (int, float)):
                raise ValueError(f"Feature '{feat}' must be a finite numeric value, got '{type(val).__name__}'")
            numeric = float(val)
            if not math.isfinite(numeric):
                raise ValueError(f"Feature '{feat}' must be a finite numeric value")
            ordered_values.append(numeric)

        # Create 1-row DataFrame preserving exact column names
        row_df = pd.DataFrame([ordered_values], columns=FEATURE_NAMES)

        # Predict probability of fraud (class 1)
        classes = list(self.pipeline.classes_)
        if 1 not in classes:
            raise ModelArtifactError("Loaded classifier does not expose the expected fraud class (1).")
        fraud_index = classes.index(1)
        prob = float(self.pipeline.predict_proba(row_df)[0, fraud_index])
        predicted_class = 1 if prob >= self.threshold else 0
        predicted_label = "FRAUD" if predicted_class == 1 else "NON_FRAUD"

        if predicted_class == 1:
            explanation = (
                f"Model score of {prob:.4f} exceeds the validation-selected decision threshold ({self.threshold:.2f}). "
                "The transaction exhibits multi-dimensional feature deviations characteristic of historical credit-card fraud."
            )
        else:
            explanation = (
                f"Model score of {prob:.4f} is below the decision threshold ({self.threshold:.2f}). "
                "The classifier score is below the selected threshold; this is not proof that the transaction is legitimate."
            )

        return PredictResponse(
            predicted_class=predicted_class,
            predicted_label=predicted_label,
            model_score=round(prob, 4),
            threshold_used=self.threshold,
            model_version=self.version,
            algorithm=str(self.metadata.get("model_algorithm") or self.metadata.get("selected_model") or "Unknown classifier"),
            score_type="uncalibrated_fraud_probability_estimate",
            explanation=explanation,
        )
