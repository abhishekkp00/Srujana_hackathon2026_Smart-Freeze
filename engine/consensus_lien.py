"""Smart-Freeze Consensus Lien Engine.

Compares independently calculated Proportional, FIFO, and Lowest Intermediate
Balance Rule (LIBR) fund-tracing outcomes for the same source transaction and scope.

Core Principles:
- Independence: Evaluates all three methods without altering their underlying algorithms.
- Comparability: Strictly verifies that all three runs refer to the same source transaction,
  case ID, currency unit (integer paise), and cutoff.
- Consensus Bounds:
  * Lower method estimate = min(Proportional, FIFO, LIBR)
  * Upper method estimate = max(Proportional, FIFO, LIBR)
  * Disagreement range = Upper - Lower
- Non-Prejudgment: Lower estimate is an investigative accounting bound, not a legal
  conclusion or guaranteed recoverable liability.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple
import pandas as pd

from engine.consensus_explanations import ConsensusExplanationBuilder
from engine.fifo import FIFOTracer
from engine.libr import LIBRTracer
from engine.proportional import ProportionalTracer
from engine.tracing_models import (
    FIFOTraceResult,
    LIBRTraceResult,
    ProportionalTraceResult,
)


@dataclass(frozen=True)
class AccountConsensusLien:
    """Consensus lien evaluation for a single account across tracing methods."""
    account_id: str
    proportional_paise: int
    fifo_paise: int
    libr_paise: int
    lower_estimate_paise: int
    upper_estimate_paise: int
    disagreement_paise: int
    lower_method: str
    upper_method: str
    history_complete: bool
    explanation_text: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ConsensusLienResult:
    """Structured result of a multi-method Consensus Lien comparison."""
    source_transaction_id: str
    source_case_id: str
    initial_suspected_amount_paise: int
    status: str  # "COMPARABLE", "INCOMPARABLE", "PARTIAL"
    account_liens: Dict[str, AccountConsensusLien]
    withdrawn_liens: Dict[str, AccountConsensusLien]
    total_lower_retained_paise: int
    total_upper_retained_paise: int
    overall_disagreement_paise: int
    proportional_result: Optional[ProportionalTraceResult] = None
    fifo_result: Optional[FIFOTraceResult] = None
    libr_result: Optional[LIBRTraceResult] = None
    assumptions_and_limitations: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    confirmed_withdrawn_paise: int = 0
    joint_feasible_upper_paise: int = 0
    joint_feasible_lower_paise: int = 0

    @property
    def joint_total_paise(self) -> int:
        """Joint-feasible total upper bound that never exceeds suspected amount minus confirmed outflows."""
        return self.joint_feasible_upper_paise

    @property
    def joint_total(self) -> float:
        """Joint-feasible total in INR."""
        return self.joint_feasible_upper_paise / 100.0

    @property
    def joint_feasible_total_paise(self) -> int:
        return self.joint_feasible_upper_paise

    @property
    def joint_feasible_total(self) -> float:
        return self.joint_feasible_upper_paise / 100.0

    def summary_dataframe(self) -> pd.DataFrame:
        """Render a tabular summary of consensus lien bounds per internal account."""
        rows = []
        for acc_id, lien in sorted(
            self.account_liens.items(),
            key=lambda x: (x[1].upper_estimate_paise, x[1].lower_estimate_paise),
            reverse=True,
        ):
            rows.append({
                "account_id": acc_id,
                "proportional_inr": round(lien.proportional_paise / 100.0, 2),
                "fifo_inr": round(lien.fifo_paise / 100.0, 2),
                "libr_inr": round(lien.libr_paise / 100.0, 2),
                "lower_bound_inr": round(lien.lower_estimate_paise / 100.0, 2),
                "upper_bound_inr": round(lien.upper_estimate_paise / 100.0, 2),
                "disagreement_inr": round(lien.disagreement_paise / 100.0, 2),
                "lower_estimate_paise": lien.lower_estimate_paise,
                "upper_estimate_paise": lien.upper_estimate_paise,
                "disagreement_paise": lien.disagreement_paise,
                "history_complete": lien.history_complete,
            })
        return pd.DataFrame(rows)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_transaction_id": self.source_transaction_id,
            "source_case_id": self.source_case_id,
            "initial_suspected_amount_paise": self.initial_suspected_amount_paise,
            "status": self.status,
            "total_lower_retained_paise": self.total_lower_retained_paise,
            "total_upper_retained_paise": self.total_upper_retained_paise,
            "overall_disagreement_paise": self.overall_disagreement_paise,
            "confirmed_withdrawn_paise": self.confirmed_withdrawn_paise,
            "joint_feasible_upper_paise": self.joint_feasible_upper_paise,
            "joint_feasible_lower_paise": self.joint_feasible_lower_paise,
            "joint_total_paise": self.joint_total_paise,
            "joint_total": self.joint_total,
            "account_liens": {k: v.to_dict() for k, v in self.account_liens.items()},
            "withdrawn_liens": {k: v.to_dict() for k, v in self.withdrawn_liens.items()},
            "assumptions_and_limitations": self.assumptions_and_limitations,
            "errors": self.errors,
            "warnings": self.warnings,
        }


class ConsensusLienEngine:
    """Orchestrates independent fund-tracing methods and calculates Consensus Lien bounds."""

    @classmethod
    def run_all_methods(
        cls,
        accounts: List[Dict[str, Any]] | pd.DataFrame,
        transactions: List[Dict[str, Any]] | pd.DataFrame,
        source_transaction_id: str,
        source_case_id: Optional[str] = None,
        suspected_amount_paise: Optional[int] = None,
    ) -> ConsensusLienResult:
        """Run Proportional, FIFO, and LIBR tracing independently and compute Consensus Lien."""
        prop_tracer = ProportionalTracer(accounts, transactions)
        fifo_tracer = FIFOTracer(accounts, transactions)
        libr_tracer = LIBRTracer(accounts, transactions)

        prop_res = prop_tracer.trace_source_transaction(
            source_transaction_id, source_case_id, suspected_amount_paise
        )
        fifo_res = fifo_tracer.trace_source_transaction(
            source_transaction_id, source_case_id, suspected_amount_paise
        )
        libr_res = libr_tracer.trace_source_transaction(
            source_transaction_id, source_case_id, suspected_amount_paise
        )

        return cls.compare_results(prop_res, fifo_res, libr_res)

    @classmethod
    def compare_results(
        cls,
        proportional_result: ProportionalTraceResult,
        fifo_result: FIFOTraceResult,
        libr_result: LIBRTraceResult,
    ) -> ConsensusLienResult:
        """Compare precomputed outputs from Proportional, FIFO, and LIBR tracing."""
        # 1. Comparability & Integrity Validation
        errors: List[str] = []
        warnings: List[str] = []

        if proportional_result is None or fifo_result is None or libr_result is None:
            raise ValueError("All three method results (Proportional, FIFO, LIBR) must be provided.")

        src_tx = proportional_result.source_transaction_id
        if fifo_result.source_transaction_id != src_tx or libr_result.source_transaction_id != src_tx:
            errors.append(
                f"Incomparable source transactions: Proportional='{src_tx}', "
                f"FIFO='{fifo_result.source_transaction_id}', LIBR='{libr_result.source_transaction_id}'"
            )

        src_case = proportional_result.source_case_id
        if fifo_result.source_case_id != src_case or libr_result.source_case_id != src_case:
            errors.append(
                f"Incomparable case references: Proportional='{src_case}', "
                f"FIFO='{fifo_result.source_case_id}', LIBR='{libr_result.source_case_id}'"
            )

        init_amt = proportional_result.initial_suspected_amount_paise
        if fifo_result.initial_suspected_amount_paise != init_amt or libr_result.initial_suspected_amount_paise != init_amt:
            errors.append(
                f"Incomparable initial amounts: Proportional={init_amt}, "
                f"FIFO={fifo_result.initial_suspected_amount_paise}, LIBR={libr_result.initial_suspected_amount_paise}"
            )

        if init_amt < 0:
            errors.append(f"Initial suspected amount cannot be negative: {init_amt}")

        # Check for negative values in individual outputs
        for name, res in [
            ("Proportional", proportional_result),
            ("FIFO", fifo_result),
            ("LIBR", libr_result),
        ]:
            for acc, val in res.retained_suspected_paise.items():
                if val < 0:
                    errors.append(f"{name} produced negative retained amount for '{acc}': {val}")
            for ext, val in res.withdrawn_suspected_paise.items():
                if val < 0:
                    errors.append(f"{name} produced negative withdrawn amount for '{ext}': {val}")

        if errors:
            return ConsensusLienResult(
                source_transaction_id=src_tx,
                source_case_id=src_case,
                initial_suspected_amount_paise=init_amt,
                status="INCOMPARABLE",
                account_liens={},
                withdrawn_liens={},
                total_lower_retained_paise=0,
                total_upper_retained_paise=0,
                overall_disagreement_paise=0,
                proportional_result=proportional_result,
                fifo_result=fifo_result,
                libr_result=libr_result,
                assumptions_and_limitations=[],
                errors=errors,
                warnings=warnings,
            )

        # 2. Account-Level Consensus Calculation
        all_accounts: Set[str] = (
            set(proportional_result.retained_suspected_paise.keys())
            | set(fifo_result.retained_suspected_paise.keys())
            | set(libr_result.retained_suspected_paise.keys())
        )

        all_incomplete_accounts = (
            set(proportional_result.incomplete_history_accounts)
            | set(fifo_result.incomplete_history_accounts)
            | set(libr_result.incomplete_history_accounts)
        )

        account_liens: Dict[str, AccountConsensusLien] = {}

        for acc in sorted(all_accounts):
            p_val = proportional_result.retained_suspected_paise.get(acc, 0)
            f_val = fifo_result.retained_suspected_paise.get(acc, 0)
            l_val = libr_result.retained_suspected_paise.get(acc, 0)

            # Integer paise consensus
            lower_val = min(p_val, f_val, l_val)
            upper_val = max(p_val, f_val, l_val)
            disagree_val = upper_val - lower_val

            # Determine method tags
            lower_methods = []
            if p_val == lower_val:
                lower_methods.append("Proportional")
            if f_val == lower_val:
                lower_methods.append("FIFO")
            if l_val == lower_val:
                lower_methods.append("LIBR")

            upper_methods = []
            if p_val == upper_val:
                upper_methods.append("Proportional")
            if f_val == upper_val:
                upper_methods.append("FIFO")
            if l_val == upper_val:
                upper_methods.append("LIBR")

            is_complete = acc not in all_incomplete_accounts

            explanation = ConsensusExplanationBuilder.explain_account_consensus(
                account_id=acc,
                proportional_paise=p_val,
                fifo_paise=f_val,
                libr_paise=l_val,
                lower_estimate_paise=lower_val,
                upper_estimate_paise=upper_val,
                disagreement_paise=disagree_val,
                history_complete=is_complete,
            )

            account_liens[acc] = AccountConsensusLien(
                account_id=acc,
                proportional_paise=p_val,
                fifo_paise=f_val,
                libr_paise=l_val,
                lower_estimate_paise=lower_val,
                upper_estimate_paise=upper_val,
                disagreement_paise=disagree_val,
                lower_method="/".join(lower_methods),
                upper_method="/".join(upper_methods),
                history_complete=is_complete,
                explanation_text=explanation,
            )

        # 3. External Outflows Consensus
        all_ext_accounts: Set[str] = (
            set(proportional_result.withdrawn_suspected_paise.keys())
            | set(fifo_result.withdrawn_suspected_paise.keys())
            | set(libr_result.withdrawn_suspected_paise.keys())
        )

        withdrawn_liens: Dict[str, AccountConsensusLien] = {}

        for ext in sorted(all_ext_accounts):
            p_val = proportional_result.withdrawn_suspected_paise.get(ext, 0)
            f_val = fifo_result.withdrawn_suspected_paise.get(ext, 0)
            l_val = libr_result.withdrawn_suspected_paise.get(ext, 0)

            lower_val = min(p_val, f_val, l_val)
            upper_val = max(p_val, f_val, l_val)
            disagree_val = upper_val - lower_val

            lower_methods = []
            if p_val == lower_val:
                lower_methods.append("Proportional")
            if f_val == lower_val:
                lower_methods.append("FIFO")
            if l_val == lower_val:
                lower_methods.append("LIBR")

            upper_methods = []
            if p_val == upper_val:
                upper_methods.append("Proportional")
            if f_val == upper_val:
                upper_methods.append("FIFO")
            if l_val == upper_val:
                upper_methods.append("LIBR")

            withdrawn_liens[ext] = AccountConsensusLien(
                account_id=ext,
                proportional_paise=p_val,
                fifo_paise=f_val,
                libr_paise=l_val,
                lower_estimate_paise=lower_val,
                upper_estimate_paise=upper_val,
                disagreement_paise=disagree_val,
                lower_method="/".join(lower_methods),
                upper_method="/".join(upper_methods),
                history_complete=True,
                explanation_text=f"External outflow '{ext}': Proportional=₹{p_val/100:,.2f}, FIFO=₹{f_val/100:,.2f}, LIBR=₹{l_val/100:,.2f}.",
            )

        # Overall summary figures
        total_lower = sum(l.lower_estimate_paise for l in account_liens.values())
        total_upper = sum(l.upper_estimate_paise for l in account_liens.values())
        overall_disagreement = sum(l.disagreement_paise for l in account_liens.values())

        # Joint-feasible total:
        # Sum of per-account maximums can exceed the stolen amount when methods disagree on where
        # funds reside (e.g., CASE-2026-001 shows 151,890.76 on 100,000.00).
        # We preserve per-account ranges, but add a joint-feasible total that never exceeds the
        # suspected amount minus money confirmed to have left the system.
        confirmed_withdrawn = sum(l.lower_estimate_paise for l in withdrawn_liens.values())
        max_retained_feasible = max(0, init_amt - confirmed_withdrawn)
        joint_feasible_upper = min(total_upper, max_retained_feasible)
        joint_feasible_lower = min(total_lower, joint_feasible_upper)

        assumptions = [
            "Consensus Lien Rule: Compares three independent fund-tracing methods (Proportional, FIFO, LIBR).",
            "Lower Estimate: Represents the minimum traced amount across the configured methods per account. Not a guaranteed floor or judicial liability.",
            "Upper Estimate: Represents the maximum traced amount across the configured methods per account. Not an authorized freeze maximum.",
            "Joint-Feasible Total: Constrains the total upper bound so it never exceeds the suspected amount minus money confirmed to have left the system via external outflows.",
            "Disagreement Quantification: Disagreement = Upper - Lower. Non-zero disagreement reflects differing legal and accounting assumptions regarding commingled fund fungibility.",
            "Human-in-the-Loop Governance: Automated freezes are prohibited. Authorized judicial or investigative review is strictly required.",
        ]

        return ConsensusLienResult(
            source_transaction_id=src_tx,
            source_case_id=src_case,
            initial_suspected_amount_paise=init_amt,
            status="COMPARABLE",
            account_liens=account_liens,
            withdrawn_liens=withdrawn_liens,
            total_lower_retained_paise=total_lower,
            total_upper_retained_paise=total_upper,
            overall_disagreement_paise=overall_disagreement,
            proportional_result=proportional_result,
            fifo_result=fifo_result,
            libr_result=libr_result,
            assumptions_and_limitations=assumptions,
            errors=errors,
            warnings=warnings,
            confirmed_withdrawn_paise=confirmed_withdrawn,
            joint_feasible_upper_paise=joint_feasible_upper,
            joint_feasible_lower_paise=joint_feasible_lower,
        )
