"""Smart-Freeze Attack Lab — Case Generation & Policy Defense Simulation.

Constructs realistic synthetic transaction trails from an abstract AttackerGenome,
simulates time-delayed transfers, commingling, and cash-out events, and evaluates
the outcome against Defenses Off vs Defense Policies (Policy V1 vs Policy V2).

Fitness = (escaped_paise + innocent_held_paise) / 100.0 (in Rupees)
Governance Notice: "simulated adversary; abstract parameters only".
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
import random
from typing import Any, Dict, List, Optional, Set, Tuple

import pandas as pd

from attacklab.genome import AttackerGenome
from engine.decision import DecisionEngine, DecisionAction
from pipeline.schemas import EXTERNAL_ACCOUNT_PREFIX


@dataclass
class SimulationOutcome:
    """Quantitative outcome of a simulated attack against a defense posture."""
    case_id: str
    family_type: str
    defense_mode: str  # "defenses_off", "policy_v1", "policy_v2"
    stolen_amount_paise: int
    escaped_paise: int
    captured_paise: int
    innocent_held_paise: int
    holds_count: int
    total_accounts_involved: int
    fitness_rupees: float  # (escaped_paise + innocent_held_paise) / 100.0
    escaped_rupees: float
    innocent_held_rupees: float
    governance_notice: str = "simulated adversary; abstract parameters only"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "case_id": self.case_id,
            "family_type": self.family_type,
            "defense_mode": self.defense_mode,
            "stolen_amount_paise": self.stolen_amount_paise,
            "escaped_paise": self.escaped_paise,
            "captured_paise": self.captured_paise,
            "innocent_held_paise": self.innocent_held_paise,
            "holds_count": self.holds_count,
            "total_accounts_involved": self.total_accounts_involved,
            "fitness_rupees": round(self.fitness_rupees, 2),
            "escaped_rupees": round(self.escaped_rupees, 2),
            "innocent_held_rupees": round(self.innocent_held_rupees, 2),
            "governance_notice": self.governance_notice,
        }


class AttackSimulator:
    """Simulates adversarial laundering schemes and evaluates policy defensive resilience."""

    def __init__(self, decision_engine: Optional[DecisionEngine] = None):
        self.decision_engine = decision_engine or DecisionEngine()

    @staticmethod
    def build_case_from_genome(
        genome: AttackerGenome,
        case_id: str,
        family_type: str,
        stolen_amount_paise: int = 10_000_000,  # ₹100,000 INR
        base_time: Optional[datetime.datetime] = None,
        seed: int = 42,
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], str]:
        """Constructs synthetic accounts and transactions for a case matching the genome parameters.
        
        Returns:
            (accounts, transactions, source_transaction_id)
        """
        rng = random.Random(seed)
        t0 = base_time or datetime.datetime(2026, 1, 15, 10, 0, 0, tzinfo=datetime.timezone.utc)

        accounts: List[Dict[str, Any]] = []
        transactions: List[Dict[str, Any]] = []

        # 1. Victim account
        victim_id = f"ACC_VIC_{case_id[-4:]}"
        victim_opening = int(stolen_amount_paise * 2.5)
        accounts.append({
            "account_id": victim_id,
            "account_type": "savings",
            "opening_balance_paise": victim_opening,
            "history_complete": True,
        })

        source_tx_id = f"TX_{case_id}_ORIGIN"

        if family_type == "family_b":
            # Family B: Tiny-amount spray (smurfing / fan-out)
            splitter_id = f"ACC_MULE_SPLIT_{case_id[-4:]}"
            accounts.append({
                "account_id": splitter_id,
                "account_type": "mule",
                "opening_balance_paise": rng.randint(50_000, 200_000),
                "history_complete": True,
            })

            # Transfer from victim to splitter
            transactions.append({
                "transaction_id": source_tx_id,
                "timestamp": t0.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "from_account": victim_id,
                "to_account": splitter_id,
                "amount_paise": stolen_amount_paise,
                "transaction_type": "transfer",
                "case_id": case_id,
                "evidence_status": "suspected_fraud",
            })

            # Fan out to spray_width destination mules
            spray = max(1, genome.spray_width)
            splits = list(genome.split_sizes)
            if len(splits) != spray:
                splits = [1.0 / spray] * spray

            cur_time = t0 + datetime.timedelta(minutes=genome.delay_between_hops_minutes)
            dest_mules = []
            for idx in range(spray):
                d_id = f"ACC_MULE_DEST_{case_id[-4:]}_{idx + 1}"
                # Clean money mixed in
                clean_bal = int(stolen_amount_paise * splits[idx] * genome.clean_mix_share * 1.5)
                accounts.append({
                    "account_id": d_id,
                    "account_type": "mule",
                    "opening_balance_paise": max(50_000, clean_bal),
                    "history_complete": True,
                })
                dest_mules.append(d_id)

                amt_share = int(stolen_amount_paise * splits[idx])
                transactions.append({
                    "transaction_id": f"TX_{case_id}_SPRAY_{idx + 1}",
                    "timestamp": cur_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "from_account": splitter_id,
                    "to_account": d_id,
                    "amount_paise": amt_share,
                    "transaction_type": "transfer",
                    "case_id": case_id,
                    "evidence_status": "suspected_fraud",
                })

            # Cash-out withdrawal after cash_out_timing_hours
            cash_time = cur_time + datetime.timedelta(hours=genome.cash_out_timing_hours)
            for idx, d_id in enumerate(dest_mules):
                amt_share = int(stolen_amount_paise * splits[idx])
                transactions.append({
                    "transaction_id": f"TX_{case_id}_CASH_{idx + 1}",
                    "timestamp": cash_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "from_account": d_id,
                    "to_account": "EXT_CASH_ATM",
                    "amount_paise": int(amt_share * 0.95),
                    "transaction_type": "withdrawal",
                    "case_id": case_id,
                    "evidence_status": "suspected_fraud",
                })

        elif family_type == "family_c":
            # Family C: Heavy Commingling (Victim -> Innocent Aggregator -> Merchants)
            agg_id = f"ACC_AGG_FAST_{case_id[-4:]}"
            # Aggregator has substantial legitimate working capital
            agg_opening = int(stolen_amount_paise * 10 * max(1.0, genome.clean_mix_share * 5.0))
            accounts.append({
                "account_id": agg_id,
                "account_type": "payment_aggregator",
                "opening_balance_paise": agg_opening,
                "history_complete": True,
            })

            transactions.append({
                "transaction_id": source_tx_id,
                "timestamp": t0.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "from_account": victim_id,
                "to_account": agg_id,
                "amount_paise": stolen_amount_paise,
                "transaction_type": "transfer",
                "case_id": case_id,
                "evidence_status": "suspected_fraud",
            })

            # Commingled settlement sweep forward to innocent merchants
            cur_time = t0 + datetime.timedelta(minutes=genome.delay_between_hops_minutes)
            merch_1 = f"ACC_MERCH_{case_id[-4:]}_1"
            merch_2 = f"ACC_MERCH_{case_id[-4:]}_2"
            accounts.append({
                "account_id": merch_1,
                "account_type": "merchant",
                "opening_balance_paise": int(stolen_amount_paise * 3),
                "history_complete": True,
            })
            accounts.append({
                "account_id": merch_2,
                "account_type": "merchant",
                "opening_balance_paise": int(stolen_amount_paise * 2),
                "history_complete": True,
            })

            s1 = int(stolen_amount_paise * 0.55)
            s2 = int(stolen_amount_paise * 0.40)
            transactions.append({
                "transaction_id": f"TX_{case_id}_SWEEP_1",
                "timestamp": cur_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "from_account": agg_id,
                "to_account": merch_1,
                "amount_paise": s1,
                "transaction_type": "transfer",
                "case_id": case_id,
                "evidence_status": "suspected_fraud",
            })
            transactions.append({
                "transaction_id": f"TX_{case_id}_SWEEP_2",
                "timestamp": (cur_time + datetime.timedelta(minutes=15)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "from_account": agg_id,
                "to_account": merch_2,
                "amount_paise": s2,
                "transaction_type": "transfer",
                "case_id": case_id,
                "evidence_status": "suspected_fraud",
            })

        else:
            # Family A: Layered Chain across sequential hops
            hops = max(1, min(6, genome.hops))
            chain_accounts = []
            for h in range(1, hops + 1):
                m_id = f"ACC_MULE_HOP_{case_id[-4:]}_{h}"
                clean_bal = int(stolen_amount_paise * genome.clean_mix_share * (1.0 + h * 0.2))
                accounts.append({
                    "account_id": m_id,
                    "account_type": "mule",
                    "opening_balance_paise": max(50_000, clean_bal),
                    "history_complete": True,
                })
                chain_accounts.append(m_id)

            # First hop: Victim -> Mule 1
            transactions.append({
                "transaction_id": source_tx_id,
                "timestamp": t0.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "from_account": victim_id,
                "to_account": chain_accounts[0],
                "amount_paise": stolen_amount_paise,
                "transaction_type": "transfer",
                "case_id": case_id,
                "evidence_status": "suspected_fraud",
            })

            # Intermediate sequential hops
            cur_time = t0
            cur_amt = stolen_amount_paise
            for h in range(len(chain_accounts) - 1):
                cur_time += datetime.timedelta(minutes=genome.delay_between_hops_minutes)
                f_acc = chain_accounts[h]
                t_acc = chain_accounts[h + 1]
                # Small leakage per hop (2%)
                cur_amt = int(cur_amt * 0.98)
                transactions.append({
                    "transaction_id": f"TX_{case_id}_HOP_{h + 1}",
                    "timestamp": cur_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "from_account": f_acc,
                    "to_account": t_acc,
                    "amount_paise": cur_amt,
                    "transaction_type": "transfer",
                    "case_id": case_id,
                    "evidence_status": "suspected_fraud",
                })

            # Final cash-out withdrawal
            last_mule = chain_accounts[-1]
            cash_time = cur_time + datetime.timedelta(hours=genome.cash_out_timing_hours)
            transactions.append({
                "transaction_id": f"TX_{case_id}_CASH_EXIT",
                "timestamp": cash_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "from_account": last_mule,
                "to_account": "EXT_CASH_ATM",
                "amount_paise": int(cur_amt * 0.95),
                "transaction_type": "withdrawal",
                "case_id": case_id,
                "evidence_status": "suspected_fraud",
            })

        return accounts, transactions, source_tx_id

    def evaluate_defense(
        self,
        genome: AttackerGenome,
        case_id: str,
        family_type: str,
        defense_mode: str,  # "defenses_off", "policy_v1", "policy_v2"
        stolen_amount_paise: int = 10_000_000,
        seed: int = 42,
    ) -> SimulationOutcome:
        """Evaluates an attack against the specified defense posture."""
        accounts, transactions, source_tx_id = self.build_case_from_genome(
            genome=genome,
            case_id=case_id,
            family_type=family_type,
            stolen_amount_paise=stolen_amount_paise,
            seed=seed,
        )

        acc_meta = {a["account_id"]: a for a in accounts}

        # Calculate reconstructed closing balances
        balances: Dict[str, int] = {a["account_id"]: int(a["opening_balance_paise"]) for a in accounts}
        for t in sorted(transactions, key=lambda x: x["timestamp"]):
            fa = t["from_account"]
            ta = t["to_account"]
            amt = int(t["amount_paise"])
            if fa in balances:
                balances[fa] -= amt
            if ta in balances:
                balances[ta] += amt

        # Attacker timing: cash-out occurs after hops * delay + cash_out_timing_hours
        total_attack_duration_hours = (
            (genome.hops * genome.delay_between_hops_minutes) / 60.0
            + genome.cash_out_timing_hours
        )

        # Velocity evasion score: naive 1-hop lump-sum fast cash-outs flag real-time AML velocity limits
        hop_evasion = min(1.0, max(0.0, (genome.hops - 1) / 3.0))
        spray_evasion = min(1.0, max(0.0, (genome.spray_width - 1) / 4.0))
        delay_evasion = min(1.0, max(0.0, genome.delay_between_hops_minutes / 180.0))
        velocity_evasion = 0.30 * hop_evasion + 0.45 * spray_evasion + 0.25 * delay_evasion

        if defense_mode == "defenses_off":
            # Defenses Off: Zero holds placed. Attacker succeeds completely; zero collateral damage.
            escaped = stolen_amount_paise
            captured = 0
            innocent_held = 0
            holds_count = 0

        elif defense_mode == "policy_v1":
            # Policy V1: Naive, aggressive uncalibrated freeze.
            # Freezes entire account closing balance on any intermediary participating in the trail.
            # Zero harm discounting, zero de-minimis threshold.
            holds_count = 0
            captured = 0
            innocent_held = 0

            # Rapid response time under naive rule: 4 hours
            defense_reaction_hours = 4.0

            for aid, bal in balances.items():
                if aid.startswith("ACC_VIC_") or aid.startswith("EXT_"):
                    continue

                holds_count += 1
                atype = acc_meta.get(aid, {}).get("account_type", "")
                opening = int(acc_meta.get(aid, {}).get("opening_balance_paise", 0))

                # Did defense trigger before cash-out?
                if total_attack_duration_hours >= defense_reaction_hours:
                    captured += min(bal, stolen_amount_paise)
                else:
                    # Naive velocity filter still intercepts un-smurfed rapid cashouts
                    vel_intercept = int(stolen_amount_paise * max(0.0, (1.0 - velocity_evasion) * 0.70))
                    captured = max(captured, vel_intercept)

                # Collateral damage: innocent funds held
                if atype in ("payment_aggregator", "merchant", "savings", "salary"):
                    innocent_held += opening  # Whole clean balance frozen
                elif atype == "mule" and genome.clean_mix_share > 0:
                    innocent_held += int(opening * genome.clean_mix_share * 1.5)

            escaped = max(0, stolen_amount_paise - captured)

        else:
            # Policy V2: Smart-Freeze Safeguards (Consensus Core + Harm Discounting + De-Minimis)
            rec_result = self.decision_engine.evaluate_case(
                case_id=case_id,
                accounts=accounts,
                transactions=transactions,
                source_transaction_id=source_tx_id,
                policy_name="balanced",
            )

            # Smart-Freeze defense response window (e.g. 6 hours for multi-method consensus)
            defense_reaction_hours = 6.0
            holds_count = 0
            raw_held_paise = 0
            innocent_held = 0

            for rec in rec_result.recommendations:
                if rec.action != "none":
                    holds_count += 1
                    raw_held_paise += rec.effective_lien_paise

                    aid = rec.account_id
                    atype = acc_meta.get(aid, {}).get("account_type", "")
                    opening = int(acc_meta.get(aid, {}).get("opening_balance_paise", 0))

                    if atype in ("payment_aggregator", "merchant", "savings", "salary"):
                        # Harm rules prevented whole account freeze; only small remaining held margin
                        innocent_held += min(rec.held_margin_paise, opening // 10)
                    elif atype == "mule" and genome.clean_mix_share > 0:
                        # Clean money commingling causes small accidental hold on mixed funds
                        innocent_held += int(opening * genome.clean_mix_share * 0.10)

            # Dual-layer defense evaluation:
            # 1. Real-time velocity interception for naive rapid cashouts:
            vel_intercept_ratio = max(0.0, (1.0 - velocity_evasion) * 0.70)
            
            # 2. Consensus lien capture:
            if total_attack_duration_hours < defense_reaction_hours:
                time_ratio = max(0.20, total_attack_duration_hours / defense_reaction_hours)
            else:
                time_ratio = 1.0

            # Smurfing and clean mixing reduce effective lien capture
            de_minimis_leak = min(0.35, max(0.0, (genome.spray_width - 1) * 0.07))
            commingle_leak = min(0.40, genome.clean_mix_share * 0.6)
            effective_lien_ratio = (1.0 - de_minimis_leak) * (1.0 - commingle_leak) * time_ratio
            consensus_captured = int(raw_held_paise * effective_lien_ratio)

            vel_captured = int(stolen_amount_paise * vel_intercept_ratio)
            captured = min(stolen_amount_paise, max(vel_captured, consensus_captured))
            escaped = max(0, stolen_amount_paise - captured)


        fitness_paise = escaped + innocent_held
        fitness_rupees = fitness_paise / 100.0

        return SimulationOutcome(
            case_id=case_id,
            family_type=family_type,
            defense_mode=defense_mode,
            stolen_amount_paise=stolen_amount_paise,
            escaped_paise=escaped,
            captured_paise=captured,
            innocent_held_paise=innocent_held,
            holds_count=holds_count,
            total_accounts_involved=len(accounts),
            fitness_rupees=fitness_rupees,
            escaped_rupees=escaped / 100.0,
            innocent_held_rupees=innocent_held / 100.0,
        )
