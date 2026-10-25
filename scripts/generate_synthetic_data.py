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
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


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


def generate_default_fixture(
    seed: int = 42,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any]]:
    """Generate deterministic 3-case benchmark synthetic accounts, transactions, cases, and ground truth."""
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


def generate_scaled_dataset(
    seed: int = 42,
    num_accounts: int = 2000,
    num_cases: int = 60,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any]]:
    """Generate a scaled, deterministic synthetic financial dataset with lot-level ground truth.

    Supports:
    - Configurable scale via num_accounts and num_cases.
    - Salaried, gig, merchant, payment-aggregator, and mule accounts.
    - 30 days of normal background commerce, payroll, and pass-through settlement traffic.
    - Four scam families:
      * Family A: Layered chain across sequential mule hops.
      * Family B: Tiny-amount spray (smurfing/fan-out) to multiple destinations.
      * Family C: Heavy commingling in high-volume merchant / payment-aggregator pools.
      * Family D: Structuring below AML reporting thresholds (< 5,000,000 paise).
    - Hard cases:
      * Seasoned mules with long legitimate transaction history prior to scam activation.
      * Innocent payment aggregators with rapid commercial pass-through.
    - Lot-level ground truth: explicit seeded spending model independent of Proportional, FIFO, or LIBR.
    - Financial integrity: strictly conserved balances and nonnegative balances throughout.
    """
    rng = random.Random(seed)

    accounts: List[Dict[str, Any]] = []
    account_ids: Set[str] = set()
    balances: Dict[str, int] = {}
    clean_balances: Dict[str, int] = {}
    account_lots: Dict[str, Dict[str, int]] = {}
    withdrawn_lots: Dict[str, Dict[str, int]] = {}

    def add_acc(aid: str, atype: str, bal: int, hist_comp: bool = True) -> None:
        accounts.append({
            "account_id": aid,
            "account_type": atype,
            "opening_balance_paise": int(bal),
            "history_complete": bool(hist_comp),
        })
        account_ids.add(aid)
        balances[aid] = int(bal)
        clean_balances[aid] = int(bal)
        account_lots[aid] = {}

    # 1. Accounts Setup
    n_sal = max(1, int(num_accounts * 0.40))
    n_gig = max(1, int(num_accounts * 0.20))
    n_merch = max(1, int(num_accounts * 0.15))
    n_agg = max(1, int(num_accounts * 0.03))
    n_mule = max(1, int(num_accounts * 0.15))
    n_vic = max(1, num_accounts - (n_sal + n_gig + n_merch + n_agg + n_mule))

    # Salaried accounts (40%)
    for i in range(1, n_sal + 1):
        add_acc(f"ACC_SAL_{i:04d}", "salaried", rng.randint(2_000_000, 15_000_000), hist_comp=(i % 50 != 13))

    # Gig worker accounts (20%)
    for i in range(1, n_gig + 1):
        add_acc(f"ACC_GIG_{i:04d}", "gig", rng.randint(500_000, 4_000_000))

    # Merchant accounts (15%)
    for i in range(1, n_merch + 1):
        add_acc(f"ACC_MERCH_{i:04d}", "merchant", rng.randint(10_000_000, 100_000_000))

    # Payment aggregators (3%) - first 10 are designated innocent aggregators with fast pass-through
    for i in range(1, n_agg + 1):
        add_acc(f"ACC_AGG_{i:04d}", "payment_aggregator", rng.randint(50_000_000, 500_000_000))

    # Mule accounts (15%) - first 30 are designated seasoned mules with long history
    for i in range(1, n_mule + 1):
        is_seasoned = (i <= 30)
        bal = rng.randint(2_000_000, 5_000_000) if is_seasoned else rng.randint(100_000, 1_000_000)
        add_acc(f"ACC_MULE_{i:04d}", "mule", bal)

    # Victims (remaining ~7%)
    for i in range(1, n_vic + 1):
        add_acc(f"ACC_VIC_{i:04d}", "savings", rng.randint(40_000_000, 250_000_000))

    base_time = datetime.datetime(2026, 1, 1, 0, 0, 0, tzinfo=datetime.timezone.utc)
    raw_txns: List[Dict[str, Any]] = []

    def make_ts(day: int, hour: int, minute: int, second: int = 0) -> str:
        dt = base_time + datetime.timedelta(days=day, hours=hour, minutes=minute, seconds=second)
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    # 2. 30 Days of Normal Background Traffic
    # A. Salary payroll runs on Day 1, 15, 28
    for day in [1, 15, 28]:
        for i in range(1, n_sal + 1):
            sal_amt = rng.randint(3_000_000, 12_000_000)
            aid = f"ACC_SAL_{i:04d}"
            sec = rng.randint(0, 86399)
            raw_txns.append({
                "timestamp": (base_time + datetime.timedelta(days=day, seconds=sec)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "from_account": "EXT_EMPLOYER_PAYROLL",
                "to_account": aid,
                "amount_paise": sal_amt,
                "transaction_type": "salary_credit",
                "case_id": "",
                "evidence_status": "verified_legitimate",
                "_scenario": "ordinary_salary_and_business",
            })
            balances[aid] += sal_amt
            clean_balances[aid] += sal_amt

        # Seasoned mules receive normal salary credits on Days 1 and 15 (building deep legitimate history)
        if day in [1, 15]:
            n_seasoned = min(30, n_mule)
            for i in range(1, n_seasoned + 1):
                sal_amt = rng.randint(2_500_000, 6_000_000)
                aid = f"ACC_MULE_{i:04d}"
                sec = rng.randint(0, 86399)
                raw_txns.append({
                    "timestamp": (base_time + datetime.timedelta(days=day, seconds=sec)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "from_account": "EXT_EMPLOYER_PAYROLL",
                    "to_account": aid,
                    "amount_paise": sal_amt,
                    "transaction_type": "salary_credit",
                    "case_id": "",
                    "evidence_status": "verified_legitimate",
                    "_scenario": "ordinary_salary_and_business",
                })
                balances[aid] += sal_amt
                clean_balances[aid] += sal_amt

    # B. Gig payouts every 2 days
    for day in range(1, 30, 2):
        for i in range(1, n_gig + 1):
            if rng.random() < 0.70:
                amt = rng.randint(80_000, 350_000)
                aid = f"ACC_GIG_{i:04d}"
                sec = rng.randint(0, 86399)
                raw_txns.append({
                    "timestamp": (base_time + datetime.timedelta(days=day, seconds=sec)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "from_account": "EXT_GIG_PLATFORM",
                    "to_account": aid,
                    "amount_paise": amt,
                    "transaction_type": "deposit",
                    "case_id": "",
                    "evidence_status": "verified_legitimate",
                    "_scenario": "ordinary_salary_and_business",
                })
                balances[aid] += amt
                clean_balances[aid] += amt

    # C. Daily retail commerce & fast pass-through aggregator traffic
    for day in range(1, 30):
        # Consumer payments to merchants
        daily_retail_count = min(350, max(50, num_accounts // 8))
        for _ in range(daily_retail_count):
            sender_id = f"ACC_SAL_{rng.randint(1, n_sal):04d}" if rng.random() < 0.65 else f"ACC_GIG_{rng.randint(1, n_gig):04d}"
            # Seasoned mules also perform normal shopping transactions
            if rng.random() < 0.05 and n_mule > 0:
                sender_id = f"ACC_MULE_{rng.randint(1, min(30, n_mule)):04d}"
            merch_id = f"ACC_MERCH_{rng.randint(1, n_merch):04d}"
            amt = rng.randint(15_000, 250_000)
            if clean_balances[sender_id] > amt + 100_000:
                sec = rng.randint(0, 86399)
                raw_txns.append({
                    "timestamp": (base_time + datetime.timedelta(days=day, seconds=sec)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "from_account": sender_id,
                    "to_account": merch_id,
                    "amount_paise": amt,
                    "transaction_type": "merchant_payment",
                    "case_id": "",
                    "evidence_status": "verified_legitimate",
                    "_scenario": "merchant_multiple_customers",
                })
                balances[sender_id] -= amt
                clean_balances[sender_id] -= amt
                balances[merch_id] += amt
                clean_balances[merch_id] += amt

        # Fast pass-through settlements for innocent aggregators (ACC_AGG_0001 to ACC_AGG_0010)
        n_fast_agg = min(10, n_agg)
        for agg_idx in range(1, n_fast_agg + 1):
            agg_id = f"ACC_AGG_{agg_idx:04d}"
            dep_amt = rng.randint(5_000_000, 25_000_000)
            sec_in = rng.randint(0, 40000)
            raw_txns.append({
                "timestamp": (base_time + datetime.timedelta(days=day, seconds=sec_in)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "from_account": "EXT_GATEWAY_IN",
                "to_account": agg_id,
                "amount_paise": dep_amt,
                "transaction_type": "deposit",
                "case_id": "",
                "evidence_status": "verified_legitimate",
                "_scenario": "ordinary_salary_and_business",
            })
            balances[agg_id] += dep_amt
            clean_balances[agg_id] += dep_amt

            # Fast pass-through settlement sweep forward to merchant within 2 hours
            sec_out = sec_in + rng.randint(1800, 7200)
            settle_amt = int(dep_amt * 0.95)
            merch_id = f"ACC_MERCH_{rng.randint(1, n_merch):04d}"
            raw_txns.append({
                "timestamp": (base_time + datetime.timedelta(days=day, seconds=sec_out)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "from_account": agg_id,
                "to_account": merch_id,
                "amount_paise": settle_amt,
                "transaction_type": "transfer",
                "case_id": "",
                "evidence_status": "verified_legitimate",
                "_scenario": "ordinary_salary_and_business",
            })
            balances[agg_id] -= settle_amt
            clean_balances[agg_id] -= settle_amt
            balances[merch_id] += settle_amt
            clean_balances[merch_id] += settle_amt

    # 3. Scam Cases from Four Families with Lot-Level Ground Truth
    cases: List[Dict[str, Any]] = []
    cases_ground_truth: Dict[str, Any] = {}
    txn_ground_truth: Dict[str, Any] = {}
    scenario_tracking: Dict[str, List[str]] = {
        "ordinary_salary_and_business": [],
        "merchant_multiple_customers": [],
        "family_a_layered_chain": [],
        "family_b_tiny_amount_spray": [],
        "family_c_heavy_commingling": [],
        "family_d_structuring_below_threshold": [],
    }

    # Explicit seeded lot-spending model function
    def move_lots(
        from_acc: str,
        to_acc: str,
        txn_id: str,
        case_id: str,
        amount_needed: int,
        mode: str = "greedy",
    ) -> int:
        avail_lots = {lid: amt for lid, amt in account_lots[from_acc].items() if lid.startswith(f"LOT-{case_id}-")}
        transferred: Dict[str, int] = {}
        rem = amount_needed

        if mode == "commingled_seeded":
            # Seeded lot drawdown: takes 40-70% of available lots to model commingling independently of FIFO/LIBR
            ratio = 0.50 + (rng.random() * 0.20 - 0.10)
            target_from_lots = min(rem, max(1, int(sum(avail_lots.values()) * ratio)))
            rem = target_from_lots

        for lid in sorted(avail_lots.keys()):
            if rem <= 0:
                break
            cur_amt = avail_lots[lid]
            take = min(cur_amt, rem)
            transferred[lid] = take
            account_lots[from_acc][lid] -= take
            if account_lots[from_acc][lid] == 0:
                del account_lots[from_acc][lid]
            rem -= take

        total_stolen = sum(transferred.values())
        if to_acc.startswith("EXT_"):
            if to_acc not in withdrawn_lots:
                withdrawn_lots[to_acc] = {}
            for lid, amt in transferred.items():
                withdrawn_lots[to_acc][lid] = withdrawn_lots[to_acc].get(lid, 0) + amt
        else:
            for lid, amt in transferred.items():
                account_lots[to_acc][lid] = account_lots[to_acc].get(lid, 0) + amt

        if transferred:
            txn_ground_truth[txn_id] = {
                "case_id": case_id,
                "transferred_lots": transferred,
                "suspected_amount_paise": total_stolen,
            }
        return total_stolen

    case_families = ["family_a", "family_b", "family_c", "family_d"]
    for case_num in range(1, num_cases + 1):
        cid = f"CASE-2026-{case_num:03d}"
        family = case_families[(case_num - 1) % 4]
        day = 14 + ((case_num - 1) % 14)  # Days 14 to 27
        victim_id = f"ACC_VIC_{((case_num - 1) % n_vic) + 1:04d}"
        stolen_amt = rng.randint(80_000, 350_000) * 100

        # Guarantee victim has sufficient liquidity
        if balances[victim_id] < stolen_amt + 5_000_000:
            balances[victim_id] += (stolen_amt + 10_000_000)
            clean_balances[victim_id] += (stolen_amt + 10_000_000)

        # Create discrete lots for this case
        num_lots = rng.randint(2, 4)
        lot_sizes: List[int] = []
        rem_lot = stolen_amt
        for l_idx in range(num_lots - 1):
            sz = int((stolen_amt // num_lots) * (0.80 + rng.random() * 0.40))
            sz = min(sz, rem_lot - (num_lots - l_idx - 1) * 1000)
            lot_sizes.append(sz)
            rem_lot -= sz
        lot_sizes.append(rem_lot)

        source_lots_meta: List[Dict[str, Any]] = []
        for l_idx, l_sz in enumerate(lot_sizes, start=1):
            lid = f"LOT-{cid}-{l_idx:02d}"
            account_lots[victim_id][lid] = l_sz
            source_lots_meta.append({
                "lot_id": lid,
                "original_amount_paise": l_sz,
                "source_case_id": cid,
            })

        rep_date = make_ts(day, 10, 0)
        cases.append({
            "case_id": cid,
            "reported_date": rep_date,
            "reported_amount_paise": stolen_amt,
            "status": "under_investigation",
        })

        if family == "family_a":
            # Family A: Layered Chain (Victim -> Seasoned Mule 1 -> Mule 2 -> Mule 3 -> Outflow)
            seasoned_count = min(30, n_mule)
            mule1 = f"ACC_MULE_{(case_num % seasoned_count) + 1:04d}"  # Mule with long history!
            mule2 = f"ACC_MULE_{seasoned_count + (case_num % max(1, n_mule - seasoned_count - 10)) + 1:04d}"
            mule3 = f"ACC_MULE_{min(n_mule, int(mule2.split('_')[-1]) + 5):04d}"

            # Txn 1: Victim -> Mule 1
            tid_1 = f"TXN_SC_{case_num:03d}_1"
            raw_txns.append({
                "timestamp": make_ts(day, 10, 15),
                "from_account": victim_id,
                "to_account": mule1,
                "amount_paise": stolen_amt,
                "transaction_type": "transfer",
                "case_id": cid,
                "evidence_status": "suspected_fraud",
                "_scenario": "family_a_layered_chain",
                "_temp_id": tid_1,
            })
            balances[victim_id] -= stolen_amt
            balances[mule1] += stolen_amt
            move_lots(victim_id, mule1, tid_1, cid, stolen_amt)

            # Txn 2: Mule 1 forwards 85% to Mule 2
            fwd1 = int(stolen_amt * 0.85)
            tid_2 = f"TXN_SC_{case_num:03d}_2"
            raw_txns.append({
                "timestamp": make_ts(day, 12, 30),
                "from_account": mule1,
                "to_account": mule2,
                "amount_paise": fwd1,
                "transaction_type": "transfer",
                "case_id": cid,
                "evidence_status": "suspected_fraud",
                "_scenario": "family_a_layered_chain",
                "_temp_id": tid_2,
            })
            balances[mule1] -= fwd1
            balances[mule2] += fwd1
            move_lots(mule1, mule2, tid_2, cid, fwd1)

            # Txn 3: Mule 2 forwards 80% to Mule 3
            fwd2 = int(fwd1 * 0.80)
            tid_3 = f"TXN_SC_{case_num:03d}_3"
            raw_txns.append({
                "timestamp": make_ts(day, 15, 0),
                "from_account": mule2,
                "to_account": mule3,
                "amount_paise": fwd2,
                "transaction_type": "transfer",
                "case_id": cid,
                "evidence_status": "suspected_fraud",
                "_scenario": "family_a_layered_chain",
                "_temp_id": tid_3,
            })
            balances[mule2] -= fwd2
            balances[mule3] += fwd2
            move_lots(mule2, mule3, tid_3, cid, fwd2)

            # Txn 4: Mule 3 withdraws 75% to cash ATM
            wth = int(fwd2 * 0.75)
            tid_4 = f"TXN_SC_{case_num:03d}_4"
            raw_txns.append({
                "timestamp": make_ts(day, 17, 45),
                "from_account": mule3,
                "to_account": "EXT_CASH_ATM",
                "amount_paise": wth,
                "transaction_type": "withdrawal",
                "case_id": cid,
                "evidence_status": "suspected_fraud",
                "_scenario": "family_a_layered_chain",
                "_temp_id": tid_4,
            })
            balances[mule3] -= wth
            move_lots(mule3, "EXT_CASH_ATM", tid_4, cid, wth)

        elif family == "family_b":
            # Family B: Tiny-Amount Spray (Smurfing / Fan-Out to multiple mules)
            sprayer = f"ACC_MULE_{min(n_mule, 40 + (case_num % max(1, n_mule - 50))):04d}"
            tid_1 = f"TXN_SC_{case_num:03d}_1"
            raw_txns.append({
                "timestamp": make_ts(day, 9, 30),
                "from_account": victim_id,
                "to_account": sprayer,
                "amount_paise": stolen_amt,
                "transaction_type": "transfer",
                "case_id": cid,
                "evidence_status": "suspected_fraud",
                "_scenario": "family_b_tiny_amount_spray",
                "_temp_id": tid_1,
            })
            balances[victim_id] -= stolen_amt
            balances[sprayer] += stolen_amt
            move_lots(victim_id, sprayer, tid_1, cid, stolen_amt)

            # Fan out to 6 destination mules
            k_splits = 6
            sub_amt = stolen_amt // k_splits
            for k in range(k_splits):
                amt_k = sub_amt if k < k_splits - 1 else (stolen_amt - sub_amt * (k_splits - 1))
                dest_mule = f"ACC_MULE_{((100 + case_num * 6 + k) % n_mule) + 1:04d}"
                tid_k = f"TXN_SC_{case_num:03d}_SP_{k}"
                raw_txns.append({
                    "timestamp": make_ts(day, 11, 10 + k * 5),
                    "from_account": sprayer,
                    "to_account": dest_mule,
                    "amount_paise": amt_k,
                    "transaction_type": "transfer",
                    "case_id": cid,
                    "evidence_status": "suspected_fraud",
                    "_scenario": "family_b_tiny_amount_spray",
                    "_temp_id": tid_k,
                })
                balances[sprayer] -= amt_k
                balances[dest_mule] += amt_k
                move_lots(sprayer, dest_mule, tid_k, cid, amt_k)

                # Destination mule withdraws half at ATM
                if k % 2 == 0:
                    w_amt = amt_k // 2
                    tid_w = f"TXN_SC_{case_num:03d}_W_{k}"
                    raw_txns.append({
                        "timestamp": make_ts(day, 14, 20 + k * 4),
                        "from_account": dest_mule,
                        "to_account": "EXT_CASH_ATM",
                        "amount_paise": w_amt,
                        "transaction_type": "withdrawal",
                        "case_id": cid,
                        "evidence_status": "suspected_fraud",
                        "_scenario": "family_b_tiny_amount_spray",
                        "_temp_id": tid_w,
                    })
                    balances[dest_mule] -= w_amt
                    move_lots(dest_mule, "EXT_CASH_ATM", tid_w, cid, w_amt)

        elif family == "family_c":
            # Family C: Heavy Commingling (Victim -> Innocent Fast Pass-Through Aggregator -> Merchants)
            n_fast_agg = min(10, n_agg)
            agg_id = f"ACC_AGG_{((case_num - 1) % n_fast_agg) + 1:04d}"  # Innocent Aggregator!
            tid_1 = f"TXN_SC_{case_num:03d}_1"
            raw_txns.append({
                "timestamp": make_ts(day, 10, 0),
                "from_account": victim_id,
                "to_account": agg_id,
                "amount_paise": stolen_amt,
                "transaction_type": "transfer",
                "case_id": cid,
                "evidence_status": "suspected_fraud",
                "_scenario": "family_c_heavy_commingling",
                "_temp_id": tid_1,
            })
            balances[victim_id] -= stolen_amt
            balances[agg_id] += stolen_amt
            move_lots(victim_id, agg_id, tid_1, cid, stolen_amt)

            # Commingled settlements to merchants
            merch_1 = f"ACC_MERCH_{((case_num * 2) % n_merch) + 1:04d}"
            merch_2 = f"ACC_MERCH_{((case_num * 2 + 1) % n_merch) + 1:04d}"
            s_amt1 = int(stolen_amt * 0.50)
            s_amt2 = int(stolen_amt * 0.35)

            tid_s1 = f"TXN_SC_{case_num:03d}_S1"
            raw_txns.append({
                "timestamp": make_ts(day, 11, 45),
                "from_account": agg_id,
                "to_account": merch_1,
                "amount_paise": s_amt1,
                "transaction_type": "transfer",
                "case_id": cid,
                "evidence_status": "suspected_fraud",
                "_scenario": "family_c_heavy_commingling",
                "_temp_id": tid_s1,
            })
            balances[agg_id] -= s_amt1
            balances[merch_1] += s_amt1
            move_lots(agg_id, merch_1, tid_s1, cid, s_amt1, mode="commingled_seeded")

            tid_s2 = f"TXN_SC_{case_num:03d}_S2"
            raw_txns.append({
                "timestamp": make_ts(day, 12, 15),
                "from_account": agg_id,
                "to_account": merch_2,
                "amount_paise": s_amt2,
                "transaction_type": "transfer",
                "case_id": cid,
                "evidence_status": "suspected_fraud",
                "_scenario": "family_c_heavy_commingling",
                "_temp_id": tid_s2,
            })
            balances[agg_id] -= s_amt2
            balances[merch_2] += s_amt2
            move_lots(agg_id, merch_2, tid_s2, cid, s_amt2, mode="commingled_seeded")

        elif family == "family_d":
            # Family D: Structuring Below a Threshold (< 5,000,000 paise / ₹50,000 INR)
            threshold_paise = 5_000_000
            mule_d1 = f"ACC_MULE_{min(n_mule, 180 + (case_num % max(1, n_mule - 180))):04d}"
            mule_d2 = f"ACC_MULE_{min(n_mule, 220 + (case_num % max(1, n_mule - 220))):04d}"

            # Partition into chunks strictly < 5,000,000 paise
            chunk_amts: List[int] = []
            rem_d = stolen_amt
            while rem_d > 0:
                take = min(rem_d, rng.randint(4_200_000, 4_900_000))
                if rem_d - take > 0 and rem_d - take < 500_000:
                    take = rem_d // 2
                take = min(take, 4_950_000)
                chunk_amts.append(take)
                rem_d -= take

            for idx, c_amt in enumerate(chunk_amts):
                assert c_amt < threshold_paise, f"Structured chunk {c_amt} exceeds threshold {threshold_paise}"
                hour = 9 + (idx * 2) % 10
                minute = (idx * 17) % 60
                tid_d = f"TXN_SC_{case_num:03d}_D_{idx}"
                raw_txns.append({
                    "timestamp": make_ts(day, hour, minute),
                    "from_account": victim_id,
                    "to_account": mule_d1,
                    "amount_paise": c_amt,
                    "transaction_type": "transfer",
                    "case_id": cid,
                    "evidence_status": "suspected_fraud",
                    "_scenario": "family_d_structuring_below_threshold",
                    "_temp_id": tid_d,
                })
                balances[victim_id] -= c_amt
                balances[mule_d1] += c_amt
                move_lots(victim_id, mule_d1, tid_d, cid, c_amt)

                tid_f = f"TXN_SC_{case_num:03d}_F_{idx}"
                raw_txns.append({
                    "timestamp": make_ts(day, hour + 1, (minute + 5) % 60),
                    "from_account": mule_d1,
                    "to_account": mule_d2,
                    "amount_paise": c_amt,
                    "transaction_type": "transfer",
                    "case_id": cid,
                    "evidence_status": "suspected_fraud",
                    "_scenario": "family_d_structuring_below_threshold",
                    "_temp_id": tid_f,
                })
                balances[mule_d1] -= c_amt
                balances[mule_d2] += c_amt
                move_lots(mule_d1, mule_d2, tid_f, cid, c_amt)

        # Assemble case ground truth entry
        retained_by_acc: Dict[str, Dict[str, int]] = {}
        for acc in account_ids:
            acc_case_lots = {lid: amt for lid, amt in account_lots[acc].items() if lid.startswith(f"LOT-{cid}-")}
            if acc_case_lots:
                retained_by_acc[acc] = acc_case_lots

        withdrawn_by_ext: Dict[str, Dict[str, int]] = {}
        for ext, l_dict in withdrawn_lots.items():
            ext_case_lots = {lid: amt for lid, amt in l_dict.items() if lid.startswith(f"LOT-{cid}-")}
            if ext_case_lots:
                withdrawn_by_ext[ext] = ext_case_lots

        total_ret = sum(sum(d.values()) for d in retained_by_acc.values())
        total_wth = sum(sum(d.values()) for d in withdrawn_by_ext.values())

        # Strict invariant: total_ret + total_wth <= stolen_amt
        assert total_ret + total_wth <= stolen_amt, (
            f"Case {cid} ground truth lots ({total_ret + total_wth} paise) exceed stolen amount ({stolen_amt} paise)"
        )

        cases_ground_truth[cid] = {
            "victim_account": victim_id,
            "origin_transfer_paise": stolen_amt,
            "family": family,
            "source_lots": source_lots_meta,
            "retained_lots": retained_by_acc,
            "withdrawn_lots": withdrawn_by_ext,
            "total_retained_paise": total_ret,
            "total_withdrawn_paise": total_wth,
            "expected_allocations": {
                acc: {
                    "retained_suspected_paise": sum(l_dict.values()),
                }
                for acc, l_dict in retained_by_acc.items()
            },
        }

    # Sort transactions deterministically and assign sequential IDs
    raw_txns.sort(key=lambda x: x["timestamp"])
    transactions: List[Dict[str, Any]] = []
    final_txn_ground_truth: Dict[str, Any] = {}

    for idx, t in enumerate(raw_txns, start=1):
        tid = f"TXN_{idx:06d}"
        t["transaction_id"] = tid
        temp_id = t.pop("_temp_id", None)
        if temp_id and temp_id in txn_ground_truth:
            final_txn_ground_truth[tid] = txn_ground_truth[temp_id]
        scen = t.pop("_scenario", "ordinary_salary_and_business")
        if scen in scenario_tracking:
            scenario_tracking[scen].append(tid)
        transactions.append(t)

    # Sort accounts by account_id and cases by case_id
    accounts.sort(key=lambda x: x["account_id"])
    cases.sort(key=lambda x: x["case_id"])

    ground_truth = {
        "_metadata": {
            "dataset_type": "synthetic_ground_truth",
            "generator_version": "2.0.0-scaled",
            "random_seed": seed,
            "num_accounts": len(accounts),
            "num_cases": len(cases),
            "num_transactions": len(transactions),
            "warning": (
                "CONFIDENTIAL EVALUATION DATA: Tracing and scoring algorithms must "
                "NEVER read this file directly. Strictly for evaluation/benchmark modules."
            ),
            "generated_at": "2026-01-31T23:59:59Z",
        },
        "cases": cases_ground_truth,
        "scenarios": scenario_tracking,
        "transactions_ground_truth": final_txn_ground_truth,
    }

    return accounts, transactions, cases, ground_truth


def generate_all_data(
    seed: int = 42,
    num_accounts: Optional[int] = None,
    num_cases: Optional[int] = None,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any]]:
    """Generate deterministic synthetic financial dataset.

    When called with no scale arguments (num_accounts is None and num_cases is None),
    generates the canonical 3-case benchmark test fixture for backward compatibility.
    When num_accounts or num_cases is specified, generates a scaled synthetic dataset.
    """
    if num_accounts is None and num_cases is None:
        return generate_default_fixture(seed=seed)
    n_acc = num_accounts if num_accounts is not None else 2000
    n_cases = num_cases if num_cases is not None else 60
    return generate_scaled_dataset(seed=seed, num_accounts=n_acc, num_cases=n_cases)


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

    is_scaled = len(accounts) > 50 or len(cases) > 5
    if not is_scaled:
        if not (30 <= len(accounts) <= 50):
            raise ValueError(f"Account count must be within 30-50, got {len(accounts)}")
    else:
        if len(accounts) < 50:
            raise ValueError(f"Scaled account count must be >= 50, got {len(accounts)}")

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
    if not is_scaled:
        if not (100 <= len(transactions) <= 300):
            raise ValueError(f"Transaction count must be within 100-300, got {len(transactions)}")
    else:
        if len(transactions) < 100:
            raise ValueError(f"Scaled transaction count must be >= 100, got {len(transactions)}")

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

    # 4. Strict Financial Conservation and Non-negative Balances Check
    sim_balances: Dict[str, int] = {a["account_id"]: a["opening_balance_paise"] for a in accounts}
    for txn in transactions:
        from_acc = txn["from_account"]
        to_acc = txn["to_account"]
        amt = txn["amount_paise"]
        if not from_acc.startswith("EXT_"):
            sim_balances[from_acc] -= amt
            if sim_balances[from_acc] < 0:
                raise ValueError(
                    f"Account '{from_acc}' reached negative balance ({sim_balances[from_acc]} paise) "
                    f"at transaction '{txn['transaction_id']}'"
                )
        if not to_acc.startswith("EXT_"):
            sim_balances[to_acc] += amt

    for aid, final_bal in sim_balances.items():
        if final_bal < 0:
            raise ValueError(f"Account '{aid}' has negative final balance: {final_bal} paise")

    # 5. Ground Truth Validation
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

        # Invariant: ground truth lot sum <= reported stolen amount
        if "total_retained_paise" in gt_case_data and "total_withdrawn_paise" in gt_case_data:
            total_lots = gt_case_data["total_retained_paise"] + gt_case_data["total_withdrawn_paise"]
            rep_amt = gt_case_data.get("origin_transfer_paise") or gt_case_data.get("reported_amount_paise", 0)
            if total_lots > rep_amt:
                raise ValueError(
                    f"Case {gt_cid} ground truth lots sum ({total_lots} paise) exceeds "
                    f"reported stolen amount ({rep_amt} paise)"
                )

    # Verify all ground truth transaction IDs exist in transactions.csv
    for gt_tid in ground_truth["transactions_ground_truth"].keys():
        if gt_tid not in transaction_ids:
            raise ValueError(f"Ground truth references unknown transaction_id: '{gt_tid}'")

    # Verify scenarios/families are covered
    gt_scenarios = ground_truth["scenarios"]
    if not is_scaled:
        for req_scen in REQUIRED_SCENARIOS:
            if req_scen not in gt_scenarios or len(gt_scenarios[req_scen]) == 0:
                raise ValueError(f"Required scenario '{req_scen}' is missing or has no associated transactions.")
    else:
        scaled_families = [
            "family_a_layered_chain",
            "family_b_tiny_amount_spray",
            "family_c_heavy_commingling",
            "family_d_structuring_below_threshold",
        ]
        for fam in scaled_families:
            if fam not in gt_scenarios or len(gt_scenarios[fam]) == 0:
                raise ValueError(f"Required scam family '{fam}' is missing or has no linked transactions.")


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
    parser.add_argument("--accounts", type=int, default=None, help="Number of accounts for scaled generation (default: 3-case benchmark fixture)")
    parser.add_argument("--cases", type=int, default=None, help="Number of fraud cases for scaled generation (default: 3-case benchmark fixture)")
    args = parser.parse_args()

    scale_desc = f"scale: accounts={args.accounts or 2000}, cases={args.cases or 60}" if (args.accounts or args.cases) else "3-case benchmark fixture"
    print(f"Generating Smart-Freeze synthetic dataset ({scale_desc}) with seed={args.seed}...")
    t0 = time.time()
    accounts, transactions, cases, ground_truth = generate_all_data(
        seed=args.seed,
        num_accounts=args.accounts,
        num_cases=args.cases,
    )
    gen_time = time.time() - t0

    print(f"Validating generated records ({gen_time:.3f}s generation time)...")
    validate_dataset(accounts, transactions, cases, ground_truth)

    out_path = Path(args.output_dir)
    print(f"Writing outputs to {out_path.resolve()}...")
    save_dataset(out_path, accounts, transactions, cases, ground_truth)
    total_time = time.time() - t0

    print("Generation complete:")
    print(f"  - Accounts: {len(accounts)} (written to {out_path / 'accounts.csv'})")
    print(f"  - Transactions: {len(transactions)} (written to {out_path / 'transactions.csv'})")
    print(f"  - Cases: {len(cases)} (written to {out_path / 'cases.csv'})")
    print(f"  - Ground Truth: {len(ground_truth['transactions_ground_truth'])} txns mapped (written to {out_path / 'ground_truth.json'})")
    print(f"  - Measured Generation Time: {gen_time:.3f}s (Total Elapsed: {total_time:.3f}s)")


if __name__ == "__main__":
    main()
