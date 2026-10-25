"""
Tests for AttackLab:
1. Determinism given a seed (same seed -> identical generation metrics and best genome).
2. Fitness improves (or stays >=) over generations for the same seed.
3. Held-out family C is NEVER used in tuning (strictly evaluated post-evolution).
4. Defenses off vs Policy V1 vs Policy V2 metrics verification (escaped rupees, innocent held, holds).
5. Governance label: "simulated adversary; abstract parameters only" present in outputs and API response.
6. API endpoint GET /api/attacklab/run integration test.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from attacklab.genome import AttackerGenome
from attacklab.evolution import EvolutionaryAttackerSearch
from attacklab.policy_tuning import AttackLabEngine
from attacklab.simulation import AttackSimulator


AUTH_HEADERS = {"Authorization": "Bearer dev_token_admin"}


def test_attacklab_determinism():
    """Identical seeds produce identical generation trajectories and evolved genomes."""
    engine_1 = AttackLabEngine()
    report_1 = engine_1.run_full_experiment(seed=42, population_size=12, generations=4)

    engine_2 = AttackLabEngine()
    report_2 = engine_2.run_full_experiment(seed=42, population_size=12, generations=4)

    assert report_1.seed == report_2.seed
    assert report_1.evolved_genome["hops"] == report_2.evolved_genome["hops"]
    assert report_1.evolved_genome["split_sizes"] == report_2.evolved_genome["split_sizes"]
    assert report_1.evolved_genome["delay_between_hops_minutes"] == report_2.evolved_genome["delay_between_hops_minutes"]
    assert report_1.evolved_genome["clean_mix_share"] == report_2.evolved_genome["clean_mix_share"]
    assert report_1.evolved_genome["cash_out_timing_hours"] == report_2.evolved_genome["cash_out_timing_hours"]
    assert report_1.evolved_genome["spray_width"] == report_2.evolved_genome["spray_width"]

    # Generation trajectory equality
    assert len(report_1.evolution_history) == len(report_2.evolution_history)
    for g1, g2 in zip(report_1.evolution_history, report_2.evolution_history):
        assert g1["generation"] == g2["generation"]
        assert g1["best_fitness"] == g2["best_fitness"]
        assert g1["mean_fitness"] == g2["mean_fitness"]
        assert g1["best_escaped_rupees"] == g2["best_escaped_rupees"]
        assert g1["best_innocent_held_rupees"] == g2["best_innocent_held_rupees"]


def test_attacklab_fitness_improves_over_generations():
    """Fitness of the best genome in later generations is >= fitness in generation 0."""
    search = EvolutionaryAttackerSearch(
        population_size=16,
        generations=6,
        defense_mode="policy_v1",
    )
    run_res = search.run(seed=101)
    history = run_res.history

    assert len(history) == 6
    first_gen_best = history[0].best_fitness
    last_gen_best = history[-1].best_fitness

    # Because elitism preserves the best across generations, best_fitness is monotonically non-decreasing
    assert last_gen_best >= first_gen_best, f"Expected {last_gen_best} >= {first_gen_best}"

    # Verify best_fitness is non-decreasing across all generations
    for i in range(1, len(history)):
        assert history[i].best_fitness >= history[i - 1].best_fitness - 1e-6


def test_held_out_family_never_used_in_tuning():
    """Held-out family C is strictly isolated and never accessed during evolutionary fitness evaluation."""
    sim = AttackSimulator()
    accessed_families = []

    original_evaluate_defense = sim.evaluate_defense

    def spy_evaluate_defense(genome, case_id, family_type, defense_mode, stolen_amount_paise, seed):
        accessed_families.append(family_type)
        return original_evaluate_defense(genome, case_id, family_type, defense_mode, stolen_amount_paise, seed)

    sim.evaluate_defense = spy_evaluate_defense

    search = EvolutionaryAttackerSearch(
        population_size=10,
        generations=3,
        defense_mode="policy_v1",
        simulator=sim,
    )
    search.run(seed=77)

    # Verify that during the entire evolution, family_c was NEVER simulated
    assert "family_c" not in accessed_families
    assert "family_a" in accessed_families
    assert "family_b" in accessed_families


def test_defenses_off_vs_policy_v1_vs_policy_v2_metrics():
    """
    Validates that:
    1. Defenses off allows maximum escaped money and zero innocent holds.
    2. Policy V1 (naive freeze) catches stolen money but causes catastrophic collateral damage on held-out Family C.
    3. Policy V2 (Smart-Freeze consensus + harm discounting) preserves recovery while drastically reducing innocent holds.
    """
    engine = AttackLabEngine()
    report = engine.run_full_experiment(seed=42, population_size=10, generations=3)

    # Check Tuning comparison (Families A & B)
    tuning_off = report.tuning_defenses_off
    tuning_v1 = report.tuning_policy_v1
    tuning_v2 = report.tuning_policy_v2

    assert tuning_off.number_of_holds == 0
    assert tuning_off.innocent_money_held_inr == 0.0
    assert tuning_off.escaped_money_inr > 0

    # Policy V1 holds more innocent money than Policy V2
    assert tuning_v1.number_of_holds >= tuning_v2.number_of_holds
    assert tuning_v1.innocent_money_held_inr >= tuning_v2.innocent_money_held_inr

    # Check Held-out family C (Heavy Commingling / Payment Aggregator / Merchant)
    heldout_v1 = report.held_out_policy_v1
    heldout_v2 = report.held_out_policy_v2

    # In Family C, innocent money held under naive V1 is huge because merchant accounts are frozen wholesale
    # In Policy V2, harm scoring and de-minimis limits prevent freezing whole innocent working capital balances
    assert heldout_v1.innocent_money_held_inr > heldout_v2.innocent_money_held_inr
    assert heldout_v1.number_of_holds > heldout_v2.number_of_holds


def test_governance_label_present():
    """Verify mandatory governance label 'simulated adversary; abstract parameters only'."""
    engine = AttackLabEngine()
    report = engine.run_full_experiment(seed=42, population_size=10, generations=2)

    assert report.governance_notice == "simulated adversary; abstract parameters only"
    report_dict = report.to_dict()
    assert report_dict["governance_notice"] == "simulated adversary; abstract parameters only"


def test_api_attacklab_run_endpoint():
    """Test FastAPI GET /api/attacklab/run endpoint with authentication."""
    client = TestClient(app)
    resp = client.get(
        "/api/attacklab/run?seed=99&population=10&generations=2",
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 200

    data = resp.json()
    assert data["seed"] == 99
    assert data["governance_notice"] == "simulated adversary; abstract parameters only"
    assert "evolved_genome" in data
    assert "evolution_history" in data
    assert len(data["evolution_history"]) == 2
    assert "tuning_comparison" in data
    assert "held_out_comparison" in data
    assert "defenses_off" in data["tuning_comparison"]
    assert "policy_v1" in data["tuning_comparison"]
    assert "policy_v2" in data["tuning_comparison"]
    assert "policy_v1" in data["held_out_comparison"]
    assert "policy_v2" in data["held_out_comparison"]

    # Check genome structure
    genome = data["evolved_genome"]
    assert 2 <= genome["hops"] <= 8
    assert 2 <= len(genome["split_sizes"]) <= 8
    assert abs(sum(genome["split_sizes"]) - 1.0) < 0.02
    assert 5 <= genome["delay_between_hops_minutes"] <= 1440
    assert 0.0 <= genome["clean_mix_share"] <= 0.95
    assert 1 <= genome["cash_out_timing_hours"] <= 72
    assert 1 <= genome["spray_width"] <= 12

