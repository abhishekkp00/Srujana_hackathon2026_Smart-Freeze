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
    assert data["service"] == "fairhold-api"
    assert data["version"] == app.version


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
    """Verify directed transaction graph serialization for Cytoscape.js."""
    graph_res = client.get("/api/graph?case_id=CASE-2026-001")
    assert graph_res.status_code == 200
    g = graph_res.json()
    assert g["total_nodes"] > 0
    assert g["total_edges"] == 5
    for node in g["nodes"]:
        assert "id" in node
        assert "label" in node
        assert "is_external" in node
    for edge in g["edges"]:
        assert "source" in edge
        assert "target" in edge
        assert edge["amount_inr"] > 0


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
    assert dq["overall_status"] == "OPERATIONAL"
    assert dq["ledger_conservation_valid"] is True
    assert len(dq["datasets"]) >= 4


def test_operational_endpoints_do_not_expose_ground_truth():
    """Verify hidden ground truth is never accessible through operational APIs."""
    main_file = Path("app/main.py").read_text(encoding="utf-8")
    assert "ground_truth.json" not in main_file
    assert "ground_truth" not in main_file.lower()
