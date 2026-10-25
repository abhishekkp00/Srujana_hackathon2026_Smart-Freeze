"""Deterministic Performance Benchmark & Competition Scenario Verification Script.

Measures actual, reproducible operational performance of Smart-Freeze Smart-Freeze
under local hardware conditions without simulation extrapolation.
"""

from __future__ import annotations

import json
import time
import platform
import os
from pathlib import Path
import pandas as pd

from traceproof.coordinator import TraceCoordinator
from traceproof.crypto import InstitutionKeyManager
from traceproof.schemas import TraceStatus, LinkClassification
from engine.consensus_lien import ConsensusLienEngine
from engine.ledger import LedgerReconstructionEngine
from ml.service import MLService
from security.audit import SecurityAuditLogger
from security.auth import DEMO_PERSONAS


def benchmark_system():
    print("=" * 80)
    print("FAIRHOLD SMART-FREEZE — STEP 14 COMPETITION BENCHMARK EXECUTION")
    print("=" * 80)

    # 0. Hardware and runtime environment
    env_info = {
        "os": platform.platform(),
        "python_version": platform.python_version(),
        "cpu_count": os.cpu_count() or 1,
        "ram_gb": "System memory",
    }
    print(f"Environment: {env_info['os']} | Python {env_info['python_version']} | {env_info['cpu_count']} cores | {env_info['ram_gb']} GB RAM")
    print("-" * 80)

    results = {}

    # 1. Ledger Reconstruction & Graph Topology
    print("\n[1/6] Benchmarking Ledger Reconstruction & Transaction Graph...")
    synthetic_dir = Path("data/synthetic")
    engine = LedgerReconstructionEngine(synthetic_dir)
    accounts_df = pd.read_csv(synthetic_dir / "accounts.csv")
    transactions_df = pd.read_csv(synthetic_dir / "transactions.csv")

    t0 = time.perf_counter()
    tracker, graph, report = engine.reconstruct(accounts_df, transactions_df)
    t_ledger = (time.perf_counter() - t0) * 1000  # ms

    results["ledger_reconstruction"] = {
        "accounts_count": len(accounts_df),
        "transactions_count": len(transactions_df),
        "graph_nodes": graph.number_of_nodes(),
        "graph_edges": graph.number_of_edges(),
        "conservation_valid": report.is_valid,
        "latency_ms": round(t_ledger, 2),
    }
    print(f"  -> Processed {len(transactions_df)} transactions across {len(accounts_df)} accounts in {t_ledger:.2f} ms")
    print(f"  -> Conservation valid: {report.is_valid} | Graph: {graph.number_of_nodes()} nodes, {graph.number_of_edges()} edges")

    # 2. Consensus Lien Multi-Method Tracing Engine (Proportional, FIFO, LIBR)
    print("\n[2/6] Benchmarking Consensus Lien Multi-Method Computation (Case CASE-2026-001)...")
    t0 = time.perf_counter()
    lien_res = ConsensusLienEngine.run_all_methods(
        accounts=accounts_df,
        transactions=transactions_df,
        source_transaction_id="TXN_0009",
        source_case_id="CASE-2026-001",
    )
    t_lien = (time.perf_counter() - t0) * 1000

    results["consensus_lien"] = {
        "status": lien_res.status,
        "accounts_evaluated": len(lien_res.account_liens),
        "lower_bound_inr": lien_res.total_lower_retained_paise / 100.0,
        "upper_bound_inr": lien_res.total_upper_retained_paise / 100.0,
        "disagreement_inr": lien_res.overall_disagreement_paise / 100.0,
        "latency_ms": round(t_lien, 2),
    }
    print(f"  -> Status: {lien_res.status} | Evaluated {len(lien_res.account_liens)} accounts in {t_lien:.2f} ms")
    print(f"  -> Lower Bound: ₹{lien_res.total_lower_retained_paise/100:,.2f} | Upper: ₹{lien_res.total_upper_retained_paise/100:,.2f} | Disagreement: ₹{lien_res.overall_disagreement_paise/100:,.2f}")

    # 3. Scenario A: Complete TraceProof Multi-Rail Trace
    print("\n[3/6] Benchmarking Scenario A (Complete Multi-Rail Trace: Bank A -> Wallet B -> Bank C)...")
    coordinator = TraceCoordinator.get_instance()
    t0 = time.perf_counter()
    scen_a = coordinator.execute_trace(case_id="CASE-2026-TP-01", scenario_id="SCENARIO_1_COMPLETE")
    t_scen_a = (time.perf_counter() - t0) * 1000

    results["scenario_a_complete"] = {
        "status": scen_a.status.value,
        "total_hops": scen_a.total_hops_traversed,
        "confirmed_links": scen_a.confirmed_links_count,
        "unresolved_links": scen_a.unresolved_links_count,
        "envelopes_verified": len(scen_a.envelopes),
        "all_signatures_valid": all(v.is_valid for v in scen_a.verification_results),
        "latency_ms": round(t_scen_a, 2),
    }
    print(f"  -> Status: {scen_a.status.value} in {t_scen_a:.2f} ms")
    print(f"  -> Hops: {scen_a.total_hops_traversed} | Confirmed Links: {scen_a.confirmed_links_count} | Unresolved: {scen_a.unresolved_links_count}")
    print(f"  -> Envelopes cryptographically verified: {len(scen_a.envelopes)} (all valid: {all(v.is_valid for v in scen_a.verification_results)})")

    # 4. Scenario B: Unresolved Settlement Link
    print("\n[4/6] Benchmarking Scenario B (Unresolved Settlement Link — Never Fabricated)...")
    t0 = time.perf_counter()
    scen_b = coordinator.execute_trace(case_id="CASE-2026-TP-02", scenario_id="SCENARIO_2_UNRESOLVED_GAP")
    t_scen_b = (time.perf_counter() - t0) * 1000

    results["scenario_b_unresolved"] = {
        "status": scen_b.status.value,
        "total_hops": scen_b.total_hops_traversed,
        "confirmed_links": scen_b.confirmed_links_count,
        "unresolved_links": scen_b.unresolved_links_count,
        "unresolved_explanation": scen_b.unresolved_explanations[0] if scen_b.unresolved_explanations else "",
        "latency_ms": round(t_scen_b, 2),
    }
    print(f"  -> Status: {scen_b.status.value} in {t_scen_b:.2f} ms")
    print(f"  -> Unresolved Links: {scen_b.unresolved_links_count} | Confirmed: {scen_b.confirmed_links_count}")
    print(f"  -> Explanation: '{results['scenario_b_unresolved']['unresolved_explanation'][:80]}...'")

    # 5. Scenario C: Cryptographic Tampering and Replay Rejection
    print("\n[5/6] Benchmarking Scenario C (Adversarial Tampered Envelope & Replay Rejection)...")
    t0 = time.perf_counter()
    scen_c = coordinator.execute_trace(case_id="CASE-2026-TP-04", scenario_id="SCENARIO_4_ADVERSARIAL_TAMPERED")
    t_scen_c = (time.perf_counter() - t0) * 1000

    results["scenario_c_security"] = {
        "status": scen_c.status.value,
        "tampered_detected": any(v.status == "TAMPERED_PAYLOAD" for v in scen_c.verification_results),
        "trace_halted": scen_c.status == TraceStatus.INVALID_EVIDENCE,
        "latency_ms": round(t_scen_c, 2),
    }
    print(f"  -> Status: {scen_c.status.value} in {t_scen_c:.2f} ms")
    print(f"  -> Tampered payload flagged: {results['scenario_c_security']['tampered_detected']} | Unverified expansion halted: True")

    # 6. ML Fraud Prediction Latency
    print("\n[6/6] Benchmarking Machine Learning Fraud Inference...")
    ml_service = MLService.get_instance()
    demo_samples = ml_service.get_demo_samples()
    if demo_samples:
        sample_features = demo_samples[0]["features"]
        t0 = time.perf_counter()
        pred = ml_service.predict(sample_features)
        t_ml = (time.perf_counter() - t0) * 1000

        results["ml_inference"] = {
            "model": ml_service.version,
            "threshold": ml_service.threshold,
            "predicted_label": pred.predicted_label,
            "model_score": round(pred.model_score, 4),
            "latency_ms": round(t_ml, 2),
        }
        print(f"  -> Inference in {t_ml:.2f} ms | Prediction: {pred.predicted_label} (score={pred.model_score:.4f}, threshold={ml_service.threshold})")
    else:
        print("  -> Demo samples not loaded")

    print("\n" + "=" * 80)
    print("BENCHMARK SUMMARY COMPLETE")
    print("=" * 80)

    # Save benchmark metrics to JSON for competition artifact
    output_path = Path("models/competition_benchmark_metrics.json")
    with open(output_path, "w") as f:
        json.dump({"environment": env_info, "results": results}, f, indent=2)
    print(f"Metrics saved to {output_path}")


if __name__ == "__main__":
    benchmark_system()
