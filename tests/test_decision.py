"""Tests for Smart-Freeze Decision Support Engine (engine/decision.py).

Verifies all safeguard invariants, transparent harm scoring, policy dials, and API endpoints:
1. Invariant 1: Harm signals can ONLY reduce the margin, NEVER the core (tested with random inputs).
2. Invariant 2: Uploaded documents NEVER release anything alone (strictly require human review).
3. Invariant 3: Accounts below configurable de-minimis total stolen amount get tracking, not a hold.
4. Invariant 4: When core is 0, margin is large, and mule score is high, recommend time-boxed margin hold needing approval.
5. Invariant 5: Account-level holds strictly require human analyst approval.
6. Invariant 6: Free funds conservation: free = max(0, balance - effective_held).
7. Policy dials: Conservative, Balanced, and Aggressive behave according to configured parameters.
8. API endpoint: GET /api/cases/{case_id}/recommendations returns valid response with governance notice.
"""

import random
from typing import Any, Dict, List
import pytest
from fastapi.testclient import TestClient

from app.main import app
from engine.decision import (
    DecisionAction,
    DecisionEngine,
    PolicyConfig,
    RECOMMENDATION_DISCLAIMER,
)

client = TestClient(app)
AUTH_HEADERS = {"Authorization": "Bearer dev_token_admin"}


# ==============================================================================
# 1. Invariant Tests with Randomized Inputs
# ==============================================================================

def test_invariant_1_harm_signals_never_reduce_core_randomized():
    """Invariant 1: Harm signals and evidence can ONLY reduce the MARGIN, NEVER the core."""
    engine = DecisionEngine()
    policy = engine.get_policy("balanced")
    rng = random.Random(101)

    for _ in range(500):
        core = rng.randint(50_000, 5_000_000)
        margin = rng.randint(0, 5_000_000)
        balance = core + margin + rng.randint(0, 2_000_000)
        harm_score = rng.random()  # 0.0 to 1.0
        mule_score = rng.uniform(0.0, 100.0)

        rec = engine.evaluate_account(
            account_id="ACC_TEST",
            current_balance=balance,
            core_paise=core,
            margin_paise=margin,
            harm_score=harm_score,
            harm_reasons=["HARM_TEST"],
            mule_score=mule_score,
            policy=policy,
            override_de_minimis=0,  # Ensure above de-minimis to test core protection
        )

        # STRICT INVARIANT: held_core must EQUAL core exactly
        assert rec.held_core_paise == core, (
            f"Harm reduced core! core={core}, held_core={rec.held_core_paise}, harm={harm_score}"
        )
        assert rec.core == core
        # Margin hold can be reduced by harm
        assert rec.held_margin_paise <= margin


def test_invariant_2_uploaded_documents_never_release_anything_alone():
    """Invariant 2: Uploaded documents NEVER release anything alone; strictly require human review."""
    engine = DecisionEngine()
    policy = engine.get_policy("balanced")

    core = 500_000
    margin = 300_000
    balance = 1_000_000

    # Baseline evaluation without documents
    rec_no_doc = engine.evaluate_account(
        account_id="ACC_MERCHANT",
        current_balance=balance,
        core_paise=core,
        margin_paise=margin,
        harm_score=0.2,
        harm_reasons=[],
        mule_score=20.0,
        policy=policy,
        uploaded_documents=None,
    )

    # Evaluation with uploaded dispute / commercial documents
    uploaded_docs = [
        {"doc_id": "DOC_1", "type": "invoice", "filename": "vendor_contract.pdf"},
        {"doc_id": "DOC_2", "type": "tax_return", "filename": "gst_return.pdf"},
    ]

    rec_with_doc = engine.evaluate_account(
        account_id="ACC_MERCHANT",
        current_balance=balance,
        core_paise=core,
        margin_paise=margin,
        harm_score=0.2,
        harm_reasons=[],
        mule_score=20.0,
        policy=policy,
        uploaded_documents=uploaded_docs,
    )

    # STRICT INVARIANTS:
    # 1. Uploaded documents must require human approval
    assert rec_with_doc.requires_human_approval is True
    # 2. Documents alone must NOT reduce the held core or margin
    assert rec_with_doc.held_core_paise == rec_no_doc.held_core_paise
    assert rec_with_doc.held_margin_paise == rec_no_doc.held_margin_paise
    # 3. Documents alone must NOT change action to 'none'
    assert rec_with_doc.action != DecisionAction.NONE.value
    # 4. Reason code is explicitly logged
    assert any("DOC_SUBMITTED_REQUIRES_ANALYST" in r for r in rec_with_doc.reasons)


