"""Smart-Freeze Attack Lab — Attacker Genome Definition.

Defines the abstract parametric genome of a simulated financial adversary.
Abstract parameters include hops, split sizes, inter-hop delays, clean money mixing,
cash-out timing, and spray width.

Governance Declaration: "simulated adversary; abstract parameters only".
"""

from __future__ import annotations

import copy
from dataclasses import asdict, dataclass, field
import random
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class AttackerGenome:
    """Parametric representation of a simulated laundering adversary.
    
    Attributes:
        hops: Sequential layering hops (1 to 6).
        split_sizes: Relative disbursement splits per branch (sum normalized to 1.0).
        delay_between_hops_minutes: Delay between transfer hops in minutes (5 to 1440 min).
        clean_mix_share: Fraction of clean commercial/payroll money mixed in (0.0 to 0.80).
        cash_out_timing_hours: Delay before ATM/crypto cash-out withdrawal (1 to 72 hours).
        spray_width: Fan-out degree / parallel mule branches (1 to 8).
    """
    hops: int = 3
    split_sizes: List[float] = field(default_factory=lambda: [0.5, 0.5])
    delay_between_hops_minutes: int = 45
    clean_mix_share: float = 0.20
    cash_out_timing_hours: int = 12
    spray_width: int = 2

    def __post_init__(self):
        self.hops = max(1, min(6, int(self.hops)))
        self.delay_between_hops_minutes = max(5, min(1440, int(self.delay_between_hops_minutes)))
        self.clean_mix_share = max(0.0, min(0.80, float(self.clean_mix_share)))
        self.cash_out_timing_hours = max(1, min(72, int(self.cash_out_timing_hours)))
        self.spray_width = max(1, min(8, int(self.spray_width)))
        
        # Normalize split sizes
        if not self.split_sizes:
            self.split_sizes = [1.0]
        else:
            s_sum = sum(self.split_sizes)
            if s_sum <= 0:
                self.split_sizes = [1.0 / len(self.split_sizes)] * len(self.split_sizes)
            else:
                self.split_sizes = [round(x / s_sum, 4) for x in self.split_sizes]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "hops": self.hops,
            "split_sizes": [round(x, 4) for x in self.split_sizes],
            "delay_between_hops_minutes": self.delay_between_hops_minutes,
            "clean_mix_share": round(self.clean_mix_share, 4),
            "cash_out_timing_hours": self.cash_out_timing_hours,
            "spray_width": self.spray_width,
            "governance_notice": "simulated adversary; abstract parameters only",
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> AttackerGenome:
        return cls(
            hops=data.get("hops", 3),
            split_sizes=data.get("split_sizes", [0.5, 0.5]),
            delay_between_hops_minutes=data.get("delay_between_hops_minutes", 45),
            clean_mix_share=data.get("clean_mix_share", 0.20),
            cash_out_timing_hours=data.get("cash_out_timing_hours", 12),
            spray_width=data.get("spray_width", 2),
        )

    @classmethod
    def random_genome(cls, rng: random.Random) -> AttackerGenome:
        """Create a randomized genome bounded within realistic operational limits."""
        hops = rng.randint(1, 6)
        spray_width = rng.randint(1, 6)
        
        # Generate random split sizes matching spray width
        raw_splits = [rng.uniform(0.2, 1.0) for _ in range(spray_width)]
        tot = sum(raw_splits)
        splits = [round(x / tot, 4) for x in raw_splits]

        delay = rng.randint(10, 360)  # 10 min to 6 hours
        clean_share = round(rng.uniform(0.0, 0.60), 3)
        cash_out = rng.randint(2, 48)

        return cls(
            hops=hops,
            split_sizes=splits,
            delay_between_hops_minutes=delay,
            clean_mix_share=clean_share,
            cash_out_timing_hours=cash_out,
            spray_width=spray_width,
        )

    def mutate(self, rng: random.Random, mutation_rate: float = 0.35) -> AttackerGenome:
        """Mutate genome parameters with bounded perturbations."""
        new_hops = self.hops
        new_delay = self.delay_between_hops_minutes
        new_clean = self.clean_mix_share
        new_cash_out = self.cash_out_timing_hours
        new_spray = self.spray_width
        new_splits = list(self.split_sizes)

        if rng.random() < mutation_rate:
            new_hops = max(1, min(6, self.hops + rng.choice([-1, 1])))

        if rng.random() < mutation_rate:
            new_spray = max(1, min(8, self.spray_width + rng.choice([-1, 1])))
            # Rescale splits to match new spray width
            raw = [rng.uniform(0.2, 1.0) for _ in range(new_spray)]
            tot = sum(raw)
            new_splits = [round(x / tot, 4) for x in raw]

        if rng.random() < mutation_rate:
            delta_delay = rng.randint(-30, 60)
            new_delay = max(5, min(1440, self.delay_between_hops_minutes + delta_delay))

        if rng.random() < mutation_rate:
            delta_clean = rng.uniform(-0.15, 0.15)
            new_clean = max(0.0, min(0.80, self.clean_mix_share + delta_clean))

        if rng.random() < mutation_rate:
            delta_co = rng.randint(-6, 8)
            new_cash_out = max(1, min(72, self.cash_out_timing_hours + delta_co))

        return AttackerGenome(
            hops=new_hops,
            split_sizes=new_splits,
            delay_between_hops_minutes=new_delay,
            clean_mix_share=new_clean,
            cash_out_timing_hours=new_cash_out,
            spray_width=new_spray,
        )

    @classmethod
    def crossover(
        cls,
        parent_a: AttackerGenome,
        parent_b: AttackerGenome,
        rng: random.Random,
    ) -> AttackerGenome:
        """Uniform single-point crossover between two parent genomes."""
        hops = parent_a.hops if rng.random() < 0.5 else parent_b.hops
        spray = parent_a.spray_width if rng.random() < 0.5 else parent_b.spray_width
        delay = parent_a.delay_between_hops_minutes if rng.random() < 0.5 else parent_b.delay_between_hops_minutes
        clean = (parent_a.clean_mix_share + parent_b.clean_mix_share) / 2.0
        cash_out = parent_a.cash_out_timing_hours if rng.random() < 0.5 else parent_b.cash_out_timing_hours
        splits = copy.deepcopy(parent_a.split_sizes if rng.random() < 0.5 else parent_b.split_sizes)

        # Ensure splits match spray
        if len(splits) != spray:
            raw = [rng.uniform(0.2, 1.0) for _ in range(spray)]
            tot = sum(raw)
            splits = [round(x / tot, 4) for x in raw]

        return cls(
            hops=hops,
            split_sizes=splits,
            delay_between_hops_minutes=delay,
            clean_mix_share=clean,
            cash_out_timing_hours=cash_out,
            spray_width=spray,
        )
