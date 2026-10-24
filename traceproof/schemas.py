"""Canonical financial event schemas, link types, and evidence models for TraceProof."""

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class FinancialEventType(str, Enum):
    BANK_TRANSFER = "BANK_TRANSFER"
    WALLET_LOAD = "WALLET_LOAD"
    INTERNAL_WALLET_TRANSFER = "INTERNAL_WALLET_TRANSFER"
    MERCHANT_PAYMENT = "MERCHANT_PAYMENT"
    SETTLEMENT_BATCH = "SETTLEMENT_BATCH"
    SETTLEMENT_ALLOCATION = "SETTLEMENT_ALLOCATION"
    FEE = "FEE"
    REFUND_REVERSAL = "REFUND_REVERSAL"
    CASH_WITHDRAWAL = "CASH_WITHDRAWAL"
    CURRENCY_CONVERSION = "CURRENCY_CONVERSION"


class LinkClassification(str, Enum):
    CONFIRMED = "CONFIRMED"            # Cryptographically signed, matching counterparty record
    INFERRED = "INFERRED"              # Probable match based on reference, but unconfirmed by counterparty
    AMBIGUOUS = "AMBIGUOUS"            # Multiple competing candidate records
    CONTRADICTORY = "CONTRADICTORY"    # Conflicting amounts, timestamps, or statuses
    UNRESOLVED = "UNRESOLVED"          # Missing link; adapter returned no record or timed out


class TraceStatus(str, Enum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    PENDING = "PENDING"
    UNAVAILABLE = "UNAVAILABLE"
    AMBIGUOUS = "AMBIGUOUS"
    INVALID_EVIDENCE = "INVALID_EVIDENCE"


class CanonicalFinancialEvent(BaseModel):
    """Normalized multi-rail financial event record."""
    event_id: str = Field(..., description="Unique event identifier")
    institution_id: str = Field(..., description="Institution identifier (BANK_A, WALLET_B, BANK_C)")
    event_type: FinancialEventType = Field(..., description="Type of financial movement")
    source_record_id: str = Field(..., description="Original record identifier in source institution")
    transaction_reference: str = Field(..., description="External or end-to-end payment reference")
    sender_token: str = Field(..., description="Sender account/wallet token (privacy preserving)")
    recipient_token: str = Field(..., description="Recipient account/wallet token")
    amount_minor: int = Field(..., description="Integer minor units (paise in INR, cents in USD)")
    currency: str = Field(default="INR", description="Three-letter ISO currency code")
    timestamp: str = Field(..., description="ISO 8601 UTC timestamp")
    event_status: str = Field(default="SUCCESS", description="SUCCESS, REVERSED, PENDING, FAILED")
    related_event_ids: List[str] = Field(default_factory=list, description="IDs of linked events (e.g. fee, refund)")
    related_reference: Optional[str] = Field(None, description="Referenced upstream/downstream payment token")
    is_settled: bool = Field(default=True, description="True if final economic settlement occurred")
    history_complete: bool = Field(default=True, description="False if institution statements have gaps")
    fee_minor: int = Field(default=0, description="Deducted service or interchange fee in minor units")
    notes: Optional[str] = Field(None, description="Audit or contextual notes")


class SignedEvidenceEnvelope(BaseModel):
    """Cryptographically signed evidence envelope verifying record integrity and origin."""
    schema_version: str = Field(default="traceproof.v1")
    trace_request_id: str = Field(..., description="Authorized trace request identifier")
    institution_id: str = Field(..., description="Signing institution ID")
    source_record_id: str = Field(..., description="Institution internal record ID")
    approved_payload: Dict[str, Any] = Field(..., description="Canonical event fields permitted for disclosure")
    payload_sha256: str = Field(..., description="Hex SHA-256 hash of deterministic payload serialization")
    key_id: str = Field(..., description="Identifier of the signing Ed25519 public key")
    signature_hex: str = Field(..., description="Ed25519 signature in hexadecimal")
    issued_at: str = Field(..., description="ISO 8601 issuance timestamp")
    expires_at: str = Field(..., description="ISO 8601 expiration timestamp")


class EnvelopeVerificationResult(BaseModel):
    """Cryptographic verification status of an evidence envelope."""
    is_valid: bool
    status: str = Field(..., description="VALID, SIGNATURE_MISMATCH, TAMPERED_PAYLOAD, EXPIRED, UNTRUSTED_KEY")
    institution_id: str
    source_record_id: str
    key_id: str
    message: str


class TraceProofNode(BaseModel):
    id: str
    label: str
    institution_id: str
    account_token: str
    account_type: str
    is_external: bool = False


class TraceProofEdge(BaseModel):
    id: str
    source: str
    target: str
    event_id: str
    institution_id: str
    event_type: FinancialEventType
    amount_minor: int
    amount_display: float
    currency: str
    timestamp: str
    link_status: LinkClassification
    evidence_status: str
    transaction_reference: str
    fee_minor: int = 0
    envelope_id: Optional[str] = None
    unresolved_reason: Optional[str] = None


class TraceProofRangeMethod(BaseModel):
    method: str
    amount_paise: int
    amount_display: float
    valid: bool
    assumption: str


class TraceProofRange(BaseModel):
    lower_bound_paise: int
    upper_bound_paise: int
    disagreement_paise: int
    lower_bound_display: float
    upper_bound_display: float
    disagreement_display: float
    methods: List[TraceProofRangeMethod]
    reasons: List[str]


class TraceProofResponse(BaseModel):
    """Complete TraceProof reconstruction output."""
    request_id: str
    case_id: str
    status: TraceStatus
    origin_institution: str
    origin_record_id: str
    total_hops_traversed: int
    confirmed_links_count: int
    inferred_links_count: int
    ambiguous_links_count: int
    unresolved_links_count: int
    nodes: List[TraceProofNode]
    edges: List[TraceProofEdge]
    envelopes: List[SignedEvidenceEnvelope]
    verification_results: List[EnvelopeVerificationResult]
    unresolved_explanations: List[str]
    evidence_bounded_range: Optional[TraceProofRange] = None
    narrative_summary: str
    governance_notice: str = Field(
        default=(
            "TraceProof reconstructs multi-rail evidence based on signed institution envelopes. "
            "Unresolved, missing, or contradictory links are visibly retained and never silently invented. "
            "A valid Ed25519 signature confirms envelope integrity and authenticity under the institutional trust registry, "
            "not factual judicial proof of guilt. All consequential decisions require authorized human review."
        )
    )


class StartTraceRequest(BaseModel):
    scenario_id: Optional[str] = Field(None, description="Preconfigured test scenario (e.g. SCENARIO_1_COMPLETE)")
    case_id: str = Field(..., description="Authorized case identifier")
    seed_reference: Optional[str] = Field(None, description="Initial transaction reference or funding token")
    max_hops: int = Field(default=5, ge=1, le=10, description="Maximum traversal depth")


class VerifyEnvelopeRequest(BaseModel):
    envelope: SignedEvidenceEnvelope
