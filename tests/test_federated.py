"""Automated Tests for Federated Multi-Rail Tracing, Passports, and Cryptographic Security.

Verifies:
1. Property test over 2,000 seeded random scenarios: federated == centralized for FIFO, Proportional, and LIBR.
2. Tamper detection: altered payload triggers signature failure.
3. Replay protection: repeated nonce rejected by destination BankNode replay store.
4. Wrong key rejection: unauthorized adversary signature rejected.
5. Expiry enforcement: expired passport rejected.
6. Missing passport range widening: unknown stolen share expands evidence range, never faking precision.
7. Startup key generation: Ed25519 keys are non-seed derived and unique per instance.
8. Case and institution binding: cross-case and misrouted passports rejected.
9. FastAPI endpoint: /api/v1/federated/compare/{case_id} returns side-by-side comparison.
"""

import datetime
import random
import uuid
from typing import Any, Dict, List, Set, Tuple
import pytest
from fastapi.testclient import TestClient
from cryptography.hazmat.primitives.asymmetric import ed25519

from app.main import app
from engine.fifo import FIFOTracer
from engine.libr import LIBRTracer
from engine.proportional import ProportionalTracer
from federated.coordinator import FederatedCoordinator, FEDERATED_RAILS
from federated.node import BankNode
from federated.schemas import (
    Passport,
    PassportVerificationStatus,
    canonical_serialize,
)
from security.auth import issue_demo_token


client = TestClient(app)


def get_auth_headers(role: str = "investigator") -> Dict[str, str]:
    return {"Authorization": "Bearer dev_token_admin"}


# ==============================================================================
# 1. Acceptance Property Test: 2,000 Seeded Random Scenarios
# ==============================================================================

def test_property_2000_scenarios_federated_equals_centralized():
    """Acceptance: 2,000 seeded random scenarios show 0 divergence across FIFO, Proportional, and LIBR."""
    rng = random.Random(42)
    insts = list(FEDERATED_RAILS)

    for sc_idx in range(2000):
        # 4 to 8 accounts distributed over the 4 rails
        n_accs = rng.randint(4, 8)
        acc_ids = [f"ACC_{i}" for i in range(n_accs)]
        acc_inst = {acc: insts[i % len(insts)] for i, acc in enumerate(acc_ids)}

        accounts = []
        for acc in acc_ids:
            accounts.append({
                "account_id": acc,
                "opening_balance_paise": rng.randint(500_000, 5_000_000),
                "history_complete": True,
                "bank_id": acc_inst[acc],
            })

        running_bals = {a["account_id"]: a["opening_balance_paise"] for a in accounts}

        # Source fraud transaction
        victim = acc_ids[0]
        mule1 = acc_ids[1]
        stolen_amt = rng.randint(100_000, 400_000)

        txns = []
        tx_id_counter = 1

        def add_tx(from_a: str, to_a: str, amt: int) -> str:
            nonlocal tx_id_counter
            tid = f"TXN_{tx_id_counter:04d}"
            ts = f"2026-01-01T{tx_id_counter // 60:02d}:{tx_id_counter % 60:02d}:00Z"
            tx_id_counter += 1
            running_bals[from_a] -= amt
            running_bals[to_a] += amt
            txns.append({
                "transaction_id": tid,
                "timestamp": ts,
                "from_account": from_a,
                "to_account": to_a,
                "amount_paise": amt,
                "transaction_type": "transfer",
            })
            return tid

        src_tx_id = add_tx(victim, mule1, stolen_amt)

        # 5 to 12 subsequent transfers across institutions
        n_tx = rng.randint(5, 12)
        for _ in range(n_tx):
            senders = [a for a, b in running_bals.items() if b > 50_000]
            if not senders:
                break
            sender = rng.choice(senders)
            receiver = rng.choice([a for a in acc_ids if a != sender])
            max_amt = min(running_bals[sender], rng.randint(20_000, 150_000))
            if max_amt <= 0:
                continue
            add_tx(sender, receiver, max_amt)

        coordinator = FederatedCoordinator(
            rails=insts,
            custom_partition_map=acc_inst,
        )
        res = coordinator.run_trace(
            accounts=accounts,
            transactions=txns,
            source_transaction_id=src_tx_id,
            case_id=f"CASE_SCEN_{sc_idx:04d}",
            suspected_amount_paise=stolen_amt,
        )

        assert res.methods_match["fifo"], f"FIFO divergence at scenario {sc_idx}"
        assert res.methods_match["proportional"], f"Proportional divergence at scenario {sc_idx}"
        assert res.methods_match["libr"], f"LIBR divergence at scenario {sc_idx}"


