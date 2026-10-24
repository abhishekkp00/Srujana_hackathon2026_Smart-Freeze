"""Comprehensive automated and adversarial tests for TraceProof multi-rail evidence reconstruction."""

import json
import pytest
from fastapi.testclient import TestClient

from app.main import app
from traceproof.coordinator import TraceCoordinator
from traceproof.crypto import InstitutionKeyManager, compute_payload_hash
from traceproof.schemas import (
    FinancialEventType,
    LinkClassification,
    TraceStatus,
    StartTraceRequest,
)


@pytest.fixture
def client() -> TestClient:
    c = TestClient(app)
    c.headers["Authorization"] = "Bearer dev_token_admin"
    return c


@pytest.fixture
def coordinator() -> TraceCoordinator:
    return TraceCoordinator.get_instance()


@pytest.fixture
def key_manager() -> InstitutionKeyManager:
    return InstitutionKeyManager.get_instance()


def test_ed25519_signature_and_verification(key_manager: InstitutionKeyManager):
    """Verify Ed25519 signing and verification across synthetic institutions."""
    payload = {
        "event_id": "EVT_TEST_001",
        "amount_minor": 500000,
        "currency": "INR",
        "sender_token": "TOK_A",
        "recipient_token": "TOK_B",
    }
    env = key_manager.sign_payload(
        institution_id="BANK_A",
        trace_request_id="REQ_TEST_01",
        source_record_id="REC_01",
        approved_payload=payload,
    )
    assert env.institution_id == "BANK_A"
    assert len(env.signature_hex) == 128  # 64-byte Ed25519 hex
    assert len(env.payload_sha256) == 64   # 32-byte SHA-256 hex

    # Verify envelope
    ver = key_manager.verify_envelope(env)
    assert ver.is_valid is True
    assert ver.status == "VALID"


def test_adversarial_tampered_payload_rejected(key_manager: InstitutionKeyManager):
    """Verify that altering approved_payload without re-signing fails verification."""
    payload = {
        "event_id": "EVT_TEST_002",
        "amount_minor": 1000000,
        "currency": "INR",
        "sender_token": "TOK_A",
        "recipient_token": "TOK_B",
    }
    env = key_manager.sign_payload(
        institution_id="WALLET_B",
        trace_request_id="REQ_TEST_02",
        source_record_id="REC_02",
        approved_payload=payload,
    )

    # Adversary alters amount from 1,000,000 to 9,000,000 paise
    tampered_env = env.model_copy(deep=True)
    tampered_env.approved_payload["amount_minor"] = 9000000

    ver = key_manager.verify_envelope(tampered_env)
    assert ver.is_valid is False
    assert ver.status == "TAMPERED_PAYLOAD"


def test_adversarial_invalid_signature_rejected(key_manager: InstitutionKeyManager):
    """Verify corrupted signature bits are rejected."""
    payload = {"event_id": "EVT_TEST_003", "amount_minor": 50000}
    env = key_manager.sign_payload(
        institution_id="BANK_C",
        trace_request_id="REQ_TEST_03",
        source_record_id="REC_03",
        approved_payload=payload,
    )

    corrupted_env = env.model_copy(deep=True)
    # Corrupt last characters of hex signature
    corrupted_env.signature_hex = corrupted_env.signature_hex[:-4] + "dead"

    ver = key_manager.verify_envelope(corrupted_env)
    assert ver.is_valid is False
    assert ver.status == "SIGNATURE_MISMATCH"


def test_scenario_1_complete_trace(coordinator: TraceCoordinator):
    """Verify Scenario 1: Complete multi-rail trace from Bank A through Wallet B to Bank C."""
    res = coordinator.execute_trace(case_id="CASE-2026-TP-01", scenario_id="SCENARIO_1_COMPLETE")
    assert res.status == TraceStatus.COMPLETE
    assert res.confirmed_links_count > 0
    assert res.unresolved_links_count == 0
    assert len(res.envelopes) >= 4
    # All verification results must be valid
    assert all(v.is_valid for v in res.verification_results)
    assert res.evidence_bounded_range is not None


def test_scenario_2_unresolved_settlement_gap_never_invented(coordinator: TraceCoordinator):
    """Verify Scenario 2: Missing counterparty link remains visibly UNRESOLVED and never fabricated."""
    res = coordinator.execute_trace(case_id="CASE-2026-TP-02", scenario_id="SCENARIO_2_UNRESOLVED_GAP")
    assert res.status == TraceStatus.PARTIAL
    assert res.unresolved_links_count >= 1

    # Check for the explicit unresolved edge
    unresolved_edges = [e for e in res.edges if e.link_status == LinkClassification.UNRESOLVED]
    assert len(unresolved_edges) == 1
    assert "UNRESOLVED" in unresolved_edges[0].id or unresolved_edges[0].link_status == LinkClassification.UNRESOLVED
    assert len(res.unresolved_explanations) >= 1
    assert "never fabricated" in res.unresolved_explanations[0]


