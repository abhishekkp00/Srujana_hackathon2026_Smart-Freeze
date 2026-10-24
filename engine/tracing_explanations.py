"""Smart-Freeze Tracing Explanations Module.

Constructs detailed, evidence-backed mathematical explanations for proportional
fund-tracing decisions. Separates mathematical allocation calculations from
human-readable narratives.
"""

from __future__ import annotations

from typing import Dict, List, Tuple
from engine.tracing_models import AllocationExplanation


class TracingExplanationBuilder:
    """Constructs step-by-step mathematical explanations for proportional allocations."""

    @staticmethod
    def build_allocation_explanation(
        transaction_id: str,
        timestamp: str,
        account_id: str,
        counterparty_account: str,
        transaction_type: str,
        total_amount_paise: int,
        balance_before_paise: int,
        pools_before: Dict[str, int],
        base_allocations: Dict[str, int],
        remainders: Dict[str, int],
        remainder_paise_awarded: Dict[str, int],
        final_allocations: Dict[str, int],
        pools_after: Dict[str, int],
    ) -> AllocationExplanation:
        """Construct an AllocationExplanation record and readable narrative."""
        exact_shares: Dict[str, str] = {}
        for cat, b_k in sorted(pools_before.items()):
            if balance_before_paise > 0:
                exact_shares[cat] = f"({total_amount_paise} * {b_k}) / {balance_before_paise}"
            else:
                exact_shares[cat] = "0/0"

        # Build readable narrative text
        lines = [
            f"Transaction {transaction_id} ({timestamp}): Account '{account_id}' transferred {total_amount_paise:,} paise to '{counterparty_account}'.",
            f"Pre-transaction total balance: {balance_before_paise:,} paise across {len(pools_before)} source pool(s):",
        ]
        for cat, b_k in sorted(pools_before.items()):
            pct = (b_k / balance_before_paise * 100.0) if balance_before_paise > 0 else 0.0
            lines.append(f"  - {cat}: {b_k:,} paise ({pct:.2f}%)")

        lines.append(f"Proportional allocation of {total_amount_paise:,} paise:")
        for cat, amt in sorted(final_allocations.items()):
            base = base_allocations.get(cat, 0)
            awarded = remainder_paise_awarded.get(cat, 0)
            rem = remainders.get(cat, 0)
            lines.append(
                f"  - {cat}: {amt:,} paise (base floor: {base:,}, mod remainder: {rem:,}, remainder awarded: +{awarded})"
            )

        lines.append("Post-transaction remaining pool balances:")
        for cat, rem_bal in sorted(pools_after.items()):
            lines.append(f"  - {cat}: {rem_bal:,} paise remaining")

        narrative = "\n".join(lines)

        return AllocationExplanation(
            transaction_id=transaction_id,
            timestamp=timestamp,
            account_id=account_id,
            counterparty_account=counterparty_account,
            transaction_type=transaction_type,
            total_amount_paise=total_amount_paise,
            balance_before_paise=balance_before_paise,
            pools_before=dict(pools_before),
            exact_shares=exact_shares,
            base_allocations=dict(base_allocations),
            remainders=dict(remainders),
            remainder_paise_awarded=dict(remainder_paise_awarded),
            final_allocations=dict(final_allocations),
            pools_after=dict(pools_after),
            explanation_text=narrative,
        )
