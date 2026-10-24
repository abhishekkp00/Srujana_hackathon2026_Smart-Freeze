"""Schema definitions and constants for the Credit Card Fraud Detection ML pipeline."""

from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field

# Canonical ordered feature list (exactly 30 features in expected order)
PCA_FEATURES = [f"V{i}" for i in range(1, 29)]
FEATURE_NAMES: List[str] = ["Time"] + PCA_FEATURES + ["Amount"]
TARGET_NAME: str = "Class"


class PredictRequest(BaseModel):
    """Transaction feature dictionary for fraud risk evaluation."""
    features: Dict[str, float] = Field(
        ...,
        description="Dictionary mapping exactly all 30 feature names (Time, V1..V28, Amount) to numeric values."
    )


class PredictResponse(BaseModel):
    """Model prediction outcome and risk analysis."""
    predicted_class: int = Field(..., description="0 for Non-Fraud, 1 for Fraud")
    predicted_label: str = Field(..., description="'FRAUD' or 'NON_FRAUD'")
    model_score: float = Field(..., description="Uncalibrated positive-class score in [0.0, 1.0]; not a calibrated fraud probability")
    threshold_used: float = Field(..., description="Validation-selected decision threshold")
    model_version: str = Field(..., description="Version of the loaded model artifact")
    algorithm: str = Field(..., description="Algorithm used (e.g. 'RandomForestClassifier')")
    score_type: str = Field(
        default="uncalibrated_positive_class_score",
        description="Definition of what model_score represents; it is not calibrated unless separate calibration is implemented and evaluated"
    )
    explanation: str = Field(
        ...,
        description="Interpretive context regarding the prediction and threshold"
    )
    governance_notice: str = Field(
        default=(
            "This model is trained on European credit-card transaction data (PCA features V1-V28, Time, Amount). "
            "It serves solely as an exploratory fraud-risk indicator. It does NOT constitute legal proof of guilt "
            "or fraud, is NOT trained on Indian banking AML records, and does NOT alter fund-tracing calculations "
            "or Consensus Lien estimates."
        )
    )


class ConfusionMatrix(BaseModel):
    true_negatives: int
    false_positives: int
    false_negatives: int
    true_positives: int


class ModelMetrics(BaseModel):
    model_name: str
    precision: float
    recall: float
    f1_score: float
    pr_auc: float
    roc_auc: float
    accuracy: float
    confusion_matrix: ConfusionMatrix
    threshold_used: float
    threshold_selection_reason: str


class EvaluationReport(BaseModel):
    dataset_source: str
    dataset_rows: int
    fraud_count: int
    non_fraud_count: int
    train_size: int
    val_size: int
    test_size: int
    features: List[str]
    training_timestamp: str
    random_seed: int
    selected_model: str
    selected_threshold: float
    primary_model_metrics: ModelMetrics
    baseline_model_metrics: ModelMetrics
    governance_notice: str


class DemoSample(BaseModel):
    sample_id: str
    description: str
    ground_truth_class: int
    ground_truth_label: str
    features: Dict[str, float]