def test_invariant_3_de_minimis_threshold_applied_to_total_stolen():
    """Invariant 3: Accounts below configurable de-minimis total stolen get tracking, not a hold."""
    engine = DecisionEngine()
    policy = engine.get_policy("balanced")  # de_minimis_total_paise = 200_000 (₹2,000)

    # Case A: Below de-minimis (core=100,000 + margin=50,000 = 150,000 paise < 200,000)
    rec_below = engine.evaluate_account(
        account_id="ACC_SMALL",
        current_balance=1_000_000,
        core_paise=100_000,
        margin_paise=50_000,
        harm_score=0.0,
        harm_reasons=[],
        mule_score=10.0,
        policy=policy,
    )
    assert rec_below.action == DecisionAction.NONE.value
    assert rec_below.held_core_paise == 0
    assert rec_below.held_margin_paise == 0
    assert rec_below.free == 1_000_000
    assert any("DE_MINIMIS_TRACKING_ONLY" in r for r in rec_below.reasons)

    # Case B: Above de-minimis (core=150,000 + margin=100,000 = 250,000 paise >= 200,000)
    rec_above = engine.evaluate_account(
        account_id="ACC_LARGE",
        current_balance=1_000_000,
        core_paise=150_000,
        margin_paise=100_000,
        harm_score=0.0,
        harm_reasons=[],
        mule_score=10.0,
        policy=policy,
    )
    assert rec_above.action != DecisionAction.NONE.value
    assert rec_above.held_core_paise == 150_000


def test_invariant_4_mule_spike_zero_core_large_margin():
    """Invariant 4: If core is 0, margin is large, and mule score high, recommend time-boxed margin hold needing approval."""
    engine = DecisionEngine()
    policy = engine.get_policy("balanced")  # large_margin_threshold = 100_000, mule_thresh = 60.0

    rec = engine.evaluate_account(
        account_id="ACC_MULE_SPIKE",
        current_balance=2_000_000,
        core_paise=0,
        margin_paise=500_000,  # >= 100,000
        harm_score=0.1,
        harm_reasons=[],
        mule_score=72.5,  # >= 60.0
        policy=policy,
    )

    # STRICT INVARIANTS:
    assert rec.core == 0
    assert rec.action == DecisionAction.LIEN_CORE_PLUS_MARGIN.value
    assert rec.held_margin_paise == 500_000
    assert rec.requires_human_approval is True
    assert any("HIGH_MULE_RISK_MARGIN_HOLD" in r for r in rec.reasons)


def test_invariant_5_account_level_hold_requires_human_approval():
    """Invariant 5: Account-level holds strictly require human analyst approval."""
    engine = DecisionEngine()
    policy = engine.get_policy("balanced")

    rec = engine.evaluate_account(
        account_id="ACC_SEVERE_MULE",
        current_balance=1_000_000,
        core_paise=800_000,
        margin_paise=150_000,
        harm_score=0.0,
        harm_reasons=[],
        mule_score=92.0,  # Critical mule
        policy=policy,
    )

    if rec.action == DecisionAction.ACCOUNT_LEVEL_HOLD.value:
        assert rec.requires_human_approval is True
        assert any("ACCOUNT_LEVEL_HOLD_ANALYST_REQ" in r for r in rec.reasons)


def test_invariant_6_free_funds_conservation_randomized():
    """Invariant 6: free = max(0, balance - effective_held); free funds are strictly non-negative."""
    engine = DecisionEngine()
    policy = engine.get_policy("balanced")
    rng = random.Random(202)

    for _ in range(500):
        balance = rng.randint(0, 5_000_000)
        core = rng.randint(0, 3_000_000)
        margin = rng.randint(0, 3_000_000)
        harm = rng.random()
        mule = rng.uniform(0.0, 100.0)

        rec = engine.evaluate_account(
            account_id="ACC_FREE_TEST",
            current_balance=balance,
            core_paise=core,
            margin_paise=margin,
            harm_score=harm,
            harm_reasons=[],
            mule_score=mule,
            policy=policy,
        )

        assert rec.free >= 0
        expected_held = min(balance, rec.held_core_paise + rec.held_margin_paise)
        assert rec.free == max(0, balance - expected_held)


