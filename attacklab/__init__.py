"""Smart-Freeze Attack Lab Module.

Simulates adversarial laundering strategies using an evolutionary search over abstract
genome parameters, tunes policy defenses on Families A and B, and validates resilience
against collateral damage on held-out Family C.

Governance Notice: "simulated adversary; abstract parameters only".
"""

from attacklab.genome import AttackerGenome
from attacklab.simulation import AttackSimulator, SimulationOutcome
from attacklab.evolution import EvolutionaryAttackerSearch, EvolutionRunResult, GenerationRecord
from attacklab.policy_tuning import AttackLabEngine, AttackLabReport, PolicyEvaluationSummary

__all__ = [
    "AttackerGenome",
    "AttackSimulator",
    "SimulationOutcome",
    "EvolutionaryAttackerSearch",
    "EvolutionRunResult",
    "GenerationRecord",
    "AttackLabEngine",
    "AttackLabReport",
    "PolicyEvaluationSummary",
]
