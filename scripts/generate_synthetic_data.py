#!/usr/bin/env python3
"""Smart-Freeze Deterministic Synthetic Financial Ledger Generator.

Generates a realistic, controlled, deterministic synthetic financial dataset for evaluating
Smart-Freeze's fund-tracing algorithms (FIFO, Proportional, LIBR) and Consensus Lien
against verified ground truth.

Scale presets:
- 'demo': 3-case benchmark fixture (~38 accounts, ~119 transactions, 3 cases)
- 'scaled': Full 12-month investigation dataset (25,000–35,000 transactions, ~2,400 accounts, ~120 cases)
  covering all 18 scenario families with lot-level ground truth and strict balance conservation.

Conventions:
- Amounts: All monetary values are represented as integer paise (1 INR = 100 paise).
  Floating-point currency values are strictly prohibited.
- Timestamps: ISO 8601 strings in UTC (YYYY-MM-DDTHH:MM:SSZ).
- Internal Accounts: Prefixed with 'ACC_' and listed in accounts.csv.
- External Counterparties: Prefixed with 'EXT_' (e.g., EXT_CASH_ATM, EXT_EMPLOYER_PAYROLL).
  External counterparties represent boundary entities outside the closed ledger.
- Cases: Distinct fraud complaints identified by 'CASE-YYYY-NNN'. Transactions unrelated
  to a fraud investigation have an empty case_id ("").
- Ground Truth: Saved separately to data/evaluation/ground_truth.json and data/synthetic/ground_truth.json.
  Tracing and scoring algorithms must never read ground truth.
"""

from __future__ import annotations

import argparse
import csv
import datetime
import json
import math
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

DEMO_SCENARIOS = [
    "ordinary_salary_and_business",
    "direct_onward_transfer",
    "split_transfers_smurfing",
    "commingling_funds",
    "partial_withdrawals_leaving_balance",
    "merchant_multiple_customers",
    "incomplete_history_account",
]

REQUIRED_SCENARIOS = DEMO_SCENARIOS

