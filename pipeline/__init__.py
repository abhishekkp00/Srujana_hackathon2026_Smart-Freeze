"""FairHold Data Pipeline Package.

Contains modules for canonical schemas, data validation, profiling, and adapters.
"""

from pipeline.adapters.elliptic_adapter import EllipticAdapter
from pipeline.adapters.synthaml_adapter import AMLNetAdapter, SynthAMLAdapter
from pipeline.adapters.synthetic_adapter import SyntheticAdapter
from pipeline.profiling import (
    DatasetProfile,
    profile_amlnet_dataset,
    profile_elliptic_dataset,
    profile_synthaml_dataset,
    profile_synthetic_dataset,
)
from pipeline.schemas import (
    CANONICAL_ACCOUNT_COLUMNS,
    CANONICAL_CASE_COLUMNS,
    CANONICAL_TRANSACTION_COLUMNS,
    CanonicalAccount,
    CanonicalCase,
    CanonicalTransaction,
    DatasetType,
)
from pipeline.validation import (
    ValidationResult,
    validate_elliptic_dataset,
    validate_synthaml_alerts,
    validate_synthetic_accounts,
    validate_synthetic_cases,
    validate_synthetic_transactions,
)

__all__ = [
    "CANONICAL_ACCOUNT_COLUMNS",
    "CANONICAL_TRANSACTION_COLUMNS",
    "CANONICAL_CASE_COLUMNS",
    "CanonicalAccount",
    "CanonicalTransaction",
    "CanonicalCase",
    "DatasetType",
    "ValidationResult",
    "validate_synthetic_accounts",
    "validate_synthetic_transactions",
    "validate_synthetic_cases",
    "validate_elliptic_dataset",
    "validate_synthaml_alerts",
    "DatasetProfile",
    "profile_synthetic_dataset",
    "profile_elliptic_dataset",
    "profile_synthaml_dataset",
    "profile_amlnet_dataset",
    "SyntheticAdapter",
    "EllipticAdapter",
    "SynthAMLAdapter",
    "AMLNetAdapter",
]
