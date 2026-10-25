"""Unit and Integration Tests for Smart-Freeze FastAPI Application.

Tests API routes, response schemas, pagination, query filtering, Consensus Lien endpoint,
Investigation Priority endpoint, and operational ground-truth isolation.
"""

from __future__ import annotations

from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
client.headers["Authorization"] = "Bearer dev_token_admin"


def test_api_health():
    """Verify health endpoint returns status healthy."""
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "smart-freeze-api"
    assert data["version"] == app.version



def test_demo_session_uses_one_dynamic_local_investigator():
    """The application exposes one demo identity whose case scope follows the current ledger."""
    personas_response = client.get("/api/auth/personas")
    assert personas_response.status_code == 200
    personas = personas_response.json()["personas"]
    assert len(personas) == 1
    persona = personas[0]
    assert persona["display_name"] == "Local demo investigator"
    assert persona["role"] == "INVESTIGATOR"

    cases_response = client.get("/api/cases")
    assert cases_response.status_code == 200
    assert persona["assigned_case_count"] == len(cases_response.json())

    login_response = client.post("/api/auth/demo-session", json={"persona_id": persona["persona_id"]})
    assert login_response.status_code == 200
    token = login_response.json()["token"]
    demo_client = TestClient(app)
    demo_client.headers["Authorization"] = f"Bearer {token}"
    session_response = demo_client.get("/api/auth/session")
    assert session_response.status_code == 200
    assert session_response.json()["user"]["display_name"] == "Local demo investigator"
    assert session_response.json()["user"]["role"] == "INVESTIGATOR"
    assert session_response.json()["user"]["assigned_case_count"] == len(cases_response.json())


def test_api_overview():
    """Verify overview endpoint returns real operational counts and ledger validation."""
    response = client.get("/api/overview")
    assert response.status_code == 200
    data = response.json()
    assert data["accounts_analyzed"] > 0
    assert data["transactions_processed"] > 0
    assert data["cases_available"] == 3
    assert data["ledger_valid"] is True
    assert data["validation_status"] == "VERIFIED"
    assert "governance_disclaimer" in data


def test_api_cases_list():
    """Verify cases list endpoint returns all cases with loss amounts and priority bands."""
    response = client.get("/api/cases")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 3
    case_ids = {c["case_id"] for c in data}
    assert "CASE-2026-001" in case_ids
    assert "CASE-2026-002" in case_ids
    assert "CASE-2026-003" in case_ids

    for c in data:
        assert c["reported_amount_inr"] > 0
        assert c["transaction_count"] > 0
        assert c["priority_band"] in {"CRITICAL", "HIGH", "MEDIUM", "LOW"}


def test_api_case_detail_and_invalid_id():
    """Verify case detail endpoint for valid and non-existent IDs."""
    response = client.get("/api/cases/CASE-2026-001")
    assert response.status_code == 200
    data = response.json()
    assert data["case_id"] == "CASE-2026-001"
    assert len(data["transactions"]) == 5
    assert "priority_score" in data

    # Non-existent ID
    err_res = client.get("/api/cases/CASE-DOES-NOT-EXIST")
    assert err_res.status_code == 404


def test_api_transactions_pagination_and_filters():
    """Verify pagination, limit, and query filtering on transactions endpoint."""
    response = client.get("/api/transactions?limit=10&offset=0")
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 10
    assert data["total"] > 10

    # Filter by case
    case_res = client.get("/api/transactions?case_id=CASE-2026-001")
    assert case_res.status_code == 200
    case_data = case_res.json()
    assert case_data["total"] == 5
    for item in case_data["items"]:
        assert item["case_id"] == "CASE-2026-001"

    # Search filter
    search_res = client.get("/api/transactions?search=TXN_0009")
    assert search_res.status_code == 200
    search_data = search_res.json()
    assert search_data["total"] >= 1
    assert any(item["transaction_id"] == "TXN_0009" for item in search_data["items"])


def test_api_accounts_and_balance_history():
    """Verify accounts list and per-account balance history endpoints."""
    acc_res = client.get("/api/accounts")
    assert acc_res.status_code == 200
    accs = acc_res.json()
    assert len(accs) > 0

    first_acc = accs[0]["account_id"]
    hist_res = client.get(f"/api/accounts/{first_acc}/balance-history")
    assert hist_res.status_code == 200
    events = hist_res.json()
    assert isinstance(events, list)

    # Invalid account history
    err_hist = client.get("/api/accounts/ACC_INVALID_9999/balance-history")
    assert err_hist.status_code == 404


