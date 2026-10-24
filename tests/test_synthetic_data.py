"""Smart-Freeze Step 1 Automated Tests: Synthetic Ledger and Project Foundation.

Verifies:
1. Output files exist and are populated.
2. Required schema columns match specifications.
3. Internal vs external account references and case references are valid.
4. Transaction IDs, account IDs, and case IDs are unique.
5. Monetary values follow strict positive/nonnegative integer paise rules.
6. Timestamps are valid ISO 8601 strings in deterministic order.
7. Ground truth is isolated from operational CSVs.
8. All seven required investigative scenarios are covered.
9. Generator produces 100% byte-for-byte identical output for identical seeds.
10. Pandas loads operational CSVs without data or type corruption.
"""

import csv
import datetime
import filecmp
import json
from pathlib import Path
import sys
import tempfile
import pandas as pd
import pytest

WORKSPACE_DIR = Path(__file__).resolve().parent.parent
if str(WORKSPACE_DIR) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_DIR))

from scripts.generate_synthetic_data import (
    ACCOUNT_COLUMNS,
    CASE_COLUMNS,
    REQUIRED_SCENARIOS,
    TRANSACTION_COLUMNS,
    generate_all_data,
    save_dataset,
    validate_dataset,
)
SYNTHETIC_DATA_DIR = WORKSPACE_DIR / "data" / "synthetic"


@pytest.fixture(scope="session")
def synthetic_files():
    """Ensure data is generated and return file paths."""
    accounts_file = SYNTHETIC_DATA_DIR / "accounts.csv"
    txns_file = SYNTHETIC_DATA_DIR / "transactions.csv"
    cases_file = SYNTHETIC_DATA_DIR / "cases.csv"
    gt_file = SYNTHETIC_DATA_DIR / "ground_truth.json"

    # If any file is missing, generate
    if not (accounts_file.exists() and txns_file.exists() and cases_file.exists() and gt_file.exists()):
        accounts, txns, cases, gt = generate_all_data(seed=42)
        validate_dataset(accounts, txns, cases, gt)
        save_dataset(SYNTHETIC_DATA_DIR, accounts, txns, cases, gt)

    return {
        "accounts": accounts_file,
        "transactions": txns_file,
        "cases": cases_file,
        "ground_truth": gt_file,
    }


def test_1_all_four_output_files_generated(synthetic_files):
    """Test 1: Verify all 4 required output files exist and are not empty."""
    for key, path in synthetic_files.items():
        assert path.exists(), f"Expected output file {path} does not exist."
        assert path.stat().st_size > 0, f"Expected output file {path} is empty."


def test_2_required_schemas_correct(synthetic_files):
    """Test 2: Verify exact required column names and JSON top-level keys."""
    # Check accounts.csv
    with open(synthetic_files["accounts"], mode="r", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)
        assert header == ACCOUNT_COLUMNS, f"accounts.csv header mismatch: {header} != {ACCOUNT_COLUMNS}"

    # Check transactions.csv
    with open(synthetic_files["transactions"], mode="r", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)
        assert header == TRANSACTION_COLUMNS, f"transactions.csv header mismatch: {header} != {TRANSACTION_COLUMNS}"

    # Check cases.csv
    with open(synthetic_files["cases"], mode="r", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)
        assert header == CASE_COLUMNS, f"cases.csv header mismatch: {header} != {CASE_COLUMNS}"

    # Check ground_truth.json
    with open(synthetic_files["ground_truth"], mode="r", encoding="utf-8") as f:
        gt_data = json.load(f)
        for key in ["_metadata", "cases", "scenarios", "transactions_ground_truth"]:
            assert key in gt_data, f"ground_truth.json missing key: {key}"


def test_3_transaction_and_account_references_valid(synthetic_files):
    """Test 3: Internal accounts exist, external counterparties are documented, cases exist."""
    with open(synthetic_files["accounts"], mode="r", encoding="utf-8") as f:
        accounts = list(csv.DictReader(f))
        account_ids = {a["account_id"] for a in accounts}

    with open(synthetic_files["cases"], mode="r", encoding="utf-8") as f:
        cases = list(csv.DictReader(f))
        case_ids = {c["case_id"] for c in cases}

    with open(synthetic_files["transactions"], mode="r", encoding="utf-8") as f:
        transactions = list(csv.DictReader(f))

    for txn in transactions:
        from_acc = txn["from_account"]
        to_acc = txn["to_account"]
        case_id = txn["case_id"]

        # Counterparty validation
        from_is_ext = from_acc.startswith("EXT_")
        to_is_ext = to_acc.startswith("EXT_")

        assert not (from_is_ext and to_is_ext), (
            f"Transaction {txn['transaction_id']} cannot connect two external entities: {from_acc} -> {to_acc}"
        )

        if not from_is_ext:
            assert from_acc in account_ids, f"Unknown internal from_account: {from_acc}"
        if not to_is_ext:
            assert to_acc in account_ids, f"Unknown internal to_account: {to_acc}"

        # Case validation
        if case_id:
            assert case_id in case_ids, f"Unknown case_id: {case_id}"


def test_4_transaction_ids_unique(synthetic_files):
    """Test 4: Verify transaction IDs, account IDs, and case IDs are strictly unique."""
    with open(synthetic_files["accounts"], mode="r", encoding="utf-8") as f:
        acc_ids = [row["account_id"] for row in csv.DictReader(f)]
        assert len(acc_ids) == len(set(acc_ids)), "Duplicate account_id found in accounts.csv"

    with open(synthetic_files["cases"], mode="r", encoding="utf-8") as f:
        case_ids = [row["case_id"] for row in csv.DictReader(f)]
        assert len(case_ids) == len(set(case_ids)), "Duplicate case_id found in cases.csv"

    with open(synthetic_files["transactions"], mode="r", encoding="utf-8") as f:
        txn_ids = [row["transaction_id"] for row in csv.DictReader(f)]
        assert len(txn_ids) == len(set(txn_ids)), "Duplicate transaction_id found in transactions.csv"


