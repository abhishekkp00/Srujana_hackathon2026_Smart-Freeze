#!/usr/bin/env python3
"""Smart-Freeze Deterministic Synthetic Financial Ledger Generator.

Generates a controlled, deterministic synthetic financial dataset for evaluating
Smart-Freeze's fund-tracing algorithms (FIFO, Proportional, LIBR) and Consensus Lien
against verified ground truth.

Conventions:
- Amounts: All monetary values are represented as integer paise (1 INR = 100 paise).
  Floating-point currency values are strictly prohibited.
- Timestamps: ISO 8601 strings in UTC (YYYY-MM-DDTHH:MM:SSZ).
- Internal Accounts: Prefixed with 'ACC_' and listed in accounts.csv.
- External Counterparties: Prefixed with 'EXT_' (e.g., EXT_CASH_ATM, EXT_SALARY_ORIGIN).
  External counterparties represent boundary entities outside the closed ledger.
- Cases: Distinct fraud complaints identified by 'CASE-YYYY-NNN'. Transactions unrelated
  to a fraud investigation have an empty case_id ("").
- Ground Truth: Saved separately to data/synthetic/ground_truth.json. Tracing and scoring
  algorithms must never read ground truth.
"""

from __future__ import annotations

import argparse
import csv
import datetime
import json
import os
import random
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple


# Schema definitions
ACCOUNT_COLUMNS = [
    "account_id",
    "account_type",
    "opening_balance_paise",
    "history_complete",
]

TRANSACTION_COLUMNS = [
    "transaction_id",
    "timestamp",
    "from_account",
    "to_account",
    "amount_paise",
    "transaction_type",
    "case_id",
    "evidence_status",
]

CASE_COLUMNS = [
    "case_id",
    "reported_date",
    "reported_amount_paise",
    "status",
]

REQUIRED_SCENARIOS = [
    "ordinary_salary_and_business",
    "direct_onward_transfer",
    "split_transfers_smurfing",
    "commingling_funds",
    "partial_withdrawals_leaving_balance",
    "merchant_multiple_customers",
    "incomplete_history_account",
]


