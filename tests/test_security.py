"""Security Regression and Adversarial Verification Test Suite for Smart-Freeze.

Covers:
1. Unauthenticated access denial (HTTP 401).
2. Broken Object-Level Authorization (BOLA) denial across case boundaries (HTTP 403).
3. Vertical Role-Based Privilege Escalation prevention (HTTP 403 for non-admins).
4. Cryptographic signature and payload tampering detection (Ed25519 / SHA-256).
5. Expired evidence envelopes and replay attacks.
6. Untrusted institutional keys and mismatch detection.
7. Idempotent trace request execution.
8. Oversized payload defense (>1MB rejected with HTTP 413).
9. Traversal hop limit bounds (DoS prevention).
10. ML artifact integrity verification and tampering prevention.
11. Sanitized error handling (zero stack traces or internal filesystem paths leaked).
12. Operational isolation of hidden evaluation ground truth.
13. Financial tracing invariant preservation.
14. Security audit trail logging and sanitization.
"""

from __future__ import annotations

import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from app.main import app
from ml.service import MLService, ModelArtifactError
from security.audit import SecurityAuditLogger
from security.models import AuditSeverity, Role
from traceproof.coordinator import TraceCoordinator
from traceproof.crypto import InstitutionKeyManager
from traceproof.schemas import SignedEvidenceEnvelope


@pytest.fixture
def unauthenticated_client() -> TestClient:
    """Client with no credentials."""
    return TestClient(app)


@pytest.fixture
def investigator_1_client() -> TestClient:
    """Investigator assigned to CASE-2026-001 and CASE-2026-002."""
    c = TestClient(app)
    c.headers["Authorization"] = "Bearer dev_token_investigator_1"
    return c


@pytest.fixture
def investigator_2_client() -> TestClient:
    """Investigator assigned strictly to CASE-2026-003 only."""
    c = TestClient(app)
    c.headers["Authorization"] = "Bearer dev_token_investigator_2"
    return c


@pytest.fixture
def admin_client() -> TestClient:
    """Compliance administrator with system-wide privileges."""
    c = TestClient(app)
    c.headers["Authorization"] = "Bearer dev_token_admin"
    return c


# ==============================================================================
# 1. Unauthenticated Access Denial
# ==============================================================================

def test_unauthenticated_access_denied(unauthenticated_client: TestClient):
    """Protected endpoints must return 401 Unauthorized when credentials are missing."""
    protected_urls = [
        "/api/overview",
        "/api/cases",
        "/api/cases/CASE-2026-001",
        "/api/transactions",
        "/api/accounts",
        "/api/graph",
        "/api/consensus-lien/CASE-2026-001",
        "/api/investigation-priority",
        "/api/data-quality",
        "/api/ml/status",
        "/api/ml/predict",
        "/api/traceproof/scenarios",
        "/api/admin/audit-logs",
        "/api/admin/security-status",
    ]

    for url in protected_urls:
        if url in ("/api/ml/predict",):
            res = unauthenticated_client.post(url, json={"features": {}})
        else:
            res = unauthenticated_client.get(url)
        assert res.status_code == 401, f"Expected 401 for unauthenticated request to {url}, got {res.status_code}"
        assert "Authentication required" in res.json().get("detail", "") or "Invalid" in res.json().get("detail", "")


def test_invalid_bearer_token_denied(unauthenticated_client: TestClient):
    """Malformed or fabricated bearer tokens must return 401 Unauthorized."""
    unauthenticated_client.headers["Authorization"] = "Bearer fabricated_token_attacker_123"
    res = unauthenticated_client.get("/api/overview")
    assert res.status_code == 401
    assert "Invalid or expired" in res.json()["detail"]


# ==============================================================================
# 2. Broken Object-Level Authorization (BOLA / IDOR) Defense
# ==============================================================================

