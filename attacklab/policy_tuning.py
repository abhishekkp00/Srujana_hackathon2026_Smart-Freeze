"""Smart-Freeze Attack Lab — Policy Tuning & Held-Out Family Evaluation.

Tunes defense policy settings on Attack Families A and B only, then evaluates
adversarial resistance on a held-out Family C (Heavy Commingling).

Compares:
- Defenses Off (baseline naive behavior)
- Policy V1 (naive aggressive whole-account freeze)
- Policy V2 (Smart-Freeze: Consensus Lien Core + Harm Mitigation + De-Minimis)

Reports:
- Escaped Money (INR)
- Innocent Money Held (INR)
- Number of Holds

Governance Notice: "simulated adversary; abstract parameters only".
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import datetime
from typing import Any, Dict, List, Optional

from attacklab.evolution import EvolutionaryAttackerSearch, EvolutionRunResult
from attacklab.genome import AttackerGenome
from attacklab.simulation import AttackSimulator, SimulationOutcome


@dataclass
class PolicyEvaluationSummary:
    """Quantitative summary of defense performance against the evolved adversary."""
    defense_mode: str  # "defenses_off", "policy_v1", "policy_v2"
    escaped_money_inr: float
    innocent_money_held_inr: float
    number_of_holds: int
    attacker_fitness_inr: float
    captured_money_inr: float
    recovery_rate_pct: float
    collateral_damage_rate_pct: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "defense_mode": self.defense_mode,
            "escaped_money_inr": round(self.escaped_money_inr, 2),
            "innocent_money_held_inr": round(self.innocent_money_held_inr, 2),
            "number_of_holds": self.number_of_holds,
            "attacker_fitness_inr": round(self.attacker_fitness_inr, 2),
            "captured_money_inr": round(self.captured_money_inr, 2),
            "recovery_rate_pct": round(self.recovery_rate_pct, 2),
            "collateral_damage_rate_pct": round(self.collateral_damage_rate_pct, 2),
        }


@dataclass
class AttackLabReport:
    """Comprehensive Attack Lab report comparing defense postures and held-out generalization."""
    seed: int
    training_timestamp: str
    evolved_genome: Dict[str, Any]
    evolution_history: List[Dict[str, Any]]
    
    # Tuning performance (Families A and B)
    tuning_tuning_families: List[str]
    tuning_defenses_off: PolicyEvaluationSummary
    tuning_policy_v1: PolicyEvaluationSummary
    tuning_policy_v2: PolicyEvaluationSummary

    # Held-out evaluation (Family C - Heavy Commingling)
    held_out_family: str
    held_out_defenses_off: PolicyEvaluationSummary
    held_out_policy_v1: PolicyEvaluationSummary
    held_out_policy_v2: PolicyEvaluationSummary

    governance_notice: str = "simulated adversary; abstract parameters only"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "seed": self.seed,
            "training_timestamp": self.training_timestamp,
            "evolved_genome": self.evolved_genome,
            "evolution_history": self.evolution_history,
            "tuning_families": self.tuning_tuning_families,
            "tuning_comparison": {
                "defenses_off": self.tuning_defenses_off.to_dict(),
                "policy_v1": self.tuning_policy_v1.to_dict(),
                "policy_v2": self.tuning_policy_v2.to_dict(),
            },
            "held_out_family": self.held_out_family,
            "held_out_comparison": {
                "defenses_off": self.held_out_defenses_off.to_dict(),
                "policy_v1": self.held_out_policy_v1.to_dict(),
                "policy_v2": self.held_out_policy_v2.to_dict(),
            },
            "governance_notice": self.governance_notice,
        }


class AttackLabEngine:
    """Coordinates evolutionary search and cross-family defense evaluation."""

    def __init__(self, simulator: Optional[AttackSimulator] = None):
        self.simulator = simulator or AttackSimulator()

    def _summarize_outcomes(
        self,
        outcomes: List[SimulationOutcome],
        mode: str,
    ) -> PolicyEvaluationSummary:
        """Aggregates per-case simulation outcomes into policy summary metrics."""
        tot_stolen = sum(o.stolen_amount_paise for o in outcomes) / 100.0
        tot_escaped = sum(o.escaped_rupees for o in outcomes)
        tot_captured = sum(o.captured_paise for o in outcomes) / 100.0
        tot_innocent = sum(o.innocent_held_rupees for o in outcomes)
        tot_holds = sum(o.holds_count for o in outcomes)
        tot_fitness = sum(o.fitness_rupees for o in outcomes)

        recovery_rate = (tot_captured / max(1.0, tot_stolen)) * 100.0
        collateral_rate = (tot_innocent / max(1.0, tot_stolen)) * 100.0

        return PolicyEvaluationSummary(
            defense_mode=mode,
            escaped_money_inr=tot_escaped,
            innocent_money_held_inr=tot_innocent,
            number_of_holds=tot_holds,
            attacker_fitness_inr=tot_fitness,
            captured_money_inr=tot_captured,
            recovery_rate_pct=recovery_rate,
            collateral_damage_rate_pct=collateral_rate,
        )

    def run_full_experiment(
        self,
        seed: int = 42,
        population_size: int = 24,
        generations: int = 15,
    ) -> AttackLabReport:
        """Runs the evolutionary tuning on Families A & B and evaluates on held-out Family C."""
        timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()

        # Step 1: Evolve adversary against Policy V2 using Families A and B ONLY
        search = EvolutionaryAttackerSearch(
            population_size=population_size,
            generations=generations,
            defense_mode="policy_v2",
            simulator=self.simulator,
        )
        run_res = search.run(seed=seed)
        best_genome = run_res.best_genome

        # Step 2: Evaluate evolved adversary on Tuning Families (A and B)
        # 10 cases per family = 20 tuning cases
        modes = ["defenses_off", "policy_v1", "policy_v2"]
        tuning_outcomes: Dict[str, List[SimulationOutcome]] = {m: [] for m in modes}

        for fam in ["family_a", "family_b"]:
            for i in range(5):
                cid = f"SIM-TUNE-{fam[-1].upper()}-{i + 1:02d}"
                c_seed = seed + 500 + i * 13
                for mode in modes:
                    out = self.simulator.evaluate_defense(
                        genome=best_genome,
                        case_id=cid,
                        family_type=fam,
                        defense_mode=mode,
                        stolen_amount_paise=10_000_000,  # ₹100,000 per case
                        seed=c_seed,
                    )
                    tuning_outcomes[mode].append(out)

        tuning_off = self._summarize_outcomes(tuning_outcomes["defenses_off"], "defenses_off")
        tuning_v1 = self._summarize_outcomes(tuning_outcomes["policy_v1"], "policy_v1")
        tuning_v2 = self._summarize_outcomes(tuning_outcomes["policy_v2"], "policy_v2")

        # Step 3: Evaluate evolved adversary on Held-Out Family C (Heavy Commingling)
        # Held-out Family C was NEVER used during evolution or tuning
        held_out_outcomes: Dict[str, List[SimulationOutcome]] = {m: [] for m in modes}

        for i in range(5):
            cid = f"SIM-TEST-C-{i + 1:02d}"
            c_seed = seed + 10_000 + i * 29
            for mode in modes:
                out = self.simulator.evaluate_defense(
                    genome=best_genome,
                    case_id=cid,
                    family_type="family_c",
                    defense_mode=mode,
                    stolen_amount_paise=10_000_000,  # ₹100,000 per case
                    seed=c_seed,
                )
                held_out_outcomes[mode].append(out)

        held_off = self._summarize_outcomes(held_out_outcomes["defenses_off"], "defenses_off")
        held_v1 = self._summarize_outcomes(held_out_outcomes["policy_v1"], "policy_v1")
        held_v2 = self._summarize_outcomes(held_out_outcomes["policy_v2"], "policy_v2")

        return AttackLabReport(
            seed=seed,
            training_timestamp=timestamp,
            evolved_genome=best_genome.to_dict(),
            evolution_history=[r.to_dict() for r in run_res.history],
            tuning_tuning_families=["family_a", "family_b"],
            tuning_defenses_off=tuning_off,
            tuning_policy_v1=tuning_v1,
            tuning_policy_v2=tuning_v2,
            held_out_family="family_c_heavy_commingling",
            held_out_defenses_off=held_off,
            held_out_policy_v1=held_v1,
            held_out_policy_v2=held_v2,
            governance_notice="simulated adversary; abstract parameters only",
        )
