"""Smart-Freeze Consensus Lien Explanations Module.

Generates structured, human-readable, evidence-based explanations comparing
proportional, FIFO, and LIBR fund-tracing outcomes for individual accounts.
Explains the mathematical causes of method agreement or disagreement without
prejudging guilt or liability.
"""

from __future__ import annotations

from typing import Dict, List, Optional


class ConsensusExplanationBuilder:
    """Builds structured narrative explanations for Consensus Lien comparisons."""

    @staticmethod
    def explain_account_consensus(
        account_id: str,
        proportional_paise: int,
        fifo_paise: int,
        libr_paise: int,
        lower_estimate_paise: int,
        upper_estimate_paise: int,
        disagreement_paise: int,
        history_complete: bool = True,
    ) -> str:
        """Construct a step-by-step human-readable explanation for an account's Consensus Lien bounds."""
        lines = [
            f"Account '{account_id}' Consensus Lien Assessment:",
            f"  - Proportional Tracing: ₹{proportional_paise / 100:,.2f} ({proportional_paise:,} paise)",
            f"  - FIFO Tracing:         ₹{fifo_paise / 100:,.2f} ({fifo_paise:,} paise)",
            f"  - LIBR Tracing:         ₹{libr_paise / 100:,.2f} ({libr_paise:,} paise)",
            f"  -> Consensus Bounds: Lower = ₹{lower_estimate_paise / 100:,.2f} | Upper = ₹{upper_estimate_paise / 100:,.2f}",
            f"  -> Method Disagreement Range: ₹{disagreement_paise / 100:,.2f} ({disagreement_paise:,} paise)",
        ]

        if disagreement_paise == 0:
            lines.append(
                "  [Analysis] Complete consensus: All three methods yield the identical retained suspected amount. "
                "This occurs when transfers are uncommingled, or when all available funds in the account were fully forwarded."
            )
        else:
            lines.append("  [Analysis] Method divergence drivers:")
            # Identify which method gave upper/lower and why
            if libr_paise == upper_estimate_paise and libr_paise > proportional_paise:
                lines.append(
                    "    * LIBR provides the upper bound because non-suspected (clean) funds absorbed outgoing "
                    "transfers under the equitable fiduciary presumption, preserving suspected funds in this account."
                )
            if proportional_paise == upper_estimate_paise and proportional_paise > libr_paise:
                lines.append(
                    "    * Proportional tracing provides the upper bound because outgoing transfers drew "
                    "pro-rata from both clean and suspected funds, leaving a proportional fraction behind."
                )
            if fifo_paise == upper_estimate_paise and fifo_paise > proportional_paise:
                lines.append(
                    "    * FIFO provides the upper bound because suspected funds arrived after earlier clean funds, "
                    "and outgoing transfers exhausted the older clean lots first."
                )
            if libr_paise == lower_estimate_paise and libr_paise < upper_estimate_paise:
                lines.append(
                    "    * LIBR provides the lower bound due to intermediate balance drawdowns or clean-fund absorption "
                    "prioritizing earlier retention."
                )
            if fifo_paise == lower_estimate_paise and fifo_paise < upper_estimate_paise:
                lines.append(
                    "    * FIFO provides the lower bound because suspected lots arrived early and were consumed first "
                    "by subsequent outgoing payments."
                )
            if proportional_paise == lower_estimate_paise and proportional_paise < upper_estimate_paise:
                lines.append(
                    "    * Proportional tracing provides the lower bound because commingling diluted the suspected "
                    "balance across multiple onward transfers."
                )

        if not history_complete:
            lines.append(
                "  [!] Incomplete Account History: Historical bank records for this account are truncated or incomplete. "
                "Attributed balances may omit prior transactions or opening balance origins."
            )

        lines.append(
            "  [Governance] Investigative Estimate Notice: Consensus Lien figures represent method-dependent accounting "
            "bounds for decision support. They do not constitute judicial proof of liability, guaranteed recovery, or an "
            "automated freeze order. Authorized human investigator review is required."
        )

        return "\n".join(lines)
