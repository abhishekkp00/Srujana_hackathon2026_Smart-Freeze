"""Smart-Freeze Tracing Evaluation Metrics Module.

Provides standard, reproducible mathematical metrics to evaluate fund-tracing
algorithm performance against controlled synthetic ground-truth allocations.

Metrics Provided:
- Absolute error in integer paise.
- Absolute error in rupees (INR) for audit display.
- Relative error with explicit handling of zero-ground-truth denominators.
- Exact match count and rate.
- Scenario-level grouping and aggregate performance statistics.

CRITICAL ISOLATION NOTICE:
This module is strictly intended for post-hoc evaluation and benchmarking.
Operational tracing engines (Proportional, FIFO, LIBR) and scoring modules
must NEVER import or read ground-truth data.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple


@dataclass(frozen=True)
class AccountMetric:
    """Evaluation metric for a single account comparing estimate to ground truth."""
    account_id: str
    estimated_paise: int
    ground_truth_paise: int
    absolute_error_paise: int
    absolute_error_inr: float
    relative_error: Optional[float]
    exact_match: bool
    relative_error_status: str  # "VALID", "ZERO_DENOMINATOR_EXACT", "ZERO_DENOMINATOR_ERROR"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class MethodEvaluationReport:
    """Evaluation summary for a specific tracing method across evaluated accounts."""
    method_name: str
    case_id: str
    account_metrics: List[AccountMetric]
    total_accounts: int
    exact_match_count: int
    exact_match_rate: float
    total_absolute_error_paise: int
    total_absolute_error_inr: float
    mean_absolute_error_paise: float
    mean_absolute_error_inr: float
    mean_relative_error: Optional[float]
    zero_denominator_count: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "method_name": self.method_name,
            "case_id": self.case_id,
            "account_metrics": [m.to_dict() for m in self.account_metrics],
            "total_accounts": self.total_accounts,
            "exact_match_count": self.exact_match_count,
            "exact_match_rate": self.exact_match_rate,
            "total_absolute_error_paise": self.total_absolute_error_paise,
            "total_absolute_error_inr": self.total_absolute_error_inr,
            "mean_absolute_error_paise": self.mean_absolute_error_paise,
            "mean_absolute_error_inr": self.mean_absolute_error_inr,
            "mean_relative_error": self.mean_relative_error,
            "zero_denominator_count": self.zero_denominator_count,
        }


class TracingMetricsCalculator:
    """Calculates audit metrics comparing traced estimates with ground-truth records."""

    @staticmethod
    def calculate_account_metric(
        account_id: str,
        estimated_paise: int,
        ground_truth_paise: int,
    ) -> AccountMetric:
        """Calculate metrics for a single account with integer paise precision.

        Zero-denominator policy:
        - If ground_truth == 0 and estimated == 0: relative_error = 0.0 (exact match)
        - If ground_truth == 0 and estimated > 0: relative_error = None (marked ZERO_DENOMINATOR_ERROR)
        - If ground_truth > 0: relative_error = abs(est - gt) / gt
        """
        abs_err = abs(estimated_paise - ground_truth_paise)
        abs_err_inr = round(abs_err / 100.0, 2)
        exact = (estimated_paise == ground_truth_paise)

        if ground_truth_paise > 0:
            rel_err: Optional[float] = round(abs_err / float(ground_truth_paise), 4)
            status = "VALID"
        elif exact:
            rel_err = 0.0
            status = "ZERO_DENOMINATOR_EXACT"
        else:
            rel_err = None
            status = "ZERO_DENOMINATOR_ERROR"

        return AccountMetric(
            account_id=account_id,
            estimated_paise=estimated_paise,
            ground_truth_paise=ground_truth_paise,
            absolute_error_paise=abs_err,
            absolute_error_inr=abs_err_inr,
            relative_error=rel_err,
            exact_match=exact,
            relative_error_status=status,
        )

    @classmethod
    def evaluate_method_allocations(
        cls,
        method_name: str,
        case_id: str,
        estimated_allocations: Dict[str, int],
        ground_truth_allocations: Dict[str, int],
    ) -> MethodEvaluationReport:
        """Evaluate a set of estimated allocations against ground-truth allocations."""
        all_accounts = sorted(set(estimated_allocations.keys()) | set(ground_truth_allocations.keys()))

        metrics: List[AccountMetric] = []
        for acc in all_accounts:
            est = estimated_allocations.get(acc, 0)
            gt = ground_truth_allocations.get(acc, 0)
            metric = cls.calculate_account_metric(acc, est, gt)
            metrics.append(metric)

        total_accounts = len(metrics)
        exact_matches = sum(1 for m in metrics if m.exact_match)
        exact_rate = round(exact_matches / float(total_accounts), 4) if total_accounts > 0 else 0.0

        total_abs_err_paise = sum(m.absolute_error_paise for m in metrics)
        total_abs_err_inr = round(total_abs_err_paise / 100.0, 2)

        mae_paise = round(total_abs_err_paise / float(total_accounts), 2) if total_accounts > 0 else 0.0
        mae_inr = round(total_abs_err_inr / float(total_accounts), 2) if total_accounts > 0 else 0.0

        valid_rel_errors = [m.relative_error for m in metrics if m.relative_error is not None]
        mean_rel_err = (
            round(sum(valid_rel_errors) / float(len(valid_rel_errors)), 4)
            if valid_rel_errors
            else None
        )

        zero_denom_errors = sum(1 for m in metrics if m.relative_error_status == "ZERO_DENOMINATOR_ERROR")

        return MethodEvaluationReport(
            method_name=method_name,
            case_id=case_id,
            account_metrics=metrics,
            total_accounts=total_accounts,
            exact_match_count=exact_matches,
            exact_match_rate=exact_rate,
            total_absolute_error_paise=total_abs_err_paise,
            total_absolute_error_inr=total_abs_err_inr,
            mean_absolute_error_paise=mae_paise,
            mean_absolute_error_inr=mae_inr,
            mean_relative_error=mean_rel_err,
            zero_denominator_count=zero_denom_errors,
        )
