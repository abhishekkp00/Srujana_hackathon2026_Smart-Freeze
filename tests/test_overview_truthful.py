"""Tests for Truthful & Explainable Overview Endpoint and Invariants."""

import pytest
from fastapi.testclient import TestClient
from app.main import app

AUTH_ADMIN = {"Authorization": "Bearer dev_token_admin"}
AUTH_INVESTIGATOR = {"Authorization": "Bearer dev_token_investigator_1"}


def test_overview_full_ledger_counts_match_api():
    """Verify Overview API returns truthful full ledger counts and denominators."""
    client = TestClient(app)
    resp = client.get("/api/overview", headers=AUTH_ADMIN)
    assert resp.status_code == 200
    data = resp.json()

    # 1. Total processed must equal full ledger count, not just case-linked subset
    assert data["transactions_processed"] == 119
    assert data["accounts_analyzed"] == 38
    assert data["cases_available"] == 3
    assert data["generator_seed"] == 42
    assert data["is_simulated"] is True

    # 2. Full ledger breakdown
    fl = data["full_ledger"]
    assert fl["total_transactions"] == 119
    assert fl["legitimate_transactions"] == 105
    assert fl["suspected_transactions"] == 14
    assert fl["case_linked_transactions"] == 14
    assert fl["unlinked_transactions"] == 105

    # Check percentages: 14/119 = 11.76%, 105/119 = 88.24%
    assert abs(fl["suspected_pct"] - 11.76) < 0.05
    assert abs(fl["legitimate_pct"] - 88.24) < 0.05
    assert fl["legitimate_transactions"] + fl["suspected_transactions"] == fl["total_transactions"]

    # 3. Daily activity consistency
    daily = data["daily_activity"]
    assert len(daily) > 0
    sum_total = sum(d["total_transactions"] for d in daily)
    sum_sus = sum(d["suspected_transactions"] for d in daily)
    sum_leg = sum(d["legitimate_transactions"] for d in daily)
    sum_cases = sum(d["cases_reported"] for d in daily)

    assert sum_total == 119
    assert sum_sus == 14
    assert sum_leg == 105
    assert sum_cases == 3


def test_overview_date_range_filtering():
    """Verify Overview API date range query filters daily_activity correctly."""
    client = TestClient(app)
    # January 10 to January 13 is the active fraud period
    resp = client.get("/api/overview?start_date=2026-01-10&end_date=2026-01-13", headers=AUTH_ADMIN)
    assert resp.status_code == 200
    data = resp.json()

    # Full ledger totals remain preserved as the denominator
    assert data["full_ledger"]["total_transactions"] == 119

    # Filtered daily activity only has dates within [2026-01-10, 2026-01-13]
    daily = data["daily_activity"]
    for d in daily:
        assert "2026-01-10" <= d["date"] <= "2026-01-13"

    sum_total = sum(d["total_transactions"] for d in daily)
    # 13 + 20 + 27 + 18 = 78 transactions
    assert sum_total == 78
    # 3 + 1 + 6 + 4 = 14 suspected transactions
    sum_sus = sum(d["suspected_transactions"] for d in daily)
    assert sum_sus == 14


def test_overview_investigator_sees_full_ledger_context():
    """Verify investigator persona also receives full ledger context, not only case-linked rows."""
    client = TestClient(app)
    resp = client.get("/api/overview", headers=AUTH_INVESTIGATOR)
    assert resp.status_code == 200
    data = resp.json()

    assert data["transactions_processed"] == 119
    assert data["full_ledger"]["total_transactions"] == 119
    assert data["full_ledger"]["suspected_transactions"] == 14
    assert data["full_ledger"]["legitimate_transactions"] == 105
