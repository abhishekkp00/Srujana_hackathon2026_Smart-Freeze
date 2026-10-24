"""Smart-Freeze Explainable Investigation Priority Scoring Engine.

Combines behavioural anomalies (B), transaction-trail evidence (T), and
historical/contextual evidence (H) into an auditable, explainable prioritization
score to assist authorized human investigators in triaging cases.

The Investigation Priority Score is a decision-support heuristic, NOT a calibrated
probability of fraud, guilt, money laundering, or legal liability.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import math
from typing import Any, Dict, List, Optional
import pandas as pd

from engine.behavioural_features import (
    BehaviouralFeatureExtractor,
    CaseFeatures,
)


GOVERNANCE_DISCLAIMER = (
    "The Investigation Priority Score is a decision-support heuristic for prioritizing cases "
    "for authorized human review. It is NOT a calibrated probability of fraud, guilt, "
    "money laundering, or legal liability. Automatic account freezes, fund releases, "
    "or case closures must never be executed based on this score. All consequential decisions "
    "require human investigation and verification."
)


@dataclass(frozen=True)
class ScoringConfig:
    """Configurable weights, thresholds, and parameters for Investigation Priority Scoring."""
    weight_b: float = 0.40  # Behavioural anomaly weight
    weight_t: float = 0.40  # Transaction-trail evidence weight
    weight_h: float = 0.20  # Historical/contextual evidence weight
    min_evidence_coverage: float = 0.50  # Minimum coverage to compute a final score
    threshold_critical: float = 80.0
    threshold_high: float = 60.0
    threshold_medium: float = 35.0
    rapid_hop_seconds: int = 7200  # 2 hours threshold
    version: str = "1.0.0-prototype"

    def __post_init__(self):
        total = self.weight_b + self.weight_t + self.weight_h
        if not math.isclose(total, 1.0, rel_tol=1e-5):
            raise ValueError(f"Weights must sum to 1.0 (got {total:.4f}).")
        if self.min_evidence_coverage < 0.0 or self.min_evidence_coverage > 1.0:
            raise ValueError("min_evidence_coverage must be between 0.0 and 1.0.")


@dataclass
class ComponentScore:
    """Score breakdown for an individual evidence component (B, T, or H)."""
    component_name: str
    score: Optional[float]
    weight: float
    is_available: bool
    description: str
    subfactors: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CasePriorityScore:
    """Complete, auditable investigation priority score and structured explanation."""
    case_id: str
    final_score: Optional[float]
    priority_band: str  # "CRITICAL", "HIGH", "MEDIUM", "LOW", "UNSCORED"
    status: str  # "SCORED", "SCORED_PARTIAL", "INSUFFICIENT_COVERAGE"
    evidence_coverage: float  # Fraction of available component weight (0.0 to 1.0)
    reported_amount_paise: int
    reported_date: str

    component_b: ComponentScore
    component_t: ComponentScore
    component_h: ComponentScore

    missing_components: List[str]
    positive_factors: List[str]
    mitigating_factors: List[str]
    data_quality_warnings: List[str]
    supporting_transaction_ids: List[str]
    supporting_account_ids: List[str]

    scoring_config_version: str
    config_weights: Dict[str, float]
    disclaimer: str = GOVERNANCE_DISCLAIMER

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        return d


class InvestigationScoringEngine:
    """Orchestrates feature extraction, normalized scoring, and deterministic ranking."""

    def __init__(self, config: Optional[ScoringConfig] = None):
        self.config = config or ScoringConfig()
        self.extractor = BehaviouralFeatureExtractor(
            rapid_hop_seconds=self.config.rapid_hop_seconds
        )

    def score_case(
        self,
        case: Dict[str, Any] | Any,
        transactions: List[Dict[str, Any]] | pd.DataFrame,
        accounts: List[Dict[str, Any]] | pd.DataFrame,
        cutoff_timestamp: Optional[str] = None,
        baseline_transactions: Optional[List[Dict[str, Any]] | pd.DataFrame] = None,
    ) -> CasePriorityScore:
        """Score an individual case and produce structured evidence explanations.

        Args:
            case: Case record.
            transactions: Transaction ledger.
            accounts: Account records.
            cutoff_timestamp: Optional cutoff string (ISO 8601 UTC).
            baseline_transactions: Optional global transactions for baseline statistics.
        """
        features = self.extractor.extract_features(
            case=case,
            transactions=transactions,
            accounts=accounts,
            cutoff_timestamp=cutoff_timestamp,
            baseline_transactions=baseline_transactions,
        )

        # Build Component Scores
        comp_b = ComponentScore(
            component_name="B (Behavioural)",
            score=features.b_score,
            weight=self.config.weight_b,
            is_available=features.b_available,
            description=features.b_reason,
            subfactors=features.b_subfactors,
        )

        comp_t = ComponentScore(
            component_name="T (Transaction-Trail)",
            score=features.t_score,
            weight=self.config.weight_t,
            is_available=features.t_available,
            description=features.t_reason,
            subfactors=features.t_subfactors,
        )

        comp_h = ComponentScore(
            component_name="H (Historical/Contextual)",
            score=features.h_score,
            weight=self.config.weight_h,
            is_available=features.h_available,
            description=features.h_reason,
            subfactors=features.h_subfactors,
        )

        missing_components: List[str] = []
        available_weights = 0.0
        weighted_sum = 0.0

        if features.b_available and features.b_score is not None:
            available_weights += self.config.weight_b
            weighted_sum += self.config.weight_b * features.b_score
        else:
            missing_components.append("B (Behavioural)")

        if features.t_available and features.t_score is not None:
            available_weights += self.config.weight_t
            weighted_sum += self.config.weight_t * features.t_score
        else:
            missing_components.append("T (Transaction-Trail)")

        if features.h_available and features.h_score is not None:
            available_weights += self.config.weight_h
            weighted_sum += self.config.weight_h * features.h_score
        else:
            missing_components.append("H (Historical/Contextual)")

        total_weight = self.config.weight_b + self.config.weight_t + self.config.weight_h
        coverage = round(available_weights / total_weight, 4) if total_weight > 0 else 0.0

        # Calculate final score with re-normalization over available weights
        if coverage < self.config.min_evidence_coverage or available_weights == 0.0:
            final_score = None
            priority_band = "UNSCORED"
            status = "INSUFFICIENT_COVERAGE"
        else:
            raw_score = weighted_sum / available_weights
            final_score = round(min(100.0, max(0.0, raw_score)), 2)
            status = "SCORED" if coverage >= 0.999 else "SCORED_PARTIAL"

            if final_score >= self.config.threshold_critical:
                priority_band = "CRITICAL"
            elif final_score >= self.config.threshold_high:
                priority_band = "HIGH"
            elif final_score >= self.config.threshold_medium:
                priority_band = "MEDIUM"
            else:
                priority_band = "LOW"

        return CasePriorityScore(
            case_id=features.case_id,
            final_score=final_score,
            priority_band=priority_band,
            status=status,
            evidence_coverage=coverage,
            reported_amount_paise=features.reported_amount_paise,
            reported_date=features.reported_date,
            component_b=comp_b,
            component_t=comp_t,
            component_h=comp_h,
            missing_components=missing_components,
            positive_factors=features.positive_factors,
            mitigating_factors=features.mitigating_factors,
            data_quality_warnings=features.data_quality_warnings,
            supporting_transaction_ids=features.supporting_transaction_ids,
            supporting_account_ids=features.supporting_account_ids,
            scoring_config_version=self.config.version,
            config_weights={
                "B": self.config.weight_b,
                "T": self.config.weight_t,
                "H": self.config.weight_h,
            },
            disclaimer=GOVERNANCE_DISCLAIMER,
        )

    def score_all_cases(
        self,
        cases: List[Dict[str, Any]] | pd.DataFrame,
        transactions: List[Dict[str, Any]] | pd.DataFrame,
        accounts: List[Dict[str, Any]] | pd.DataFrame,
        cutoff_timestamp: Optional[str] = None,
    ) -> List[CasePriorityScore]:
        """Score all cases in the input list or DataFrame.

        Args:
            cases: Collection of cases.
            transactions: Full transaction journal.
            accounts: Account ledger.
            cutoff_timestamp: Optional cutoff timestamp.
        """
        if isinstance(cases, pd.DataFrame):
            case_list = cases.to_dict(orient="records")
        else:
            case_list = cases

        scores: List[CasePriorityScore] = []
        for c in case_list:
            res = self.score_case(
                case=c,
                transactions=transactions,
                accounts=accounts,
                cutoff_timestamp=cutoff_timestamp,
                baseline_transactions=transactions,
            )
            scores.append(res)

        return scores

    @staticmethod
    def rank_cases(scores: List[CasePriorityScore]) -> List[CasePriorityScore]:
        """Rank cases deterministically using explicit, documented tie-breaking.

        Tie-breaking hierarchy:
        1. final_score (descending; None scores placed last)
        2. evidence_coverage (descending)
        3. reported_amount_paise (descending)
        4. case_id (ascending lexicographical order)
        """
        # Stable sort: first sort by secondary tie-breaker (case_id ascending),
        # then sort by primary numerical criteria descending.
        by_case_id = sorted(scores, key=lambda s: str(s.case_id))
        return sorted(
            by_case_id,
            key=lambda s: (
                s.final_score if s.final_score is not None else -1.0,
                s.evidence_coverage,
                s.reported_amount_paise,
            ),
            reverse=True,
        )

    @staticmethod
    def to_dataframe(scores: List[CasePriorityScore]) -> pd.DataFrame:
        """Convert a list of CasePriorityScore objects to a presentation DataFrame."""
        rows = []
        for s in scores:
            rows.append({
                "case_id": s.case_id,
                "final_score": s.final_score,
                "priority_band": s.priority_band,
                "status": s.status,
                "evidence_coverage": s.evidence_coverage,
                "reported_amount_inr": s.reported_amount_paise / 100.0,
                "b_score": s.component_b.score,
                "t_score": s.component_t.score,
                "h_score": s.component_h.score,
                "missing_components": ", ".join(s.missing_components) if s.missing_components else "None",
                "warning_count": len(s.data_quality_warnings),
                "supporting_tx_count": len(s.supporting_transaction_ids),
                "supporting_acc_count": len(s.supporting_account_ids),
            })
        return pd.DataFrame(rows)
