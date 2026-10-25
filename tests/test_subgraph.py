"""Tests for BoundedSubgraphExtractor and case subgraph endpoint."""

from __future__ import annotations

import pytest
import pandas as pd
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient

from engine.subgraph import BoundedSubgraphExtractor, BoundedSubgraphResult
from app.main import app


@pytest.fixture
def sample_chain_data():
    """Build a linear transfer chain with known timestamps."""
    t0 = datetime(2026, 3, 1, 10, 0, tzinfo=timezone.utc)
    accounts = [
        {
            "account_id": f"ACC_{i}",
            "account_type": "SAVINGS",
            "opening_balance_paise": 100000,
            "current_balance_paise": 100000,
        }
        for i in range(6)
    ]
    transactions = [
        {
            "transaction_id": "TX_SRC",
            "from_account": "ACC_0",
            "to_account": "ACC_1",
            "amount_paise": 50000,
            "timestamp": t0.isoformat(),
            "transaction_type": "P2P",
        },
        {
            "transaction_id": "TX_1",
            "from_account": "ACC_1",
            "to_account": "ACC_2",
            "amount_paise": 40000,
            "timestamp": (t0 + timedelta(hours=1)).isoformat(),
            "transaction_type": "P2P",
        },
        {
            "transaction_id": "TX_2",
            "from_account": "ACC_2",
            "to_account": "ACC_3",
            "amount_paise": 30000,
            "timestamp": (t0 + timedelta(hours=3)).isoformat(),
            "transaction_type": "P2P",
        },
        {
            "transaction_id": "TX_3",
            "from_account": "ACC_3",
            "to_account": "ACC_4",
            "amount_paise": 20000,
            "timestamp": (t0 + timedelta(hours=10)).isoformat(),
            "transaction_type": "P2P",
        },
        {
            "transaction_id": "TX_4",
            "from_account": "ACC_4",
            "to_account": "ACC_5",
            "amount_paise": 10000,
            "timestamp": (t0 + timedelta(hours=25)).isoformat(),
            "transaction_type": "P2P",
        },
    ]
    return accounts, transactions


def test_hop_bounding(sample_chain_data):
    accounts, transactions = sample_chain_data

    # max_hops=1: only root (ACC_0 -> ACC_1)
    res_h1 = BoundedSubgraphExtractor.extract(
        accounts=accounts,
        transactions=transactions,
        source_transaction_id="TX_SRC",
        max_hops=1,
    )
    assert res_h1.edge_count == 1
    assert [t["transaction_id"] for t in res_h1.transactions] == ["TX_SRC"]
    assert res_h1.hop_distances == {"ACC_0": 0, "ACC_1": 1}

    # max_hops=2: root + TX_1 (ACC_1 -> ACC_2)
    res_h2 = BoundedSubgraphExtractor.extract(
        accounts=accounts,
        transactions=transactions,
        source_transaction_id="TX_SRC",
        max_hops=2,
    )
    assert res_h2.edge_count == 2
    assert [t["transaction_id"] for t in res_h2.transactions] == ["TX_SRC", "TX_1"]
    assert res_h2.hop_distances == {"ACC_0": 0, "ACC_1": 1, "ACC_2": 2}

    # max_hops=3: root + TX_1 + TX_2
    res_h3 = BoundedSubgraphExtractor.extract(
        accounts=accounts,
        transactions=transactions,
        source_transaction_id="TX_SRC",
        max_hops=3,
    )
    assert res_h3.edge_count == 3
    assert [t["transaction_id"] for t in res_h3.transactions] == ["TX_SRC", "TX_1", "TX_2"]


def test_time_window_bounding(sample_chain_data):
    accounts, transactions = sample_chain_data

    # Window of 4 hours from t0:
    # TX_SRC is at t0, TX_1 at +1h, TX_2 at +3h -> included.
    # TX_3 is at +10h -> excluded even if max_hops=5
    res = BoundedSubgraphExtractor.extract(
        accounts=accounts,
        transactions=transactions,
        source_transaction_id="TX_SRC",
        max_hops=5,
        time_window_hours=4.0,
    )
    tx_ids = [t["transaction_id"] for t in res.transactions]
    assert "TX_SRC" in tx_ids
    assert "TX_1" in tx_ids
    assert "TX_2" in tx_ids
    assert "TX_3" not in tx_ids
    assert "TX_4" not in tx_ids
    assert res.cutoff_timestamp is not None


def test_edge_cap_safety(sample_chain_data):
    accounts, transactions = sample_chain_data

    # Cap to 2 edges
    res = BoundedSubgraphExtractor.extract(
        accounts=accounts,
        transactions=transactions,
        source_transaction_id="TX_SRC",
        max_hops=5,
        max_edges=2,
    )
    assert res.edge_count == 2
    assert len(res.transactions) == 2


def test_missing_source_transaction_raises(sample_chain_data):
    accounts, transactions = sample_chain_data
    with pytest.raises(KeyError, match="Source transaction 'NON_EXISTENT' not found"):
        BoundedSubgraphExtractor.extract(
            accounts=accounts,
            transactions=transactions,
            source_transaction_id="NON_EXISTENT",
        )


def test_subgraph_api_endpoint():
    client = TestClient(app)
    headers = {"Authorization": "Bearer dev_token_admin"}
    resp = client.get("/api/cases/CASE-2026-001/subgraph?max_hops=3&time_window_hours=48", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "source_transaction_id" in data
    assert "node_count" in data
    assert "edge_count" in data
    assert "hop_distances" in data
    assert data["max_hops"] == 3
    assert data["time_window_hours"] == 48.0
    assert data["node_count"] > 0
    assert data["edge_count"] > 0
