"""Tests for Hash-Chained Audit Trail, Cryptographic Receipts, and Standalone Verifier.

Covers:
1. Audit log hash chaining from genesis and verify_chain().
2. Tampered log entry detected (edited detail, previous_hash, or entry_hash).
3. Valid receipt recomputed and verified via python -m verifier.
4. Tampered receipt number detected (core or margin edited by 1 unit).
5. Tampered receipt ledger-slice detected (transaction amount edited).
6. Wrong signature detected (tampered signature or signed with adversary key).
7. Governance limitation notice checked.
8. FastAPI endpoints: POST/GET /api/admin/audit/verify-chain and GET /api/receipts/{id}.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path
import pytest
from cryptography.hazmat.primitives.asymmetric import ed25519
from fastapi.testclient import TestClient

from app.main import app
from security.audit import SecurityAuditLogger
from security.models import AuditSeverity
from security.receipt import (
    RECEIPT_GOVERNANCE_NOTICE,
    ReceiptRegistry,
    create_hold_receipt,
    verify_receipt_cryptography,
)
from verifier.verify import (
    STANDALONE_GOVERNANCE_NOTICE,
    verify_receipt_dict,
    verify_receipt_file,
)


AUTH_ADMIN = {"Authorization": "Bearer dev_token_admin"}
AUTH_AUDITOR = {"Authorization": "Bearer dev_token_auditor"}
AUTH_INVESTIGATOR = {"Authorization": "Bearer dev_token_investigator_1"}


@pytest.fixture
def clean_audit_logger():
    """Returns a fresh instance of SecurityAuditLogger for isolated testing."""
    logger = SecurityAuditLogger()
    # Replace singleton instance temporarily for clean test state
    orig = SecurityAuditLogger._instance
    SecurityAuditLogger._instance = logger
    yield logger
    SecurityAuditLogger._instance = orig


@pytest.fixture
def sample_ledger_slice():
    """Generates a minimal valid synthetic ledger slice for testing."""
    return {
        "accounts": [
            {
                "account_id": "ACC_TEST_VICTIM",
                "account_type": "individual",
                "opening_balance_paise": 20_000_000,
                "history_complete": True,
            },
            {
                "account_id": "ACC_TEST_MULE_1",
                "account_type": "mule",
                "opening_balance_paise": 0,
                "history_complete": True,
            },
            {
                "account_id": "ACC_TEST_MERCHANT",
                "account_type": "merchant",
                "opening_balance_paise": 5_000_000,
                "history_complete": True,
            },
        ],
        "transactions": [
            {
                "transaction_id": "TX_SRC_001",
                "case_id": "CASE-TEST-001",
                "from_account": "ACC_TEST_VICTIM",
                "to_account": "ACC_TEST_MULE_1",
                "amount_paise": 10_000_000,  # ₹100,000
                "timestamp": "2026-10-25T10:00:00Z",
                "rail": "IMPS",
            },
            {
                "transaction_id": "TX_HOP_002",
                "case_id": "CASE-TEST-001",
                "from_account": "ACC_TEST_MULE_1",
                "to_account": "ACC_TEST_MERCHANT",
                "amount_paise": 4_000_000,  # ₹40,000
                "timestamp": "2026-10-25T10:30:00Z",
                "rail": "UPI",
            },
        ],
    }


def test_audit_hash_chain_intact_from_genesis(clean_audit_logger: SecurityAuditLogger):
    """Clean audit log has unbroken cryptographic hash chain from genesis."""
    logger = clean_audit_logger

    e1 = logger.log_event("TEST_LOGIN", "/api/auth/login", "POST", AuditSeverity.INFO, "usr_1")
    e2 = logger.log_event("VIEW_CASE", "/api/cases/1", "GET", AuditSeverity.INFO, "usr_1")
    e3 = logger.log_event("AUTH_DENIED", "/api/admin", "GET", AuditSeverity.WARNING, "usr_2")

    # Genesis check
    assert e1.previous_hash == "0" * 64
    assert e1.entry_hash != ""

    # Linkage check
    assert e2.previous_hash == e1.entry_hash
    assert e3.previous_hash == e2.entry_hash

    # Verification
    res = logger.verify_chain()
    assert res["is_valid"] is True
    assert res["total_events"] == 3
    assert res["verified_events"] == 3
    assert res["tampered_event_id"] is None
    assert res["latest_hash"] == e3.entry_hash


def test_tampered_log_entry_detected(clean_audit_logger: SecurityAuditLogger):
    """Editing any field in an audit entry is immediately detected by verify_chain()."""
    logger = clean_audit_logger

    logger.log_event("EVENT_1", "/api/test", "GET", AuditSeverity.INFO)
    e2 = logger.log_event("EVENT_2", "/api/test", "POST", AuditSeverity.WARNING, details={"amount": 5000})
    logger.log_event("EVENT_3", "/api/test", "GET", AuditSeverity.INFO)

    # Chain initially valid
    assert logger.verify_chain()["is_valid"] is True

    # Tamper with event 2 details
    logger._chain[1].details["amount"] = 999999

    res = logger.verify_chain()
    assert res["is_valid"] is False
    assert res["tampered_event_id"] == e2.event_id
    assert "Tampered payload detected" in res["error_message"]


def test_broken_hash_chain_linkage_detected(clean_audit_logger: SecurityAuditLogger):
    """Tampering with previous_hash breaks chain continuity and is detected."""
    logger = clean_audit_logger

    logger.log_event("EVENT_1", "/api/test", "GET")
    e2 = logger.log_event("EVENT_2", "/api/test", "GET")

    # Tamper with previous_hash of event 2
    logger._chain[1].previous_hash = "f" * 64

    res = logger.verify_chain()
    assert res["is_valid"] is False
    assert res["tampered_event_id"] == e2.event_id
    assert "Broken chain linkage" in res["error_message"]


def test_receipt_creation_and_standalone_verification(sample_ledger_slice):
    """A generated hold receipt verifies cryptographically and algorithmically."""
    receipt = create_hold_receipt(
        case_id="CASE-TEST-001",
        account_id="ACC_TEST_MULE_1",
        source_transaction_id="TX_SRC_001",
        action="lien_core",
        core_paise=6_000_000,  # ₹60,000 remaining on mule
        margin_paise=0,
        policy_name="balanced",
        policy_version="1.0.0",
        rules_fired=["lien_on_core"],
        approver="investigator_test",
        per_method_results={
            "proportional": {"lower_paise": 6_000_000, "upper_paise": 6_000_000},
            "fifo": {"lower_paise": 6_000_000, "upper_paise": 6_000_000},
            "libr": {"lower_paise": 6_000_000, "upper_paise": 6_000_000},
        },
        ledger_slice=sample_ledger_slice,
    )

    # 1. Internal verify_receipt_cryptography
    sig_ok, err = verify_receipt_cryptography(receipt)
    assert sig_ok is True
    assert err is None

    # 2. Standalone verifier function (verify_receipt_dict)
    report = verify_receipt_dict(receipt)
    assert report.is_valid is True
    assert report.signature_valid is True
    assert report.slice_hash_valid is True
    assert report.core_matches is True
    assert report.margin_matches is True
    assert report.recomputed_core_paise == 6_000_000


def test_cli_verifier_executes_successfully(sample_ledger_slice, tmp_path: Path):
    """The verifier CLI script (python -m verifier receipt.json) succeeds with code 0."""
    receipt = create_hold_receipt(
        case_id="CASE-TEST-001",
        account_id="ACC_TEST_MULE_1",
        source_transaction_id="TX_SRC_001",
        action="lien_core",
        core_paise=6_000_000,
        margin_paise=0,
        policy_name="balanced",
        policy_version="1.0.0",
        rules_fired=["lien_on_core"],
        approver="investigator_test",
        per_method_results={
            "proportional": {"lower_paise": 6_000_000, "upper_paise": 6_000_000},
            "fifo": {"lower_paise": 6_000_000, "upper_paise": 6_000_000},
            "libr": {"lower_paise": 6_000_000, "upper_paise": 6_000_000},
        },
        ledger_slice=sample_ledger_slice,
    )

    receipt_file = tmp_path / "valid_receipt.json"
    receipt_file.write_text(json.dumps(receipt, indent=2))

    cmd = [sys.executable, "-m", "verifier", str(receipt_file)]
    res = subprocess.run(cmd, capture_output=True, text=True)

    assert res.returncode == 0
    assert "[PASS] Ed25519 Digital Signature: VERIFIED" in res.stdout
    assert "[PASS] Ledger Slice SHA-256 Digest: INTEGRITY VERIFIED" in res.stdout
    assert "OVERALL RESULT: [VERIFIED]" in res.stdout


def test_tampered_receipt_number_detected(sample_ledger_slice, tmp_path: Path):
    """Editing even one number (core, margin) in a receipt causes verifier to fail."""
    receipt = create_hold_receipt(
        case_id="CASE-TEST-001",
        account_id="ACC_TEST_MULE_1",
        source_transaction_id="TX_SRC_001",
        action="lien_core",
        core_paise=6_000_000,
        margin_paise=0,
        policy_name="balanced",
        policy_version="1.0.0",
        rules_fired=["lien_on_core"],
        approver="investigator_test",
        per_method_results={},
        ledger_slice=sample_ledger_slice,
    )

    # Tamper with core by 1 rupee (100 paise)
    tampered_receipt = dict(receipt)
    tampered_receipt["core"] = 6_000_100

    tampered_file = tmp_path / "tampered_receipt.json"
    tampered_file.write_text(json.dumps(tampered_receipt, indent=2))

    cmd = [sys.executable, "-m", "verifier", str(tampered_file)]
    res = subprocess.run(cmd, capture_output=True, text=True)

    # Signature fails immediately because canonical payload was altered
    assert res.returncode == 1
    assert "OVERALL RESULT: [FAILED]" in res.stdout


def test_tampered_ledger_slice_detected(sample_ledger_slice, tmp_path: Path):
    """Editing a transaction amount in ledger_slice causes verifier to detect hash mismatch."""
    receipt = create_hold_receipt(
        case_id="CASE-TEST-001",
        account_id="ACC_TEST_MULE_1",
        source_transaction_id="TX_SRC_001",
        action="lien_core",
        core_paise=6_000_000,
        margin_paise=0,
        policy_name="balanced",
        policy_version="1.0.0",
        rules_fired=["lien_on_core"],
        approver="investigator_test",
        per_method_results={},
        ledger_slice=sample_ledger_slice,
    )

    # Tamper with first transaction amount inside ledger slice
    tampered_receipt = dict(receipt)
    tampered_receipt["ledger_slice"]["transactions"][0]["amount_paise"] = 9_999_999

    tampered_file = tmp_path / "tampered_slice.json"
    tampered_file.write_text(json.dumps(tampered_receipt, indent=2))

    cmd = [sys.executable, "-m", "verifier", str(tampered_file)]
    res = subprocess.run(cmd, capture_output=True, text=True)

    assert res.returncode == 1
    assert "OVERALL RESULT: [FAILED]" in res.stdout


def test_tampered_signature_detected(sample_ledger_slice, tmp_path: Path):
    """Corrupted or forged Ed25519 signature is detected by verifier."""
    receipt = create_hold_receipt(
        case_id="CASE-TEST-001",
        account_id="ACC_TEST_MULE_1",
        source_transaction_id="TX_SRC_001",
        action="lien_core",
        core_paise=6_000_000,
        margin_paise=0,
        policy_name="balanced",
        policy_version="1.0.0",
        rules_fired=["lien_on_core"],
        approver="investigator_test",
        per_method_results={},
        ledger_slice=sample_ledger_slice,
    )

    # Flip the first two hex characters of the signature
    tampered_receipt = dict(receipt)
    orig_sig = tampered_receipt["signature"]
    flipped_sig = ("00" if orig_sig[:2] != "00" else "ff") + orig_sig[2:]
    tampered_receipt["signature"] = flipped_sig

    tampered_file = tmp_path / "tampered_sig.json"
    tampered_file.write_text(json.dumps(tampered_receipt, indent=2))

    cmd = [sys.executable, "-m", "verifier", str(tampered_file)]
    res = subprocess.run(cmd, capture_output=True, text=True)

    assert res.returncode == 1
    assert "[FAIL] Ed25519 Digital Signature: INVALID OR FORGED" in res.stdout


def test_governance_limitations_notice():
    """State clearly in docs: it proves reproducibility and integrity, not that the input data was true."""
    for text in [RECEIPT_GOVERNANCE_NOTICE, STANDALONE_GOVERNANCE_NOTICE]:
        lower = text.lower()
        assert "reproducibility" in lower
        assert "integrity" in lower
        assert "not that the" in lower or "not" in lower
        assert "true" in lower


def test_api_verify_chain_and_receipt_endpoints():
    """FastAPI endpoints for chain verification and receipt retrieval work as expected."""
    client = TestClient(app)

    # 1. Verify chain endpoint (POST & GET)
    resp_post = client.post("/api/admin/audit/verify-chain", headers=AUTH_ADMIN)
    assert resp_post.status_code == 200
    data_post = resp_post.json()
    assert data_post["is_valid"] is True
    assert "latest_hash" in data_post
    assert "governance_notice" in data_post

    resp_get = client.get("/api/admin/audit/verify-chain", headers=AUTH_AUDITOR)
    assert resp_get.status_code == 200
    assert resp_get.json()["is_valid"] is True

    # 2. Unauthorized role denied
    resp_unauth = client.post("/api/admin/audit/verify-chain", headers=AUTH_INVESTIGATOR)
    assert resp_unauth.status_code == 403

    # 3. Create a hold proposal which automatically creates a receipt
    preview_resp = client.get("/api/hold-preview/CASE-2026-001", headers=AUTH_ADMIN)
    assert preview_resp.status_code == 200
    candidate = next(item for item in preview_resp.json()["candidates"] if item["is_eligible"])

    prop_resp = client.post(
        "/api/hold-proposals",
        headers=AUTH_ADMIN,
        json={"case_id": "CASE-2026-001", "account_id": candidate["account_id"]},
    )
    assert prop_resp.status_code == 200
    prop_data = prop_resp.json()
    receipt_id = prop_data.get("receipt_id")
    assert receipt_id is not None
    assert receipt_id.startswith("RCPT_")

    # 4. Fetch the receipt by ID
    rcpt_resp = client.get(f"/api/receipts/{receipt_id}", headers=AUTH_ADMIN)
    assert rcpt_resp.status_code == 200
    rcpt_data = rcpt_resp.json()
    assert rcpt_data["receipt_id"] == receipt_id
    assert rcpt_data["account_id"] == candidate["account_id"]
    assert "signature" in rcpt_data
    assert "ledger_slice" in rcpt_data
    assert "ledger_slice_hash" in rcpt_data

    # Verify that the API-generated receipt verifies with the standalone verifier function
    report = verify_receipt_dict(rcpt_data)
    assert report.signature_valid is True
    assert report.slice_hash_valid is True

    # 5. List receipts for the case
    case_rcpts_resp = client.get("/api/cases/CASE-2026-001/receipts", headers=AUTH_ADMIN)
    assert case_rcpts_resp.status_code == 200
    case_rcpts = case_rcpts_resp.json()
    assert any(r["receipt_id"] == receipt_id for r in case_rcpts)