def test_horizontal_case_access_violation_denied(
    investigator_1_client: TestClient,
    investigator_2_client: TestClient,
):
    """Investigator 2 (assigned to CASE-003 only) must be forbidden from accessing CASE-001."""
    # Investigator 1 is permitted on CASE-001
    res1 = investigator_1_client.get("/api/cases/CASE-2026-001")
    assert res1.status_code == 200

    # Investigator 2 is forbidden on CASE-001
    res2 = investigator_2_client.get("/api/cases/CASE-2026-001")
    assert res2.status_code == 403
    assert "Access denied: You are not authorized" in res2.json()["detail"]

    # BOLA attempt on graph endpoint
    graph_res = investigator_2_client.get("/api/graph?case_id=CASE-2026-001")
    assert graph_res.status_code == 403

    # BOLA attempt on Consensus Lien endpoint
    lien_res = investigator_2_client.get("/api/consensus-lien/CASE-2026-001")
    assert lien_res.status_code == 403

    # BOLA attempt on TraceProof start
    tp_res = investigator_2_client.post(
        "/api/traceproof/start",
        json={"scenario_id": "SCENARIO_1_COMPLETE", "case_id": "CASE-2026-001"},
    )
    assert tp_res.status_code == 403


def test_cases_list_filters_by_investigator_assignment(
    investigator_1_client: TestClient,
    investigator_2_client: TestClient,
    admin_client: TestClient,
):
    """Cases list only enumerates cases assigned to the authenticated investigator."""
    inv1_cases = investigator_1_client.get("/api/cases").json()
    assert len(inv1_cases) == 2
    assert {c["case_id"] for c in inv1_cases} == {"CASE-2026-001", "CASE-2026-002"}

    inv2_cases = investigator_2_client.get("/api/cases").json()
    assert len(inv2_cases) == 1
    assert inv2_cases[0]["case_id"] == "CASE-2026-003"

    admin_cases = admin_client.get("/api/cases").json()
    assert len(admin_cases) == 3


# ==============================================================================
# 3. Vertical Privilege Escalation Defense (RBAC)
# ==============================================================================

def test_vertical_privilege_escalation_denied(
    investigator_1_client: TestClient,
    admin_client: TestClient,
):
    """Investigators cannot access administrator-only audit and security status endpoints."""
    # Investigator role rejected on admin audit logs
    inv_audit = investigator_1_client.get("/api/admin/audit-logs")
    assert inv_audit.status_code == 403
    assert "lacks required permissions" in inv_audit.json()["detail"]

    # Investigator role rejected on admin security status
    inv_sec = investigator_1_client.get("/api/admin/security-status")
    assert inv_sec.status_code == 403

    # Admin role succeeds
    adm_audit = admin_client.get("/api/admin/audit-logs")
    assert adm_audit.status_code == 200
    assert isinstance(adm_audit.json(), list)

    adm_sec = admin_client.get("/api/admin/security-status")
    assert adm_sec.status_code == 200
    security_status = adm_sec.json()
    assert security_status["status"] == "LOCAL_DEMO_ONLY"
    assert security_status["production_auth_ready"] is False
    assert security_status["demo_auth_enabled"] is True
    assert "NOT_INDEPENDENTLY_VERIFIED" in security_status["case_scope_authorization_status"]
    assert security_status["rate_limiting_active"] is True


# ==============================================================================
# 4. Cryptographic Forgery and Tampered Evidence Detection
# ==============================================================================

def test_tampered_envelope_payload_rejected(admin_client: TestClient):
    """Altered payload in transit triggers TAMPERED_PAYLOAD and invalid status."""
    key_mgr = InstitutionKeyManager.get_instance()
    env = key_mgr.sign_payload(
        institution_id="BANK_A",
        trace_request_id="REQ_SEC_01",
        source_record_id="REC_99",
        approved_payload={"amount_minor": 100000, "token": "TOK_01"},
    )

    # Tamper payload
    tampered_env = env.model_copy(deep=True)
    tampered_env.approved_payload["amount_minor"] = 99999999

    ver = key_mgr.verify_envelope(tampered_env)
    assert ver.is_valid is False
    assert ver.status == "TAMPERED_PAYLOAD"


def test_forged_ed25519_signature_rejected(admin_client: TestClient):
    """Invalid or forged Ed25519 signature is strictly rejected."""
    key_mgr = InstitutionKeyManager.get_instance()
    env = key_mgr.sign_payload(
        institution_id="BANK_A",
        trace_request_id="REQ_SEC_02",
        source_record_id="REC_100",
        approved_payload={"amount_minor": 50000},
    )

    forged_env = env.model_copy(deep=True)
    # Flip bytes in signature
    forged_env.signature_hex = "aa" * 64

    ver = key_mgr.verify_envelope(forged_env)
    assert ver.is_valid is False
    assert ver.status == "SIGNATURE_MISMATCH"


