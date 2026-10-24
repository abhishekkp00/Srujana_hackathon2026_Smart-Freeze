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
    """Structured, immutable security audit event."""
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


class SecurityStatusResponse(BaseModel):
    """System-wide security posture and defense telemetry."""
    status: str
    auth_mode: str
    pki_signature_algorithm: str
    model_sha256_verified: bool
    bola_enforcement_active: bool
    rate_limiting_active: bool
    hidden_data_isolated: bool
    total_audit_events: int
    security_denials_count: int
    active_institutions_registered: int
