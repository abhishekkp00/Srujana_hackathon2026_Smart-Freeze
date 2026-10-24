"""Unit tests for FairHold directed transaction graph (engine.transaction_graph).

Tests:
1. Internal accounts are represented as nodes.
2. Internal transfers create directed edges from sender to receiver.
3. Multiple transactions between the same accounts are preserved (MultiDiGraph).
4. Edge attributes retain complete provenance.
5. External flows update node attributes without creating fake internal nodes.
6. Graph summary metrics (nodes, edges, components, isolated accounts).
7. Graph serialization format.
"""

import networkx as nx
import pytest

from engine.transaction_graph import TransactionGraphEngine


@pytest.fixture
def graph_fixture_data():
    accounts = [
        {"account_id": "ACC_1", "account_type": "savings", "opening_balance_paise": 500000, "history_complete": True},
        {"account_id": "ACC_2", "account_type": "current", "opening_balance_paise": 300000, "history_complete": True},
        {"account_id": "ACC_ISOLATED", "account_type": "savings", "opening_balance_paise": 100000, "history_complete": True},
    ]
    transactions = [
        # Transfer 1: ACC_1 -> ACC_2
        {
            "transaction_id": "TXN_01",
            "timestamp": "2026-01-15T10:00:00Z",
            "from_account": "ACC_1",
            "to_account": "ACC_2",
            "amount_paise": 50000,
            "transaction_type": "transfer",
            "case_id": "CASE-2026-001",
            "evidence_status": "suspected_fraud",
        },
        # Transfer 2: ACC_1 -> ACC_2 (Second transfer between same accounts!)
        {
            "transaction_id": "TXN_02",
            "timestamp": "2026-01-15T12:00:00Z",
            "from_account": "ACC_1",
            "to_account": "ACC_2",
            "amount_paise": 30000,
            "transaction_type": "transfer",
            "case_id": "CASE-2026-001",
            "evidence_status": "suspected_fraud",
        },
        # External deposit into ACC_1
        {
            "transaction_id": "TXN_DEP",
            "timestamp": "2026-01-15T09:00:00Z",
            "from_account": "EXT_ATM",
            "to_account": "ACC_1",
            "amount_paise": 100000,
            "transaction_type": "deposit",
            "case_id": "",
            "evidence_status": "unflagged",
        },
        # External withdrawal from ACC_2
        {
            "transaction_id": "TXN_WTH",
            "timestamp": "2026-01-15T14:00:00Z",
            "from_account": "ACC_2",
            "to_account": "EXT_MERCHANT",
            "amount_paise": 20000,
            "transaction_type": "withdrawal",
            "case_id": "",
            "evidence_status": "unflagged",
        },
    ]
    return accounts, transactions


def test_transaction_graph_nodes_and_multiple_edges(graph_fixture_data):
    accounts, transactions = graph_fixture_data
    g = TransactionGraphEngine.build_graph(accounts, transactions)

    # 3 internal accounts as nodes
    assert g.number_of_nodes() == 3
    assert set(g.nodes) == {"ACC_1", "ACC_2", "ACC_ISOLATED"}

    # External counterparties must NOT be nodes in internal transfer graph
    assert "EXT_ATM" not in g.nodes
    assert "EXT_MERCHANT" not in g.nodes

    # 2 internal transfer edges between ACC_1 and ACC_2 (MultiDiGraph preserves both!)
    assert g.number_of_edges() == 2
    assert g.has_edge("ACC_1", "ACC_2", key="TXN_01")
    assert g.has_edge("ACC_1", "ACC_2", key="TXN_02")

    edge1 = g.get_edge_data("ACC_1", "ACC_2", key="TXN_01")
    assert edge1["amount_paise"] == 50000
    assert edge1["case_id"] == "CASE-2026-001"

    edge2 = g.get_edge_data("ACC_1", "ACC_2", key="TXN_02")
    assert edge2["amount_paise"] == 30000


def test_external_flows_recorded_on_nodes(graph_fixture_data):
    accounts, transactions = graph_fixture_data
    g = TransactionGraphEngine.build_graph(accounts, transactions)

    # ACC_1 received external deposit of 100,000 paise
    assert g.nodes["ACC_1"]["external_deposits_paise"] == 100000
    # ACC_2 performed external withdrawal of 20,000 paise
    assert g.nodes["ACC_2"]["external_withdrawals_paise"] == 20000


def test_transaction_graph_summary(graph_fixture_data):
    accounts, transactions = graph_fixture_data
    g = TransactionGraphEngine.build_graph(accounts, transactions)
    summary = TransactionGraphEngine.summarize_graph(g)

    assert summary.internal_account_nodes == 3
    assert summary.internal_transfer_edges == 2
    # Isolated accounts
    assert "ACC_ISOLATED" in summary.isolated_accounts
    # Top sender is ACC_1 (80,000 paise total outflow)
    assert summary.top_senders_by_volume[0]["account_id"] == "ACC_1"
    assert summary.top_senders_by_volume[0]["outflow_paise"] == 80000
    # Top receiver is ACC_2 (80,000 paise total inflow)
    assert summary.top_receivers_by_volume[0]["account_id"] == "ACC_2"
    assert summary.top_receivers_by_volume[0]["inflow_paise"] == 80000


def test_transaction_graph_serialization(graph_fixture_data):
    accounts, transactions = graph_fixture_data
    g = TransactionGraphEngine.build_graph(accounts, transactions)
    d = TransactionGraphEngine.serialize_to_dict(g)

    assert d["node_count"] == 3
    assert d["edge_count"] == 2
    assert len(d["nodes"]) == 3
    assert len(d["edges"]) == 2