def test_5_amounts_and_balances_follow_integer_paise_rules(synthetic_files):
    """Test 5: Positive integer paise for txns and reported cases; nonnegative for opening balances."""
    with open(synthetic_files["accounts"], mode="r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            raw = row["opening_balance_paise"]
            assert raw.isdigit(), f"Opening balance must be integer digits, got '{raw}'"
            val = int(raw)
            assert val >= 0, f"Opening balance must be non-negative, got {val}"

    with open(synthetic_files["cases"], mode="r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            raw = row["reported_amount_paise"]
            assert raw.isdigit(), f"Reported amount must be integer digits, got '{raw}'"
            val = int(raw)
            assert val > 0, f"Reported amount must be strictly positive, got {val}"

    with open(synthetic_files["transactions"], mode="r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            raw = row["amount_paise"]
            assert raw.isdigit(), f"Transaction amount must be integer digits, got '{raw}'"
            val = int(raw)
            assert val > 0, f"Transaction amount must be strictly positive, got {val}"


def test_6_timestamps_are_valid_and_ordered(synthetic_files):
    """Test 6: Valid ISO 8601 timestamps and deterministic chronological order."""
    with open(synthetic_files["transactions"], mode="r", encoding="utf-8") as f:
        prev_ts = None
        for row in csv.DictReader(f):
            ts_str = row["timestamp"]
            # Validate ISO format parsing
            dt = datetime.datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            assert dt is not None
            if prev_ts is not None:
                assert ts_str >= prev_ts, f"Transactions not in chronological order: {prev_ts} > {ts_str}"
            prev_ts = ts_str


def test_7_ground_truth_stored_separately(synthetic_files):
    """Test 7: Ground truth is physically separate from operational ledger CSVs."""
    # Ensure operational CSVs do not leak ground truth fields
    with open(synthetic_files["transactions"], mode="r", encoding="utf-8") as f:
        header = next(csv.reader(f))
        for forbidden in ["source_lot_id", "tainted_amount", "remaining_balance", "is_suspected_flow"]:
            assert forbidden not in header, f"Operational transactions.csv leaks ground-truth field: {forbidden}"

    # Ensure ground_truth.json has warning metadata
    with open(synthetic_files["ground_truth"], mode="r", encoding="utf-8") as f:
        gt_data = json.load(f)
        warning = gt_data["_metadata"].get("warning", "")
        assert "NEVER read" in warning or "CONFIDENTIAL" in warning


def test_8_all_required_scenarios_covered(synthetic_files):
    """Test 8: Verify all 7 required investigative scenarios are represented."""
    with open(synthetic_files["ground_truth"], mode="r", encoding="utf-8") as f:
        gt_data = json.load(f)
        scenarios = gt_data.get("scenarios", {})

        for scen in REQUIRED_SCENARIOS:
            assert scen in scenarios, f"Required scenario '{scen}' missing from ground truth."
            assert len(scenarios[scen]) > 0, f"Scenario '{scen}' has no linked transactions."

    # Check incomplete history account presence
    with open(synthetic_files["accounts"], mode="r", encoding="utf-8") as f:
        accounts = list(csv.DictReader(f))
        incomplete_accounts = [a for a in accounts if a["history_complete"] == "False"]
        assert len(incomplete_accounts) >= 1, "At least one account must have history_complete=False."


def test_9_deterministic_identical_generation():
    """Test 9: Running generator twice with same seed produces 100% byte-for-byte identical output."""
    with tempfile.TemporaryDirectory() as dir1, tempfile.TemporaryDirectory() as dir2:
        path1 = Path(dir1)
        path2 = Path(dir2)

        # First run
        acc1, txns1, cases1, gt1 = generate_all_data(seed=42)
        validate_dataset(acc1, txns1, cases1, gt1)
        save_dataset(path1, acc1, txns1, cases1, gt1)

        # Second run
        acc2, txns2, cases2, gt2 = generate_all_data(seed=42)
        validate_dataset(acc2, txns2, cases2, gt2)
        save_dataset(path2, acc2, txns2, cases2, gt2)

        # Compare files
        for filename in ["accounts.csv", "transactions.csv", "cases.csv", "ground_truth.json"]:
            file1 = path1 / filename
            file2 = path2 / filename
            assert filecmp.cmp(file1, file2, shallow=False), f"File {filename} differed between identical seed runs."


def test_10_pandas_loading_integrity(synthetic_files):
    """Test 10: Pandas can load all CSVs without corruption or type errors."""
    df_accounts = pd.read_csv(synthetic_files["accounts"])
    assert len(df_accounts) == 38
    assert df_accounts["opening_balance_paise"].dtype.kind in ("i", "u")  # Integer type
    assert df_accounts["history_complete"].dtype.kind == "b"  # Boolean type

    df_txns = pd.read_csv(synthetic_files["transactions"], keep_default_na=False)
    assert len(df_txns) == 119
    assert df_txns["amount_paise"].dtype.kind in ("i", "u")  # Integer type
    assert df_txns["transaction_id"].nunique() == len(df_txns)

    df_cases = pd.read_csv(synthetic_files["cases"])
    assert len(df_cases) == 3
    assert df_cases["reported_amount_paise"].dtype.kind in ("i", "u")  # Integer type
