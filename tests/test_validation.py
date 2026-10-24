"""Unit tests for FairHold structural and semantic validation (pipeline.validation).

Tests all validation constraints using small, isolated in-memory fixtures:
- Required column presence
- Duplicate ID detection
- Timestamp ISO 8601 parsing
- Integer paise positive/nonnegative constraints
- Reference integrity (internal accounts and cases)
- Prohibited transfers (self-transfer, dual external)
- Elliptic and SynthAML schema validation and provenance warnings
"""

import pandas as pd
import pytest

from pipeline.validation import (
    validate_date_string,
    validate_elliptic_dataset,
    validate_iso_timestamp,
    validate_synthaml_alerts,
    validate_synthetic_accounts,
    validate_synthetic_cases,
    validate_synthetic_transactions,
)


# ==============================================================================
# Helper fixtures
# ==============================================================================

@pytest.fixture
def valid_accounts_df():
    return pd.DataFrame([
        {"account_id": "ACC_001", "account_type": "savings", "opening_balance_paise": 100000, "history_complete": True},
        {"account_id": "ACC_002", "account_type": "current", "opening_balance_paise": 500000, "history_complete": True},
        {"account_id": "ACC_003", "account_type": "salary", "opening_balance_paise": 0, "history_complete": False},
    ])


@pytest.fixture
def valid_cases_df():
    return pd.DataFrame([
        {"case_id": "CASE-2026-001", "reported_date": "2026-01-15T10:00:00Z", "reported_amount_paise": 1000000, "status": "under_investigation"},
    ])


@pytest.fixture
def valid_transactions_df():
    return pd.DataFrame([
        {
            "transaction_id": "TXN_0001",
            "timestamp": "2026-01-16T10:00:00Z",
            "from_account": "EXT_DEPOSIT_BANK",
            "to_account": "ACC_001",
            "amount_paise": 200000,
            "transaction_type": "deposit",
            "case_id": "",
            "evidence_status": "unflagged",
        },
        {
            "transaction_id": "TXN_0002",
            "timestamp": "2026-01-16T11:00:00Z",
            "from_account": "ACC_001",
            "to_account": "ACC_002",
            "amount_paise": 50000,
            "transaction_type": "transfer",
            "case_id": "CASE-2026-001",
            "evidence_status": "suspected_fraud",
        },
    ])


# ==============================================================================
# Accounts Validation Tests
# ==============================================================================

def test_accounts_valid(valid_accounts_df):
    res = validate_synthetic_accounts(valid_accounts_df)
    assert res.is_valid
    assert len(res.errors) == 0
    # Incomplete history account should produce a quality warning
    assert any("incomplete statement history" in w for w in res.warnings)


def test_accounts_missing_columns(valid_accounts_df):
    df = valid_accounts_df.drop(columns=["opening_balance_paise"])
    res = validate_synthetic_accounts(df)
    assert not res.is_valid
    assert any("Missing required columns" in e for e in res.errors)


def test_accounts_duplicate_ids(valid_accounts_df):
    df = pd.concat([valid_accounts_df, valid_accounts_df.iloc[[0]]], ignore_index=True)
    res = validate_synthetic_accounts(df)
    assert not res.is_valid
    assert any("duplicate account_ids" in e for e in res.errors)


def test_accounts_negative_opening_balance(valid_accounts_df):
    df = valid_accounts_df.copy()
    df.loc[0, "opening_balance_paise"] = -500
    res = validate_synthetic_accounts(df)
    assert not res.is_valid
    assert any("negative opening_balance_paise" in e for e in res.errors)


def test_accounts_non_integer_balance(valid_accounts_df):
    df = valid_accounts_df.copy()
    df["opening_balance_paise"] = [123.45, 500000, 0]
    res = validate_synthetic_accounts(df)
    assert not res.is_valid
    assert any("non-integer opening_balance_paise" in e for e in res.errors)


# ==============================================================================
# Transactions Validation Tests
# ==============================================================================

def test_transactions_valid(valid_transactions_df):
    valid_accs = {"ACC_001", "ACC_002", "ACC_003"}
    valid_cases = {"CASE-2026-001"}
    res = validate_synthetic_transactions(valid_transactions_df, valid_accounts=valid_accs, valid_cases=valid_cases)
    assert res.is_valid
    assert len(res.errors) == 0


def test_transactions_missing_columns(valid_transactions_df):
    df = valid_transactions_df.drop(columns=["amount_paise"])
    res = validate_synthetic_transactions(df)
    assert not res.is_valid
    assert any("Missing required columns" in e for e in res.errors)


def test_transactions_duplicate_ids(valid_transactions_df):
    df = pd.concat([valid_transactions_df, valid_transactions_df.iloc[[0]]], ignore_index=True)
    res = validate_synthetic_transactions(df)
    assert not res.is_valid
    assert any("duplicate transaction_ids" in e for e in res.errors)