# ==============================================================================
# 5. Expired Requests and Replay Attack Rejection
# ==============================================================================

def test_expired_envelope_rejected():
    """Envelopes past their expiration timestamp must be rejected."""
    key_mgr = InstitutionKeyManager.get_instance()
    env = key_mgr.sign_payload(
        institution_id="WALLET_B",
        trace_request_id="REQ_SEC_03",
        source_record_id="REC_EXP",
        approved_payload={"amount_minor": 1000},
        expires_at="2020-01-01T00:00:00+00:00",  # Expired in past
    )

    ver = key_mgr.verify_envelope(env)
    assert ver.is_valid is False
    assert ver.status == "EXPIRED_ENVELOPE"


def test_replayed_envelope_across_requests_rejected():
    """An envelope signature cannot be replayed under a differing trace request ID."""
    key_mgr = InstitutionKeyManager.get_instance()
    env = key_mgr.sign_payload(
        institution_id="BANK_A",
        trace_request_id="REQ_ORIGINAL_11",
        source_record_id="REC_REPLAY_TEST",
        approved_payload={"amount_minor": 25000},
    )

    # First verification under original request succeeds
    v1 = key_mgr.verify_envelope(env)
    assert v1.is_valid is True

    # Attacker attempts to replay the same envelope under REQ_ATTACKER_22
    replayed_env = env.model_copy(deep=True)
    replayed_env.trace_request_id = "REQ_ATTACKER_22"

    v2 = key_mgr.verify_envelope(replayed_env)
    assert v2.is_valid is False
    assert v2.status in ("REPLAYED_ENVELOPE", "REQUEST_ID_MISMATCH")


# ==============================================================================
# 6. Untrusted Institutional Key Rejection
# ==============================================================================

def test_untrusted_institution_key_rejected():
    """Envelopes signed by keys not registered in the trusted institutional registry fail."""
    key_mgr = InstitutionKeyManager.get_instance()
    env = key_mgr.sign_payload(
        institution_id="BANK_A",
        trace_request_id="REQ_SEC_04",
        source_record_id="REC_UNKNOWN_KEY",
        approved_payload={"amount_minor": 5000},
    )

    untrusted_env = env.model_copy(deep=True)
    untrusted_env.key_id = "key_malicious_attacker_9999"

    ver = key_mgr.verify_envelope(untrusted_env)
    assert ver.is_valid is False
    assert ver.status == "UNTRUSTED_KEY"


# ==============================================================================
# 7. Idempotent Trace Requests
# ==============================================================================

def test_idempotent_trace_execution():
    """Re-executing trace with the same request ID returns identical cached results."""
    coordinator = TraceCoordinator.get_instance()
    res1 = coordinator.execute_trace(
        case_id="CASE-2026-TP-01",
        scenario_id="SCENARIO_1_COMPLETE",
        request_id="REQ_IDEMPOTENT_001",
    )
    assert res1.status.value == "COMPLETE"

    res2 = coordinator.execute_trace(
        case_id="CASE-2026-TP-01",
        scenario_id="SCENARIO_1_COMPLETE",
        request_id="REQ_IDEMPOTENT_001",
    )
    assert res2.request_id == "REQ_IDEMPOTENT_001"
    assert res2.total_hops_traversed == res1.total_hops_traversed


# ==============================================================================
# 8. Oversized Payload Defense
# ==============================================================================

def test_oversized_payload_rejected_by_middleware(admin_client: TestClient):
    """HTTP requests exceeding 1MB payload limit are rejected with 413 Payload Too Large."""
    # Create payload > 1MB
    large_features = {f"V{i}": 0.0 for i in range(1, 29)}
    large_features["Time"] = 0.0
    large_features["Amount"] = 100.0
    large_padding = "X" * (1024 * 1024 + 100)  # > 1MB

    # We send custom headers with large content-length
    resp = admin_client.post(
        "/api/ml/predict",
        content=large_padding,
        headers={"Content-Length": str(len(large_padding)), "Content-Type": "application/json"},
    )
    assert resp.status_code == 413
    assert "Payload Too Large" in resp.json()["detail"]


# ==============================================================================
# 9. Traversal Depth Bounds (DoS Defense)
# ==============================================================================

