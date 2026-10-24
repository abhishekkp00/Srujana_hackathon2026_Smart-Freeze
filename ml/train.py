"""Training, threshold selection, held-out evaluation, and artifact serialization."""

import json
import hashlib
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Tuple

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import RobustScaler

from ml.dataset import load_and_validate_dataset, create_stratified_partitions
from ml.schemas import (
    FEATURE_NAMES,
    PCA_FEATURES,
    TARGET_NAME,
    ConfusionMatrix,
    ModelMetrics,
    EvaluationReport,
    DemoSample,
)

ROOT_DIR = Path(__file__).resolve().parents[1]
MODEL_DIR = Path(os.getenv("FAIRHOLD_MODEL_DIR", str(ROOT_DIR / "models"))).resolve()
MODEL_ARTIFACT_PATH = MODEL_DIR / "fraud_detector_v1.joblib"
METADATA_PATH = MODEL_DIR / "model_metadata.json"
DEMO_SAMPLES_PATH = MODEL_DIR / "demo_samples.json"


def build_preprocessor() -> ColumnTransformer:
    """Build preprocessing pipeline scaling Time and Amount while passing PCA features."""
    return ColumnTransformer(
        transformers=[
            ("scaler", RobustScaler(), ["Time", "Amount"]),
            ("passthrough", "passthrough", PCA_FEATURES),
        ],
        remainder="drop",
    )


def select_optimal_threshold(
    pipeline: Pipeline, X_val: pd.DataFrame, y_val: pd.Series
) -> Tuple[float, float, str]:
    """Find the operating threshold on validation data that optimizes F1 for class 1.
    
    Returns (best_threshold, best_val_f1, reason).
    """
    val_probs = pipeline.predict_proba(X_val)[:, 1]
    thresholds = np.linspace(0.05, 0.95, 91)
    best_f1 = -1.0
    best_thresh = 0.50

    for t in thresholds:
        preds = (val_probs >= t).astype(int)
        score = f1_score(y_val, preds, zero_division=0)
        if score > best_f1:
            best_f1 = score
            best_thresh = float(round(t, 2))

    reason = (
        f"Selected threshold {best_thresh:.2f} maximizes validation F1 score ({best_f1:.4f}) "
        "on the minority fraud class, optimizing the trade-off between precision and recall "
        "under severe class imbalance without referencing the test partition."
    )
    return best_thresh, float(best_f1), reason


def evaluate_model_on_test(
    model_name: str,
    pipeline: Pipeline,
    X_test: pd.DataFrame,
    y_test: pd.Series,
    threshold: float,
    threshold_reason: str,
) -> ModelMetrics:
    """Evaluate pipeline on held-out test data at the selected threshold."""
    probs = pipeline.predict_proba(X_test)[:, 1]
    preds = (probs >= threshold).astype(int)

    tn, fp, fn, tp = confusion_matrix(y_test, preds).ravel()

    return ModelMetrics(
        model_name=model_name,
        precision=float(precision_score(y_test, preds, zero_division=0)),
        recall=float(recall_score(y_test, preds, zero_division=0)),
        f1_score=float(f1_score(y_test, preds, zero_division=0)),
        pr_auc=float(average_precision_score(y_test, probs)),
        roc_auc=float(roc_auc_score(y_test, probs)),
        accuracy=float(accuracy_score(y_test, preds)),
        confusion_matrix=ConfusionMatrix(
            true_negatives=int(tn),
            false_positives=int(fp),
            false_negatives=int(fn),
            true_positives=int(tp),
        ),
        threshold_used=float(threshold),
        threshold_selection_reason=threshold_reason,
    )


def extract_demo_samples(
    df: pd.DataFrame, X_test: pd.DataFrame, y_test: pd.Series, count_per_class: int = 5
) -> list[Dict[str, Any]]:
    """Extract representative real demo transactions from the test partition."""
    fraud_indices = y_test[y_test == 1].index[:count_per_class]
    legit_indices = y_test[y_test == 0].index[:count_per_class]

    samples = []
    for idx in fraud_indices:
        row = X_test.loc[idx]
        samples.append({
            "sample_id": f"TEST_FRAUD_{idx}",
            "description": f"Historical confirmed fraud record (Test Index {idx}, Amount: €{row['Amount']:.2f})",
            "ground_truth_class": 1,
            "ground_truth_label": "FRAUD",
            "features": {col: float(row[col]) for col in FEATURE_NAMES},
        })

    for idx in legit_indices:
        row = X_test.loc[idx]
        samples.append({
            "sample_id": f"TEST_LEGIT_{idx}",
            "description": f"Historical legitimate transaction (Test Index {idx}, Amount: €{row['Amount']:.2f})",
            "ground_truth_class": 0,
            "ground_truth_label": "NON_FRAUD",
            "features": {col: float(row[col]) for col in FEATURE_NAMES},
        })

    return samples