# ==============================================================================
# 2. Security & Adversarial Verification Tests
# ==============================================================================

def test_startup_keys_are_fresh_non_seed_derived():
    """Verify nodes generate genuine Ed25519 keys at startup (no seed-derived keys)."""
    node1 = BankNode("BANK_A")
    node2 = BankNode("BANK_A")

    # Independent instances must have distinct keypairs
    assert node1.public_key_hex != node2.public_key_hex
    assert node1.public_key.public_bytes_raw() != node2.public_key.public_bytes_raw()


def test_passport_tamper_detection():
    """Verify that tampering with passport payload invalidates the signature."""
    node_a = BankNode("BANK_A")
    node_b = BankNode("BANK_B")
    reg = {"BANK_A": node_a.public_key, "BANK_B": node_b.public_key}

    passport = node_a.sign_passport(
        case_id="CASE-001",
        to_institution="BANK_B",
        transfer_ref="TX_100",
        amount_minor=1_000_000,
        fifo_segments=[(1_000_000, 500_000)],
        proportional_stolen=500_000,
        libr_stolen=500_000,
    )

    # Valid passport succeeds
    v_clean = node_b.verify_and_ingest_passport(passport, "CASE-001", reg)
    assert v_clean.is_valid
    assert v_clean.status == PassportVerificationStatus.VALID

    # Tampered amount fails
    tampered_dict = passport.model_dump()
    tampered_dict["amount_minor"] = 2_000_000
    tampered_dict["nonce"] = str(uuid.uuid4())
    tampered_passport = Passport(**tampered_dict)

    v_tampered = node_b.verify_and_ingest_passport(tampered_passport, "CASE-001", reg)
    assert not v_tampered.is_valid
    assert v_tampered.status == PassportVerificationStatus.INVALID_SIGNATURE


def test_passport_replay_protection():
    """Verify that submitting the same passport or nonce twice is rejected by replay store."""
    node_a = BankNode("BANK_A")
    node_b = BankNode("BANK_B")
    reg = {"BANK_A": node_a.public_key, "BANK_B": node_b.public_key}

    passport = node_a.sign_passport(
        case_id="CASE-001",
        to_institution="BANK_B",
        transfer_ref="TX_101",
        amount_minor=500_000,
        fifo_segments=[(500_000, 500_000)],
        proportional_stolen=500_000,
        libr_stolen=500_000,
    )

    # First submission accepted
    v1 = node_b.verify_and_ingest_passport(passport, "CASE-001", reg)
    assert v1.is_valid

    # Replay of same passport rejected
    v2 = node_b.verify_and_ingest_passport(passport, "CASE-001", reg)
    assert not v2.is_valid
    assert v2.status == PassportVerificationStatus.REPLAY_DETECTED


def test_passport_wrong_key_rejection():
    """Verify that passports signed by an adversary key are rejected."""
    node_a = BankNode("BANK_A")
    node_b = BankNode("BANK_B")
    reg = {"BANK_A": node_a.public_key, "BANK_B": node_b.public_key}

    adversary_key = ed25519.Ed25519PrivateKey.generate()

    passport = node_a.sign_passport(
        case_id="CASE-001",
        to_institution="BANK_B",
        transfer_ref="TX_102",
        amount_minor=750_000,
        fifo_segments=[(750_000, 750_000)],
        proportional_stolen=750_000,
        libr_stolen=750_000,
    )

    # Forge signature using adversary key
    forged_dict = passport.model_dump()
    signable = passport.to_signable_bytes()
    forged_dict["signature"] = adversary_key.sign(signable).hex()
    forged_passport = Passport(**forged_dict)

    v = node_b.verify_and_ingest_passport(forged_passport, "CASE-001", reg)
    assert not v.is_valid
    assert v.status == PassportVerificationStatus.INVALID_SIGNATURE


def test_passport_expiry_enforcement():
    """Verify that expired passports are rejected."""
    node_a = BankNode("BANK_A")
    node_b = BankNode("BANK_B")
    reg = {"BANK_A": node_a.public_key, "BANK_B": node_b.public_key}

    past_time = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=2)

    passport = node_a.sign_passport(
        case_id="CASE-001",
        to_institution="BANK_B",
        transfer_ref="TX_103",
        amount_minor=300_000,
        fifo_segments=[(300_000, 300_000)],
        proportional_stolen=300_000,
        libr_stolen=300_000,
        now_dt=past_time,
        expires_in_seconds=60,  # Expired 1 hour 59 mins ago
    )

    v = node_b.verify_and_ingest_passport(passport, "CASE-001", reg)
    assert not v.is_valid
    assert v.status == PassportVerificationStatus.EXPIRED