ALL_18_SCENARIO_FAMILIES = [
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


def generate_default_fixture(
    seed: int = 42,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any]]:
    """Generate deterministic 3-case benchmark synthetic accounts, transactions, cases, and ground truth."""
    rng = random.Random(seed)

    accounts: List[Dict[str, Any]] = []

    def add_acc(acc_id: str, acc_type: str, bal_paise: int, hist_comp: bool = True) -> None:
        accounts.append({
            "account_id": acc_id,
            "account_type": acc_type,
            "opening_balance_paise": int(bal_paise),
            "history_complete": bool(hist_comp),
        })

    # Victims of fraud complaints
    add_acc("ACC_VICTIM_01", "savings", 25_000_000)
    add_acc("ACC_VICTIM_02", "current", 30_000_000)
    add_acc("ACC_VICTIM_03", "savings", 40_000_000)

    # Case 1: Direct transfer, commingling & layer 2
    add_acc("ACC_MULE_DIRECT_01", "savings", 500_000)
    add_acc("ACC_COMMINGLED_01", "current", 5_000_000)
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
    add_acc("ACC_INCOMPLETE_01", "savings", 0, hist_comp=False)

    # Legitimate corporate entity & employees
    add_acc("ACC_CORP_PAYROLL", "corporate", 150_000_000)
    for i in range(1, 9):
        add_acc(f"ACC_EMP_{i:02d}", "salary", rng.randint(200_000, 1_000_000))
    add_acc("ACC_LANDLORD_01", "current", 10_000_000)

    # Legitimate merchant & retail customers
    add_acc("ACC_MERCHANT_01", "merchant", 20_000_000)
    for i in range(1, 11):
        add_acc(f"ACC_CUST_{i:02d}", "savings", rng.randint(1_000_000, 3_000_000))

    # General personal background accounts
    add_acc("ACC_PERSONAL_01", "savings", 3_000_000)
    add_acc("ACC_PERSONAL_02", "savings", 3_000_000)
    add_acc("ACC_PERSONAL_03", "current", 3_000_000)

    cases: List[Dict[str, Any]] = [
        {
            "case_id": "CASE-2026-001",
            "reported_date": "2026-01-16T10:00:00Z",
            "reported_amount_paise": 10_000_000,
            "status": "under_investigation",
        },
        {
            "case_id": "CASE-2026-002",
            "reported_date": "2026-01-18T14:30:00Z",
            "reported_amount_paise": 15_000_000,
            "status": "under_investigation",
        },
        {
            "case_id": "CASE-2026-003",
            "reported_date": "2026-01-20T09:15:00Z",
            "reported_amount_paise": 20_000_000,
            "status": "under_investigation",
        },
    ]

    raw_txns: List[Dict[str, Any]] = []
    base_time = datetime.datetime(2026, 1, 10, 8, 0, 0, tzinfo=datetime.timezone.utc)

    def txn_time(day_offset: int, hour: int, minute: int, second: int = 0) -> str:
        dt = base_time + datetime.timedelta(days=day_offset, hours=hour, minutes=minute, seconds=second)
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    # A. Case 1
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
    raw_txns.append({
        "timestamp": txn_time(1, 10, 0),
        "from_account": "EXT_CLIENT_PAYMENT",
        "to_account": "ACC_COMMINGLED_01",
        "amount_paise": 4_000_000,
        "transaction_type": "deposit",
        "case_id": "",
        "evidence_status": "verified_legitimate",
        "_scenario": "commingling_funds",
    })
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

    # B. Case 2
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

    # C. Case 3
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

    # D. Ordinary Salary & Business Activities
    for cycle_offset in [0, 14]:
        for emp_idx in range(1, 9):
            emp_id = f"ACC_EMP_{emp_idx:02d}"
            raw_txns.append({
                "timestamp": txn_time(cycle_offset, 8, emp_idx * 5),
                "from_account": "ACC_CORP_PAYROLL",
                "to_account": emp_id,
                "amount_paise": 5_000_000,
                "transaction_type": "salary_credit",
                "case_id": "",
                "evidence_status": "verified_legitimate",
                "_scenario": "ordinary_salary_and_business",
            })
            raw_txns.append({
                "timestamp": txn_time(cycle_offset + 1, 10, emp_idx * 5),
                "from_account": emp_id,
                "to_account": "ACC_LANDLORD_01",
                "amount_paise": 1_500_000,
                "transaction_type": "transfer",
                "case_id": "",
                "evidence_status": "verified_legitimate",
                "_scenario": "ordinary_salary_and_business",
            })
            raw_txns.append({
                "timestamp": txn_time(cycle_offset + 2, 12, emp_idx * 5),
                "from_account": emp_id,
                "to_account": "EXT_UTILITY_GATEWAY",
                "amount_paise": 350_000,
                "transaction_type": "transfer",
                "case_id": "",
                "evidence_status": "verified_legitimate",
                "_scenario": "ordinary_salary_and_business",
            })

    # E. Merchant payments
    for day in [1, 2, 3, 4]:
        for cust_idx in range(1, 11):
            cust_id = f"ACC_CUST_{cust_idx:02d}"
            amt = (cust_idx * 15_000) + (day * 10_000)
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

    raw_txns.sort(key=lambda t: (t["timestamp"], t["from_account"], t["to_account"], t["amount_paise"]))

    transactions: List[Dict[str, Any]] = []
    ground_truth_txns: Dict[str, Any] = {}
    scenario_tracking: Dict[str, List[str]] = {s: [] for s in DEMO_SCENARIOS}

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

        if scenario in scenario_tracking:
            scenario_tracking[scenario].append(txn_id)

        is_suspected = bool(raw["case_id"])
        ground_truth_txns[txn_id] = {
            "contains_suspected_funds": is_suspected,
            "suspected_amount_paise": int(raw["amount_paise"]) if is_suspected else 0,
            "legitimate_amount_paise": 0 if is_suspected else int(raw["amount_paise"]),
            "source_case_id": raw["case_id"],
            "scenario": scenario,
        }

    ground_truth: Dict[str, Any] = {
        "_metadata": {
            "dataset_type": "synthetic_ground_truth",
            "generator_version": "1.0.0-demo",
            "random_seed": seed,
            "num_accounts": len(accounts),
            "num_cases": len(cases),
            "num_transactions": len(transactions),
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
                        "commingled_with_legitimate_paise": 9_000_000,
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
    num_accounts: int = 2400,
    num_cases: int = 120,
    days: int = 365,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any]]:
    """Generate a scaled, 12-month deterministic synthetic financial dataset (25k-35k transactions).

    Features:
    - 2,000–3,000 accounts across realistic banking archetypes.
    - 12 months (365 days) of timestamps.
    - Calibrated transaction volume: ~25,000–32,000 transactions.
    - Nonconstant log-normal/gamma amount distributions with realistic minor units (paise).
    - 18 comprehensive scenario families.
    - Strict financial conservation: Opening + Ext Inflows - Ext Outflows == Final Balances.
    - Zero negative balances at any point in simulation.
    - Lot-level ground truth tracking.
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

    # 1. Accounts Setup (~2400 accounts)
    n_sal = int(num_accounts * 0.40)       # 960 salaried
    n_gig = int(num_accounts * 0.20)       # 480 gig workers
    n_merch = int(num_accounts * 0.15)     # 360 merchants
    n_hv_merch = int(num_accounts * 0.02)  # 48 high volume merchants
    n_agg = int(num_accounts * 0.03)       # 72 payment aggregators
    n_wlt = int(num_accounts * 0.03)       # 72 digital wallets / PPI
    n_dorm = int(num_accounts * 0.04)      # 96 dormant accounts
    n_inter = int(num_accounts * 0.01)     # 24 intermediary accounts
    n_mule = int(num_accounts * 0.10)      # 240 mule accounts
    n_vic = num_accounts - (n_sal + n_gig + n_merch + n_hv_merch + n_agg + n_wlt + n_dorm + n_inter + n_mule)

    for i in range(1, n_sal + 1):
        add_acc(f"ACC_SAL_{i:04d}", "salaried", rng.randint(2_000_000, 15_000_000), hist_comp=(i % 35 != 7))
    for i in range(1, n_gig + 1):
        add_acc(f"ACC_GIG_{i:04d}", "gig", rng.randint(500_000, 4_000_000))
    for i in range(1, n_merch + 1):
        add_acc(f"ACC_MERCH_{i:04d}", "merchant", rng.randint(10_000_000, 100_000_000))
    for i in range(1, n_hv_merch + 1):
        add_acc(f"ACC_HV_MERCH_{i:04d}", "high_volume_merchant", rng.randint(50_000_000, 250_000_000))
    for i in range(1, n_agg + 1):
        add_acc(f"ACC_AGG_{i:04d}", "payment_aggregator", rng.randint(50_000_000, 500_000_000))
    for i in range(1, n_wlt + 1):
        add_acc(f"ACC_WLT_{i:04d}", "wallet_ppi", rng.randint(5_000_000, 30_000_000))
    for i in range(1, n_dorm + 1):
        add_acc(f"ACC_DORM_{i:04d}", "dormant", rng.randint(1_000_000, 5_000_000))
    for i in range(1, n_inter + 1):
        add_acc(f"ACC_INTER_{i:04d}", "intermediary", rng.randint(500_000, 2_000_000))
    for i in range(1, n_mule + 1):
        is_seasoned = (i <= 40)
        bal = rng.randint(2_500_000, 6_000_000) if is_seasoned else rng.randint(100_000, 1_000_000)
        add_acc(f"ACC_MULE_{i:04d}", "mule", bal, hist_comp=(i % 25 != 3))
    for i in range(1, n_vic + 1):
        add_acc(f"ACC_VIC_{i:04d}", "savings", rng.randint(50_000_000, 300_000_000))

    # Dedicated accounts for the 5-6 node / 7-8 edge standard benchmark case
    add_acc("ACC_VIC_0999", "savings", 50_000_000)  # ₹5,00,000 opening
    add_acc("ACC_MULE_0991", "mule", 500_000)      # ₹5,000 opening
    add_acc("ACC_MULE_0992", "mule", 200_000)      # ₹2,000 opening
    add_acc("ACC_MULE_0993", "mule", 300_000)      # ₹3,000 opening
    add_acc("ACC_MULE_0994", "mule", 1_000_000)    # ₹10,000 opening

    base_time = datetime.datetime(2025, 1, 1, 0, 0, 0, tzinfo=datetime.timezone.utc)
    raw_txns: List[Dict[str, Any]] = []

    def make_ts(day: int, hour: int, minute: int, second: int = 0) -> str:
        dt = base_time + datetime.timedelta(days=day, hours=hour, minutes=minute, seconds=second)
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    # 2. 12 Months of Payroll
    salary_days = []
    for m in range(12):
        base_d = m * 30
        for d in [1, 15, 28]:
            if base_d + d < days:
                salary_days.append(base_d + d)

    for day in salary_days:
        for i in range(1, n_sal + 1):
            if (i * 7 + day) % 8 < 3:
                sal_amt = rng.randint(2_800_000, 14_000_000)
                aid = f"ACC_SAL_{i:04d}"
                sec = rng.randint(0, 86399)
                raw_txns.append({
                    "timestamp": make_ts(day, 0, 0, sec),
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

        # Seasoned mules receive payroll during initial months
        if day < 180 and day % 30 == 1:
            for i in range(1, min(40, n_mule) + 1):
                sal_amt = rng.randint(2_500_000, 5_500_000)
                aid = f"ACC_MULE_{i:04d}"
                sec = rng.randint(0, 86399)
                raw_txns.append({
                    "timestamp": make_ts(day, 0, 0, sec),
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

    # 3. Gig platform payouts weekly (~4,800 txns)
    for day in range(1, days, 7):
        for i in range(1, n_gig + 1):
            if (i * 3 + day) % 6 < 2:
                amt = rng.randint(60_000, 320_000)
                aid = f"ACC_GIG_{i:04d}"
                sec = rng.randint(0, 86399)
                raw_txns.append({
                    "timestamp": make_ts(day, 0, 0, sec),
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

    # 4. Daily retail commerce across 365 days
    for day in range(1, days):
        n_daily = rng.randint(16, 22)
        for _ in range(n_daily):
            sender_id = f"ACC_SAL_{rng.randint(1, n_sal):04d}" if rng.random() < 0.70 else f"ACC_GIG_{rng.randint(1, n_gig):04d}"
            if day < 180 and rng.random() < 0.05:
                sender_id = f"ACC_MULE_{rng.randint(1, min(40, n_mule)):04d}"

            log_mu = 7.5
            log_sigma = 0.8
            amt = int(math.exp(rng.gauss(log_mu, log_sigma)) * 10)
            amt = max(10_000, min(1_500_000, amt))

            if rng.random() < 0.40:
                receiver_id = f"ACC_HV_MERCH_{rng.randint(1, n_hv_merch):04d}"
                scen = "high_volume_legitimate_merchants"
            else:
                receiver_id = f"ACC_MERCH_{rng.randint(1, n_merch):04d}"
                scen = "ordinary_salary_and_business"

            if clean_balances[sender_id] > amt + 100_000:
                sec = rng.randint(28800, 75600)
                raw_txns.append({
                    "timestamp": make_ts(day, 0, 0, sec),
                    "from_account": sender_id,
                    "to_account": receiver_id,
                    "amount_paise": amt,
                    "transaction_type": "merchant_payment",
                    "case_id": "",
                    "evidence_status": "verified_legitimate",
                    "_scenario": scen,
                })
                balances[sender_id] -= amt
                clean_balances[sender_id] -= amt
                balances[receiver_id] += amt
                clean_balances[receiver_id] += amt

    # 5. Daily Aggregator settlements
    for day in range(1, days):
        n_swp = min(5, n_agg)
        for agg_idx in range(1, n_swp + 1):
            agg_id = f"ACC_AGG_{agg_idx:04d}"
            dep_amt = rng.randint(4_000_000, 18_000_000)
            sec_in = rng.randint(0, 36000)
            raw_txns.append({
                "timestamp": make_ts(day, 0, 0, sec_in),
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

            sec_out = sec_in + rng.randint(1800, 7200)
            settle_amt = int(dep_amt * 0.95)
            merch_id = f"ACC_MERCH_{rng.randint(1, n_merch):04d}"
            raw_txns.append({
                "timestamp": make_ts(day, 0, 0, sec_out),
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

    # 6. Build Cases across 18 Scenario Families with Lot-Level Ground Truth
    cases: List[Dict[str, Any]] = []
    cases_ground_truth: Dict[str, Any] = {}
    txn_ground_truth: Dict[str, Any] = {}
    all_tracked_keys = sorted(set(DEMO_SCENARIOS + ALL_18_SCENARIO_FAMILIES))
    scenario_tracking: Dict[str, List[str]] = {s: [] for s in all_tracked_keys}

    def move_lots(from_acc: str, to_acc: str, tid: str, cid: str, amt: int, mode: str = "greedy") -> int:
        avail = {l: a for l, a in account_lots[from_acc].items() if l.startswith(f"LOT-{cid}-")}
        transferred: Dict[str, int] = {}
        rem = amt
        if mode == "commingled_seeded":
            ratio = 0.50 + (rng.random() * 0.20 - 0.10)
            rem = min(rem, max(1, int(sum(avail.values()) * ratio)))

        for l in sorted(avail.keys()):
            if rem <= 0:
                break
            take = min(avail[l], rem)
            transferred[l] = take
            account_lots[from_acc][l] -= take
            if account_lots[from_acc][l] == 0:
                del account_lots[from_acc][l]
            rem -= take

        tot = sum(transferred.values())
        if to_acc.startswith("EXT_"):
            if to_acc not in withdrawn_lots:
                withdrawn_lots[to_acc] = {}
            for l, a in transferred.items():
                withdrawn_lots[to_acc][l] = withdrawn_lots[to_acc].get(l, 0) + a
        else:
            for l, a in transferred.items():
                account_lots[to_acc][l] = account_lots[to_acc].get(l, 0) + a

        if transferred:
            txn_ground_truth[tid] = {
                "case_id": cid,
                "transferred_lots": transferred,
                "suspected_amount_paise": tot,
            }
        return tot

    FAMILIES = [
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

    # Dedicated 5-6 node / 7-8 edge standard benchmark case
    ref_cid = "CASE-2026-000"
    ref_stolen = 25_000_000  # ₹2,50,000.00
    ref_day = 220            # Mid August 2025

    account_lots["ACC_VIC_0999"][f"LOT-{ref_cid}-01"] = 15_000_000
    account_lots["ACC_VIC_0999"][f"LOT-{ref_cid}-02"] = 10_000_000
    ref_source_lots = [
        {"lot_id": f"LOT-{ref_cid}-01", "original_amount_paise": 15_000_000, "source_case_id": ref_cid},
        {"lot_id": f"LOT-{ref_cid}-02", "original_amount_paise": 10_000_000, "source_case_id": ref_cid},
    ]

    cases.append({
        "case_id": ref_cid,
        "reported_date": make_ts(ref_day, 9, 0),
        "reported_amount_paise": ref_stolen,
        "status": "under_investigation",
    })

    # Exact 8 transactions across 6 nodes (ACC_VIC_0999, ACC_MULE_0991, 0992, 0993, 0994, EXT_CASH_ATM)
    # Edge 1: Origin theft (Vic -> Mule 1)
    t_r1 = "TXN_REF_001"
    raw_txns.append({
        "timestamp": make_ts(ref_day, 9, 15),
        "from_account": "ACC_VIC_0999",
        "to_account": "ACC_MULE_0991",
        "amount_paise": 25_000_000,
        "transaction_type": "transfer",
        "case_id": ref_cid,
        "evidence_status": "suspected_fraud",
        "_scenario": "family_a_layered_chain",
        "_temp_id": t_r1,
    })
    balances["ACC_VIC_0999"] -= 25_000_000
    balances["ACC_MULE_0991"] += 25_000_000
    move_lots("ACC_VIC_0999", "ACC_MULE_0991", t_r1, ref_cid, 25_000_000)

    # Edge 2: Smurfing Split Branch A (Mule 1 -> Mule 2)
    t_r2 = "TXN_REF_002"
    raw_txns.append({
        "timestamp": make_ts(ref_day, 9, 45),
        "from_account": "ACC_MULE_0991",
        "to_account": "ACC_MULE_0992",
        "amount_paise": 12_000_000,
        "transaction_type": "transfer",
        "case_id": ref_cid,
        "evidence_status": "suspected_fraud",
        "_scenario": "family_b_tiny_amount_spray",
        "_temp_id": t_r2,
    })
    balances["ACC_MULE_0991"] -= 12_000_000
    balances["ACC_MULE_0992"] += 12_000_000
    move_lots("ACC_MULE_0991", "ACC_MULE_0992", t_r2, ref_cid, 12_000_000)

    # Edge 3: Smurfing Split Branch B (Mule 1 -> Mule 3)
    t_r3 = "TXN_REF_003"
    raw_txns.append({
        "timestamp": make_ts(ref_day, 9, 50),
        "from_account": "ACC_MULE_0991",
        "to_account": "ACC_MULE_0993",
        "amount_paise": 10_000_000,
        "transaction_type": "transfer",
        "case_id": ref_cid,
        "evidence_status": "suspected_fraud",
        "_scenario": "family_b_tiny_amount_spray",
        "_temp_id": t_r3,
    })
    balances["ACC_MULE_0991"] -= 10_000_000
    balances["ACC_MULE_0993"] += 10_000_000
    move_lots("ACC_MULE_0991", "ACC_MULE_0993", t_r3, ref_cid, 10_000_000)

    # Edge 4: Partial ATM Cash-out from Mule 1
    t_r4 = "TXN_REF_004"
    raw_txns.append({
        "timestamp": make_ts(ref_day, 10, 15),
        "from_account": "ACC_MULE_0991",
        "to_account": "EXT_CASH_ATM",
        "amount_paise": 2_000_000,
        "transaction_type": "withdrawal",
        "case_id": ref_cid,
        "evidence_status": "suspected_fraud",
        "_scenario": "partial_withdrawals_leaving_balance",
        "_temp_id": t_r4,
    })
    balances["ACC_MULE_0991"] -= 2_000_000
    move_lots("ACC_MULE_0991", "EXT_CASH_ATM", t_r4, ref_cid, 2_000_000)

    # Edge 5: Layer 2 Branch A -> Terminal Mule 4
    t_r5 = "TXN_REF_005"
    raw_txns.append({
        "timestamp": make_ts(ref_day, 10, 30),
        "from_account": "ACC_MULE_0992",
        "to_account": "ACC_MULE_0994",
        "amount_paise": 9_000_000,
        "transaction_type": "transfer",
        "case_id": ref_cid,
        "evidence_status": "suspected_fraud",
        "_scenario": "family_a_layered_chain",
        "_temp_id": t_r5,
    })
    balances["ACC_MULE_0992"] -= 9_000_000
    balances["ACC_MULE_0994"] += 9_000_000
    move_lots("ACC_MULE_0992", "ACC_MULE_0994", t_r5, ref_cid, 9_000_000)

    # Edge 6: Layer 2 Branch B -> Terminal Mule 4 (Convergence)
    t_r6 = "TXN_REF_006"
    raw_txns.append({
        "timestamp": make_ts(ref_day, 10, 45),
        "from_account": "ACC_MULE_0993",
        "to_account": "ACC_MULE_0994",
        "amount_paise": 8_000_000,
        "transaction_type": "transfer",
        "case_id": ref_cid,
        "evidence_status": "suspected_fraud",
        "_scenario": "family_a_layered_chain",
        "_temp_id": t_r6,
    })
    balances["ACC_MULE_0993"] -= 8_000_000
    balances["ACC_MULE_0994"] += 8_000_000
    move_lots("ACC_MULE_0993", "ACC_MULE_0994", t_r6, ref_cid, 8_000_000)

    # Edge 7: Terminal Mule 4 -> ATM Cash-out
    t_r7 = "TXN_REF_007"
    raw_txns.append({
        "timestamp": make_ts(ref_day, 11, 30),
        "from_account": "ACC_MULE_0994",
        "to_account": "EXT_CASH_ATM",
        "amount_paise": 11_000_000,
        "transaction_type": "withdrawal",
        "case_id": ref_cid,
        "evidence_status": "suspected_fraud",
        "_scenario": "partial_withdrawals_leaving_balance",
        "_temp_id": t_r7,
    })
    balances["ACC_MULE_0994"] -= 11_000_000
    move_lots("ACC_MULE_0994", "EXT_CASH_ATM", t_r7, ref_cid, 11_000_000)

    # Edge 8: Branch A Cash-out
    t_r8 = "TXN_REF_008"
    raw_txns.append({
        "timestamp": make_ts(ref_day, 11, 45),
        "from_account": "ACC_MULE_0992",
        "to_account": "EXT_CASH_ATM",
        "amount_paise": 1_000_000,
        "transaction_type": "withdrawal",
        "case_id": ref_cid,
        "evidence_status": "suspected_fraud",
        "_scenario": "partial_withdrawals_leaving_balance",
        "_temp_id": t_r8,
    })
    balances["ACC_MULE_0992"] -= 1_000_000
    move_lots("ACC_MULE_0992", "EXT_CASH_ATM", t_r8, ref_cid, 1_000_000)

    cases_ground_truth[ref_cid] = {
        "victim_account": "ACC_VIC_0999",
        "origin_transfer_paise": ref_stolen,
        "family": "layered_chain_with_smurfing",
        "source_lots": ref_source_lots,
        "retained_lots": {
            "ACC_MULE_0991": {f"LOT-{ref_cid}-01": 1_000_000},
            "ACC_MULE_0992": {f"LOT-{ref_cid}-01": 2_000_000},
            "ACC_MULE_0993": {f"LOT-{ref_cid}-02": 2_000_000},
            "ACC_MULE_0994": {f"LOT-{ref_cid}-01": 3_000_000, f"LOT-{ref_cid}-02": 3_000_000},
        },
        "withdrawn_lots": {
            "EXT_CASH_ATM": {f"LOT-{ref_cid}-01": 9_000_000, f"LOT-{ref_cid}-02": 5_000_000},
        },
        "total_retained_paise": 11_000_000,
        "total_withdrawn_paise": 14_000_000,
        "expected_allocations": {
            "ACC_MULE_0991": {"retained_suspected_paise": 1_000_000},
            "ACC_MULE_0992": {"retained_suspected_paise": 2_000_000},
            "ACC_MULE_0993": {"retained_suspected_paise": 2_000_000},
            "ACC_MULE_0994": {"retained_suspected_paise": 6_000_000},
        },
    }

    for c_idx in range(1, num_cases + 1):
        cid = f"CASE-2026-{c_idx:03d}"
        family = FAMILIES[(c_idx - 1) % len(FAMILIES)]
        day = 180 + ((c_idx * 3) % 170)  # Days 180 to 350
        vic = f"ACC_VIC_{((c_idx - 1) % n_vic) + 1:04d}"
        stolen = rng.randint(80_000, 350_000) * 100

        # Guarantee victim liquidity through valid opening balance or explicit deposit
        if balances[vic] < stolen + 5_000_000:
            topup_amt = stolen + 10_000_000
            t_topup = f"TXN_SC_{c_idx:03d}_TOPUP"
            raw_txns.append({
                "timestamp": make_ts(day - 1, 9, 0),
                "from_account": "EXT_SAVINGS_DEPOSIT",
                "to_account": vic,
                "amount_paise": topup_amt,
                "transaction_type": "deposit",
                "case_id": "",
                "evidence_status": "verified_legitimate",
                "_scenario": "ordinary_salary_and_business",
                "_temp_id": t_topup,
            })
            balances[vic] += topup_amt
            clean_balances[vic] += topup_amt

        # Create discrete lots (at least 2 lots per case)
        num_lots = 2 + (c_idx % 2)
        lot_sizes: List[int] = []
        rem_lot = stolen
        for l_idx in range(num_lots - 1):
            sz = int((stolen // num_lots) * (0.85 + (c_idx * 7 % 25) / 100.0))
            sz = min(sz, rem_lot - (num_lots - l_idx - 1) * 1000)
            lot_sizes.append(sz)
            rem_lot -= sz
        lot_sizes.append(rem_lot)

        source_lots_meta: List[Dict[str, Any]] = []
        for l_idx, l_sz in enumerate(lot_sizes, start=1):
            lid = f"LOT-{cid}-{l_idx:02d}"
            account_lots[vic][lid] = l_sz
            source_lots_meta.append({
                "lot_id": lid,
                "original_amount_paise": l_sz,
                "source_case_id": cid,
            })

        cases.append({
            "case_id": cid,
            "reported_date": make_ts(day, 10, 0),
            "reported_amount_paise": stolen,
            "status": "under_investigation",
        })

        if family == "family_a_layered_chain":
            m1 = f"ACC_MULE_{(c_idx % n_mule) + 1:04d}"
            m2 = f"ACC_MULE_{((c_idx + 1) % n_mule) + 1:04d}"
            m3 = f"ACC_MULE_{((c_idx + 2) % n_mule) + 1:04d}"
            t1 = f"TXN_SC_{c_idx:03d}_1"
            raw_txns.append({"timestamp": make_ts(day, 10, 15), "from_account": vic, "to_account": m1, "amount_paise": stolen, "transaction_type": "transfer", "case_id": cid, "evidence_status": "suspected_fraud", "_scenario": family, "_temp_id": t1})
            balances[vic] -= stolen
            balances[m1] += stolen
            move_lots(vic, m1, t1, cid, stolen)
            fwd1 = int(stolen * 0.85)
            t2 = f"TXN_SC_{c_idx:03d}_2"
            raw_txns.append({"timestamp": make_ts(day, 12, 30), "from_account": m1, "to_account": m2, "amount_paise": fwd1, "transaction_type": "transfer", "case_id": cid, "evidence_status": "suspected_fraud", "_scenario": family, "_temp_id": t2})
            balances[m1] -= fwd1
            balances[m2] += fwd1
            move_lots(m1, m2, t2, cid, fwd1)
            fwd2 = int(fwd1 * 0.80)
            t3 = f"TXN_SC_{c_idx:03d}_3"
            raw_txns.append({"timestamp": make_ts(day, 14, 0), "from_account": m2, "to_account": m3, "amount_paise": fwd2, "transaction_type": "transfer", "case_id": cid, "evidence_status": "suspected_fraud", "_scenario": family, "_temp_id": t3})
            balances[m2] -= fwd2
            balances[m3] += fwd2
            move_lots(m2, m3, t3, cid, fwd2)
            w = int(fwd2 * 0.70)
            t4 = f"TXN_SC_{c_idx:03d}_4"
            raw_txns.append({"timestamp": make_ts(day, 16, 0), "from_account": m3, "to_account": "EXT_CASH_ATM", "amount_paise": w, "transaction_type": "withdrawal", "case_id": cid, "evidence_status": "suspected_fraud", "_scenario": family, "_temp_id": t4})
            balances[m3] -= w
            move_lots(m3, "EXT_CASH_ATM", t4, cid, w)

        elif family == "family_b_tiny_amount_spray":
            spray = f"ACC_MULE_{((c_idx * 3) % n_mule) + 1:04d}"
            t1 = f"TXN_SC_{c_idx:03d}_1"
            raw_txns.append({"timestamp": make_ts(day, 9, 30), "from_account": vic, "to_account": spray, "amount_paise": stolen, "transaction_type": "transfer", "case_id": cid, "evidence_status": "suspected_fraud", "_scenario": family, "_temp_id": t1})
            balances[vic] -= stolen
            balances[spray] += stolen
            move_lots(vic, spray, t1, cid, stolen)
            k_splits = 6
            sub = stolen // k_splits
            for k in range(k_splits):
                amt_k = sub if k < k_splits - 1 else (stolen - sub * (k_splits - 1))
                dest = f"ACC_MULE_{((120 + c_idx * 6 + k) % n_mule) + 1:04d}"
                tk = f"TXN_SC_{c_idx:03d}_SP_{k}"
                raw_txns.append({"timestamp": make_ts(day, 11, 10 + k * 4), "from_account": spray, "to_account": dest, "amount_paise": amt_k, "transaction_type": "transfer", "case_id": cid, "evidence_status": "suspected_fraud", "_scenario": family, "_temp_id": tk})
                balances[spray] -= amt_k
                balances[dest] += amt_k
                move_lots(spray, dest, tk, cid, amt_k)

        elif family == "family_c_heavy_commingling":
            agg = f"ACC_AGG_{((c_idx - 1) % 10) + 1:04d}"
            t1 = f"TXN_SC_{c_idx:03d}_1"
            raw_txns.append({"timestamp": make_ts(day, 10, 0), "from_account": vic, "to_account": agg, "amount_paise": stolen, "transaction_type": "transfer", "case_id": cid, "evidence_status": "suspected_fraud", "_scenario": family, "_temp_id": t1})
            balances[vic] -= stolen
            balances[agg] += stolen
            move_lots(vic, agg, t1, cid, stolen)
            m1 = f"ACC_MERCH_{((c_idx * 2) % n_merch) + 1:04d}"
            s1 = int(stolen * 0.55)
            ts1 = f"TXN_SC_{c_idx:03d}_S1"
            raw_txns.append({"timestamp": make_ts(day, 11, 30), "from_account": agg, "to_account": m1, "amount_paise": s1, "transaction_type": "transfer", "case_id": cid, "evidence_status": "suspected_fraud", "_scenario": family, "_temp_id": ts1})
            balances[agg] -= s1
            balances[m1] += s1
            move_lots(agg, m1, ts1, cid, s1, mode="commingled_seeded")

        elif family == "family_d_structuring_below_threshold":
            m1 = f"ACC_MULE_{1 + (c_idx * 2) % n_mule:04d}"
            m2 = f"ACC_MULE_{1 + (c_idx * 2 + 1) % n_mule:04d}"
            chunks = []
            rem_d = stolen
            while rem_d > 0:
                take = min(rem_d, rng.randint(4_200_000, 4_900_000))
                chunks.append(take)
                rem_d -= take
            for idx, c_amt in enumerate(chunks):
                tid_d = f"TXN_SC_{c_idx:03d}_D_{idx}"
                raw_txns.append({"timestamp": make_ts(day, 9 + (idx % 6), (idx * 15) % 60), "from_account": vic, "to_account": m1, "amount_paise": c_amt, "transaction_type": "transfer", "case_id": cid, "evidence_status": "suspected_fraud", "_scenario": family, "_temp_id": tid_d})
                balances[vic] -= c_amt
                balances[m1] += c_amt
                move_lots(vic, m1, tid_d, cid, c_amt)
                tid_f = f"TXN_SC_{c_idx:03d}_F_{idx}"
                raw_txns.append({"timestamp": make_ts(day, 10 + (idx % 6), (idx * 15 + 5) % 60), "from_account": m1, "to_account": m2, "amount_paise": c_amt, "transaction_type": "transfer", "case_id": cid, "evidence_status": "suspected_fraud", "_scenario": family, "_temp_id": tid_f})
                balances[m1] -= c_amt
                balances[m2] += c_amt
                move_lots(m1, m2, tid_f, cid, c_amt)

        elif family == "partial_withdrawals_leaving_balance":
            m1 = f"ACC_MULE_{((c_idx * 3) % n_mule) + 1:04d}"
            t1 = f"TXN_SC_{c_idx:03d}_1"
            raw_txns.append({"timestamp": make_ts(day, 10, 0), "from_account": vic, "to_account": m1, "amount_paise": stolen, "transaction_type": "transfer", "case_id": cid, "evidence_status": "suspected_fraud", "_scenario": family, "_temp_id": t1})
            balances[vic] -= stolen
            balances[m1] += stolen
            move_lots(vic, m1, t1, cid, stolen)
            w_amt = int(stolen * 0.45)
            tw = f"TXN_SC_{c_idx:03d}_W"
            raw_txns.append({"timestamp": make_ts(day, 13, 0), "from_account": m1, "to_account": "EXT_CASH_ATM", "amount_paise": w_amt, "transaction_type": "withdrawal", "case_id": cid, "evidence_status": "suspected_fraud", "_scenario": family, "_temp_id": tw})
            balances[m1] -= w_amt
            move_lots(m1, "EXT_CASH_ATM", tw, cid, w_amt)

        elif family == "later_legitimate_credits_entering_commingled":
            m1 = f"ACC_MULE_{((c_idx * 4) % n_mule) + 1:04d}"
            t1 = f"TXN_SC_{c_idx:03d}_1"
            raw_txns.append({"timestamp": make_ts(day, 10, 0), "from_account": vic, "to_account": m1, "amount_paise": stolen, "transaction_type": "transfer", "case_id": cid, "evidence_status": "suspected_fraud", "_scenario": family, "_temp_id": t1})
            balances[vic] -= stolen
            balances[m1] += stolen
            move_lots(vic, m1, t1, cid, stolen)
            clean_dep = int(stolen * 1.2)
            td = f"TXN_SC_{c_idx:03d}_CLEAN"
            raw_txns.append({"timestamp": make_ts(day + 1, 11, 0), "from_account": "EXT_EMPLOYER_PAYROLL", "to_account": m1, "amount_paise": clean_dep, "transaction_type": "salary_credit", "case_id": "", "evidence_status": "verified_legitimate", "_scenario": family, "_temp_id": td})
            balances[m1] += clean_dep
            clean_balances[m1] += clean_dep

        elif family == "refunds_and_reversals":
            merch = f"ACC_MERCH_{((c_idx * 3) % n_merch) + 1:04d}"
            t1 = f"TXN_SC_{c_idx:03d}_1"
            raw_txns.append({"timestamp": make_ts(day, 10, 0), "from_account": vic, "to_account": merch, "amount_paise": stolen, "transaction_type": "merchant_payment", "case_id": cid, "evidence_status": "suspected_fraud", "_scenario": family, "_temp_id": t1})
            balances[vic] -= stolen
            balances[merch] += stolen
            move_lots(vic, merch, t1, cid, stolen)
            tr = f"TXN_SC_{c_idx:03d}_REV"
            raw_txns.append({"timestamp": make_ts(day + 1, 9, 30), "from_account": merch, "to_account": vic, "amount_paise": stolen, "transaction_type": "refund", "case_id": cid, "evidence_status": "verified_legitimate", "_scenario": family, "_temp_id": tr})
            balances[merch] -= stolen
            balances[vic] += stolen
            move_lots(merch, vic, tr, cid, stolen)

        elif family == "rapid_movement_between_accounts":
            m1 = f"ACC_MULE_{((c_idx * 5) % n_mule) + 1:04d}"
            m2 = f"ACC_MULE_{((c_idx * 5 + 1) % n_mule) + 1:04d}"
            m3 = f"ACC_MULE_{((c_idx * 5 + 2) % n_mule) + 1:04d}"
            t1 = f"TXN_SC_{c_idx:03d}_1"
            raw_txns.append({"timestamp": make_ts(day, 14, 0), "from_account": vic, "to_account": m1, "amount_paise": stolen, "transaction_type": "transfer", "case_id": cid, "evidence_status": "suspected_fraud", "_scenario": family, "_temp_id": t1})
            balances[vic] -= stolen
            balances[m1] += stolen
            move_lots(vic, m1, t1, cid, stolen)
            t2 = f"TXN_SC_{c_idx:03d}_2"
            raw_txns.append({"timestamp": make_ts(day, 14, 8), "from_account": m1, "to_account": m2, "amount_paise": stolen, "transaction_type": "transfer", "case_id": cid, "evidence_status": "suspected_fraud", "_scenario": family, "_temp_id": t2})
            balances[m1] -= stolen
            balances[m2] += stolen
            move_lots(m1, m2, t2, cid, stolen)
            t3 = f"TXN_SC_{c_idx:03d}_3"
            raw_txns.append({"timestamp": make_ts(day, 14, 18), "from_account": m2, "to_account": m3, "amount_paise": stolen, "transaction_type": "transfer", "case_id": cid, "evidence_status": "suspected_fraud", "_scenario": family, "_temp_id": t3})
            balances[m2] -= stolen
            balances[m3] += stolen
            move_lots(m2, m3, t3, cid, stolen)

        elif family == "dormant_account_activation":
            dorm = f"ACC_DORM_{((c_idx * 2) % n_dorm) + 1:04d}"
            m1 = f"ACC_MULE_{((c_idx * 2) % n_mule) + 1:04d}"
            t1 = f"TXN_SC_{c_idx:03d}_1"
            raw_txns.append({"timestamp": make_ts(day, 10, 0), "from_account": vic, "to_account": dorm, "amount_paise": stolen, "transaction_type": "transfer", "case_id": cid, "evidence_status": "suspected_fraud", "_scenario": family, "_temp_id": t1})
            balances[vic] -= stolen
            balances[dorm] += stolen
            move_lots(vic, dorm, t1, cid, stolen)
            t2 = f"TXN_SC_{c_idx:03d}_2"
            raw_txns.append({"timestamp": make_ts(day, 13, 0), "from_account": dorm, "to_account": m1, "amount_paise": stolen, "transaction_type": "transfer", "case_id": cid, "evidence_status": "suspected_fraud", "_scenario": family, "_temp_id": t2})
            balances[dorm] -= stolen
            balances[m1] += stolen
            move_lots(dorm, m1, t2, cid, stolen)

        elif family == "shared_intermediary_accounts":
            inter = f"ACC_INTER_{((c_idx * 2) % n_inter) + 1:04d}"
            m1 = f"ACC_MULE_{((c_idx * 3) % n_mule) + 1:04d}"
            t1 = f"TXN_SC_{c_idx:03d}_1"
            raw_txns.append({"timestamp": make_ts(day, 10, 0), "from_account": vic, "to_account": inter, "amount_paise": stolen, "transaction_type": "transfer", "case_id": cid, "evidence_status": "suspected_fraud", "_scenario": family, "_temp_id": t1})
            balances[vic] -= stolen
            balances[inter] += stolen
            move_lots(vic, inter, t1, cid, stolen)
            t2 = f"TXN_SC_{c_idx:03d}_2"
            raw_txns.append({"timestamp": make_ts(day, 12, 0), "from_account": inter, "to_account": m1, "amount_paise": stolen, "transaction_type": "transfer", "case_id": cid, "evidence_status": "suspected_fraud", "_scenario": family, "_temp_id": t2})
            balances[inter] -= stolen
            balances[m1] += stolen
            move_lots(inter, m1, t2, cid, stolen)

        elif family == "incomplete_history_account":
            inc_mule = f"ACC_MULE_{min(3, n_mule):04d}"
            t1 = f"TXN_SC_{c_idx:03d}_1"
            raw_txns.append({"timestamp": make_ts(day, 10, 0), "from_account": vic, "to_account": inc_mule, "amount_paise": stolen, "transaction_type": "transfer", "case_id": cid, "evidence_status": "suspected_fraud", "_scenario": family, "_temp_id": t1})
            balances[vic] -= stolen
            balances[inc_mule] += stolen
            move_lots(vic, inc_mule, t1, cid, stolen)

        elif family == "dead_end_stuck_funds":
            m1 = f"ACC_MULE_{((c_idx * 7) % n_mule) + 1:04d}"
            t1 = f"TXN_SC_{c_idx:03d}_1"
            raw_txns.append({"timestamp": make_ts(day, 10, 0), "from_account": vic, "to_account": m1, "amount_paise": stolen, "transaction_type": "transfer", "case_id": cid, "evidence_status": "suspected_fraud", "_scenario": family, "_temp_id": t1})
            balances[vic] -= stolen
            balances[m1] += stolen
            move_lots(vic, m1, t1, cid, stolen)

        elif family == "multi_event_case":
            m1 = f"ACC_MULE_{((c_idx * 4) % n_mule) + 1:04d}"
            half1 = stolen // 2
            half2 = stolen - half1
            t1 = f"TXN_SC_{c_idx:03d}_1"
            raw_txns.append({"timestamp": make_ts(day, 10, 0), "from_account": vic, "to_account": m1, "amount_paise": half1, "transaction_type": "transfer", "case_id": cid, "evidence_status": "suspected_fraud", "_scenario": family, "_temp_id": t1})
            balances[vic] -= half1
            balances[m1] += half1
            move_lots(vic, m1, t1, cid, half1)
            t2 = f"TXN_SC_{c_idx:03d}_2"
            raw_txns.append({"timestamp": make_ts(day + 3, 11, 0), "from_account": vic, "to_account": m1, "amount_paise": half2, "transaction_type": "transfer", "case_id": cid, "evidence_status": "suspected_fraud", "_scenario": family, "_temp_id": t2})
            balances[vic] -= half2
            balances[m1] += half2
            move_lots(vic, m1, t2, cid, half2)

        elif family == "method_divergence_case":
            m1 = f"ACC_MULE_{((c_idx * 6) % n_mule) + 1:04d}"
            t1 = f"TXN_SC_{c_idx:03d}_1"
            raw_txns.append({"timestamp": make_ts(day, 10, 0), "from_account": vic, "to_account": m1, "amount_paise": stolen, "transaction_type": "transfer", "case_id": cid, "evidence_status": "suspected_fraud", "_scenario": family, "_temp_id": t1})
            balances[vic] -= stolen
            balances[m1] += stolen
            move_lots(vic, m1, t1, cid, stolen)
            dip = int(stolen * 0.70)
            tw = f"TXN_SC_{c_idx:03d}_W"
            raw_txns.append({"timestamp": make_ts(day, 12, 0), "from_account": m1, "to_account": "EXT_CASH_ATM", "amount_paise": dip, "transaction_type": "withdrawal", "case_id": cid, "evidence_status": "suspected_fraud", "_scenario": family, "_temp_id": tw})
            balances[m1] -= dip
            move_lots(m1, "EXT_CASH_ATM", tw, cid, dip)
            cd = int(stolen * 0.80)
            tcd = f"TXN_SC_{c_idx:03d}_CLEAN"
            raw_txns.append({"timestamp": make_ts(day + 1, 10, 0), "from_account": "EXT_EMPLOYER_PAYROLL", "to_account": m1, "amount_paise": cd, "transaction_type": "deposit", "case_id": "", "evidence_status": "verified_legitimate", "_scenario": family, "_temp_id": tcd})
            balances[m1] += cd
            clean_balances[m1] += cd

        elif family == "ineligible_hold_drained_case":
            m1 = f"ACC_MULE_{((c_idx * 7) % n_mule) + 1:04d}"
            t1 = f"TXN_SC_{c_idx:03d}_1"
            raw_txns.append({"timestamp": make_ts(day, 10, 0), "from_account": vic, "to_account": m1, "amount_paise": stolen, "transaction_type": "transfer", "case_id": cid, "evidence_status": "suspected_fraud", "_scenario": family, "_temp_id": t1})
            balances[vic] -= stolen
            balances[m1] += stolen
            move_lots(vic, m1, t1, cid, stolen)
            drain = stolen
            tw = f"TXN_SC_{c_idx:03d}_DRAIN"
            raw_txns.append({"timestamp": make_ts(day, 11, 0), "from_account": m1, "to_account": "EXT_CASH_ATM", "amount_paise": drain, "transaction_type": "withdrawal", "case_id": cid, "evidence_status": "suspected_fraud", "_scenario": family, "_temp_id": tw})
            balances[m1] -= drain
            move_lots(m1, "EXT_CASH_ATM", tw, cid, stolen)

        elif family == "ambiguous_evidence_case":
            m1 = f"ACC_MULE_{((c_idx * 8) % n_mule) + 1:04d}"
            t1 = f"TXN_SC_{c_idx:03d}_1"
            raw_txns.append({"timestamp": make_ts(day, 10, 0), "from_account": vic, "to_account": m1, "amount_paise": stolen, "transaction_type": "transfer", "case_id": cid, "evidence_status": "unverified", "_scenario": family, "_temp_id": t1})
            balances[vic] -= stolen
            balances[m1] += stolen
            move_lots(vic, m1, t1, cid, stolen)

        # Build case ground truth metadata
        retained_by_acc: Dict[str, Dict[str, int]] = {}
        for acc in account_ids:
            acc_case_lots = {l: a for l, a in account_lots[acc].items() if l.startswith(f"LOT-{cid}-")}
            if acc_case_lots:
                retained_by_acc[acc] = acc_case_lots

        withdrawn_by_ext: Dict[str, Dict[str, int]] = {}
        for ext, l_dict in withdrawn_lots.items():
            ext_case_lots = {l: a for l, a in l_dict.items() if l.startswith(f"LOT-{cid}-")}
            if ext_case_lots:
                withdrawn_by_ext[ext] = ext_case_lots

        total_ret = sum(sum(d.values()) for d in retained_by_acc.values())
        total_wth = sum(sum(d.values()) for d in withdrawn_by_ext.values())

        cases_ground_truth[cid] = {
            "victim_account": vic,
            "origin_transfer_paise": stolen,
            "family": family,
            "source_lots": source_lots_meta,
            "retained_lots": retained_by_acc,
            "withdrawn_lots": withdrawn_by_ext,
            "total_retained_paise": total_ret,
            "total_withdrawn_paise": total_wth,
            "expected_allocations": {
                acc: {"retained_suspected_paise": sum(l_dict.values())}
                for acc, l_dict in retained_by_acc.items()
            },
        }

    # 7. Sort deterministically and assign sequential IDs
    raw_txns.sort(key=lambda x: (x["timestamp"], x["from_account"], x["to_account"]))
    transactions: List[Dict[str, Any]] = []
    final_txn_ground_truth: Dict[str, Any] = {}

    for idx, t in enumerate(raw_txns, start=1):
        tid = f"TXN_{idx:06d}"
        t["transaction_id"] = tid
        temp_id = t.pop("_temp_id", None)
        if temp_id and temp_id in txn_ground_truth:
            final_txn_ground_truth[tid] = txn_ground_truth[temp_id]
        scen = t.pop("_scenario", "ordinary_salary_and_business")
        scen_aliases = [scen]
        if scen == "family_a_layered_chain":
            scen_aliases.append("direct_onward_transfer")
        elif scen == "family_b_tiny_amount_spray":
            scen_aliases.append("split_transfers_smurfing")
        elif scen == "family_c_heavy_commingling":
            scen_aliases.append("commingling_funds")
        elif scen == "high_volume_legitimate_merchants":
            scen_aliases.append("merchant_multiple_customers")
        for s_alias in scen_aliases:
            if s_alias in scenario_tracking:
                scenario_tracking[s_alias].append(tid)
        transactions.append(t)

    accounts.sort(key=lambda x: x["account_id"])
    cases.sort(key=lambda x: x["case_id"])

    # Strict conservation invariant assertion
    tot_opening = sum(a["opening_balance_paise"] for a in accounts)
    tot_ext_in = sum(t["amount_paise"] for t in transactions if t["from_account"].startswith("EXT_"))
    tot_ext_out = sum(t["amount_paise"] for t in transactions if t["to_account"].startswith("EXT_"))
    tot_final = sum(balances.values())
    assert tot_opening + tot_ext_in - tot_ext_out == tot_final, (
        f"Conservation invariant violated: {tot_opening} + {tot_ext_in} - {tot_ext_out} != {tot_final}"
    )

    ground_truth = {
        "_metadata": {
            "dataset_type": "synthetic_ground_truth",
            "generator_version": "2.0.0-scaled-12month",
            "random_seed": seed,
            "num_accounts": len(accounts),
            "num_cases": len(cases),
            "num_transactions": len(transactions),
            "timespan_days": days,
            "warning": (
                "CONFIDENTIAL EVALUATION DATA: Tracing and scoring algorithms must "
                "NEVER read this file directly. Strictly for evaluation/benchmark modules."
            ),
            "generated_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
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
    days: int = 365,
    preset: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any]]:
    """Generate synthetic dataset based on chosen preset or parameters."""
    if preset == "demo" or (preset is None and num_accounts is None and num_cases is None):
        return generate_default_fixture(seed=seed)
    n_acc = num_accounts if num_accounts is not None else 2400
    n_cases = num_cases if num_cases is not None else 120
    return generate_scaled_dataset(seed=seed, num_accounts=n_acc, num_cases=n_cases, days=days)


def validate_dataset(
    accounts: List[Dict[str, Any]],
    transactions: List[Dict[str, Any]],
    cases: List[Dict[str, Any]],
    ground_truth: Dict[str, Any],
) -> None:
    """Validate all generated records against Smart-Freeze financial integrity constraints."""
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
            raise ValueError(f"Account opening_balance_paise must be nonnegative integer paise, got {bal}")

        if not isinstance(acc["history_complete"], bool):
            raise ValueError(f"Account history_complete must be boolean, got {acc['history_complete']}")
        if not acc["history_complete"]:
            has_incomplete_history = True

    if not has_incomplete_history:
        raise ValueError("No account found with history_complete == False.")

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

        try:
            datetime.datetime.fromisoformat(c["reported_date"].replace("Z", "+00:00"))
        except Exception as e:
            raise ValueError(f"Invalid case reported_date '{c['reported_date']}': {e}")

    if not transactions:
        raise ValueError("Transactions list is empty.")

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

        amt = txn["amount_paise"]
        if not isinstance(amt, int) or amt <= 0:
            raise ValueError(f"Transaction amount_paise must be positive integer paise, got {amt}")

        ts = txn["timestamp"]
        try:
            datetime.datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except Exception as e:
            raise ValueError(f"Invalid transaction timestamp '{ts}': {e}")

        if prev_timestamp and ts < prev_timestamp:
            raise ValueError(f"Transactions are not sorted deterministically by timestamp: {prev_timestamp} > {ts}")
        prev_timestamp = ts

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

        cid = txn["case_id"]
        if cid and cid not in case_ids:
            raise ValueError(f"Transaction {tid} references unknown case_id: '{cid}'")

    # Strict financial conservation and non-negative balance verification
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

    if not isinstance(ground_truth, dict):
        raise ValueError("Ground truth must be a dictionary.")

    for required_key in ["_metadata", "cases", "scenarios", "transactions_ground_truth"]:
        if required_key not in ground_truth:
            raise ValueError(f"Ground truth missing required top-level key: '{required_key}'")

    for gt_cid in ground_truth["cases"].keys():
        if gt_cid not in case_ids:
            raise ValueError(f"Ground truth references unknown case_id: '{gt_cid}'")


def save_dataset_atomic(
    output_dir: Path,
    accounts: List[Dict[str, Any]],
    transactions: List[Dict[str, Any]],
    cases: List[Dict[str, Any]],
    ground_truth: Dict[str, Any],
) -> None:
    """Save validated dataset files to disk using atomic replacement."""
    output_dir.mkdir(parents=True, exist_ok=True)

    def write_csv_atomic(path: Path, fieldnames: List[str], rows: List[Dict[str, Any]]) -> None:
        tmp_path = path.with_suffix(".csv.tmp")
        with open(tmp_path, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        tmp_path.replace(path)

    def write_json_atomic(path: Path, data: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(".json.tmp")
        with open(tmp_path, mode="w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, sort_keys=True)
        tmp_path.replace(path)

    # 1. Operational CSV files (NEVER contain ground truth tags)
    write_csv_atomic(output_dir / "accounts.csv", ACCOUNT_COLUMNS, accounts)
    write_csv_atomic(output_dir / "transactions.csv", TRANSACTION_COLUMNS, transactions)
    write_csv_atomic(output_dir / "cases.csv", CASE_COLUMNS, cases)

    # 2. Ground Truth JSON (saved in output_dir and data/evaluation/ground_truth.json)
    write_json_atomic(output_dir / "ground_truth.json", ground_truth)
    eval_gt_path = Path("data/evaluation/ground_truth.json")
    write_json_atomic(eval_gt_path, ground_truth)


save_dataset = save_dataset_atomic


def main() -> None:
    """CLI entrypoint for synthetic data generation."""
    parser = argparse.ArgumentParser(description="Smart-Freeze Synthetic Financial Data Generator")
    parser.add_argument("--preset", type=str, choices=["demo", "scaled"], default="scaled", help="Dataset preset: 'demo' (3 cases, ~119 txns) or 'scaled' (25k-35k txns, 12 months)")
    parser.add_argument("--seed", type=int, default=42, help="Deterministic random seed (default: 42)")
    parser.add_argument("--output-dir", type=str, default="data/synthetic", help="Output directory (default: data/synthetic)")
    parser.add_argument("--accounts", type=int, default=None, help="Custom account count for scaled generation (default: 2400)")
    parser.add_argument("--cases", type=int, default=None, help="Custom case count for scaled generation (default: 120)")
    parser.add_argument("--days", type=int, default=365, help="Timespan in days for scaled generation (default: 365)")
    args = parser.parse_args()

    print(f"Generating Smart-Freeze synthetic dataset [preset={args.preset}, seed={args.seed}]...")
    t0 = time.time()
    accounts, transactions, cases, ground_truth = generate_all_data(
        seed=args.seed,
        num_accounts=args.accounts,
        num_cases=args.cases,
        days=args.days,
        preset=args.preset,
    )
    gen_time = time.time() - t0

    print(f"Validating dataset ({gen_time:.3f}s generation time)...")
    validate_dataset(accounts, transactions, cases, ground_truth)

    out_path = Path(args.output_dir)
    print(f"Writing outputs atomically to {out_path.resolve()}...")
    save_dataset_atomic(out_path, accounts, transactions, cases, ground_truth)
    total_time = time.time() - t0

    print("Generation complete:")
    print(f"  - Accounts: {len(accounts):,} (written to {out_path / 'accounts.csv'})")
    print(f"  - Transactions: {len(transactions):,} (written to {out_path / 'transactions.csv'})")
    print(f"  - Cases: {len(cases):,} (written to {out_path / 'cases.csv'})")
    print(f"  - Ground Truth: {len(ground_truth['transactions_ground_truth']):,} lot mappings")
    print(f"  - Evaluation Mirror: data/evaluation/ground_truth.json")
    print(f"  - Measured Elapsed Time: {total_time:.3f}s")


if __name__ == "__main__":
    main()