def run_training_pipeline(
    csv_path: str | Path | None = None,
    random_state: int = 42,
    model_version: str = "v1.0.0",
) -> Dict[str, Any]:
    """Execute end-to-end ML training, evaluation, and artifact export."""
    started_at = time.perf_counter()
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    dataset_path = Path(csv_path) if csv_path is not None else ROOT_DIR / "data" / "raw" / "creditcard.csv"
    if not dataset_path.is_absolute():
        dataset_path = (ROOT_DIR / dataset_path).resolve()
    else:
        dataset_path = dataset_path.resolve()

    print(f"[{datetime.now(timezone.utc).isoformat()}] Step 1: Loading and validating dataset from '{dataset_path}'...")
    df = load_and_validate_dataset(str(dataset_path))
    total_rows = len(df)
    fraud_count = int(df[TARGET_NAME].sum())
    non_fraud_count = total_rows - fraud_count
    print(f"Dataset verified: {total_rows:,} rows (Fraud: {fraud_count:,}, Non-fraud: {non_fraud_count:,})")

    print("Step 2: Creating stratified partitions (70% Train, 15% Val, 15% Test)...")
    X_train, y_train, X_val, y_val, X_test, y_test = create_stratified_partitions(
        df, train_ratio=0.70, val_ratio=0.15, test_ratio=0.15, random_state=random_state
    )
    print(f"Splits -> Train: {len(X_train):,}, Validation: {len(X_val):,}, Held-out Test: {len(X_test):,}")

    # Baseline Model: Logistic Regression
    print("Step 3: Training Baseline Model (Logistic Regression with class_weight='balanced')...")
    lr_start = time.time()
    lr_pipeline = Pipeline([
        ("preprocessor", build_preprocessor()),
        ("classifier", LogisticRegression(
            class_weight="balanced",
            max_iter=1000,
            random_state=random_state,
            solver="lbfgs",
        )),
    ])
    lr_pipeline.fit(X_train, y_train)
    lr_duration = time.time() - lr_start
    print(f"Baseline trained in {lr_duration:.2f}s.")

    # Select threshold on validation set for Baseline
    lr_thresh, lr_val_f1, lr_reason = select_optimal_threshold(lr_pipeline, X_val, y_val)
    print(f"Baseline validation threshold: {lr_thresh:.2f} (Val F1: {lr_val_f1:.4f})")

    # Primary Model: Random Forest Classifier
    print("Step 4: Training Primary Model (Random Forest Classifier, 100 trees, max_depth=12)...")
    rf_start = time.time()
    rf_pipeline = Pipeline([
        ("preprocessor", build_preprocessor()),
        ("classifier", RandomForestClassifier(
            n_estimators=100,
            max_depth=12,
            class_weight="balanced",
            random_state=random_state,
            n_jobs=-1,
        )),
    ])
    rf_pipeline.fit(X_train, y_train)
    rf_duration = time.time() - rf_start
    print(f"Primary Random Forest trained in {rf_duration:.2f}s.")

    # Select threshold on validation set for Primary Model
    rf_thresh, rf_val_f1, rf_reason = select_optimal_threshold(rf_pipeline, X_val, y_val)
    print(f"Primary validation threshold: {rf_thresh:.2f} (Val F1: {rf_val_f1:.4f})")

    # Step 5: Held-out Test Evaluation
    print("Step 5: Evaluating both models on held-out test partition...")
    baseline_metrics = evaluate_model_on_test(
        model_name="Logistic Regression (Baseline)",
        pipeline=lr_pipeline,
        X_test=X_test,
        y_test=y_test,
        threshold=lr_thresh,
        threshold_reason=lr_reason,
    )
    primary_metrics = evaluate_model_on_test(
        model_name="Random Forest Classifier (Primary)",
        pipeline=rf_pipeline,
        X_test=X_test,
        y_test=y_test,
        threshold=rf_thresh,
        threshold_reason=rf_reason,
    )

    print(f"\n--- Held-Out Test Evaluation Results ---")
    print(f"Baseline LR: Precision={baseline_metrics.precision:.4f}, Recall={baseline_metrics.recall:.4f}, F1={baseline_metrics.f1_score:.4f}, PR-AUC={baseline_metrics.pr_auc:.4f}, ROC-AUC={baseline_metrics.roc_auc:.4f}")
    print(f"Primary RF:  Precision={primary_metrics.precision:.4f}, Recall={primary_metrics.recall:.4f}, F1={primary_metrics.f1_score:.4f}, PR-AUC={primary_metrics.pr_auc:.4f}, ROC-AUC={primary_metrics.roc_auc:.4f}")
    print(f"RF Confusion Matrix: TP={primary_metrics.confusion_matrix.true_positives}, FP={primary_metrics.confusion_matrix.false_positives}, TN={primary_metrics.confusion_matrix.true_negatives}, FN={primary_metrics.confusion_matrix.false_negatives}")

    # Step 6: Serialize Artifacts
    print(f"Step 6: Serializing fitted Random Forest pipeline to '{MODEL_ARTIFACT_PATH}'...")
    joblib.dump(rf_pipeline, MODEL_ARTIFACT_PATH, compress=3)
    artifact_digest = hashlib.sha256()
    with MODEL_ARTIFACT_PATH.open("rb") as artifact_file:
        for chunk in iter(lambda: artifact_file.read(1024 * 1024), b""):
            artifact_digest.update(chunk)
    artifact_sha256 = artifact_digest.hexdigest()

    eval_report = EvaluationReport(
        dataset_source="European Credit Card Fraud Detection (ULB / Worldline, Kaggle)",
        dataset_rows=total_rows,
        fraud_count=fraud_count,
        non_fraud_count=non_fraud_count,
        train_size=len(X_train),
        val_size=len(X_val),
        test_size=len(X_test),
        features=FEATURE_NAMES,
        training_timestamp=datetime.now(timezone.utc).isoformat(),
        random_seed=random_state,
        selected_model="Random Forest Classifier",
        selected_threshold=rf_thresh,
        primary_model_metrics=primary_metrics,
        baseline_model_metrics=baseline_metrics,
        governance_notice=(
            "The model output is an uncalibrated fraud-risk heuristic on European credit card PCA features. "
            "It does NOT establish legal guilt or liability, is NOT trained on Indian bank AML transactions, "
            "and does NOT alter proportional, FIFO, LIBR, or Consensus Lien tracing estimates."
        ),
    )

    # Include reproducibility and integrity metadata derived from this actual training run.
    metadata = eval_report.model_dump()
    metadata.update({
        "model_version": model_version,
        "model_algorithm": "RandomForestClassifier",
        "model_configuration": {
            "n_estimators": 100,
            "max_depth": 12,
            "class_weight": "balanced",
            "random_state": random_state,
            "n_jobs": -1,
        },
        "dataset_path_at_training": str(dataset_path),
        "artifact_sha256": artifact_sha256,
        "training_duration_seconds": round(time.perf_counter() - started_at, 3),
        "baseline_training_duration_seconds": round(lr_duration, 3),
        "primary_training_duration_seconds": round(rf_duration, 3),
    })
    with METADATA_PATH.open("w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)
    print(f"Saved metadata and artifact SHA-256 to '{METADATA_PATH}'.")

    # Save demo samples JSON
    demo_samples = extract_demo_samples(df, X_test, y_test, count_per_class=5)
    with open(DEMO_SAMPLES_PATH, "w") as f:
        json.dump(demo_samples, f, indent=2)
    print(f"Saved {len(demo_samples)} real demo samples to '{DEMO_SAMPLES_PATH}'.")

    return {
        "status": "SUCCESS",
        "model_version": model_version,
        "dataset_path": str(dataset_path),
        "dataset_rows": total_rows,
        "fraud_count": fraud_count,
        "non_fraud_count": non_fraud_count,
        "train_size": len(X_train),
        "val_size": len(X_val),
        "test_size": len(X_test),
        "artifact_sha256": artifact_sha256,
        "primary_metrics": primary_metrics.model_dump(),
        "baseline_metrics": baseline_metrics.model_dump(),
        "rf_training_duration_sec": rf_duration,
        "lr_training_duration_sec": lr_duration,
        "selected_threshold": rf_thresh,
        "artifact_path": str(MODEL_ARTIFACT_PATH),
        "metadata_path": str(METADATA_PATH),
    }


if __name__ == "__main__":
    run_training_pipeline()
