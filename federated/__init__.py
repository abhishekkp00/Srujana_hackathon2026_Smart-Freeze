"""Federated Multi-Rail Fund Tracing Module.

Provides BankNode, Passport schema, and FederatedCoordinator for evidence-preserving
cross-institution fund tracing.
"""

from federated.schemas import (
    AccountEvidenceRange,
    FederatedComparisonResponse,
    Passport,
    PassportVerificationResult,
    PassportVerificationStatus,
    canonical_serialize,
)
from federated.node import BankNode
from federated.coordinator import FederatedCoordinator, FEDERATED_RAILS

__all__ = [
    "AccountEvidenceRange",
    "BankNode",
    "FEDERATED_RAILS",
    "FederatedComparisonResponse",
    "FederatedCoordinator",
    "Passport",
    "PassportVerificationResult",
    "PassportVerificationStatus",
    "canonical_serialize",
]
