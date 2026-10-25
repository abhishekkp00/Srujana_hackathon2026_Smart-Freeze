"""Passport and Federated Tracing Schemas.

Defines the Passport schema for cross-institution fund tracing, cryptographic
serialization, and verification models.
"""

from __future__ import annotations

import json
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field


class PassportVerificationStatus(str, Enum):
    """Result status of passport verification."""
    VALID = "valid"
    INVALID_SIGNATURE = "invalid_signature"
    EXPIRED = "expired"
    REPLAY_DETECTED = "replay_detected"
    WRONG_KEY = "wrong_key"
    CASE_MISMATCH = "case_mismatch"
    INSTITUTION_MISMATCH = "institution_mismatch"
    AMOUNT_MISMATCH = "amount_mismatch"
    MISSING_PASSPORT = "missing_passport"
    CORRUPTED_PAYLOAD = "corrupted_payload"


def canonical_serialize(payload: Dict[str, Any]) -> bytes:
    """Deterministically serialize payload dictionary into UTF-8 bytes.

    Uses sorted keys and compact separators with no whitespace to guarantee
    byte-for-byte identical representation across platforms.
    """
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


class Passport(BaseModel):
    """Cryptographically signed passport carrying evidence across institution rails."""

    case_id: str = Field(..., description="Investigative case ID to which this transfer is cryptographically bound")
    from_institution: str = Field(..., description="Origin institution identifier (e.g. BANK_A, WALLET_W)")
    to_institution: str = Field(..., description="Destination institution identifier (e.g. BANK_B)")
    transfer_ref: str = Field(..., description="Unique transaction or transfer reference ID")
    amount_minor: int = Field(..., description="Total transfer amount in minor currency units (paise)")
    nonce: str = Field(..., description="Cryptographically random single-use nonce")
    issued_at: str = Field(..., description="ISO 8601 UTC timestamp of passport issuance")
    expires_at: str = Field(..., description="ISO 8601 UTC timestamp of passport expiration")
    signature: str = Field(..., description="Hex-encoded Ed25519 digital signature over canonical payload")

    # Per-method stolen fund tracing data
    fifo_segments: List[Tuple[int, int]] = Field(
        ...,
        description="Ordered FIFO lot segments [(segment_amount, stolen_amount), ...] in chronological order",
    )
    proportional_stolen: int = Field(..., description="Suspected stolen portion under proportional tracing (paise)")
    libr_stolen: int = Field(..., description="Suspected stolen portion under Lowest Intermediate Balance Rule (paise)")
    proportional_categories: Optional[Dict[str, int]] = Field(
        default=None,
        description="Optional detailed category allocation breakdown for proportional tracing",
    )

    def get_signable_payload(self) -> Dict[str, Any]:
        """Extract signable payload dictionary excluding the signature itself."""
        payload: Dict[str, Any] = {
            "case_id": self.case_id,
            "from_institution": self.from_institution,
            "to_institution": self.to_institution,
            "transfer_ref": self.transfer_ref,
            "amount_minor": self.amount_minor,
            "nonce": self.nonce,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "fifo_segments": self.fifo_segments,
            "proportional_stolen": self.proportional_stolen,
            "libr_stolen": self.libr_stolen,
        }
        if self.proportional_categories is not None:
            payload["proportional_categories"] = self.proportional_categories
        return payload

    def to_signable_bytes(self) -> bytes:
        """Produce canonical bytes for Ed25519 signing and verification."""
        return canonical_serialize(self.get_signable_payload())


class PassportVerificationResult(BaseModel):
    """Detailed outcome of passport verification at a destination node."""

    is_valid: bool
    status: PassportVerificationStatus
    detail: str
    transfer_ref: str
    from_institution: str
    to_institution: str


class AccountEvidenceRange(BaseModel):
    """Evidence-bounded uncertainty range for suspected funds in an account."""

    account_id: str
    institution_id: str
    min_suspected_paise: int
    max_suspected_paise: int
    widened_by_missing_paise: int
    has_unverified_inflow: bool


class FederatedComparisonResponse(BaseModel):
    """Side-by-side comparison between centralized and federated fund tracing."""

    case_id: str
    institutions: List[str]
    account_partitions: Dict[str, List[str]]
    centralized_results: Dict[str, Dict[str, int]]
    federated_results: Dict[str, Dict[str, int]]
    methods_match: Dict[str, bool]
    passports: List[Dict[str, Any]]
    account_ranges: Dict[str, AccountEvidenceRange]
    unverified_transfers_count: int
