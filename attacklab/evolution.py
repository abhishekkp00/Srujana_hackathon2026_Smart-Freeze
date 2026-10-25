"""Smart-Freeze Attack Lab — Seeded Evolutionary Search.

Optimizes attacker genome parameters (hops, split sizes, inter-hop delay, clean money
mix share, cash-out timing, spray width) against the defensive posture using a genetic
algorithm.

Fitness Function:
  Maximize: (escaped_rupees + innocent_rupees_held)

Tuning Boundary:
  Training & fitness evaluation uses Attack Families A and B ONLY.
  Held-out Family C is strictly isolated and never seen during evolution.

Governance Notice: "simulated adversary; abstract parameters only".
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import copy
import datetime
import random
from typing import Any, Dict, List, Optional, Tuple

from attacklab.genome import AttackerGenome
from attacklab.simulation import AttackSimulator, SimulationOutcome


@dataclass
class GenerationRecord:
    """Telemetry recorded for a single generation of the evolutionary search."""
    generation: int
    best_fitness: float
    mean_fitness: float
    best_escaped_rupees: float
    best_innocent_held_rupees: float
    best_genome: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "generation": self.generation,
            "best_fitness": round(self.best_fitness, 2),
            "mean_fitness": round(self.mean_fitness, 2),
            "best_escaped_rupees": round(self.best_escaped_rupees, 2),
            "best_innocent_held_rupees": round(self.best_innocent_held_rupees, 2),
            "best_genome": self.best_genome,
        }


@dataclass
class EvolutionRunResult:
    """Complete results from an evolutionary adversary search."""
    seed: int
    population_size: int
    generations_count: int
    history: List[GenerationRecord]
    best_genome: AttackerGenome
    best_fitness: float
    tuning_families: List[str]
    training_timestamp: str
    governance_notice: str = "simulated adversary; abstract parameters only"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "seed": self.seed,
            "population_size": self.population_size,
            "generations_count": self.generations_count,
            "history": [g.to_dict() for g in self.history],
            "best_genome": self.best_genome.to_dict(),
            "best_fitness": round(self.best_fitness, 2),
            "tuning_families": self.tuning_families,
            "training_timestamp": self.training_timestamp,
            "governance_notice": self.governance_notice,
        }


class EvolutionaryAttackerSearch:
    """Seeded Genetic Algorithm optimizing laundering genomes against defense policies."""

    def __init__(
        self,
        population_size: int = 24,
        generations: int = 15,
        mutation_rate: float = 0.35,
        crossover_rate: float = 0.70,
        elite_count: int = 2,
        defense_mode: str = "policy_v2",
        simulator: Optional[AttackSimulator] = None,
    ):
        self.population_size = max(5, min(60, population_size))
        self.generations = max(2, min(40, generations))
        self.mutation_rate = mutation_rate
        self.crossover_rate = crossover_rate
        self.elite_count = max(1, elite_count)
        self.defense_mode = defense_mode
        self.simulator = simulator or AttackSimulator()

    def evaluate_fitness(
        self,
        genome: AttackerGenome,
        seed: int,
    ) -> Tuple[float, float, float]:
        """Evaluate genome fitness against Attack Families A and B ONLY.
        
        Returns:
            (total_fitness_rupees, escaped_rupees, innocent_held_rupees)
        """
        # Strictly Families A and B only
        tuning_families = ["family_a", "family_b"]
        total_fitness = 0.0
        tot_escaped = 0.0
        tot_innocent = 0.0

        for idx, fam in enumerate(tuning_families):
            cid = f"SIM-TUNE-{fam[-1].upper()}-{idx + 1:02d}"
            outcome = self.simulator.evaluate_defense(
                genome=genome,
                case_id=cid,
                family_type=fam,
                defense_mode=self.defense_mode,
                stolen_amount_paise=10_000_000,  # ₹100,000 INR per case
                seed=seed + idx * 100,
            )
            total_fitness += outcome.fitness_rupees
            tot_escaped += outcome.escaped_rupees
            tot_innocent += outcome.innocent_held_rupees

        # Average across tuning cases
        n = len(tuning_families)
        return total_fitness / n, tot_escaped / n, tot_innocent / n

    def run(self, seed: int = 42) -> EvolutionRunResult:
        """Executes the deterministic evolutionary search given a seed."""
        rng = random.Random(seed)
        timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()

        # 1. Initialize deterministic random population
        population: List[AttackerGenome] = [
            AttackerGenome.random_genome(rng) for _ in range(self.population_size)
        ]

        history: List[GenerationRecord] = []
        global_best_genome = population[0]
        global_best_fitness = -1.0

        for gen in range(self.generations):
            fitness_records: List[Tuple[float, float, float, AttackerGenome]] = []
            for idx, g in enumerate(population):
                # Evaluate genome deterministically on tuning benchmark suite
                fit, esc, inn = self.evaluate_fitness(g, seed)
                fitness_records.append((fit, esc, inn, g))

            # Sort descending by fitness
            fitness_records.sort(key=lambda x: x[0], reverse=True)

            best_fit, best_esc, best_inn, best_g = fitness_records[0]
            mean_fit = sum(x[0] for x in fitness_records) / len(fitness_records)

            if best_fit > global_best_fitness:
                global_best_fitness = best_fit
                global_best_genome = best_g

            record = GenerationRecord(
                generation=gen,
                best_fitness=best_fit,
                mean_fitness=mean_fit,
                best_escaped_rupees=best_esc,
                best_innocent_held_rupees=best_inn,
                best_genome=best_g.to_dict(),
            )
            history.append(record)

            # Check if last generation
            if gen == self.generations - 1:
                break

            # 2. Elitism: preserve top performers
            new_population: List[AttackerGenome] = [
                rec[3] for rec in fitness_records[:self.elite_count]
            ]

            # 3. Tournament selection + Crossover + Mutation
            tournament_size = 3
            while len(new_population) < self.population_size:
                # Tournament parent A
                candidates_a = rng.sample(fitness_records, tournament_size)
                parent_a = max(candidates_a, key=lambda x: x[0])[3]

                # Tournament parent B
                candidates_b = rng.sample(fitness_records, tournament_size)
                parent_b = max(candidates_b, key=lambda x: x[0])[3]

                # Crossover
                if rng.random() < self.crossover_rate:
                    child = AttackerGenome.crossover(parent_a, parent_b, rng)
                else:
                    child = copy.deepcopy(parent_a if rng.random() < 0.5 else parent_b)

                # Mutation
                child = child.mutate(rng, self.mutation_rate)
                new_population.append(child)

            population = new_population

        return EvolutionRunResult(
            seed=seed,
            population_size=self.population_size,
            generations_count=self.generations,
            history=history,
            best_genome=global_best_genome,
            best_fitness=global_best_fitness,
            tuning_families=["family_a", "family_b"],
            training_timestamp=timestamp,
            governance_notice="simulated adversary; abstract parameters only",
        )