# ==============================================================================
# 2. Policy Dial Configuration Tests
# ==============================================================================

def test_policy_dials_conservative_vs_aggressive():
    """Verify conservative policy protects margin more, while aggressive captures more."""
    engine = DecisionEngine()
    p_cons = engine.get_policy("conservative")
    p_aggr = engine.get_policy("aggressive")

    balance = 2_000_000
    core = 400_000
    margin = 300_000
    harm = 0.50
    mule = 40.0

    rec_cons = engine.evaluate_account(
        "ACC_DIAL", balance, core, margin, harm, ["HARM_SALARY"], mule, p_cons
    )
    rec_aggr = engine.evaluate_account(
        "ACC_DIAL", balance, core, margin, harm, ["HARM_SALARY"], mule, p_aggr
    )

    # Conservative discounts margin more (harm_reduction_factor 1.0 vs 0.2)
    assert rec_cons.held_margin_paise < rec_aggr.held_margin_paise
    # But both preserve the core exactly
    assert rec_cons.held_core_paise == core
    assert rec_aggr.held_core_paise == core


# ==============================================================================
# 3. Transparent Harm Score Rules Test
# ==============================================================================

def test_transparent_harm_score_calculation():
    """Verify clean balance share, salary, merchant, and debits rules with reason codes."""
    engine = DecisionEngine()

    txs = [
        {"to_account": "ACC_HARM", "amount_paise": 500_000, "transaction_type": "salary_credit"},
        {"from_account": "ACC_HARM", "amount_paise": 50_000, "transaction_type": "utility"},
    ]
    meta = {"account_type": "salaried"}

    score, reasons = engine.compute_harm_score(
        account_id="ACC_HARM",
        current_balance=10_000_000,
        upper_suspected=500_000,  # 95% clean
        transactions=txs,
        account_meta=meta,
    )

    assert score > 0.70  # clean share (0.38) + salary (0.30) + scheduled (0.10)
    assert any("HARM_CLEAN_MAJORITY" in r for r in reasons)
    assert any("HARM_SALARY_INCOME" in r for r in reasons)
    assert any("HARM_SCHEDULED_DEBITS" in r for r in reasons)


# ==============================================================================
# 4. API Endpoint Integration Tests
# ==============================================================================

def test_api_case_recommendations_endpoint():
    """Verify GET /api/cases/{case_id}/recommendations returns structured recommendations."""
    resp = client.get("/api/cases/CASE-2026-001/recommendations", headers=AUTH_HEADERS)
    assert resp.status_code == 200, f"Error: {resp.text}"

    data = resp.json()
    assert data["case_id"] == "CASE-2026-001"
    assert data["policy_name"] == "balanced"
    assert data["policy_version"] == "1.0.0"
    assert data["governance_notice"] == RECOMMENDATION_DISCLAIMER
    assert len(data["recommendations"]) > 0

    for rec in data["recommendations"]:
        assert rec["action"] in [a.value for a in DecisionAction]
        assert rec["free"] >= 0
        assert rec["core"] >= 0
        assert rec["margin"] >= 0
        assert isinstance(rec["reasons"], list)
        assert isinstance(rec["requires_human_approval"], bool)


def test_api_case_recommendations_policy_param():
    """Verify policy dial query parameter switches policy in API output."""
    resp_cons = client.get(
        "/api/cases/CASE-2026-001/recommendations?policy=conservative",
        headers=AUTH_HEADERS,
    )
    assert resp_cons.status_code == 200
    assert resp_cons.json()["policy_name"] == "conservative"

    resp_aggr = client.get(
        "/api/cases/CASE-2026-001/recommendations?policy=aggressive",
        headers=AUTH_HEADERS,
    )
    assert resp_aggr.status_code == 200
    assert resp_aggr.json()["policy_name"] == "aggressive"
