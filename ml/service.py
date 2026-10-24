"""Model inference service with cached loading, strict schema validation, and governance."""

import json
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

MODEL_DIR = Path("models")
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
        """Load and validate the model pipeline, metadata, and demo samples."""
        if not self.artifact_path.exists():
            # Pipeline will remain unloaded
            return

        if not self.metadata_path.exists():
            raise ModelArtifactError(f"Metadata file missing at '{self.metadata_path}'")

        # Load metadata
        with open(self.metadata_path, "r") as f:
            self.metadata = json.load(f)

        self.threshold = float(self.metadata.get("selected_threshold", 0.50))
        self.version = self.metadata.get("primary_model_metrics", {}).get("model_name", "v1.0.0")

        # Security check: Artifact size bound (< 50MB)
        file_size = self.artifact_path.stat().st_size
        if file_size > 50 * 1024 * 1024:
            raise ModelArtifactError(f"Model artifact exceeds 50MB size limit ({file_size} bytes)")

        # Security check: Cryptographic SHA-256 integrity verification
        expected_sha = self.metadata.get("artifact_sha256")
        if expected_sha:
            import hashlib
            with open(self.artifact_path, "rb") as f:
                actual_sha = hashlib.sha256(f.read()).hexdigest()
            if actual_sha != expected_sha:
                raise ModelArtifactError(
                    f"Model artifact integrity check failed! Expected SHA-256 '{expected_sha}', "
                    f"got '{actual_sha}'. Refusing to deserialize potentially tampered model."
                )

        # Load pipeline safely from trusted local path
        try:
            loaded = joblib.load(self.artifact_path)
            if not isinstance(loaded, Pipeline):
                raise ModelArtifactError(f"Loaded object is not an sklearn.pipeline.Pipeline (got {type(loaded)})")
            self.pipeline = loaded
        except Exception as e:
            raise ModelArtifactError(f"Failed to load model artifact: {e}")

        # Load demo samples if available
        if self.demo_path.exists():
            with open(self.demo_path, "r") as f:
                self.demo_samples = json.load(f)

    @property
    def is_loaded(self) -> bool:
        return self.pipeline is not None and self.metadata is not None

    def get_status(self) -> Dict[str, Any]:
        """Return operational status of the ML model."""
        if not self.is_loaded:
            return {
                "status": "UNAVAILABLE",
                "message": "Model artifact not loaded. Run 'python scripts/train_ml_model.py' to train and export artifacts.",
                "model_version": None,
                "selected_threshold": None,
                "feature_count": len(FEATURE_NAMES),
                "features": FEATURE_NAMES,
            }

        return {
            "status": "LOADED",
            "model_version": "v1.0.0",
            "algorithm": "RandomForestClassifier (100 trees, max_depth=12)",
            "selected_threshold": self.threshold,
            "feature_count": len(FEATURE_NAMES),
            "features": FEATURE_NAMES,
            "training_timestamp": self.metadata.get("training_timestamp"),
            "dataset_source": self.metadata.get("dataset_source"),
            "held_out_test_f1": self.metadata.get("primary_model_metrics", {}).get("f1_score"),
            "held_out_test_pr_auc": self.metadata.get("primary_model_metrics", {}).get("pr_auc"),
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

        # Ensure all values are numeric
        ordered_values = []
        for feat in FEATURE_NAMES:
            val = feature_dict[feat]
            if val is None or not isinstance(val, (int, float)):
                raise ValueError(f"Feature '{feat}' must be a numeric value, got '{type(val).__name__}'")
            ordered_values.append(float(val))

        # Create 1-row DataFrame preserving exact column names
        row_df = pd.DataFrame([ordered_values], columns=FEATURE_NAMES)

        # Predict probability of fraud (class 1)
        prob = float(self.pipeline.predict_proba(row_df)[0, 1])
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
                "Feature vector is consistent with typical legitimate card transaction profiles in historical data."
            )

        return PredictResponse(
            predicted_class=predicted_class,
            predicted_label=predicted_label,
            model_score=round(prob, 4),
            threshold_used=self.threshold,
            model_version="v1.0.0",
            algorithm="RandomForestClassifier",
            score_type="uncalibrated_fraud_probability_estimate",
            explanation=explanation,
        )