def test_transactions_invalid_timestamp(valid_transactions_df):
    df = valid_transactions_df.copy()
    df.loc[0, "timestamp"] = "2026-99-99 25:99:99"
    res = validate_synthetic_transactions(df)
    assert not res.is_valid
    assert any("invalid ISO 8601 timestamp" in e for e in res.errors)


def test_transactions_zero_or_negative_amount(valid_transactions_df):
    df1 = valid_transactions_df.copy()
    df1.loc[0, "amount_paise"] = 0
    res1 = validate_synthetic_transactions(df1)
    assert not res1.is_valid
    assert any("non-positive amount_paise" in e for e in res1.errors)

    df2 = valid_transactions_df.copy()
    df2.loc[0, "amount_paise"] = -100
    res2 = validate_synthetic_transactions(df2)
    assert not res2.is_valid
    assert any("non-positive amount_paise" in e for e in res2.errors)


def test_transactions_non_integer_amount(valid_transactions_df):
    df = valid_transactions_df.copy()
    df["amount_paise"] = [1500.50, 50000]
    res = validate_synthetic_transactions(df)
    assert not res.is_valid
    assert any("non-integer amount_paise" in e for e in res.errors)


def test_transactions_self_transfer_prohibited(valid_transactions_df):
    df = valid_transactions_df.copy()
    df.loc[0, "from_account"] = "ACC_001"
    df.loc[0, "to_account"] = "ACC_001"
    res = validate_synthetic_transactions(df)
    assert not res.is_valid
    assert any("self-transfer prohibited" in e for e in res.errors)


def test_transactions_both_counterparties_external(valid_transactions_df):
    df = valid_transactions_df.copy()
    df.loc[0, "from_account"] = "EXT_BANK_A"
    df.loc[0, "to_account"] = "EXT_BANK_B"
    res = validate_synthetic_transactions(df)
    assert not res.is_valid
    assert any("both counterparties external" in e for e in res.errors)


def test_transactions_broken_internal_account_ref(valid_transactions_df):
    valid_accs = {"ACC_001"}  # ACC_002 is missing from registry
    res = validate_synthetic_transactions(valid_transactions_df, valid_accounts=valid_accs)
    assert not res.is_valid
    assert any("unknown internal to_account 'ACC_002'" in e for e in res.errors)


def test_transactions_broken_case_ref(valid_transactions_df):
    valid_accs = {"ACC_001", "ACC_002"}
    valid_cases = {"CASE-2026-999"}  # CASE-2026-001 is missing
    res = validate_synthetic_transactions(valid_transactions_df, valid_accounts=valid_accs, valid_cases=valid_cases)
    assert not res.is_valid
    assert any("unreferenced case_id 'CASE-2026-001'" in e for e in res.errors)


# ==============================================================================
# Cases Validation Tests
# ==============================================================================

def test_cases_valid(valid_cases_df):
    res = validate_synthetic_cases(valid_cases_df)
    assert res.is_valid
    assert len(res.errors) == 0


def test_cases_invalid_reported_date(valid_cases_df):
    df = valid_cases_df.copy()
    df.loc[0, "reported_date"] = "not-a-date"
    res = validate_synthetic_cases(df)
    assert not res.is_valid
    assert any("invalid ISO reported_date" in e for e in res.errors)


def test_cases_non_positive_amount(valid_cases_df):
    df = valid_cases_df.copy()
    df.loc[0, "reported_amount_paise"] = 0
    res = validate_synthetic_cases(df)
    assert not res.is_valid
    assert any("non-positive reported_amount_paise" in e for e in res.errors)


# ==============================================================================
# External Datasets Validation Tests
# ==============================================================================

def test_elliptic_validation_success():
    df_c = pd.DataFrame({"txId": [101, 102], "class": ["1", "2"]})
    df_e = pd.DataFrame({"txId1": [101], "txId2": [102]})
    res = validate_elliptic_dataset(df_c, df_e)
    assert res.is_valid
    assert len(res.errors) == 0


def test_elliptic_validation_missing_columns():
    df_c = pd.DataFrame({"id": [101], "label": ["1"]})
    df_e = pd.DataFrame({"txId1": [101], "txId2": [102]})
    res = validate_elliptic_dataset(df_c, df_e)
    assert not res.is_valid


def test_synthaml_alerts_validation_provenance_warning():
    df_alerts = pd.DataFrame([
        {"AlertID": 1, "Date": "2020-05-01", "Outcome": "Report"},
        {"AlertID": 2, "Date": "2020-05-02", "Outcome": "Dismiss"},
    ])
    # When companion transactions file is missing, should produce provenance warning
    res = validate_synthaml_alerts(df_alerts, transactions_file_present=False)
    assert res.is_valid
    assert any("companion file is missing" in w for w in res.warnings)


def test_synthaml_alerts_invalid_date():
    df_alerts = pd.DataFrame([
        {"AlertID": 1, "Date": "05/01/2020", "Outcome": "Report"},
    ])
    res = validate_synthaml_alerts(df_alerts, transactions_file_present=True)
    assert not res.is_valid
    assert any("invalid date format" in e for e in res.errors)
