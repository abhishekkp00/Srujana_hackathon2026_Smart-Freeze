"""Smart-Freeze Evaluation Package.

Contains modules for comparing tracing outputs against controlled ground truth
and computing audit metrics. Hidden ground truth is isolated here and must never
be accessed by operational tracing or scoring modules.
"""

from evaluation.tracing_metrics import (
    AccountMetric,
    MethodEvaluationReport,
    TracingMetricsCalculator,
)
from evaluation.run_tracing_evaluation import evaluate_cases

__all__ = [
    "AccountMetric",
    "MethodEvaluationReport",
    "TracingMetricsCalculator",
    "evaluate_cases",
]
