"""Dataset loading, validation, and stratified partitioning for credit card fraud detection."""

import os
from pathlib import Path
from typing import Tuple, Dict, Any
import pandas as pd
from sklearn.model_selection import train_test_split

from ml.schemas import FEATURE_NAMES, TARGET_NAME


class DatasetValidationError(Exception):
    """Raised when the dataset fails schema or data validation."""
    pass


def load_and_validate_dataset(csv_path: str = "data/raw/creditcard.csv") -> pd.DataFrame:
    """Load creditcard.csv and strictly validate its schema and target."""
    path = Path(csv_path)
    if not path.exists():
        raise FileNotFoundError(
            f"Dataset file not found at '{csv_path}'. "
            "Please download creditcard.csv from https://www.kaggle.com/datasets/mlg-ulb/creditcardfraud "
            "and place it in data/raw/creditcard.csv."
        )

    df = pd.read_csv(path)

    # Verify column count and exact names
    expected_cols = set(FEATURE_NAMES + [TARGET_NAME])
    actual_cols = set(df.columns)
    missing_cols = expected_cols - actual_cols
    if missing_cols:
        raise DatasetValidationError(f"Missing required columns in dataset: {sorted(missing_cols)}")

    # Verify target distribution
    unique_classes = set(df[TARGET_NAME].unique())
    if not unique_classes.issubset({0, 1}):
        raise DatasetValidationError(f"Unexpected target classes in {TARGET_NAME}: {unique_classes}")

    if df[TARGET_NAME].sum() == 0:
        raise DatasetValidationError("Dataset contains zero fraud samples (class 1).")

    # Check for NaNs
    nan_count = df[FEATURE_NAMES + [TARGET_NAME]].isna().sum().sum()
    if nan_count > 0:
        raise DatasetValidationError(f"Dataset contains {nan_count} unexpected NaN values.")

    return df


def create_stratified_partitions(
    df: pd.DataFrame,
    train_ratio: float = 0.70,
    val_ratio: float = 0.15,
    test_ratio: float = 0.15,
    random_state: int = 42,
) -> Tuple[pd.DataFrame, pd.Series, pd.DataFrame, pd.Series, pd.DataFrame, pd.Series]:
    """Create reproducible stratified train, validation, and test partitions.
    
    The final test set is strictly partitioned and held out.
    """
    assert abs((train_ratio + val_ratio + test_ratio) - 1.0) < 1e-6, "Ratios must sum to 1.0"

    X = df[FEATURE_NAMES].copy()
    y = df[TARGET_NAME].copy()

    # First split: train vs (val + test)
    temp_ratio = val_ratio + test_ratio
    X_train, X_temp, y_train, y_temp = train_test_split(
        X, y,
        test_size=temp_ratio,
        stratify=y,
        random_state=random_state
    )

    # Second split: val vs test (equal split of the remaining temp)
    val_share = val_ratio / temp_ratio
    X_val, X_test, y_val, y_test = train_test_split(
        X_temp, y_temp,
        test_size=(1.0 - val_share),
        stratify=y_temp,
        random_state=random_state
    )

    return X_train, y_train, X_val, y_val, X_test, y_test