def generate_all_data(
    seed: int = 42,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any]]:
    """Generate deterministic synthetic accounts, transactions, cases, and ground truth."""
    rng = random.Random(seed)

    # ---------------------------------------------------------
    # 1. Accounts Setup (~38 internal accounts)
    # ---------------------------------------------------------
    accounts: List[Dict[str, Any]] = []

    def add_acc(acc_id: str, acc_type: str, bal_paise: int, hist_comp: bool = True) -> None:
        accounts.append({
            "account_id": acc_id,
            "account_type": acc_type,
            "opening_balance_paise": int(bal_paise),
            "history_complete": bool(hist_comp),
        })

    # Victims of fraud complaints
    add_acc("ACC_VICTIM_01", "savings", 25_000_000)  # 250,000 INR
    add_acc("ACC_VICTIM_02", "current", 30_000_000)  # 300,000 INR
    add_acc("ACC_VICTIM_03", "savings", 40_000_000)  # 400,000 INR

    # Case 1: Direct transfer, commingling & layer 2
    add_acc("ACC_MULE_DIRECT_01", "savings", 500_000)
    add_acc("ACC_COMMINGLED_01", "current", 5_000_000)  # legitimate opening balance
    add_acc("ACC_LAYER2_01", "savings", 100_000)
    add_acc("ACC_LAYER2_02", "savings", 200_000)

    # Case 2: Split transfers (fan-out / smurfing)
    add_acc("ACC_SPLITTER_01", "current", 300_000)
    add_acc("ACC_MULE_SPLIT_01", "savings", 100_000)
    add_acc("ACC_MULE_SPLIT_02", "savings", 150_000)
    add_acc("ACC_MULE_SPLIT_03", "savings", 50_000)
    add_acc("ACC_CRYPTO_OTC_01", "current", 1_000_000)

    # Case 3: Partial withdrawals & incomplete history
    add_acc("ACC_MULE_PARTIAL_01", "savings", 100_000)
    add_acc("ACC_INCOMPLETE_01", "savings", 0, hist_comp=False)  # Account with incomplete history

    # Legitimate corporate entity & employees
    add_acc("ACC_CORP_PAYROLL", "corporate", 150_000_000)  # 1.5M INR
    for i in range(1, 9):
        add_acc(f"ACC_EMP_{i:02d}", "salary", rng.randint(200_000, 1_000_000))
    add_acc("ACC_LANDLORD_01", "current", 10_000_000)

    # Legitimate merchant & retail customers
    add_acc("ACC_MERCHANT_01", "merchant", 20_000_000)
    for i in range(1, 11):
        add_acc(f"ACC_CUST_{i:02d}", "savings", rng.randint(1_000_000, 3_000_000))

    # General personal background accounts (scaled to support background transactions)
    add_acc("ACC_PERSONAL_01", "savings", 3_000_000)
    add_acc("ACC_PERSONAL_02", "savings", 3_000_000)
    add_acc("ACC_PERSONAL_03", "current", 3_000_000)

    # ---------------------------------------------------------
    # 2. Cases Setup (3 Distinct Fraud Cases)
    # ---------------------------------------------------------
    cases: List[Dict[str, Any]] = [
        {
            "case_id": "CASE-2026-001",
            "reported_date": "2026-01-16T10:00:00Z",
            "reported_amount_paise": 10_000_000,  # 100,000 INR
            "status": "under_investigation",
        },
        {
            "case_id": "CASE-2026-002",
            "reported_date": "2026-01-18T14:30:00Z",
            "reported_amount_paise": 15_000_000,  # 150,000 INR
            "status": "under_investigation",
        },
        {
            "case_id": "CASE-2026-003",
            "reported_date": "2026-01-20T09:15:00Z",
            "reported_amount_paise": 20_000_000,  # 200,000 INR
            "status": "under_investigation",
        },
    ]

    # ---------------------------------------------------------
    # 3. Transactions Generation (~150-180 transactions)
    # ---------------------------------------------------------
    raw_txns: List[Dict[str, Any]] = []
    base_time = datetime.datetime(2026, 1, 10, 8, 0, 0, tzinfo=datetime.timezone.utc)

    def txn_time(day_offset: int, hour: int, minute: int, second: int = 0) -> str:
        dt = base_time + datetime.timedelta(days=day_offset, hours=hour, minutes=minute, seconds=second)
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    # A. Case 1 Transactions: Fraud Inflow -> Direct Transfer -> Commingling -> Layer 2 Outflows
    # Fraud origin
    raw_txns.append({
        "timestamp": txn_time(0, 9, 15),
        "from_account": "ACC_VICTIM_01",
        "to_account": "ACC_MULE_DIRECT_01",
        "amount_paise": 10_000_000,
        "transaction_type": "transfer",
        "case_id": "CASE-2026-001",
        "evidence_status": "suspected_fraud",
        "_scenario": "direct_onward_transfer",
    })
    # Direct onward transfer: Mule forwards 8,000,000 paise to Commingled account, keeping 2,000,000
    raw_txns.append({
        "timestamp": txn_time(0, 10, 0),
        "from_account": "ACC_MULE_DIRECT_01",
        "to_account": "ACC_COMMINGLED_01",
        "amount_paise": 8_000_000,
        "transaction_type": "transfer",
        "case_id": "CASE-2026-001",
        "evidence_status": "suspected_fraud",
        "_scenario": "direct_onward_transfer",
    })
    # Mule withdraws 500,000 paise to external cash ATM
    raw_txns.append({
        "timestamp": txn_time(0, 11, 30),
        "from_account": "ACC_MULE_DIRECT_01",
        "to_account": "EXT_CASH_ATM",
        "amount_paise": 500_000,
        "transaction_type": "withdrawal",
        "case_id": "CASE-2026-001",
        "evidence_status": "suspected_fraud",
        "_scenario": "partial_withdrawals_leaving_balance",
    })

    # Commingling: Commingled account receives legitimate consulting payment
    raw_txns.append({
        "timestamp": txn_time(1, 10, 0),
        "from_account": "EXT_CLIENT_PAYMENT",
        "to_account": "ACC_COMMINGLED_01",
        "amount_paise": 4_000_000,  # 40,000 INR legitimate
        "transaction_type": "deposit",
        "case_id": "",
        "evidence_status": "verified_legitimate",
        "_scenario": "commingling_funds",
    })
    # Commingled account transfers funds onward in layers
    raw_txns.append({
        "timestamp": txn_time(1, 14, 0),
        "from_account": "ACC_COMMINGLED_01",
        "to_account": "ACC_LAYER2_01",
        "amount_paise": 6_000_000,
        "transaction_type": "transfer",
        "case_id": "CASE-2026-001",
        "evidence_status": "suspected_fraud",
        "_scenario": "commingling_funds",
    })
    raw_txns.append({
        "timestamp": txn_time(2, 9, 30),
        "from_account": "ACC_COMMINGLED_01",
        "to_account": "ACC_LAYER2_02",
        "amount_paise": 3_000_000,
        "transaction_type": "transfer",
        "case_id": "CASE-2026-001",
        "evidence_status": "suspected_fraud",
        "_scenario": "commingling_funds",
    })

    # B. Case 2 Transactions: Split Transfers (Smurfing/Fan-out)
    # Fraud origin
    raw_txns.append({
        "timestamp": txn_time(2, 10, 0),
        "from_account": "ACC_VICTIM_02",
        "to_account": "ACC_SPLITTER_01",
        "amount_paise": 15_000_000,
        "transaction_type": "transfer",
        "case_id": "CASE-2026-002",
        "evidence_status": "suspected_fraud",
        "_scenario": "split_transfers_smurfing",
    })
    # Fan out to 3 destination mules
    raw_txns.append({
        "timestamp": txn_time(2, 11, 0),
        "from_account": "ACC_SPLITTER_01",
        "to_account": "ACC_MULE_SPLIT_01",
        "amount_paise": 5_000_000,
        "transaction_type": "transfer",
        "case_id": "CASE-2026-002",
        "evidence_status": "suspected_fraud",
        "_scenario": "split_transfers_smurfing",
    })
    raw_txns.append({
        "timestamp": txn_time(2, 11, 15),
        "from_account": "ACC_SPLITTER_01",
        "to_account": "ACC_MULE_SPLIT_02",
        "amount_paise": 5_000_000,
        "transaction_type": "transfer",
        "case_id": "CASE-2026-002",
        "evidence_status": "suspected_fraud",
        "_scenario": "split_transfers_smurfing",
    })
    raw_txns.append({
        "timestamp": txn_time(2, 11, 30),
        "from_account": "ACC_SPLITTER_01",
        "to_account": "ACC_MULE_SPLIT_03",
        "amount_paise": 4_000_000,
        "transaction_type": "transfer",
        "case_id": "CASE-2026-002",
        "evidence_status": "suspected_fraud",
        "_scenario": "split_transfers_smurfing",
    })
    # Splitter keeps 1,000,000 commission; Mule 1 buys retail at Merchant
    raw_txns.append({
        "timestamp": txn_time(2, 15, 0),
        "from_account": "ACC_MULE_SPLIT_01",
        "to_account": "ACC_MERCHANT_01",
        "amount_paise": 100_000,
        "transaction_type": "merchant_payment",
        "case_id": "CASE-2026-002",
        "evidence_status": "suspected_fraud",
        "_scenario": "merchant_multiple_customers",
    })
    # Mule 2 transfers to Crypto OTC account
    raw_txns.append({
        "timestamp": txn_time(2, 16, 0),
        "from_account": "ACC_MULE_SPLIT_02",
        "to_account": "ACC_CRYPTO_OTC_01",
        "amount_paise": 4_500_000,
        "transaction_type": "transfer",
        "case_id": "CASE-2026-002",
        "evidence_status": "suspected_fraud",
        "_scenario": "split_transfers_smurfing",
    })
    # Mule 3 transfers to Incomplete History account
    raw_txns.append({
        "timestamp": txn_time(2, 17, 0),
        "from_account": "ACC_MULE_SPLIT_03",
        "to_account": "ACC_INCOMPLETE_01",
        "amount_paise": 3_500_000,
        "transaction_type": "transfer",
        "case_id": "CASE-2026-002",
        "evidence_status": "suspected_fraud",
        "_scenario": "incomplete_history_account",
    })

    # C. Case 3 Transactions: Partial Withdrawal leaving Remaining Balance
    raw_txns.append({
        "timestamp": txn_time(3, 9, 0),
        "from_account": "ACC_VICTIM_03",
        "to_account": "ACC_MULE_PARTIAL_01",
        "amount_paise": 20_000_000,
        "transaction_type": "transfer",
        "case_id": "CASE-2026-003",
        "evidence_status": "suspected_fraud",
        "_scenario": "partial_withdrawals_leaving_balance",
    })
    # Mule withdraws 12,000,000 paise via ATM cash out, leaving 8,000,000 remaining
    raw_txns.append({
        "timestamp": txn_time(3, 11, 0),
        "from_account": "ACC_MULE_PARTIAL_01",
        "to_account": "EXT_CASH_ATM",
        "amount_paise": 12_000_000,
        "transaction_type": "withdrawal",
        "case_id": "CASE-2026-003",
        "evidence_status": "suspected_fraud",
        "_scenario": "partial_withdrawals_leaving_balance",
    })

    # D. Ordinary Salary & Business Activities (Scenario 1)
    # Payroll distributions for 8 employees across 2 pay cycles
    for cycle_offset in [0, 14]:
        for emp_idx in range(1, 9):
            emp_id = f"ACC_EMP_{emp_idx:02d}"
            raw_txns.append({
                "timestamp": txn_time(cycle_offset, 8, emp_idx * 5),
                "from_account": "ACC_CORP_PAYROLL",
                "to_account": emp_id,
                "amount_paise": 5_000_000,  # 50,000 INR salary
                "transaction_type": "salary_credit",
                "case_id": "",
                "evidence_status": "verified_legitimate",
                "_scenario": "ordinary_salary_and_business",
            })
            # Employee pays landlord rent
            raw_txns.append({
                "timestamp": txn_time(cycle_offset + 1, 10, emp_idx * 5),
                "from_account": emp_id,
                "to_account": "ACC_LANDLORD_01",
                "amount_paise": 1_500_000,  # 15,000 INR rent
                "transaction_type": "transfer",
                "case_id": "",
                "evidence_status": "verified_legitimate",
                "_scenario": "ordinary_salary_and_business",
            })
            # Employee utility bill payment via external gateway
            raw_txns.append({
                "timestamp": txn_time(cycle_offset + 2, 12, emp_idx * 5),
                "from_account": emp_id,
                "to_account": "EXT_UTILITY_GATEWAY",
                "amount_paise": 350_000,  # 3,500 INR utility
                "transaction_type": "transfer",
                "case_id": "",
                "evidence_status": "verified_legitimate",
                "_scenario": "ordinary_salary_and_business",
            })

    # E. Legitimate Merchant Receiving Payments from Multiple Customers (Scenario 6)
    # 10 Customers making repeated purchases across 4 days
    for day in [1, 2, 3, 4]:
        for cust_idx in range(1, 11):
            cust_id = f"ACC_CUST_{cust_idx:02d}"
            amt = (cust_idx * 15_000) + (day * 10_000)  # deterministically varied amounts (paise)
            raw_txns.append({
                "timestamp": txn_time(day, 12 + (cust_idx % 6), (cust_idx * 5) % 60),
                "from_account": cust_id,
                "to_account": "ACC_MERCHANT_01",
                "amount_paise": amt,
                "transaction_type": "merchant_payment",
                "case_id": "",
                "evidence_status": "verified_legitimate",
                "_scenario": "merchant_multiple_customers",
            })

    # Merchant settles funds to wholesale supplier
    for day in [2, 4]:
        raw_txns.append({
            "timestamp": txn_time(day, 19, 0),
            "from_account": "ACC_MERCHANT_01",
            "to_account": "EXT_SUPPLIER_WHOLESALE",
            "amount_paise": 1_500_000,
            "transaction_type": "transfer",
            "case_id": "",
            "evidence_status": "verified_legitimate",
            "_scenario": "merchant_multiple_customers",
        })

    # F. General Background Transfers among personal accounts
    for i in range(1, 15):
        raw_txns.append({
            "timestamp": txn_time(i % 5, 14, (i * 4) % 60),
            "from_account": f"ACC_PERSONAL_{(i % 3) + 1:02d}",
            "to_account": f"ACC_CUST_{(i % 10) + 1:02d}",
            "amount_paise": 50_000 * i,
            "transaction_type": "transfer",
            "case_id": "",
            "evidence_status": "verified_legitimate",
            "_scenario": "ordinary_salary_and_business",
        })

    # ---------------------------------------------------------
    # 4. Deterministic Ordering and ID Assignment
    # ---------------------------------------------------------
    # Sort deterministically by timestamp, from_account, to_account, amount
    raw_txns.sort(key=lambda t: (t["timestamp"], t["from_account"], t["to_account"], t["amount_paise"]))

    transactions: List[Dict[str, Any]] = []
    ground_truth_txns: Dict[str, Any] = {}
    scenario_tracking: Dict[str, List[str]] = {s: [] for s in REQUIRED_SCENARIOS}

    for idx, raw in enumerate(raw_txns, start=1):
        txn_id = f"TXN_{idx:04d}"
        scenario = raw["_scenario"]

        transactions.append({
            "transaction_id": txn_id,
            "timestamp": raw["timestamp"],
            "from_account": raw["from_account"],
            "to_account": raw["to_account"],
            "amount_paise": int(raw["amount_paise"]),
            "transaction_type": raw["transaction_type"],
            "case_id": raw["case_id"],
            "evidence_status": raw["evidence_status"],
        })

        scenario_tracking[scenario].append(txn_id)

        # Ground truth tracking
        is_suspected = bool(raw["case_id"])
        ground_truth_txns[txn_id] = {
            "contains_suspected_funds": is_suspected,
            "suspected_amount_paise": int(raw["amount_paise"]) if is_suspected else 0,
            "legitimate_amount_paise": 0 if is_suspected else int(raw["amount_paise"]),
            "source_case_id": raw["case_id"],
            "scenario": scenario,
        }

    # ---------------------------------------------------------
    # 5. Ground Truth Data Assembly
    # ---------------------------------------------------------
    ground_truth: Dict[str, Any] = {
        "_metadata": {
            "dataset_type": "synthetic_ground_truth",
            "generator_version": "1.0.0",
            "random_seed": seed,
            "warning": (
                "CONFIDENTIAL EVALUATION DATA: Tracing and scoring algorithms must "
                "NEVER read this file directly. Strictly for evaluation/benchmark modules."
            ),
            "generated_at": "2026-01-20T12:00:00Z",
        },
        "cases": {
            "CASE-2026-001": {
                "victim_account": "ACC_VICTIM_01",
                "origin_transfer_paise": 10_000_000,
                "source_lots": [
                    {
                        "lot_id": "LOT-CASE1-01",
                        "original_amount_paise": 10_000_000,
                        "source_case_id": "CASE-2026-001",
                        "initial_receiver": "ACC_MULE_DIRECT_01",
                    }
                ],
                "expected_allocations": {
                    "ACC_MULE_DIRECT_01": {
                        "received_suspected_paise": 10_000_000,
                        "forwarded_suspected_paise": 8_000_000,
                        "withdrawn_suspected_paise": 500_000,
                        "retained_suspected_paise": 1_500_000,
                    },
                    "ACC_COMMINGLED_01": {
                        "received_suspected_paise": 8_000_000,
                        "commingled_with_legitimate_paise": 9_000_000,  # 5M opening + 4M deposit
                        "total_outflow_paise": 9_000_000,
                    },
                },
            },
            "CASE-2026-002": {
                "victim_account": "ACC_VICTIM_02",
                "origin_transfer_paise": 15_000_000,
                "source_lots": [
                    {
                        "lot_id": "LOT-CASE2-01",
                        "original_amount_paise": 15_000_000,
                        "source_case_id": "CASE-2026-002",
                        "initial_receiver": "ACC_SPLITTER_01",
                    }
                ],
                "fan_out_accounts": ["ACC_MULE_SPLIT_01", "ACC_MULE_SPLIT_02", "ACC_MULE_SPLIT_03"],
            },
            "CASE-2026-003": {
                "victim_account": "ACC_VICTIM_03",
                "origin_transfer_paise": 20_000_000,
                "source_lots": [
                    {
                        "lot_id": "LOT-CASE3-01",
                        "original_amount_paise": 20_000_000,
                        "source_case_id": "CASE-2026-003",
                        "initial_receiver": "ACC_MULE_PARTIAL_01",
                    }
                ],
                "expected_allocations": {
                    "ACC_MULE_PARTIAL_01": {
                        "received_suspected_paise": 20_000_000,
                        "withdrawn_cash_paise": 12_000_000,
                        "retained_suspected_paise": 8_000_000,
                    }
                },
            },
        },
        "scenarios": scenario_tracking,
        "transactions_ground_truth": ground_truth_txns,
    }

    return accounts, transactions, cases, ground_truth


