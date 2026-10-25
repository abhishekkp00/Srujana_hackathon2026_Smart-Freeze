"""Thread-safe Cryptographic Hash-Chained Security Audit Trail for Smart-Freeze.

Records and protects security-relevant events such as:
- Authorization denials (401/403)
- Broken Object-Level Authorization (BOLA) attempts
- Cryptographic verification failures (tampered payload, invalid signature, untrusted key, expired envelope)
- Replay attacks
- Administrative operations
- Hold recommendations & cryptographic approval receipts
- Rate limit violations
- Uncaught exceptions / error correlation IDs

Every entry includes the SHA-256 hash of the previous entry, establishing a tamper-evident
audit log. verify_chain() validates that the hash sequence and payload integrity are unbroken.

Notice on Limitation:
Cryptographic verification and hash-chaining prove algorithmic reproducibility and tamper-evident
integrity of the audit log; they do NOT prove that the underlying input ledger records, transaction
events, or external banking claims are objectively true in the real world.
"""

from __future__ import annotations

import hashlib
import json
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from security.models import AuditSeverity, SecurityAuditEvent


GENESIS_PREVIOUS_HASH = "0" * 64
AUDIT_GOVERNANCE_NOTICE = (
    "Cryptographic hash chaining proves algorithmic reproducibility and log integrity; "
    "it does not establish that logged actions reflect real-world truth."
)


def compute_canonical_event_hash(
    event_id: str,
    timestamp: str,
    event_type: str,
    user_id: Optional[str],
    user_role: Optional[str],
    ip_address: Optional[str],
    endpoint: str,
    method: str,
    details: Dict[str, Any],
    severity: str,
    previous_hash: str,
) -> str:
    """Compute SHA-256 hex digest of the canonical JSON representation of an audit event."""
    payload = {
        "event_id": event_id,
        "timestamp": timestamp,
        "event_type": event_type,
        "user_id": user_id,
        "user_role": user_role,
        "ip_address": ip_address,
        "endpoint": endpoint,
        "method": method,
        "details": details,
        "severity": severity,
        "previous_hash": previous_hash,
    }
    canonical_bytes = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(canonical_bytes).hexdigest()


class SecurityAuditLogger:
    """Thread-safe cryptographic hash-chained security audit log."""

    _instance: Optional["SecurityAuditLogger"] = None
    _lock = threading.Lock()

    def __init__(self, max_events: int = 10000):
        self._max_events = max_events
        self._chain: List[SecurityAuditEvent] = []
        self._last_hash: str = GENESIS_PREVIOUS_HASH
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
        """Create, sanitize, hash-chain, and record an immutable security audit event."""
        event_id = f"SEC_EVT_{uuid.uuid4().hex[:12].upper()}"
        now_iso = datetime.now(timezone.utc).isoformat()
        clean_details = self.sanitize_details(details or {})
        sev_str = severity.value if isinstance(severity, AuditSeverity) else str(severity)

        with self._lock:
            prev_hash = self._last_hash
            entry_hash = compute_canonical_event_hash(
                event_id=event_id,
                timestamp=now_iso,
                event_type=event_type,
                user_id=user_id,
                user_role=user_role,
                ip_address=ip_address,
                endpoint=endpoint,
                method=method,
                details=clean_details,
                severity=sev_str,
                previous_hash=prev_hash,
            )

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
                previous_hash=prev_hash,
                entry_hash=entry_hash,
            )

            self._chain.append(event)
            self._last_hash = entry_hash

            if severity in (AuditSeverity.WARNING, AuditSeverity.HIGH, AuditSeverity.CRITICAL):
                self._denials_count += 1

        return event

    def verify_chain(self) -> Dict[str, Any]:
        """Verify cryptographic integrity of the audit hash chain from genesis.
        
        Returns:
            Dictionary with keys:
            - is_valid: bool
            - total_events: int
            - verified_events: int
            - latest_hash: str
            - tampered_event_id: Optional[str]
            - error_message: Optional[str]
            - governance_notice: str
        """
        with self._lock:
            chain = list(self._chain)

        if not chain:
            return {
                "is_valid": True,
                "total_events": 0,
                "verified_events": 0,
                "latest_hash": GENESIS_PREVIOUS_HASH,
                "tampered_event_id": None,
                "error_message": None,
                "governance_notice": AUDIT_GOVERNANCE_NOTICE,
            }

        expected_prev = GENESIS_PREVIOUS_HASH
        for idx, event in enumerate(chain):
            # 1. Verify previous_hash linkage
            if event.previous_hash != expected_prev:
                return {
                    "is_valid": False,
                    "total_events": len(chain),
                    "verified_events": idx,
                    "latest_hash": self._last_hash,
                    "tampered_event_id": event.event_id,
                    "error_message": (
                        f"Broken chain linkage at event {event.event_id} (index {idx}): "
                        f"expected previous_hash '{expected_prev}', got '{event.previous_hash}'"
                    ),
                    "governance_notice": AUDIT_GOVERNANCE_NOTICE,
                }

            # 2. Recompute payload hash
            sev_str = event.severity.value if isinstance(event.severity, AuditSeverity) else str(event.severity)
            recomputed = compute_canonical_event_hash(
                event_id=event.event_id,
                timestamp=event.timestamp,
                event_type=event.event_type,
                user_id=event.user_id,
                user_role=event.user_role,
                ip_address=event.ip_address,
                endpoint=event.endpoint,
                method=event.method,
                details=event.details,
                severity=sev_str,
                previous_hash=expected_prev,
            )

            if event.entry_hash != recomputed:
                return {
                    "is_valid": False,
                    "total_events": len(chain),
                    "verified_events": idx,
                    "latest_hash": self._last_hash,
                    "tampered_event_id": event.event_id,
                    "error_message": (
                        f"Tampered payload detected at event {event.event_id} (index {idx}): "
                        f"expected entry_hash '{recomputed}', got '{event.entry_hash}'"
                    ),
                    "governance_notice": AUDIT_GOVERNANCE_NOTICE,
                }

            expected_prev = event.entry_hash

        return {
            "is_valid": True,
            "total_events": len(chain),
            "verified_events": len(chain),
            "latest_hash": expected_prev,
            "tampered_event_id": None,
            "error_message": None,
            "governance_notice": AUDIT_GOVERNANCE_NOTICE,
        }

    def get_events(
        self,
        limit: int = 100,
        severity: Optional[AuditSeverity] = None,
        event_type: Optional[str] = None,
    ) -> List[SecurityAuditEvent]:
        """Query recent security events with filtering in recent-first order."""
        with self._lock:
            # Reversed so most recent events are returned first
            results = list(reversed(self._chain))

        if severity:
            results = [e for e in results if e.severity == severity]
        if event_type:
            results = [e for e in results if e.event_type == event_type]

        return results[:limit]

    def get_telemetry(self) -> Dict[str, Any]:
        """Return audit telemetry counts."""
        with self._lock:
            return {
                "total_events": len(self._chain),
                "denials_count": self._denials_count,
                "latest_hash": self._last_hash,
            }