def test_scenario_3_fee_and_refund_handling(coordinator: TraceCoordinator):
    """Verify Scenario 3: Platform fee and partial refund reversal are properly tracked."""
    res = coordinator.execute_trace(case_id="CASE-2026-TP-03", scenario_id="SCENARIO_3_POOLED_SETTLEMENT_FEE_REFUND")
    assert res.status == TraceStatus.COMPLETE
    event_types = {e.event_type for e in res.edges}
    assert FinancialEventType.FEE in event_types
    assert FinancialEventType.MERCHANT_PAYMENT in event_types
    assert FinancialEventType.CASH_WITHDRAWAL in event_types


def test_scenario_4_adversarial_tampered_envelope(coordinator: TraceCoordinator):
    """Verify Scenario 4: Tampered envelope halts branch and marks status INVALID_EVIDENCE."""
    res = coordinator.execute_trace(case_id="CASE-2026-TP-04", scenario_id="SCENARIO_4_ADVERSARIAL_TAMPERED")
    assert res.status == TraceStatus.INVALID_EVIDENCE
    assert any(not v.is_valid for v in res.verification_results)
    assert "CRITICAL ALERT" in res.narrative_summary


def test_api_traceproof_scenarios(client: TestClient):
    """Verify GET /api/traceproof/scenarios endpoint."""
    resp = client.get("/api/traceproof/scenarios")
    assert resp.status_code == 200
    scenarios = resp.json()
    assert len(scenarios) == 4
    ids = {s["scenario_id"] for s in scenarios}
    assert "SCENARIO_1_COMPLETE" in ids
    assert "SCENARIO_2_UNRESOLVED_GAP" in ids


def test_api_traceproof_start_and_get(client: TestClient):
    """Verify POST /api/traceproof/start and GET /api/traceproof/requests/{id}."""
    start_resp = client.post(
        "/api/traceproof/start",
        json={"scenario_id": "SCENARIO_1_COMPLETE", "case_id": "CASE-2026-TP-01"},
    )
    assert start_resp.status_code == 200
    trace = start_resp.json()
    assert trace["status"] == "COMPLETE"
    req_id = trace["request_id"]

    # Retrieve by ID
    get_resp = client.get(f"/api/traceproof/requests/{req_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["request_id"] == req_id


def test_api_traceproof_verify_envelope(client: TestClient, key_manager: InstitutionKeyManager):
    """Verify POST /api/traceproof/verify-envelope standalone verification endpoint."""
    payload = {"event_id": "EVT_TEST_API", "amount_minor": 250000}
    env = key_manager.sign_payload("BANK_A", "REQ_API", "REC_API", payload)

    resp = client.post("/api/traceproof/verify-envelope", json={"envelope": env.model_dump()})
    assert resp.status_code == 200
    res = resp.json()
    assert res["is_valid"] is True
    assert res["status"] == "VALID"


def test_preservation_of_ml_and_financial_tracing(client: TestClient):
    """Verify running TraceProof does not modify existing ML or Consensus Lien calculations."""
    # 1. Consensus Lien check
    lien_before = client.get("/api/consensus-lien/CASE-2026-001").json()

    # 2. ML status check
    ml_status_before = client.get("/api/ml/status").json()

    # 3. Run all TraceProof scenarios
    for sc in ["SCENARIO_1_COMPLETE", "SCENARIO_2_UNRESOLVED_GAP", "SCENARIO_4_ADVERSARIAL_TAMPERED"]:
        client.post("/api/traceproof/start", json={"scenario_id": sc, "case_id": "CASE-TEST"})

    # 4. Verify Consensus Lien unchanged
    lien_after = client.get("/api/consensus-lien/CASE-2026-001").json()
    assert lien_before["total_lower_bound_paise"] == lien_after["total_lower_bound_paise"]
    assert lien_before["total_upper_bound_paise"] == lien_after["total_upper_bound_paise"]

    # 5. Verify ML status unchanged
    ml_status_after = client.get("/api/ml/status").json()
    assert ml_status_before["status"] == ml_status_after["status"]
    assert ml_status_before["model_version"] == ml_status_after["model_version"]