def validate_dataset(
    accounts: List[Dict[str, Any]],
    transactions: List[Dict[str, Any]],
    cases: List[Dict[str, Any]],
    ground_truth: Dict[str, Any],
) -> None:
    """Validate all generated records against Smart-Freeze financial integrity constraints."""
    # 1. Accounts Validation
    if not accounts:
        raise ValueError("Accounts list is empty.")
    account_ids: Set[str] = set()
    has_incomplete_history = False

    for acc in accounts:
        for col in ACCOUNT_COLUMNS:
            if col not in acc:
                raise ValueError(f"Account record missing column '{col}': {acc}")
        aid = acc["account_id"]
        if not isinstance(aid, str) or not aid:
            raise ValueError(f"Invalid account_id: {aid}")
        if aid in account_ids:
            raise ValueError(f"Duplicate account_id detected: {aid}")
        account_ids.add(aid)

        bal = acc["opening_balance_paise"]
        if not isinstance(bal, int) or bal < 0:
            raise ValueError(f"Account opening_balance_paise must be nonnegative integer paise, got {bal} ({type(bal)})")

        if not isinstance(acc["history_complete"], bool):
            raise ValueError(f"Account history_complete must be boolean, got {acc['history_complete']}")
        if not acc["history_complete"]:
            has_incomplete_history = True

    if not has_incomplete_history:
        raise ValueError("No account found with history_complete == False.")

    if not (30 <= len(accounts) <= 50):
        raise ValueError(f"Account count must be within 30-50, got {len(accounts)}")

    # 2. Cases Validation
    if not cases:
        raise ValueError("Cases list is empty.")
    case_ids: Set[str] = set()
    for c in cases:
        for col in CASE_COLUMNS:
            if col not in c:
                raise ValueError(f"Case record missing column '{col}': {c}")
        cid = c["case_id"]
        if not isinstance(cid, str) or not cid:
            raise ValueError(f"Invalid case_id: {cid}")
        if cid in case_ids:
            raise ValueError(f"Duplicate case_id detected: {cid}")
        case_ids.add(cid)

        amt = c["reported_amount_paise"]
        if not isinstance(amt, int) or amt <= 0:
            raise ValueError(f"Case reported_amount_paise must be positive integer paise, got {amt}")

        # Check timestamp
        try:
            datetime.datetime.fromisoformat(c["reported_date"].replace("Z", "+00:00"))
        except Exception as e:
            raise ValueError(f"Invalid case reported_date '{c['reported_date']}': {e}")

    # 3. Transactions Validation
    if not transactions:
        raise ValueError("Transactions list is empty.")
    if not (100 <= len(transactions) <= 300):
        raise ValueError(f"Transaction count must be within 100-300, got {len(transactions)}")

    transaction_ids: Set[str] = set()
    prev_timestamp: str = ""

    for txn in transactions:
        for col in TRANSACTION_COLUMNS:
            if col not in txn:
                raise ValueError(f"Transaction record missing column '{col}': {txn}")
        tid = txn["transaction_id"]
        if not isinstance(tid, str) or not tid:
            raise ValueError(f"Invalid transaction_id: {tid}")
        if tid in transaction_ids:
            raise ValueError(f"Duplicate transaction_id detected: {tid}")
        transaction_ids.add(tid)

        # Validate amounts
        amt = txn["amount_paise"]
        if not isinstance(amt, int) or amt <= 0:
            raise ValueError(f"Transaction amount_paise must be positive integer paise, got {amt}")

        # Validate timestamps
        ts = txn["timestamp"]
        try:
            datetime.datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except Exception as e:
            raise ValueError(f"Invalid transaction timestamp '{ts}': {e}")

        if prev_timestamp and ts < prev_timestamp:
            raise ValueError(f"Transactions are not sorted deterministically by timestamp: {prev_timestamp} > {ts}")
        prev_timestamp = ts

        # Validate internal accounts vs external counterparties
        from_acc = txn["from_account"]
        to_acc = txn["to_account"]

        if not from_acc or not to_acc:
            raise ValueError(f"Transaction {tid} has empty from_account or to_account.")

        from_is_ext = from_acc.startswith("EXT_")
        to_is_ext = to_acc.startswith("EXT_")

        if from_is_ext and to_is_ext:
            raise ValueError(f"Transaction {tid} connects two external entities ({from_acc} -> {to_acc}).")

        if not from_is_ext and from_acc not in account_ids:
            raise ValueError(f"Transaction {tid} references unknown internal from_account: '{from_acc}'")

        if not to_is_ext and to_acc not in account_ids:
            raise ValueError(f"Transaction {tid} references unknown internal to_account: '{to_acc}'")

        # Validate case reference
        cid = txn["case_id"]
        if cid and cid not in case_ids:
            raise ValueError(f"Transaction {tid} references unknown case_id: '{cid}'")

    # 4. Ground Truth Validation
    if not isinstance(ground_truth, dict):
        raise ValueError("Ground truth must be a dictionary.")

    for required_key in ["_metadata", "cases", "scenarios", "transactions_ground_truth"]:
        if required_key not in ground_truth:
            raise ValueError(f"Ground truth missing required top-level key: '{required_key}'")

    # Verify all ground truth case IDs exist in cases.csv
    for gt_cid, gt_case_data in ground_truth["cases"].items():
        if gt_cid not in case_ids:
            raise ValueError(f"Ground truth references unknown case_id: '{gt_cid}'")
        victim = gt_case_data.get("victim_account")
        if victim and victim not in account_ids:
            raise ValueError(f"Ground truth case {gt_cid} references unknown victim account '{victim}'")

    # Verify all ground truth transaction IDs exist in transactions.csv
    for gt_tid in ground_truth["transactions_ground_truth"].keys():
        if gt_tid not in transaction_ids:
            raise ValueError(f"Ground truth references unknown transaction_id: '{gt_tid}'")

    # Verify all required scenarios are covered
    gt_scenarios = ground_truth["scenarios"]
    for req_scen in REQUIRED_SCENARIOS:
        if req_scen not in gt_scenarios or len(gt_scenarios[req_scen]) == 0:
            raise ValueError(f"Required scenario '{req_scen}' is missing or has no associated transactions.")


