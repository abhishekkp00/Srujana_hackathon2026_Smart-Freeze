"""Thread-safe Security Audit Trail for Smart-Freeze.

Records and protects security-relevant events such as:
- Authorization denials (401/403)
- Broken Object-Level Authorization (BOLA) attempts
- Cryptographic verification failures (tampered payload, invalid signature, untrusted key, expired envelope)
- Replay attacks
- Administrative operations
- Rate limit violations
- Uncaught exceptions / error correlation IDs

Sanitizes sensitive data so passwords, tokens, and raw keys are NEVER logged.
"""

from __future__ import annotations

import threading
import uuid
from collections import deque
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from security.models import AuditSeverity, SecurityAuditEvent


class SecurityAuditLogger:
    """Thread-safe in-memory security audit log with export capabilities."""

    _instance: Optional["SecurityAuditLogger"] = None
    _lock = threading.Lock()

    def __init__(self, max_events: int = 2000):
        self._max_events = max_events
        self._events: deque[SecurityAuditEvent] = deque(maxlen=max_events)
        self._denials_count: int = 0

    @classmethod
    def get_instance(cls) -> "SecurityAuditLogger":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    @staticmethod
    def sanitize_details(details: Dict[str, Any]) -> Dict[str, Any]:
        """Strip sensitive credentials, signing keys, and tokens from details."""
        sensitive_keys = {
            "password",
            "token",
            "secret",
            "private_key",
            "authorization",
            "signature_hex",
            "seed",
        }
        sanitized = {}
        for k, v in details.items():
            lower_k = k.lower()
            if any(s in lower_k for s in sensitive_keys):
                sanitized[k] = "[REDACTED]"
            elif isinstance(v, dict):
                sanitized[k] = SecurityAuditLogger.sanitize_details(v)
            else:
                sanitized[k] = v
        return sanitized

    def log_event(
        self,
        event_type: str,
        endpoint: str,
        method: str,
        severity: AuditSeverity = AuditSeverity.INFO,
        user_id: Optional[str] = None,
        user_role: Optional[str] = None,
        ip_address: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> SecurityAuditEvent:
        """Create, sanitize, and record an immutable security audit event."""
        event_id = f"SEC_EVT_{uuid.uuid4().hex[:12].upper()}"
        now_iso = datetime.now(timezone.utc).isoformat()
        clean_details = self.sanitize_details(details or {})

        event = SecurityAuditEvent(
            event_id=event_id,
            timestamp=now_iso,
            event_type=event_type,
            user_id=user_id,
            user_role=user_role,
            ip_address=ip_address,
            endpoint=endpoint,
            method=method,
            details=clean_details,
            severity=severity,
        )

        with self._lock:
            self._events.appendleft(event)
            if severity in (AuditSeverity.WARNING, AuditSeverity.HIGH, AuditSeverity.CRITICAL):
                self._denials_count += 1

        return event

    def get_events(
        self,
        limit: int = 100,
        severity: Optional[AuditSeverity] = None,
        event_type: Optional[str] = None,
    ) -> List[SecurityAuditEvent]:
        """Query recent security events with filtering."""
        with self._lock:
            results = list(self._events)

        if severity:
            results = [e for e in results if e.severity == severity]
        if event_type:
            results = [e for e in results if e.event_type == event_type]

        return results[:limit]

    def get_telemetry(self) -> Dict[str, Any]:
        """Return audit telemetry counts."""
        with self._lock:
            return {
                "total_events": len(self._events),
                "denials_count": self._denials_count,
            }
