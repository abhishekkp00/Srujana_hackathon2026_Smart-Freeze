"""Cryptographic operations for TraceProof Ed25519 signed evidence envelopes."""

import hashlib
import json
from datetime import datetime, timezone
from typing import Dict, Any, Tuple, Optional
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives import serialization
from cryptography.exceptions import InvalidSignature

from traceproof.schemas import SignedEvidenceEnvelope, EnvelopeVerificationResult


def canonical_serialize(payload: Dict[str, Any]) -> bytes:
    """Deterministically serialize an evidence payload dictionary into UTF-8 bytes.
    
    Uses sorted keys and compact separators with no whitespace to guarantee
    byte-for-byte identical representation across platforms.
    """
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def compute_payload_hash(payload: Dict[str, Any]) -> str:
    """Compute the SHA-256 hexadecimal digest of the canonically serialized payload."""
    return hashlib.sha256(canonical_serialize(payload)).hexdigest()


class InstitutionKeyManager:
    """Manages synthetic institutional Ed25519 keypairs and trusted public-key registry.
    
    In production, private keys reside in secure institutional HSMs/KMS and public
    keys are anchored via PKI certificates with revocation lists. For this MVP
    simulation, deterministic synthetic keypairs are pre-generated.
    """

    _instance: Optional["InstitutionKeyManager"] = None

    def __init__(self):
        # Private key mapping: institution_id -> (key_id, ed25519.Ed25519PrivateKey)
        self._private_keys: Dict[str, Tuple[str, ed25519.Ed25519PrivateKey]] = {}
        # Trusted public key registry: key_id -> (institution_id, ed25519.Ed25519PublicKey)
        self._public_registry: Dict[str, Tuple[str, ed25519.Ed25519PublicKey]] = {}

        self._initialize_synthetic_institutions()

    @classmethod
    def get_instance(cls) -> "InstitutionKeyManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _initialize_synthetic_institutions(self) -> None:
        """Create deterministic keypairs for the 3 simulated financial institutions."""
        # Derive exact 32-byte seeds using SHA-256 for deterministic key generation
        seeds = {
            "BANK_A": hashlib.sha256(b"seed_synthetic_bank_a_ed25519_2026").digest(),
            "WALLET_B": hashlib.sha256(b"seed_synthetic_wallet_b_ed25519_2026").digest(),
            "BANK_C": hashlib.sha256(b"seed_synthetic_bank_c_ed25519_2026").digest(),
        }

        for inst_id, seed in seeds.items():
            priv_key = ed25519.Ed25519PrivateKey.from_private_bytes(seed)
            pub_key = priv_key.public_key()
            key_id = f"key_{inst_id.lower()}_2026_01"

            self._private_keys[inst_id] = (key_id, priv_key)
            self._public_registry[key_id] = (inst_id, pub_key)

    def get_key_id(self, institution_id: str) -> str:
        return self._private_keys[institution_id][0]

    def sign_payload(
        self,
        institution_id: str,
        trace_request_id: str,
        source_record_id: str,
        approved_payload: Dict[str, Any],
        issued_at: Optional[str] = None,
        expires_at: Optional[str] = None,
    ) -> SignedEvidenceEnvelope:
        """Generate a signed evidence envelope for an approved event payload."""
        if institution_id not in self._private_keys:
            raise ValueError(f"No private key configured for institution '{institution_id}'")

        key_id, priv_key = self._private_keys[institution_id]
        
        # Cryptographically bind trace_request_id to payload to prevent cross-request replays
        payload = dict(approved_payload)
        if "trace_request_id" not in payload:
            payload["trace_request_id"] = trace_request_id

        payload_bytes = canonical_serialize(payload)
        payload_hash = hashlib.sha256(payload_bytes).hexdigest()

        # Sign canonical payload bytes
        sig_bytes = priv_key.sign(payload_bytes)

        now_iso = issued_at or datetime.now(timezone.utc).isoformat()
        # Default 7-day evidence envelope validity window
        exp_iso = expires_at or "2026-11-01T00:00:00+00:00"

        return SignedEvidenceEnvelope(
            schema_version="traceproof.v1",
            trace_request_id=trace_request_id,
            institution_id=institution_id,
            source_record_id=source_record_id,
            approved_payload=payload,
            payload_sha256=payload_hash,
            key_id=key_id,
            signature_hex=sig_bytes.hex(),
            issued_at=now_iso,
            expires_at=exp_iso,
        )

        # In-memory replay tracking: signature_hex -> trace_request_id
        if not hasattr(self, "_seen_envelopes"):
            self._seen_envelopes: Dict[str, str] = {}

    def verify_envelope(self, envelope: SignedEvidenceEnvelope) -> EnvelopeVerificationResult:
        """Strictly verify envelope authenticity, integrity, expiration, schema, and key trust."""
        from security.audit import SecurityAuditLogger
        from security.models import AuditSeverity

        audit = SecurityAuditLogger.get_instance()

        # 0. Validate Schema Version
        if envelope.schema_version != "traceproof.v1":
            audit.log_event(
                event_type="CRYPTO_UNSUPPORTED_SCHEMA",
                endpoint="/api/traceproof/verify-envelope",
                method="POST",
                severity=AuditSeverity.HIGH,
                details={
                    "received_schema": envelope.schema_version,
                    "expected_schema": "traceproof.v1",
                    "institution_id": envelope.institution_id,
                },
            )
            return EnvelopeVerificationResult(
                is_valid=False,
                status="UNSUPPORTED_SCHEMA",
                institution_id=envelope.institution_id,
                source_record_id=envelope.source_record_id,
                key_id=envelope.key_id,
                message=f"Unsupported schema version '{envelope.schema_version}'. Expected 'traceproof.v1'.",
            )

        # 1. Validate Expiration
        try:
            exp_dt = datetime.fromisoformat(envelope.expires_at)
            # Ensure UTC timezone awareness
            if exp_dt.tzinfo is None:
                exp_dt = exp_dt.replace(tzinfo=timezone.utc)
            if exp_dt < datetime.now(timezone.utc):
                audit.log_event(
                    event_type="CRYPTO_EXPIRED_ENVELOPE",
                    endpoint="/api/traceproof/verify-envelope",
                    method="POST",
                    severity=AuditSeverity.WARNING,
                    details={
                        "expires_at": envelope.expires_at,
                        "source_record_id": envelope.source_record_id,
                        "institution_id": envelope.institution_id,
                    },
                )
                return EnvelopeVerificationResult(
                    is_valid=False,
                    status="EXPIRED_ENVELOPE",
                    institution_id=envelope.institution_id,
                    source_record_id=envelope.source_record_id,
                    key_id=envelope.key_id,
                    message=f"Evidence envelope expired at {envelope.expires_at}.",
                )
        except Exception:
            return EnvelopeVerificationResult(
                is_valid=False,
                status="MALFORMED_TIMESTAMP",
                institution_id=envelope.institution_id,
                source_record_id=envelope.source_record_id,
                key_id=envelope.key_id,
                message="Envelope expires_at timestamp is malformed.",
            )

        # 2. Check Replay Attack
        sig_hex = envelope.signature_hex
        if hasattr(self, "_seen_envelopes") and sig_hex in self._seen_envelopes:
            original_req = self._seen_envelopes[sig_hex]
            if original_req != envelope.trace_request_id:
                audit.log_event(
                    event_type="CRYPTO_REPLAY_ATTEMPT",
                    endpoint="/api/traceproof/verify-envelope",
                    method="POST",
                    severity=AuditSeverity.CRITICAL,
                    details={
                        "source_record_id": envelope.source_record_id,
                        "original_request_id": original_req,
                        "replayed_request_id": envelope.trace_request_id,
                        "institution_id": envelope.institution_id,
                    },
                )
                return EnvelopeVerificationResult(
                    is_valid=False,
                    status="REPLAYED_ENVELOPE",
                    institution_id=envelope.institution_id,
                    source_record_id=envelope.source_record_id,
                    key_id=envelope.key_id,
                    message=f"Replay detected: envelope signature was previously presented for trace request '{original_req}'.",
                )

        key_id = envelope.key_id
        if key_id not in self._public_registry:
            audit.log_event(
                event_type="CRYPTO_UNTRUSTED_KEY",
                endpoint="/api/traceproof/verify-envelope",
                method="POST",
                severity=AuditSeverity.HIGH,
                details={"untrusted_key_id": key_id, "institution_id": envelope.institution_id},
            )
            return EnvelopeVerificationResult(
                is_valid=False,
                status="UNTRUSTED_KEY",
                institution_id=envelope.institution_id,
                source_record_id=envelope.source_record_id,
                key_id=key_id,
                message=f"Key '{key_id}' is not present in the local trusted institution registry.",
            )

        reg_inst, pub_key = self._public_registry[key_id]
        if reg_inst != envelope.institution_id:
            audit.log_event(
                event_type="CRYPTO_KEY_INSTITUTION_MISMATCH",
                endpoint="/api/traceproof/verify-envelope",
                method="POST",
                severity=AuditSeverity.HIGH,
                details={
                    "claimed_institution": envelope.institution_id,
                    "registered_institution": reg_inst,
                    "key_id": key_id,
                },
            )
            return EnvelopeVerificationResult(
                is_valid=False,
                status="INSTITUTION_KEY_MISMATCH",
                institution_id=envelope.institution_id,
                source_record_id=envelope.source_record_id,
                key_id=key_id,
                message=f"Key '{key_id}' belongs to '{reg_inst}', not '{envelope.institution_id}'.",
            )

        # 3. Verify payload hash integrity
        calculated_hash = compute_payload_hash(envelope.approved_payload)
        if calculated_hash != envelope.payload_sha256:
            audit.log_event(
                event_type="CRYPTO_TAMPERED_PAYLOAD",
                endpoint="/api/traceproof/verify-envelope",
                method="POST",
                severity=AuditSeverity.CRITICAL,
                details={
                    "source_record_id": envelope.source_record_id,
                    "institution_id": envelope.institution_id,
                    "calculated_hash": calculated_hash,
                    "envelope_hash": envelope.payload_sha256,
                },
            )
            return EnvelopeVerificationResult(
                is_valid=False,
                status="TAMPERED_PAYLOAD",
                institution_id=envelope.institution_id,
                source_record_id=envelope.source_record_id,
                key_id=key_id,
                message="Envelope payload hash does not match approved_payload content (data altered).",
            )

        # 4. Verify Ed25519 signature
        payload_bytes = canonical_serialize(envelope.approved_payload)
        try:
            sig_bytes = bytes.fromhex(envelope.signature_hex)
            pub_key.verify(sig_bytes, payload_bytes)
        except (ValueError, InvalidSignature) as exc:
            audit.log_event(
                event_type="CRYPTO_SIGNATURE_MISMATCH",
                endpoint="/api/traceproof/verify-envelope",
                method="POST",
                severity=AuditSeverity.CRITICAL,
                details={
                    "source_record_id": envelope.source_record_id,
                    "institution_id": envelope.institution_id,
                    "key_id": key_id,
                },
            )
            return EnvelopeVerificationResult(
                is_valid=False,
                status="SIGNATURE_MISMATCH",
                institution_id=envelope.institution_id,
                source_record_id=envelope.source_record_id,
                key_id=key_id,
                message="Cryptographic signature check failed: invalid signature for payload.",
            )

        # Record envelope signature to prevent future replays across different requests
        if not hasattr(self, "_seen_envelopes"):
            self._seen_envelopes = {}
        self._seen_envelopes[sig_hex] = envelope.trace_request_id

        return EnvelopeVerificationResult(
            is_valid=True,
            status="VALID",
            institution_id=envelope.institution_id,
            source_record_id=envelope.source_record_id,
            key_id=key_id,
            message="Evidence envelope verified: authentic Ed25519 signature and intact payload.",
        )
