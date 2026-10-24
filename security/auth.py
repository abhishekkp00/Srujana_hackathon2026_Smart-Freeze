"""Authentication and Authorization Provider for Smart-Freeze.

Defines the enterprise OIDC / OAuth 2.0 interface and an isolated development
identity provider with preconfigured demonstration personas.

Enforces Deny-By-Default:
- Validates Bearer token format and signature.
- Verifies user role privileges (Vertical access control).
- Verifies case assignment (Horizontal access control / BOLA defense).
- Fails closed in production environments if unconfigured.
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional
from fastapi import Depends, Header, HTTPException, Request, status

from security.audit import SecurityAuditLogger
from security.models import AuditSeverity, AuthContext, Role, User

# Active environment: "development", "test", or "production"
ENV_MODE = os.getenv("SMART_FREEZE_ENV", "production").strip().lower()
# Explicit opt-in: public/re-deployed instances must never inherit known demo bearer tokens.
DEMO_AUTH_ENABLED = ENV_MODE in {"development", "test"} and os.getenv("ENABLE_DEMO_AUTH", "false").strip().lower() in {"1", "true", "yes"}

# Mock demonstration personas for local development and testing
DEMO_PERSONAS: Dict[str, User] = {
    "dev_token_investigator_1": User(
        user_id="USR_INV_CHEN",
        email="sarah.chen@fairhold.internal",
        display_name="Sarah Chen (Investigator)",
        role=Role.INVESTIGATOR,
        assigned_cases=[
            "CASE-2026-001",
            "CASE-2026-002",
            "CASE-2026-TP-01",
            "CASE-2026-TP-02",
            "CASE-2026-TP-03",
            "CASE-2026-TP-04",
        ],
        institution_id="FIU_IND_CENTRAL",
    ),
    "dev_token_investigator_2": User(
        user_id="USR_INV_VANCE",
        email="marcus.vance@fairhold.internal",
        display_name="Marcus Vance (Investigator)",
        role=Role.INVESTIGATOR,
        assigned_cases=["CASE-2026-003"],
        institution_id="FIU_IND_CENTRAL",
    ),
    "dev_token_admin": User(
        user_id="USR_ADM_THORNE",
        email="alex.thorne@fairhold.internal",
        display_name="Alex Thorne (Lead Compliance Admin)",
        role=Role.COMPLIANCE_ADMIN,
        assigned_cases=["*"],
        institution_id="FIU_IND_CENTRAL",
    ),
    "dev_token_auditor": User(
        user_id="USR_AUD_NAIR",
        email="priya.nair@fairhold.internal",
        display_name="Priya Nair (External Auditor)",
        role=Role.AUDITOR,
        assigned_cases=["*"],
        institution_id="INDEPENDENT_AUDIT_CORP",
    ),
}


class AuthenticationProvider(ABC):
    """Abstract interface for enterprise identity providers."""

    @abstractmethod
    def authenticate(self, token: str) -> Optional[AuthContext]:
        """Validate bearer token and return active AuthContext, or None."""
        pass


class OIDCAuthenticationProvider(AuthenticationProvider):
    """Production enterprise OIDC / OAuth 2.0 provider.
    
    Placeholder only. JWT signature, issuer, audience, expiry and role claims are not
    implemented, so this provider intentionally accepts no token until completed and tested.
    """

    def __init__(self, jwks_url: Optional[str] = None, client_id: Optional[str] = None):
        self.jwks_url = jwks_url or os.getenv("OIDC_JWKS_URL")
        self.client_id = client_id or os.getenv("OIDC_CLIENT_ID")
        self.is_configured = bool(self.jwks_url and self.client_id)
        self.is_implemented = False

    def authenticate(self, token: str) -> Optional[AuthContext]:
        # Fail closed even when endpoint configuration exists: JWT verification is not implemented.
        return None


class DevTokenAuthProvider(AuthenticationProvider):
    """Isolated local development and testing identity provider."""

    def authenticate(self, token: str) -> Optional[AuthContext]:
        if DEMO_AUTH_ENABLED and token in DEMO_PERSONAS:
            user = DEMO_PERSONAS[token]
            now_iso = datetime.now(timezone.utc).isoformat()
            return AuthContext(
                user=user,
                token_type="dev_bearer",
                issued_at=now_iso,
                expires_at="DEMO_SESSION",
            )
        return None


def get_auth_provider() -> AuthenticationProvider:
    """Return configured authentication provider based on environment."""
    if not DEMO_AUTH_ENABLED:
        return OIDCAuthenticationProvider()
    return DevTokenAuthProvider()


# Singleton provider instance
_active_provider = get_auth_provider()


def get_current_user(
    request: Request,
    authorization: Optional[str] = Header(None),
) -> AuthContext:
    """FastAPI dependency to extract and authenticate Bearer token.
    
    Denies access by default if token is missing, expired, or invalid.
    """
    audit = SecurityAuditLogger.get_instance()
    client_ip = request.client.host if request.client else "unknown"
    path = request.url.path

    if not DEMO_AUTH_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No fully implemented identity provider is configured. Enable the local demo identity mode only for isolated development, or integrate and verify institutional OIDC before deployment.",
        )

    if not authorization:
        audit.log_event(
            event_type="AUTH_MISSING_CREDENTIALS",
            endpoint=path,
            method=request.method,
            severity=AuditSeverity.WARNING,
            ip_address=client_ip,
            details={"reason": "Missing Authorization header"},
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Provide 'Authorization: Bearer <token>' header.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    parts = authorization.strip().split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        audit.log_event(
            event_type="AUTH_MALFORMED_HEADER",
            endpoint=path,
            method=request.method,
            severity=AuditSeverity.WARNING,
            ip_address=client_ip,
            details={"reason": "Invalid Authorization header format"},
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Authorization format. Expected 'Bearer <token>'.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = parts[1]
    auth_context = _active_provider.authenticate(token)

    if not auth_context:
        audit.log_event(
            event_type="AUTH_INVALID_TOKEN",
            endpoint=path,
            method=request.method,
            severity=AuditSeverity.WARNING,
            ip_address=client_ip,
            details={"reason": "Unrecognized or expired token"},
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return auth_context


def require_role(*permitted_roles: Role) -> Callable[[AuthContext], AuthContext]:
    """Dependency factory enforcing vertical Role-Based Access Control (RBAC)."""
    def role_checker(
        request: Request,
        auth: AuthContext = Depends(get_current_user),
    ) -> AuthContext:
        if not auth.has_role(*permitted_roles):
            audit = SecurityAuditLogger.get_instance()
            client_ip = request.client.host if request.client else "unknown"
            audit.log_event(
                event_type="VERTICAL_PRIVILEGE_VIOLATION",
                endpoint=request.url.path,
                method=request.method,
                severity=AuditSeverity.HIGH,
                user_id=auth.user.user_id,
                user_role=auth.user.role.value,
                ip_address=client_ip,
                details={
                    "user_role": auth.user.role.value,
                    "permitted_roles": [r.value for r in permitted_roles],
                },
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Forbidden: Role '{auth.user.role.value}' lacks required permissions for this operation.",
            )
        return auth
    return role_checker


def check_case_access(
    case_id: str,
    auth: AuthContext,
    endpoint: str,
    method: str,
    client_ip: str,
) -> None:
    """Verify that the user is authorized to access the specified case (BOLA defense)."""
    if not auth.can_access_case(case_id):
        audit = SecurityAuditLogger.get_instance()
        audit.log_event(
            event_type="BOLA_UNAUTHORIZED_CASE_ACCESS",
            endpoint=endpoint,
            method=method,
            severity=AuditSeverity.CRITICAL,
            user_id=auth.user.user_id,
            user_role=auth.user.role.value,
            ip_address=client_ip,
            details={
                "requested_case_id": case_id,
                "assigned_cases": auth.user.assigned_cases,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access denied: You are not authorized to access or modify case '{case_id}'.",
        )