def test_api_graph_endpoint():
    """The case graph starts at a source event and includes explicitly labelled follow-on context."""
    graph_res = client.get("/api/graph?case_id=CASE-2026-001")
    assert graph_res.status_code == 200
    graph = graph_res.json()
    assert graph["total_nodes"] > 0
    assert graph["total_edges"] >= 5
    assert graph["source_transaction_id"] == "TXN_0009"
    assert graph["source_amount_inr"] == 100000.0
    assert "neither proves" in graph["flow_scope"].lower()
    for node in graph["nodes"]:
        assert "id" in node
        assert "label" in node
        assert "is_external" in node
        assert "flow_level" in node
        assert "flagged_by_case_evidence" in node
    flagged_node_ids = {node["id"] for node in graph["nodes"] if node["flagged_by_case_evidence"]}
    assert "ACC_MULE_DIRECT_01" in flagged_node_ids
    assert "ACC_COMMINGLED_01" in flagged_node_ids
    assert "ACC_VICTIM_01" not in flagged_node_ids
    source_edges = [edge for edge in graph["edges"] if edge["is_source_transaction"]]
    assert len(source_edges) == 1
    assert source_edges[0]["id"] == graph["source_transaction_id"]
    assert source_edges[0]["linkage_basis"] == "CASE_REFERENCE"
    context_credit = next(edge for edge in graph["edges"] if edge["id"] == "TXN_0014")
    assert context_credit["linkage_basis"] == "ACCOUNT_CONTEXT"
    assert context_credit["target"] == "ACC_COMMINGLED_01"
    lien_response = client.get("/api/consensus-lien/CASE-2026-001")
    assert lien_response.status_code == 200
    assert lien_response.json()["source_transaction_id"] == graph["source_transaction_id"]
    for edge in graph["edges"]:
        assert "source" in edge
        assert "target" in edge
        assert edge["amount_inr"] > 0
        assert edge["linkage_basis"] in {"CASE_REFERENCE", "CHRONOLOGICALLY_REACHABLE", "ACCOUNT_CONTEXT"}



def test_hold_preview_uses_ledger_balance_and_consensus_lower_bound():
    """A hold preview is derived from current balances and tracing output, not a fixed amount."""
    response = client.get("/api/hold-preview/CASE-2026-001")
    assert response.status_code == 200
    data = response.json()
    assert data["case_id"] == "CASE-2026-001"
    assert data["source_transaction_id"] == "TXN_0009"
    assert data["execution_status"] == "SIMULATION_ONLY_NOT_SENT_TO_BANK"
    assert "min(" in data["formula"].lower()
    eligible = [candidate for candidate in data["candidates"] if candidate["is_eligible"]]
    assert eligible
    candidate = eligible[0]
    assert candidate["proposed_hold_paise"] > 0
    assert candidate["proposed_hold_paise"] <= candidate["lower_bound_paise"]
    assert candidate["proposed_hold_paise"] <= candidate["current_balance_paise"]
    assert candidate["history_complete"] is True


def test_simulated_hold_proposal_is_audited_and_never_claims_to_freeze_funds():
    """Creating a demo request records its basis and status without claiming bank execution."""
    preview_response = client.get("/api/hold-preview/CASE-2026-001")
    assert preview_response.status_code == 200
    candidate = next(item for item in preview_response.json()["candidates"] if item["is_eligible"])

    response = client.post("/api/hold-proposals", json={
        "case_id": "CASE-2026-001",
        "account_id": candidate["account_id"],
    })
    assert response.status_code == 200
    result = response.json()
    assert result["case_id"] == "CASE-2026-001"
    assert result["source_transaction_id"] == preview_response.json()["source_transaction_id"]
    assert result["account_id"] == candidate["account_id"]
    assert result["proposed_hold_paise"] == candidate["proposed_hold_paise"]
    assert result["audit_event_id"]
    assert result["status"] == "SIMULATED_PENDING_AUTHORIZED_REVIEW"
    assert result["execution_status"] == "SIMULATION_ONLY_NOT_SENT_TO_BANK"
    assert "no funds were frozen" in result["message"].lower()

    history = client.get("/api/hold-proposals?case_id=CASE-2026-001")
    assert history.status_code == 200
    assert any(item["proposal_id"] == result["proposal_id"] for item in history.json())


def test_api_consensus_lien_endpoint():
    """Verify Consensus Lien endpoint returns exact lower/upper bounds and explanation."""
    res = client.get("/api/consensus-lien/CASE-2026-001")
    assert res.status_code == 200
    data = res.json()
    assert data["case_id"] == "CASE-2026-001"
    assert data["source_transaction_id"] == "TXN_0009"
    assert data["consensus_status"] == "COMPARABLE"
    assert data["total_lower_bound_paise"] > 0
    assert data["total_upper_bound_paise"] >= data["total_lower_bound_paise"]
    assert data["total_disagreement_paise"] == (
        data["total_upper_bound_paise"] - data["total_lower_bound_paise"]
    )
    assert len(data["account_liens"]) > 0
    assert "explanation" in data
    assert "governance_notice" in data


def test_api_investigation_priority_endpoints():
    """Verify investigation priority scoring endpoints."""
    # List all ranked
    list_res = client.get("/api/investigation-priority")
    assert list_res.status_code == 200
    scores = list_res.json()
    assert len(scores) == 3
    assert scores[0]["final_score"] >= scores[1]["final_score"]

    # Single case detail
    single_res = client.get("/api/investigation-priority/CASE-2026-001")
    assert single_res.status_code == 200
    sc = single_res.json()
    assert sc["case_id"] == "CASE-2026-001"
    assert "component_b" in sc
    assert "component_t" in sc
    assert "component_h" in sc
    assert len(sc["supporting_transaction_ids"]) == 5


def test_api_data_quality_endpoint():
    """Verify data quality reporting endpoint."""
    res = client.get("/api/data-quality")
    assert res.status_code == 200
    dq = res.json()
    assert dq["overall_status"] in {"HEALTHY", "DEGRADED"}
    assert dq["ledger_conservation_valid"] is True
    assert len(dq["datasets"]) >= 4


def test_operational_endpoints_do_not_expose_ground_truth():
    """Verify hidden ground truth is never accessible through operational APIs."""
    main_file = Path("app/main.py").read_text(encoding="utf-8")
    assert "ground_truth.json" not in main_file
    assert "ground_truth" not in main_file.lower()
