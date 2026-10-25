"""Security and Governance Models for Smart-Freeze.

Defines roles, users, authentication contexts, security audit events,
and error response models following institutional governance standards.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class Role(str, Enum):
    """Authorized organizational roles with explicit privilege tiers."""
    INVESTIGATOR = "INVESTIGATOR"
    COMPLIANCE_ADMIN = "COMPLIANCE_ADMIN"
    AUDITOR = "AUDITOR"


class User(BaseModel):
    """Authenticated user profile with assigned case permissions."""
    user_id: str
    email: str
    display_name: str
    role: Role
    assigned_cases: List[str] = Field(
        default_factory=list,
        description="List of case IDs the user is authorized to inspect. ['*'] grants all cases.",
    )
    institution_id: str = "FIU_IND_CENTRAL"


class AuthContext(BaseModel):
    """Active session authorization context."""
    user: User
    token_type: str = "dev_bearer"
    issued_at: str
    expires_at: str

    def has_role(self, *roles: Role) -> bool:
        """Check if user role matches one of the permitted roles."""
        return self.user.role in roles

    def can_access_case(self, case_id: str) -> bool:
        """Enforce Object-Level Authorization (prevent BOLA/IDOR).
        
        Admins and auditors have system-wide read access. Investigators
        may only access cases explicitly assigned to them.
        """
        if self.user.role in (Role.COMPLIANCE_ADMIN, Role.AUDITOR):
            return True
        if "*" in self.user.assigned_cases:
            return True
        return case_id in self.user.assigned_cases


class AuditSeverity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class SecurityAuditEvent(BaseModel):
    """Structured, hash-chained, immutable security audit event."""
    event_id: str
    timestamp: str
    event_type: str
    user_id: Optional[str] = None
    user_role: Optional[str] = None
    ip_address: Optional[str] = None
    endpoint: str
    method: str
    details: Dict[str, Any] = Field(default_factory=dict)
    severity: AuditSeverity = AuditSeverity.INFO
    previous_hash: str = Field(
        default="0" * 64,
        description="SHA-256 hash of the previous event in the chain ('0'*64 for genesis)",
    )
    entry_hash: str = Field(
        default="",
        description="SHA-256 hash of this event's canonical fields and previous_hash",
    )


class ChainVerificationResponse(BaseModel):
    """Outcome of verifying cryptographic integrity of the audit hash chain."""
    is_valid: bool
    total_events: int
    verified_events: int
    latest_hash: str
    tampered_event_id: Optional[str] = None
    error_message: Optional[str] = None
    governance_notice: str = (
        "Cryptographic hash chaining proves algorithmic reproducibility and log integrity; "
        "it does not establish that logged actions reflect real-world truth."
    )


class SecurityStatusResponse(BaseModel):
    """Runtime security telemetry with explicit limitations."""
    status: str
    auth_mode: str
    production_auth_ready: bool
    demo_auth_enabled: bool
    pki_signature_algorithm: str
    model_sha256_verified: bool
    case_scope_authorization_status: str
    rate_limiting_active: bool
    rate_limiting_scope: str
    hidden_data_isolation_status: str
    total_audit_events: int
    security_denials_count: int
    active_institutions_registered: int