def test_passport_case_and_institution_binding():
    """Verify that passports bound to wrong case or wrong destination institution are rejected."""
    node_a = BankNode("BANK_A")
    node_b = BankNode("BANK_B")
    node_c = BankNode("BANK_C")
    reg = {"BANK_A": node_a.public_key, "BANK_B": node_b.public_key, "BANK_C": node_c.public_key}

    passport = node_a.sign_passport(
        case_id="CASE-001",
        to_institution="BANK_B",
        transfer_ref="TX_104",
        amount_minor=200_000,
        fifo_segments=[(200_000, 200_000)],
        proportional_stolen=200_000,
        libr_stolen=200_000,
    )

    # Wrong case ID
    v_case = node_b.verify_and_ingest_passport(passport, "CASE-DIFFERENT", reg)
    assert not v_case.is_valid
    assert v_case.status == PassportVerificationStatus.CASE_MISMATCH

    # Wrong destination node (addressed to BANK_B, received by BANK_C)
    v_inst = node_c.verify_and_ingest_passport(passport, "CASE-001", reg)
    assert not v_inst.is_valid
    assert v_inst.status == PassportVerificationStatus.INSTITUTION_MISMATCH


def test_missing_passport_widens_uncertainty_range():
    """Verify that missing passports widen evidence range rather than fabricating precision."""
    accounts = [
        {"account_id": "ACC_A", "opening_balance_paise": 1_000_000, "history_complete": True, "bank_id": "BANK_A"},
        {"account_id": "ACC_B", "opening_balance_paise": 500_000, "history_complete": True, "bank_id": "BANK_A"},
        {"account_id": "ACC_C", "opening_balance_paise": 200_000, "history_complete": True, "bank_id": "BANK_B"},
    ]
    txns = [
        {"transaction_id": "TX_SRC", "timestamp": "2026-01-01T10:00:00Z", "from_account": "ACC_A", "to_account": "ACC_B", "amount_paise": 400_000, "transaction_type": "transfer"},
        {"transaction_id": "TX_HOP", "timestamp": "2026-01-01T11:00:00Z", "from_account": "ACC_B", "to_account": "ACC_C", "amount_paise": 300_000, "transaction_type": "transfer"},
    ]

    # Run with fault_missing_transfers on cross-institution hop TX_HOP
    coordinator = FederatedCoordinator()
    res = coordinator.run_trace(
        accounts=accounts,
        transactions=txns,
        source_transaction_id="TX_SRC",
        case_id="CASE_TEST_MISSING",
        suspected_amount_paise=400_000,
        fault_missing_transfers={"TX_HOP"},
    )

    assert res.unverified_transfers_count == 1
    # Check that ACC_C has widened range
    range_c = res.account_ranges["ACC_C"]
    assert range_c.has_unverified_inflow
    assert range_c.widened_by_missing_paise == 300_000
    assert range_c.max_suspected_paise >= 300_000


# ==============================================================================
# 3. API Endpoint Tests
# ==============================================================================

def test_api_federated_compare_endpoint_success():
    """Verify GET /api/v1/federated/compare/{case_id} returns valid side-by-side results."""
    headers = get_auth_headers("investigator")
    response = client.get("/api/v1/federated/compare/CASE-2026-001", headers=headers)
    assert response.status_code == 200, f"API error: {response.text}"

    data = response.json()
    assert data["case_id"] == "CASE-2026-001"
    assert "centralized_results" in data
    assert "federated_results" in data
    assert "methods_match" in data
    assert "institutions" in data
    assert len(data["institutions"]) == 4

    # All three methods match on the verified dataset
    assert data["methods_match"]["fifo"] is True
    assert data["methods_match"]["proportional"] is True
    assert data["methods_match"]["libr"] is True


def test_api_federated_compare_simulated_faults():
    """Verify fault query parameters trigger range widening and unverified logging."""
    headers = get_auth_headers("investigator")
    response = client.get(
        "/api/v1/federated/compare/CASE-2026-001?simulate_missing=true",
        headers=headers,
    )
    assert response.status_code == 200

    data = response.json()
    assert data["unverified_transfers_count"] >= 1
    # Check that at least one account range was widened
    widened_accs = [
        acc for acc, r in data["account_ranges"].items() if r["widened_by_missing_paise"] > 0
    ]
    assert len(widened_accs) >= 1
