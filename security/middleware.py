"""Security Middlewares for Smart-Freeze FastAPI application.

Provides:
- SecurityHeadersMiddleware: Sets defense-in-depth HTTP response headers (CSP, HSTS, XFO, etc.).
- RequestSizeLimitMiddleware: Rejects oversized request payloads (>1MB) to prevent buffer overflows and memory exhaustion (HTTP 413).
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from security.audit import SecurityAuditLogger
from security.models import AuditSeverity

# Default maximum request payload: 1 MB
MAX_REQUEST_BYTES = 1 * 1024 * 1024


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Enforces strict defense-in-depth HTTP security headers."""

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)

        # Content-Type sniffing protection
        response.headers["X-Content-Type-Options"] = "nosniff"
        # Clickjacking defense
        response.headers["X-Frame-Options"] = "DENY"
        # Cross-Site Scripting protection for legacy browsers
        response.headers["X-XSS-Protection"] = "1; mode=block"
        # Referrer policy to prevent information leakage
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        # Restrict browser features and hardware APIs
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        # Mask server implementation details
        response.headers["Server"] = "Smart-Freeze-Gateway"

        # Content Security Policy (strict self-origin)
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; "
            "connect-src 'self'"
        )

        # Enforce HTTPS HSTS if running over TLS or in production
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

        return response


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    """Rejects incoming HTTP request bodies that exceed MAX_REQUEST_BYTES."""

    async def dispatch(self, request: Request, call_next) -> Response:
        content_length_str = request.headers.get("content-length")
        if content_length_str:
            try:
                content_length = int(content_length_str)
                if content_length > MAX_REQUEST_BYTES:
                    audit = SecurityAuditLogger.get_instance()
                    client_ip = request.client.host if request.client else "unknown"
                    audit.log_event(
                        event_type="OVERSIZED_REQUEST_BLOCKED",
                        endpoint=request.url.path,
                        method=request.method,
                        severity=AuditSeverity.HIGH,
                        ip_address=client_ip,
                        details={
                            "content_length": content_length,
                            "max_allowed": MAX_REQUEST_BYTES,
                        },
                    )
                    return JSONResponse(
                        status_code=413,
                        content={
                            "detail": f"Payload Too Large: request body size {content_length} bytes exceeds 1MB limit.",
                        },
                    )
            except ValueError:
                pass

        return await call_next(request)
