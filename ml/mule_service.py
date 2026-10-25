"""Smart-Freeze Interpretable Mule-vs-Bystander Model Inference Service.

Loads the verifiable, standardized Logistic Regression model trained on simulated
behavioral ledger features. Evaluates account suspicion and extracts transparent
reason codes from standardized feature contributions.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
import json
import math
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import joblib
import numpy as np
import pandas as pd

from engine.behavioural_features import (
    MULE_FEATURE_NAMES,
    AccountBehaviouralFeatures,
    AccountFeatureExtractor,
)

ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_MODEL_DIR = Path(os.getenv("SMART_FREEZE_MODEL_DIR", str(ROOT_DIR / "models"))).resolve()
DEFAULT_ARTIFACT_PATH = DEFAULT_MODEL_DIR / "mule_detector_v1.joblib"
DEFAULT_CARD_PATH = DEFAULT_MODEL_DIR / "mule_detector_model_card.json"


@dataclass
class MulePrediction:
    """Interpretable mule suspicion prediction with standardized reason codes."""
    account_id: str
    case_id: str
    mule_probability: float
    mule_score: float  # 0.0 to 100.0 scale
    is_suspicious_mule: bool
    threshold_used: float
    feature_values: Dict[str, float]
    standardized_contributions: Dict[str, float]
    reason_codes: List[str]
    governance_label: str = "trained on simulated data"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class MuleDetectorService:
    """Inference service for interpretable mule-vs-bystander classification."""

    _instance: Optional["MuleDetectorService"] = None

    def __init__(
        self,
        artifact_path: Path = DEFAULT_ARTIFACT_PATH,
        model_card_path: Path = DEFAULT_CARD_PATH,
    ):
        self.artifact_path = Path(artifact_path)
        self.model_card_path = Path(model_card_path)
        self.classifier: Any = None
        self.scaler: Any = None
        self.model_card: Optional[Dict[str, Any]] = None
        self.threshold: float = 0.50
        self.is_loaded: bool = False
        self.load_error: Optional[str] = None
        self.extractor = AccountFeatureExtractor()
        self._load_model()

    @classmethod
    def get_instance(cls) -> "MuleDetectorService":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _load_model(self) -> None:
        """Load artifact and verify integrity against recorded model card SHA-256."""
        self.classifier = None
        self.scaler = None
        self.model_card = None
        self.is_loaded = False
        self.load_error = None

        if not self.artifact_path.is_file():
            self.load_error = f"Model artifact '{self.artifact_path}' is unavailable. Run ml/train_mule_detector.py."
            return

        if not self.model_card_path.is_file():
            self.load_error = f"Model card '{self.model_card_path}' is missing."
            return

        try:
            with open(self.model_card_path, "r", encoding="utf-8") as f:
                card = json.load(f)

            expected_sha = card.get("artifact_sha256", "")
            with open(self.artifact_path, "rb") as f:
                actual_sha = hashlib.sha256(f.read()).hexdigest()

            if expected_sha and actual_sha.lower() != expected_sha.lower():
                self.load_error = (
                    f"Integrity check failed: artifact SHA-256 ({actual_sha[:16]}...) does not "
                    f"match model card recorded digest ({expected_sha[:16]}...)."
                )
                return

            payload = joblib.load(self.artifact_path)
            self.classifier = payload["classifier"]
            self.scaler = payload["scaler"]
            self.model_card = card
            self.threshold = float(card.get("selected_threshold", 0.50))
            self.is_loaded = True
        except Exception as e:
            self.load_error = f"Failed to load mule detector: {e}"
            self.is_loaded = False

    def predict_account(
        self,
        account_id: str,
        case_id: str,
        transactions: List[Dict[str, Any]] | pd.DataFrame,
        accounts: List[Dict[str, Any]] | pd.DataFrame,
        baseline_median_paise: Optional[int] = None,
    ) -> MulePrediction:
        """Extract features and produce an interpretable prediction with reason codes."""
        feats = self.extractor.extract_account_features(
            account_id=account_id,
            case_id=case_id,
            transactions=transactions,
            accounts=accounts,
            baseline_median_paise=baseline_median_paise,
        )
        raw_dict = feats.to_dict()
        vec_df = pd.DataFrame([[raw_dict[fn] for fn in MULE_FEATURE_NAMES]], columns=MULE_FEATURE_NAMES)

        if not self.is_loaded or self.classifier is None or self.scaler is None:
            # Fallback heuristic if artifact not yet loaded
            return MulePrediction(
                account_id=account_id,
                case_id=case_id,
                mule_probability=0.50,
                mule_score=50.0,
                is_suspicious_mule=False,
                threshold_used=0.50,
                feature_values=raw_dict,
                standardized_contributions={},
                reason_codes=["MODEL_UNAVAILABLE_FALLBACK"],
                governance_label="trained on simulated data",
            )

        # Standardize using trained scaler
        z_scores = self.scaler.transform(vec_df)[0]
        coefs = self.classifier.coef_[0]
        intercept = float(self.classifier.intercept_[0])

        contributions: Dict[str, float] = {}
        reason_codes: List[str] = []

        for fn, z, beta in zip(MULE_FEATURE_NAMES, z_scores, coefs):
            delta = float(beta * z)
            contributions[fn] = round(delta, 4)

            # Generate structured reason codes
            if delta > 0.35:
                if fn == "rapid_pass_through_ratio":
                    reason_codes.append("MULE_RAPID_PASS_THROUGH")
                elif fn == "drain_rate":
                    reason_codes.append("MULE_HIGH_DRAIN_RATE")
                elif fn == "amount_deviation_ratio":
                    reason_codes.append("MULE_AMOUNT_DEVIATION")
                elif fn == "fan_out_degree":
                    reason_codes.append("MULE_FAN_OUT_DISBURSEMENT")
                elif fn == "fan_in_degree":
                    reason_codes.append("MULE_FAN_IN_CONCENTRATION")
                elif fn == "cash_exit_ratio":
                    reason_codes.append("MULE_CASH_EXIT_CONVERSION")
                elif fn == "inbound_velocity":
                    reason_codes.append("MULE_INBOUND_VELOCITY")
                elif fn == "has_incomplete_history":
                    reason_codes.append("MULE_INCOMPLETE_HISTORY")
            elif delta < -0.35:
                if fn == "clean_balance_ratio":
                    reason_codes.append("BYSTANDER_HIGH_CLEAN_CAPITAL")
                elif fn == "merchant_settlement_ratio":
                    reason_codes.append("BYSTANDER_MERCHANT_SETTLEMENT")

        # Probability from logistic sigmoid
        logit = intercept + float(np.sum(coefs * z_scores))
        prob = 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, logit))))
        prob = round(prob, 4)
        mule_score = round(prob * 100.0, 1)

        return MulePrediction(
            account_id=account_id,
            case_id=case_id,
            mule_probability=prob,
            mule_score=mule_score,
            is_suspicious_mule=bool(prob >= self.threshold),
            threshold_used=self.threshold,
            feature_values=raw_dict,
            standardized_contributions=contributions,
            reason_codes=reason_codes,
            governance_label="trained on simulated data",
        )

    def predict_case_accounts(
        self,
        case_id: str,
        transactions: List[Dict[str, Any]] | pd.DataFrame,
        accounts: List[Dict[str, Any]] | pd.DataFrame,
        baseline_median_paise: Optional[int] = None,
    ) -> Dict[str, MulePrediction]:
        """Produce mule predictions for all accounts participating in a case trail."""
        account_features = self.extractor.extract_case_accounts_features(
            case_id=case_id,
            transactions=transactions,
            accounts=accounts,
            baseline_median_paise=baseline_median_paise,
        )
        predictions: Dict[str, MulePrediction] = {}
        for aid in account_features.keys():
            predictions[aid] = self.predict_account(
                account_id=aid,
                case_id=case_id,
                transactions=transactions,
                accounts=accounts,
                baseline_median_paise=baseline_median_paise,
            )
        return predictions

    def get_status(self) -> Dict[str, Any]:
        """Return operational status and metadata of the mule detector."""
        if not self.is_loaded or self.model_card is None:
            return {
                "status": "UNAVAILABLE",
                "message": self.load_error or "Model artifacts unavailable.",
                "governance_label": "trained on simulated data",
                "is_loaded": False,
            }

        return {
            "status": "LOADED",
            "model_name": self.model_card.get("model_name"),
            "model_version": self.model_card.get("model_version"),
            "model_algorithm": self.model_card.get("model_algorithm"),
            "governance_label": self.model_card.get("governance_label", "trained on simulated data"),
            "dataset_source": self.model_card.get("dataset_source"),
            "training_timestamp": self.model_card.get("training_timestamp"),
            "selected_threshold": self.threshold,
            "feature_names": MULE_FEATURE_NAMES,
            "artifact_sha256": self.model_card.get("artifact_sha256"),
            "training_data_sha256": self.model_card.get("training_data_sha256"),
            "test_roc_auc": self.model_card.get("test_metrics", {}).get("roc_auc"),
            "test_pr_auc": self.model_card.get("test_metrics", {}).get("pr_auc"),
            "aggregator_hard_case_false_positive_rate": self.model_card.get("validation_metrics", {}).get("aggregator_hard_case_false_positive_rate"),
            "label_shuffle_sanity_passed": self.model_card.get("sanity_checks", {}).get("label_shuffle_passed"),
            "is_loaded": True,
        }

    def get_model_card(self) -> Dict[str, Any]:
        """Return the complete model card."""
        if not self.is_loaded or self.model_card is None:
            return {"error": self.load_error or "Model card unavailable."}
        return self.model_card
