"""Tests for Smart-Freeze Scaled 25,000+ Investigation Dataset.

Verifies:
- Minimum scale (>= 20,000 transactions, >= 2,000 accounts, >= 100 cases)
- 12-month temporal span and deterministic chronological sorting
- Strict double-entry balance conservation: Opening + Ext Inflows - Ext Outflows == Final
- Non-negative balances across all internal accounts at every transaction step
- Ground truth isolation: operational CSVs contain no evaluation/ground truth tags
- All 18 scenario families represented
- Profiler output validity
"""

import csv
import datetime
import json
from pathlib import Path
import pytest

DATA_DIR = Path("data/synthetic")
EVAL_DIR = Path("data/evaluation")
PROCESSED_DIR = Path("data/processed")


def test_scaled_dataset_scale_and_chronology():
    """Verify scale requirements: 25k-35k transactions, ~2.4k accounts, ~120 cases over 12 months."""
    acc_path = DATA_DIR / "accounts.csv"
    txn_path = DATA_DIR / "transactions.csv"
    cas_path = DATA_DIR / "cases.csv"

    assert acc_path.exists(), "accounts.csv not found"
    assert txn_path.exists(), "transactions.csv not found"
    assert cas_path.exists(), "cases.csv not found"

    with open(acc_path, mode="r", encoding="utf-8") as f:
        accounts = list(csv.DictReader(f))
    with open(txn_path, mode="r", encoding="utf-8") as f:
        transactions = list(csv.DictReader(f))
    with open(cas_path, mode="r", encoding="utf-8") as f:
        cases = list(csv.DictReader(f))

    assert len(accounts) >= 2000, f"Expected >= 2,000 accounts, got {len(accounts)}"
    assert 20000 <= len(transactions) <= 40000, f"Expected 20,000-40,000 transactions, got {len(transactions)}"
    assert len(cases) >= 100, f"Expected >= 100 cases, got {len(cases)}"

    # Chronology & Timespan check
    timestamps = [t["timestamp"] for t in transactions]
    assert timestamps == sorted(timestamps), "Transactions are not sorted deterministically by timestamp"

    dt_start = datetime.datetime.fromisoformat(timestamps[0].replace("Z", "+00:00"))
    dt_end = datetime.datetime.fromisoformat(timestamps[-1].replace("Z", "+00:00"))
    span_days = (dt_end - dt_start).days
    assert span_days >= 300, f"Expected at least 300 days of timestamps (12 months), got {span_days} days"


def test_strict_conservation_and_nonnegative_balances():
    """Verify double-entry balance conservation and zero negative balances."""
    acc_path = DATA_DIR / "accounts.csv"
    txn_path = DATA_DIR / "transactions.csv"

    with open(acc_path, mode="r", encoding="utf-8") as f:
        accounts = list(csv.DictReader(f))
    with open(txn_path, mode="r", encoding="utf-8") as f:
        transactions = list(csv.DictReader(f))

    balances = {a["account_id"]: int(a["opening_balance_paise"]) for a in accounts}
    tot_opening = sum(balances.values())
    tot_ext_in = 0
    tot_ext_out = 0

    for t in transactions:
        fa = t["from_account"]
        ta = t["to_account"]
        amt = int(t["amount_paise"])

        assert amt > 0, f"Transaction {t['transaction_id']} has non-positive amount {amt}"

        if fa.startswith("EXT_"):
            tot_ext_in += amt
        else:
            assert fa in balances, f"Unknown from_account: {fa}"
            balances[fa] -= amt
            assert balances[fa] >= 0, (
                f"Account {fa} reached negative balance ({balances[fa]} paise) "
                f"at transaction {t['transaction_id']}"
            )

        if ta.startswith("EXT_"):
            tot_ext_out += amt
        else:
            assert ta in balances, f"Unknown to_account: {ta}"
            balances[ta] += amt

    tot_final = sum(balances.values())
    assert tot_opening + tot_ext_in - tot_ext_out == tot_final, (
        f"Conservation equation violated: {tot_opening} + {tot_ext_in} - {tot_ext_out} != {tot_final}"
    )


def test_ground_truth_isolation():
    """Verify operational CSVs contain no ground truth fields and ground_truth.json is intact."""
    acc_path = DATA_DIR / "accounts.csv"
    txn_path = DATA_DIR / "transactions.csv"
    cas_path = DATA_DIR / "cases.csv"

    with open(acc_path, mode="r", encoding="utf-8") as f:
        acc_headers = csv.DictReader(f).fieldnames
    with open(txn_path, mode="r", encoding="utf-8") as f:
        txn_headers = csv.DictReader(f).fieldnames
    with open(cas_path, mode="r", encoding="utf-8") as f:
        cas_headers = csv.DictReader(f).fieldnames

    assert set(acc_headers) == {"account_id", "account_type", "opening_balance_paise", "history_complete"}
    assert set(txn_headers) == {
        "transaction_id", "timestamp", "from_account", "to_account",
        "amount_paise", "transaction_type", "case_id", "evidence_status",
    }
    assert set(cas_headers) == {"case_id", "reported_date", "reported_amount_paise", "status"}

    # Ground truth files
    gt_path = DATA_DIR / "ground_truth.json"
    eval_gt_path = EVAL_DIR / "ground_truth.json"

    assert gt_path.exists(), "data/synthetic/ground_truth.json missing"
    assert eval_gt_path.exists(), "data/evaluation/ground_truth.json missing"

    with open(gt_path, mode="r", encoding="utf-8") as f:
        gt = json.load(f)

    assert "_metadata" in gt
    assert "cases" in gt
    assert "scenarios" in gt
    assert "transactions_ground_truth" in gt
    assert len(gt["cases"]) >= 100


def test_all_18_scenario_families_covered():
    """Verify all 18 required scenario families are present in ground truth tracking."""
    gt_path = DATA_DIR / "ground_truth.json"
    with open(gt_path, mode="r", encoding="utf-8") as f:
        gt = json.load(f)

    scenarios = gt.get("scenarios", {})
    expected_families = [
        "ordinary_salary_and_business",
        "high_volume_legitimate_merchants",
        "family_a_layered_chain",
        "family_b_tiny_amount_spray",
        "family_c_heavy_commingling",
        "family_d_structuring_below_threshold",
        "partial_withdrawals_leaving_balance",
        "later_legitimate_credits_entering_commingled",
        "refunds_and_reversals",
        "rapid_movement_between_accounts",
        "dormant_account_activation",
        "shared_intermediary_accounts",
        "incomplete_history_account",
        "dead_end_stuck_funds",
        "multi_event_case",
        "method_divergence_case",
        "ineligible_hold_drained_case",
        "ambiguous_evidence_case",
    ]

    for fam in expected_families:
        assert fam in scenarios, f"Missing scenario family: {fam}"
        assert len(scenarios[fam]) > 0, f"Scenario family {fam} has 0 transactions"


def test_profiler_output_validity():
    """Verify synthetic_data_profile.json was generated and has consistent metrics."""
    profile_path = PROCESSED_DIR / "synthetic_data_profile.json"
    assert profile_path.exists(), "synthetic_data_profile.json missing"

    with open(profile_path, mode="r", encoding="utf-8") as f:
        prof = json.load(f)

    assert prof["summary"]["total_transactions"] >= 20000
    assert prof["financial_integrity"]["conservation_equation_holds"] is True
    assert prof["financial_integrity"]["zero_negative_balances_verified"] is True
