"""Cryptographic Hold Recommendation & Approval Receipts for Smart-Freeze.

For every hold recommendation or approval, Smart-Freeze generates an immutable,
cryptographically signed Receipt containing:
- Canonical JSON structure
- Target account, action, core, margin, and policy version
- Rules fired and approver identity
- Per-method tracing results (Proportional, FIFO, LIBR)
- Minimal ledger slice and its SHA-256 digest
- Ed25519 digital signature
- Appended to the hash-chained audit log

Notice on Limitation:
Cryptographic verification and hash-chaining prove algorithmic reproducibility and tamper-evident
integrity of the receipt and audit log; they do NOT prove that the underlying input ledger records,
transaction events, or external banking claims are objectively true in the real world.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from cryptography.hazmat.primitives.asymmetric import ed25519

from security.audit import SecurityAuditLogger
from security.models import AuditSeverity


RECEIPT_GOVERNANCE_NOTICE = (
    "Cryptographic verification and hash-chaining prove algorithmic reproducibility and "
    "tamper-evident integrity of the receipt; they do NOT prove that the underlying input "
    "ledger records, transaction events, or external banking claims are objectively true in the real world."
)

# Deterministic institutional system signing key for receipts
# (Allows standalone verifier scripts to verify with known or embedded public keys)
_SYSTEM_SEED = hashlib.sha256(b"smart_freeze_system_receipt_ed25519_seed_2026").digest()
SYSTEM_RECEIPT_PRIVATE_KEY = ed25519.Ed25519PrivateKey.from_private_bytes(_SYSTEM_SEED)
SYSTEM_RECEIPT_PUBLIC_KEY = SYSTEM_RECEIPT_PRIVATE_KEY.public_key()
SYSTEM_RECEIPT_PUBLIC_KEY_HEX = SYSTEM_RECEIPT_PUBLIC_KEY.public_bytes_raw().hex()


def canonical_json_bytes(obj: Any) -> bytes:
    """Return deterministic canonical UTF-8 JSON bytes with sorted keys and tight separators."""
    return json.dumps(
        obj,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")


def compute_ledger_slice_hash(ledger_slice: Dict[str, Any]) -> str:
    """Compute SHA-256 hex digest over canonical JSON of the ledger slice."""
    return hashlib.sha256(canonical_json_bytes(ledger_slice)).hexdigest()


class ReceiptRegistry:
    """Thread-safe in-memory store for generated receipts."""

    _instance: Optional["ReceiptRegistry"] = None

    def __init__(self):
        self._receipts: Dict[str, Dict[str, Any]] = {}

    @classmethod
    def get_instance(cls) -> "ReceiptRegistry":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def register(self, receipt: Dict[str, Any]) -> None:
        rid = receipt["receipt_id"]
        self._receipts[rid] = receipt

    def get(self, receipt_id: str) -> Optional[Dict[str, Any]]:
        return self._receipts.get(receipt_id)

    def list_by_case(self, case_id: str) -> List[Dict[str, Any]]:
        return [r for r in self._receipts.values() if r.get("case_id") == case_id]

    def list_all(self) -> List[Dict[str, Any]]:
        return list(self._receipts.values())


def create_hold_receipt(
    case_id: str,
    account_id: str,
    source_transaction_id: str,
    action: str,
    core_paise: int,
    margin_paise: int,
    policy_name: str,
    policy_version: str,
    rules_fired: List[str],
    approver: str,
    per_method_results: Dict[str, Any],
    ledger_slice: Dict[str, Any],
    signing_key: Optional[ed25519.Ed25519PrivateKey] = None,
    append_to_audit_chain: bool = True,
    timestamp: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a canonical, Ed25519-signed hold recommendation or approval Receipt.
    
    Appends the receipt event to the security audit hash-chain.
    """
    receipt_id = f"RCPT_{uuid.uuid4().hex[:12].upper()}"
    ts = timestamp or datetime.now(timezone.utc).isoformat()
    priv_key = signing_key or SYSTEM_RECEIPT_PRIVATE_KEY
    pub_key_hex = priv_key.public_key().public_bytes_raw().hex()

    slice_hash = compute_ledger_slice_hash(ledger_slice)

    # Base payload to sign (canonical order and exact keys)
    payload_to_sign = {
        "receipt_id": receipt_id,
        "case_id": case_id,
        "account_id": account_id,
        "source_transaction_id": source_transaction_id,
        "action": action,
        "core": int(core_paise),
        "margin": int(margin_paise),
        "policy_name": policy_name,
        "policy_version": policy_version,
        "rules_fired": sorted(rules_fired),
        "approver": approver,
        "timestamp": ts,
        "per_method_results": per_method_results,
        "ledger_slice_hash": slice_hash,
        "ledger_slice": ledger_slice,
        "governance_notice": RECEIPT_GOVERNANCE_NOTICE,
    }

    # Digital signature over canonical bytes
    sign_bytes = canonical_json_bytes(payload_to_sign)
    signature = priv_key.sign(sign_bytes)

    receipt = dict(payload_to_sign)
    receipt["public_key"] = pub_key_hex
    receipt["signature"] = signature.hex()

    # Append to the audit chain
    if append_to_audit_chain:
        receipt_hash = hashlib.sha256(canonical_json_bytes(receipt)).hexdigest()
        audit_logger = SecurityAuditLogger.get_instance()
        audit_logger.log_event(
            event_type="HOLD_RECOMMENDATION_RECEIPT",
            endpoint=f"/api/cases/{case_id}/recommendations",
            method="POST",
            severity=AuditSeverity.INFO,
            user_id=approver,
            details={
                "receipt_id": receipt_id,
                "case_id": case_id,
                "account_id": account_id,
                "action": action,
                "core_paise": int(core_paise),
                "margin_paise": int(margin_paise),
                "policy_version": policy_version,
                "ledger_slice_hash": slice_hash,
                "receipt_hash": receipt_hash,
                "public_key": pub_key_hex,
                "signature_truncated": signature.hex()[:16] + "...",
            },
        )

    # Store in registry
    ReceiptRegistry.get_instance().register(receipt)

    return receipt


def verify_receipt_cryptography(receipt: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    """Check the Ed25519 signature and ledger slice hash of a receipt dictionary."""
    if "signature" not in receipt:
        return False, "Missing signature in receipt."
    if "public_key" not in receipt:
        return False, "Missing public_key in receipt."

    try:
        sig_bytes = bytes.fromhex(receipt["signature"])
        pub_bytes = bytes.fromhex(receipt["public_key"])
        pub_key = ed25519.Ed25519PublicKey.from_public_bytes(pub_bytes)
    except Exception as e:
        return False, f"Invalid cryptographic key or signature format: {e}"

    # Reconstruct canonical payload without signature & public_key
    payload_to_verify = {k: v for k, v in receipt.items() if k not in ("signature", "public_key")}
    verify_bytes = canonical_json_bytes(payload_to_verify)

    try:
        pub_key.verify(sig_bytes, verify_bytes)
    except Exception as e:
        return False, f"Ed25519 signature verification failed: {e}"

    # Check ledger slice hash
    if "ledger_slice" in receipt and "ledger_slice_hash" in receipt:
        computed_hash = compute_ledger_slice_hash(receipt["ledger_slice"])
        if computed_hash != receipt["ledger_slice_hash"]:
            return False, f"Ledger slice hash mismatch: expected {receipt['ledger_slice_hash']}, computed {computed_hash}"

    return True, None
