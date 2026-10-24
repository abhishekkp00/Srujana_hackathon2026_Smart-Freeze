"""Smart-Freeze Security and Defensive Governance Package."""

from security.models import AuditSeverity, AuthContext, Role, SecurityAuditEvent, User
from security.auth import get_current_user, require_role, check_case_access
from security.audit import SecurityAuditLogger
from security.rate_limiter import rate_limit, SlidingWindowRateLimiter
from security.middleware import SecurityHeadersMiddleware, RequestSizeLimitMiddleware

__all__ = [
    "AuditSeverity",
    "AuthContext",
    "Role",
    "SecurityAuditEvent",
    "User",
    "get_current_user",
    "require_role",
    "check_case_access",
    "SecurityAuditLogger",
    "rate_limit",
    "SlidingWindowRateLimiter",
    "SecurityHeadersMiddleware",
    "RequestSizeLimitMiddleware",
]
