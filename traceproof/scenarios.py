"""Preconfigured demonstrable scenarios for TraceProof multi-rail verification."""

from typing import Dict, Any, List


DEMO_SCENARIOS: Dict[str, Dict[str, Any]] = {
    "SCENARIO_1_COMPLETE": {
        "scenario_id": "SCENARIO_1_COMPLETE",
        "title": "Full Multi-Rail Trail (Bank A -> Wallet B -> Bank C)",
        "case_id": "CASE-2026-TP-01",
        "seed_reference": "REF_PAY_2026_001_HOP1",
        "description": (
            "Complete verified multi-hop transaction path: Bank A wire outward transfer -> "
            "Wallet B nodal load -> Wallet B internal P2P transfer -> Bank C settlement allocation. "
            "All Ed25519 signatures are authentic and counterparties are cryptographically confirmed."
        ),
        "expected_status": "COMPLETE",
        "anomaly_settings": {},
    },
    "SCENARIO_2_UNRESOLVED_GAP": {
        "scenario_id": "SCENARIO_2_UNRESOLVED_GAP",
        "title": "Unresolved Settlement Link (Missing Wallet-to-Bank C Allocation)",
        "case_id": "CASE-2026-TP-02",
        "seed_reference": "REF_PAY_2026_001_HOP1",
        "description": (
            "Wallet B recorded an outward merchant checkout transfer, but Bank C / Settlement provider "
            "has no corresponding allocation record. Instead of fabricating the missing hop, TraceProof "
            "flags the relationship as visibly UNRESOLVED, halts the forward branch, and audits the missing rail."
        ),
        "expected_status": "PARTIAL",
        "anomaly_settings": {
            "BANK_C": {"simulate_missing": True},
        },
    },
    "SCENARIO_3_POOLED_SETTLEMENT_FEE_REFUND": {
        "scenario_id": "SCENARIO_3_POOLED_SETTLEMENT_FEE_REFUND",
        "title": "Pooled Multilateral Settlement with Platform Fee & Refund",
        "case_id": "CASE-2026-TP-03",
        "seed_reference": "REF_PAY_2026_001_HOP1",
        "description": (
            "Traces through intermediary fees and partial refunds. Distinguishes underlying economic "
            "payments from aggregated settlement batches to prevent double-counting. Identifies "
            "terminal cash-out boundaries at ATM withdrawal points."
        ),
        "expected_status": "COMPLETE",
        "anomaly_settings": {},
    },
    "SCENARIO_4_ADVERSARIAL_TAMPERED": {
        "scenario_id": "SCENARIO_4_ADVERSARIAL_TAMPERED",
        "title": "Adversarial Integrity Failure (Tampered Envelope in Transit)",
        "case_id": "CASE-2026-TP-04",
        "seed_reference": "REF_PAY_2026_001_HOP1",
        "description": (
            "An adversary or rogue intermediary modified the evidence payload amount in transit. "
            "TraceProof detects the SHA-256 payload hash / Ed25519 signature mismatch, flags the "
            "envelope as TAMPERED_PAYLOAD, and halts unverified expansion."
        ),
        "expected_status": "INVALID_EVIDENCE",
        "anomaly_settings": {
            "WALLET_B": {"simulate_tampered": True},
        },
    },
}


def get_scenario_metadata_list() -> List[Dict[str, Any]]:
    return [
        {
            "scenario_id": sc["scenario_id"],
            "title": sc["title"],
            "case_id": sc["case_id"],
            "seed_reference": sc["seed_reference"],
            "description": sc["description"],
            "expected_status": sc["expected_status"],
        }
        for sc in DEMO_SCENARIOS.values()
    ]
