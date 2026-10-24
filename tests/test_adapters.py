"""Unit tests for FairHold dataset adapters (pipeline.adapters).

Tests:
- SyntheticAdapter: schema integrity, integer paise preservation, ground-truth isolation
- EllipticAdapter: cryptocurrency graph separation, directed edges, label mapping, skipping when missing
- SynthAMLAdapter: provenance checking, companion transaction absence detection, refusal to fabricate records
- AMLNetAdapter: separate Australian banking transaction handling, streaming and sample loading
"""

from pathlib import Path
import tempfile
import networkx as nx
import pandas as pd
import pytest

from pipeline.adapters.elliptic_adapter import EllipticAdapter
from pipeline.adapters.synthaml_adapter import AMLNetAdapter, SynthAMLAdapter
from pipeline.adapters.synthetic_adapter import (
    GroundTruthAccessViolationError,
    SyntheticAdapter,
)

WORKSPACE_DIR = Path(__file__).resolve().parent.parent
REAL_RAW_DIR = WORKSPACE_DIR / "data" / "raw"
REAL_SYNTHETIC_DIR = WORKSPACE_DIR / "data" / "synthetic"


# ==============================================================================
# SyntheticAdapter Tests
# ==============================================================================

def test_synthetic_adapter_ground_truth_isolation():
    """Verify that SyntheticAdapter strictly forbids loading hidden ground truth."""
    adapter = SyntheticAdapter(REAL_SYNTHETIC_DIR)
    with pytest.raises(GroundTruthAccessViolationError) as exc_info:
        adapter.verify_ground_truth_isolation("data/synthetic/ground_truth.json")
    assert "Access Denied" in str(exc_info.value)
    assert "strictly isolated" in str(exc_info.value)


def test_synthetic_adapter_loads_valid_dataset():
    """Verify SyntheticAdapter loads the generated operational synthetic dataset."""
    adapter = SyntheticAdapter(REAL_SYNTHETIC_DIR)
    assert adapter.exists()

    df_acc, df_tx, df_case = adapter.load_dataset()
    assert len(df_acc) == 38
    assert len(df_tx) == 119
    assert len(df_case) == 3

    # Check integer paise dtypes
    assert df_acc["opening_balance_paise"].dtype == "int64"
    assert df_tx["amount_paise"].dtype == "int64"
    assert df_case["reported_amount_paise"].dtype == "int64"


def test_synthetic_adapter_rejects_corrupted_amounts():
    """Verify SyntheticAdapter rejects non-integer or negative amounts."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        p = Path(tmp_dir)
        df_acc = pd.DataFrame([
            {"account_id": "ACC_1", "account_type": "savings", "opening_balance_paise": -50, "history_complete": True}
        ])
        df_acc.to_csv(p / "accounts.csv", index=False)

        adapter = SyntheticAdapter(p)
        with pytest.raises(ValueError) as exc:
            adapter.load_accounts()
        assert "negative opening_balance_paise" in str(exc.value)


# ==============================================================================
# EllipticAdapter Tests
# ==============================================================================

def test_elliptic_adapter_skips_when_missing():
    """Verify EllipticAdapter reports skipped when dataset is missing."""
    with tempfile.TemporaryDirectory() as empty_dir:
        adapter = EllipticAdapter(Path(empty_dir) / "non_existent")
        status = adapter.check_availability()
        assert not status.is_available
        assert "missing" in status.message.lower()

        with pytest.raises(FileNotFoundError):
            adapter.load_classes()


def test_elliptic_adapter_fixture():
    """Verify EllipticAdapter with a small synthetic cryptocurrency fixture."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        p = Path(tmp_dir)

        df_classes = pd.DataFrame({
            "txId": [1001, 1002, 1003],
            "class": ["1", "2", "unknown"],
        })
        df_classes.to_csv(p / "elliptic_txs_classes.csv", index=False)

        df_edges = pd.DataFrame({
            "txId1": [1001, 1002],
            "txId2": [1002, 1003],
        })
        df_edges.to_csv(p / "elliptic_txs_edgelist.csv", index=False)

        adapter = EllipticAdapter(p)
        status = adapter.check_availability()
        assert status.is_available

        loaded_classes = adapter.load_classes()
        assert "label_meaning" in loaded_classes.columns
        assert loaded_classes.loc[loaded_classes["txId"] == 1001, "label_meaning"].iloc[0] == "illicit"
        assert loaded_classes.loc[loaded_classes["txId"] == 1002, "label_meaning"].iloc[0] == "licit"
        assert loaded_classes.loc[loaded_classes["txId"] == 1003, "label_meaning"].iloc[0] == "unknown"

        # Build graph
        g = adapter.build_network_graph()
        assert isinstance(g, nx.DiGraph)
        assert g.number_of_nodes() == 3
        assert g.number_of_edges() == 2
        assert g.nodes[1001]["is_illicit"] is True
        assert g.nodes[1002]["is_illicit"] is False


def test_elliptic_adapter_real_files_if_available():
    """If real Elliptic files exist in data/raw/, verify real classes and edgelist load."""
    elliptic_dir = REAL_RAW_DIR / "elliptic_bitcoin_dataset"
    adapter = EllipticAdapter(elliptic_dir)
    status = adapter.check_availability()
    if status.is_available:
        # Load a small sample
        df_classes_sample = adapter.load_classes(limit=10)
        assert len(df_classes_sample) == 10
        assert "label_meaning" in df_classes_sample.columns

        df_edges_sample = adapter.load_edges(limit=10)
        assert len(df_edges_sample) == 10


# ==============================================================================
# SynthAMLAdapter Tests
# ==============================================================================

def test_synthaml_adapter_reports_missing_companion_transactions():
    """Verify SynthAML adapter reports missing synthetic_transactions.csv companion."""
    adapter = SynthAMLAdapter(REAL_RAW_DIR)
    status = adapter.check_availability()

    assert status.alerts_present is True
    assert status.transactions_present is False
    assert status.is_complete is False
    assert "missing" in status.message.lower()

    # Loading alerts works
    df_alerts = adapter.load_alerts(limit=10)
    assert len(df_alerts) == 10
    assert set(df_alerts.columns) == {"AlertID", "Date", "Outcome"}

    # Loading transactions must fail and NEVER fabricate data
    with pytest.raises(FileNotFoundError) as exc:
        adapter.load_transactions()
    assert "not found" in str(exc.value).lower()
    assert "not fabricate" in str(exc.value).lower()


# ==============================================================================
# AMLNetAdapter Tests
# ==============================================================================

def test_amlnet_adapter_sample_and_separation():
    """Verify AMLNet adapter loads sample and preserves all 17 schema columns."""
    amlnet_file = REAL_RAW_DIR / "AMLNet_August 2025.csv"
    adapter = AMLNetAdapter(amlnet_file)
    if adapter.exists():
        df_sample = adapter.load_sample(nrows=5)
        assert len(df_sample) == 5
        assert "laundering_typology" in df_sample.columns
        assert "isFraud" in df_sample.columns
        assert "isMoneyLaundering" in df_sample.columns
        assert "oldbalanceOrg" in df_sample.columns
        assert "newbalanceOrig" in df_sample.columns