def save_dataset(
    output_dir: Path,
    accounts: List[Dict[str, Any]],
    transactions: List[Dict[str, Any]],
    cases: List[Dict[str, Any]],
    ground_truth: Dict[str, Any],
) -> None:
    """Save validated dataset files to disk."""
    output_dir.mkdir(parents=True, exist_ok=True)

    # Save accounts.csv
    accounts_path = output_dir / "accounts.csv"
    with open(accounts_path, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=ACCOUNT_COLUMNS)
        writer.writeheader()
        writer.writerows(accounts)

    # Save transactions.csv
    transactions_path = output_dir / "transactions.csv"
    with open(transactions_path, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=TRANSACTION_COLUMNS)
        writer.writeheader()
        writer.writerows(transactions)

    # Save cases.csv
    cases_path = output_dir / "cases.csv"
    with open(cases_path, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CASE_COLUMNS)
        writer.writeheader()
        writer.writerows(cases)

    # Save ground_truth.json (Deterministic serialization)
    gt_path = output_dir / "ground_truth.json"
    with open(gt_path, mode="w", encoding="utf-8") as f:
        json.dump(ground_truth, f, indent=2, sort_keys=True)


def main() -> None:
    """CLI entrypoint for synthetic data generation."""
    parser = argparse.ArgumentParser(description="Smart-Freeze Synthetic Financial Data Generator")
    parser.add_argument("--seed", type=int, default=42, help="Deterministic random seed (default: 42)")
    parser.add_argument(
        "--output-dir",
        type=str,
        default="data/synthetic",
        help="Directory to save generated files (default: data/synthetic)",
    )
    args = parser.parse_args()

    print(f"Generating Smart-Freeze synthetic dataset with seed={args.seed}...")
    accounts, transactions, cases, ground_truth = generate_all_data(seed=args.seed)

    print("Validating generated records...")
    validate_dataset(accounts, transactions, cases, ground_truth)

    out_path = Path(args.output_dir)
    print(f"Writing outputs to {out_path.resolve()}...")
    save_dataset(out_path, accounts, transactions, cases, ground_truth)

    print("Generation complete:")
    print(f"  - Accounts: {len(accounts)} (written to {out_path / 'accounts.csv'})")
    print(f"  - Transactions: {len(transactions)} (written to {out_path / 'transactions.csv'})")
    print(f"  - Cases: {len(cases)} (written to {out_path / 'cases.csv'})")
    print(f"  - Ground Truth: {len(ground_truth['transactions_ground_truth'])} txns mapped (written to {out_path / 'ground_truth.json'})")


if __name__ == "__main__":
    main()