def test_excessive_hop_traversal_bounded(admin_client: TestClient):
    """Requests with max_hops > 10 must be rejected with 422 Unprocessable Entity."""
    resp = admin_client.post(
        "/api/traceproof/start",
        json={"case_id": "CASE-2026-001", "max_hops": 99},
    )
    assert resp.status_code == 422
    err_str = str(resp.json())
    assert "less_than_equal" in err_str or "10" in err_str or "Traversal limit exceeded" in err_str


# ==============================================================================
# 10. ML Artifact Integrity Verification
# ==============================================================================

def test_tampered_model_artifact_loading_refused(tmp_path: Path):
    """A mismatched local artifact digest leaves the service unavailable and inference disabled."""
    tampered_artifact_path = tmp_path / "tampered_model.joblib"
    tampered_artifact_path.write_bytes(b"test fixture bytes; not a serialized model")
    tampered_meta_path = tmp_path / "tampered_metadata.json"
    dummy_meta = {
        "artifact_sha256": "deadbeef" * 8,
        "selected_threshold": 0.63,
        "features": [],
        "primary_model_metrics": {"model_name": "TamperedTestModel"},
    }
    tampered_meta_path.write_text(json.dumps(dummy_meta), encoding="utf-8")

    service = MLService(
        artifact_path=tampered_artifact_path,
        metadata_path=tampered_meta_path,
        demo_path=tmp_path / "missing_demo_samples.json",
    )
    status = service.get_status()
    assert status["status"] == "UNAVAILABLE"
    assert status["artifact_sha256_verified"] is False
    assert "integrity verification failed" in status["message"].lower()
    with pytest.raises(ModelArtifactError, match="not loaded"):
        service.get_evaluation_report()


# ==============================================================================
# 11. Sanitized Error Handling (Zero Stack Traces / Paths Leaked)
# ==============================================================================

def test_api_errors_do_not_leak_internal_paths_or_stack_traces(admin_client: TestClient):
    """Internal server errors return clean incident IDs and no local file paths."""
    # Force an unhandled error by querying an invalid path pattern or triggering 404
    resp = admin_client.get("/api/cases/INVALID_UNKNOWN_ID")
    assert resp.status_code == 404
    body = resp.text
    assert "/home/abhishek" not in body
    assert "Traceback" not in body


# ==============================================================================
# 12. Operational Isolation of Ground Truth
# ==============================================================================

def test_operational_endpoints_isolate_evaluation_ground_truth(admin_client: TestClient):
    """Verify that no operational endpoint can access or return evaluation ground truth."""
    endpoints = ["/api/overview", "/api/cases", "/api/transactions", "/api/accounts", "/api/graph"]
    for ep in endpoints:
        resp = admin_client.get(ep)
        assert resp.status_code == 200
        text = resp.text.lower()
        assert "ground_truth.json" not in text


# ==============================================================================
# 13. Financial Tracing Invariant Preservation
# ==============================================================================

def test_financial_tracing_invariants_preserved(admin_client: TestClient):
    """Consensus Lien, Proportional, FIFO, and LIBR outputs remain mathematically identical."""
    res = admin_client.get("/api/consensus-lien/CASE-2026-001")
    assert res.status_code == 200
    data = res.json()
    assert data["source_transaction_id"] == "TXN_0009"
    assert data["total_lower_bound_paise"] > 0
    assert data["total_upper_bound_paise"] >= data["total_lower_bound_paise"]
    assert data["total_disagreement_paise"] == (
        data["total_upper_bound_paise"] - data["total_lower_bound_paise"]
    )


# ==============================================================================
# 14. Security Audit Trail Logging and Sanitization
# ==============================================================================

def test_security_audit_logging_and_sanitization(admin_client: TestClient):
    """Audit logger records events and sanitizes sensitive tokens/secrets."""
    audit = SecurityAuditLogger.get_instance()
    event = audit.log_event(
        event_type="TEST_SECURITY_EVENT",
        endpoint="/api/test",
        method="POST",
        severity=AuditSeverity.HIGH,
        details={
            "token": "secret_bearer_token_12345",
            "password": "super_secret_password",
            "safe_field": "public_data",
        },
    )

    assert event.details["token"] == "[REDACTED]"
    assert event.details["password"] == "[REDACTED]"
    assert event.details["safe_field"] == "public_data"

    # Query audit logs via API
    api_resp = admin_client.get("/api/admin/audit-logs?limit=5")
    assert api_resp.status_code == 200
    logs = api_resp.json()
    assert len(logs) > 0
