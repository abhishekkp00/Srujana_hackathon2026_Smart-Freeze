"""Smart-Freeze Lowest Intermediate Balance Rule (LIBR) Fund-Tracing Engine.

Implements a deterministic, explainable Lowest Intermediate Balance Rule (LIBR)
tracing engine for financial fraud investigations.

LIBR Core Principles and Convention:
1. When suspected source funds are deposited into an account, they establish an initial
   attributed balance for that source transaction/case.
2. Under the equitable presumption (fiduciary spends own funds first), general/clean
   funds in the account are presumed withdrawn first. Suspected funds are only dissipated
   once non-suspected funds are completely exhausted.
3. The Lowest Intermediate Balance Rule limits the attributable source amount to the
   lowest balance reached by the account at or after the source inflow.
4. No Replenishment: Subsequent deposits of clean funds from third parties increase the
   available account balance, but do NOT restore or replenish source attribution that was
   previously dissipated when the balance dropped.
5. Internal Transfers: When an outgoing transfer draws from suspected funds (because clean
   funds are insufficient), the attributed amount is propagated to the recipient account
   and tracked under LIBR in the destination account.
6. Exact Arithmetic: All balances and attributions are computed strictly in integer paise.
7. Decision-Support Notice: LIBR is an investigative accounting convention; it does not
   represent a universal judicial ruling or proof of guilt.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, Tuple
import pandas as pd

from engine.tracing_models import (
    CATEGORY_LEGITIMATE,
    CATEGORY_UNKNOWN,
    LIBRAttributionEvent,
    LIBRTraceResult,
    TracingHop,
    make_suspected_category,
)
from pipeline.schemas import EXTERNAL_ACCOUNT_PREFIX


class LIBRTracer:
    """Deterministic Lowest Intermediate Balance Rule (LIBR) fund-tracing engine."""

    def __init__(
        self,
        accounts: List[Dict[str, Any]] | pd.DataFrame,
        transactions: List[Dict[str, Any]] | pd.DataFrame,
    ):
        self.accounts_raw = (
            accounts.to_dict(orient="records")
            if isinstance(accounts, pd.DataFrame)
            else list(accounts)
        )
        self.transactions_raw = (
            transactions.to_dict(orient="records")
            if isinstance(transactions, pd.DataFrame)
            else list(transactions)
        )

        # Build account metadata lookup
        self.account_meta: Dict[str, Dict[str, Any]] = {}
        for acc in self.accounts_raw:
            acc_id = str(acc["account_id"]).strip()
            self.account_meta[acc_id] = {
                "opening_balance_paise": int(acc["opening_balance_paise"]),
                "history_complete": bool(acc.get("history_complete", True)),
                "bank_id": str(acc.get("bank_id", "")),
                "account_type": str(acc.get("account_type", "")),
            }

        # Deterministically sort transactions by (timestamp, transaction_id)
        self.transactions = sorted(
            self.transactions_raw,
            key=lambda t: (str(t["timestamp"]), str(t["transaction_id"])),
        )

    def trace_source_transaction(
        self,
        source_transaction_id: str,
        source_case_id: Optional[str] = None,
        suspected_amount_paise: Optional[int] = None,
    ) -> LIBRTraceResult:
        """Execute deterministic LIBR fund tracing for a single designated suspected source transaction.

        Args:
            source_transaction_id: Transaction ID designated as fraud origin.
            source_case_id: Associated fraud case ID (inferred from transaction if None).
            suspected_amount_paise: Disputed amount in paise (inferred from transaction if None).
        """
        source_tx = None
        for tx in self.transactions:
            if tx["transaction_id"] == source_transaction_id:
                source_tx = tx
                break

        if source_tx is None:
            raise KeyError(
                f"Source transaction '{source_transaction_id}' not found in ledger."
            )

        case_id = (
            source_case_id or source_tx.get("case_id") or "UNKNOWN_CASE"
        ).strip()
        suspected_amt = int(
            suspected_amount_paise
            if suspected_amount_paise is not None
            else source_tx["amount_paise"]
        )
        if suspected_amt <= 0:
            raise ValueError(
                f"Suspected amount must be strictly positive: {suspected_amt}"
            )

        designated_source = {
            "transaction_id": source_transaction_id,
            "case_id": case_id,
            "amount_paise": suspected_amt,
        }

        return self.trace_sources([designated_source])

    def trace_sources(
        self,
        designated_sources: List[Dict[str, Any]],
    ) -> LIBRTraceResult:
        """Execute deterministic LIBR fund tracing for one or more designated suspected sources.

        Args:
            designated_sources: List of dicts specifying transaction_id, case_id, amount_paise.
        """
        if not designated_sources:
            raise ValueError("At least one designated source transaction is required.")

        # Build lookup of designated source transactions
        source_map: Dict[str, Dict[str, Any]] = {}
        suspected_categories: Set[str] = set()
        primary_tx_id = designated_sources[0]["transaction_id"]
        primary_case_id = designated_sources[0].get("case_id", "UNKNOWN_CASE")
        total_initial_suspected = 0

        for src in designated_sources:
            tx_id = str(src["transaction_id"]).strip()
            cid = str(src.get("case_id") or "UNKNOWN_CASE").strip()
            amt = int(src.get("amount_paise", 0))
            cat = make_suspected_category(tx_id, cid)
            source_map[tx_id] = {
                "case_id": cid,
                "amount_paise": amt,
                "category": cat,
            }
            suspected_categories.add(cat)
            total_initial_suspected += amt

        # Initialize account running balances and attributed suspected pools
        balances: Dict[str, int] = {}
        attributed_suspected: Dict[str, Dict[str, int]] = {}
        lowest_intermediate: Dict[str, int] = {}

        for acc_id, meta in self.account_meta.items():
            balances[acc_id] = meta["opening_balance_paise"]
            attributed_suspected[acc_id] = {}

        transfer_hops: List[TracingHop] = []
        events: List[LIBRAttributionEvent] = []
        external_outflows: Dict[str, Dict[str, int]] = {}
        hop_counter = 0

        # Process transactions sequentially in deterministic chronological order
        for tx in self.transactions:
            tx_id = str(tx["transaction_id"]).strip()
            ts = str(tx["timestamp"]).strip()
            from_acc = str(tx["from_account"]).strip()
            to_acc = str(tx["to_account"]).strip()
            amount = int(tx["amount_paise"])
            tx_type = str(tx.get("transaction_type", "transfer")).strip()
            tx_case = str(tx.get("case_id", "") or "").strip()
            evidence_status = str(tx.get("evidence_status", "unflagged")).strip()

            is_from_ext = from_acc.startswith(EXTERNAL_ACCOUNT_PREFIX)
            is_to_ext = to_acc.startswith(EXTERNAL_ACCOUNT_PREFIX)

            if from_acc not in balances and not is_from_ext:
                balances[from_acc] = 0
                attributed_suspected[from_acc] = {}
            if to_acc not in balances and not is_to_ext:
                balances[to_acc] = 0
                attributed_suspected[to_acc] = {}

            # -------------------------------------------------------------
            # Case 1: Designated suspected source transaction
            # -------------------------------------------------------------
            if tx_id in source_map:
                src_info = source_map[tx_id]
                sus_amt = src_info["amount_paise"] or amount
                cid = src_info["case_id"]
                sus_cat = src_info["category"]

                # If sender is internal, deduct from sender
                if not is_from_ext and from_acc in balances:
                    bal_before = balances[from_acc]
                    if amount > bal_before:
                        raise ValueError(
                            f"Account '{from_acc}' has insufficient balance ({bal_before} paise) "
                            f"for source transaction '{tx_id}' of {amount} paise."
                        )
                    balances[from_acc] -= amount
                    if from_acc in lowest_intermediate:
                        lowest_intermediate[from_acc] = min(
                            lowest_intermediate[from_acc], balances[from_acc]
                        )

                # Credit recipient
                bal_before_to = balances[to_acc]
                balances[to_acc] += amount
                bal_after_to = balances[to_acc]

                # Update attribution in to_acc
                attr_before_to = sum(attributed_suspected[to_acc].values())
                attributed_suspected[to_acc][sus_cat] = (
                    attributed_suspected[to_acc].get(sus_cat, 0) + sus_amt
                )
                attr_after_to = sum(attributed_suspected[to_acc].values())

                # Set / update lowest intermediate balance for to_acc
                if to_acc not in lowest_intermediate:
                    lowest_intermediate[to_acc] = bal_after_to
                else:
                    lowest_intermediate[to_acc] = min(
                        lowest_intermediate[to_acc], bal_after_to
                    )

                explanation = (
                    f"Designated source inflow: {amount:,} paise credited from '{from_acc}' to '{to_acc}'. "
                    f"Established {sus_amt:,} paise attributed to suspected source '{tx_id}' ({cid}). "
                    f"Account balance: {bal_before_to:,} -> {bal_after_to:,} paise."
                )

                events.append(
                    LIBRAttributionEvent(
                        transaction_id=tx_id,
                        timestamp=ts,
                        account_id=to_acc,
                        counterparty_account=from_acc,
                        transaction_type=tx_type,
                        total_amount_paise=amount,
                        balance_before_paise=bal_before_to,
                        balance_after_paise=bal_after_to,
                        attributed_before_paise=attr_before_to,
                        attributed_after_paise=attr_after_to,
                        lowest_intermediate_balance_paise=lowest_intermediate[to_acc],
                        attribution_reduction_paise=0,
                        propagated_amount_paise=sus_amt,
                        explanation_text=explanation,
                    )
                )

                # Record hop
                hop_counter += 1
                transfer_hops.append(
                    TracingHop(
                        hop_index=hop_counter,
                        transaction_id=tx_id,
                        timestamp=ts,
                        from_account=from_acc,
                        to_account=to_acc,
                        total_amount_paise=amount,
                        suspected_amount_paise=sus_amt,
                        allocated_by_category={sus_cat: sus_amt},
                        case_id=cid,
                        evidence_status=evidence_status,
                    )
                )
                continue

            # -------------------------------------------------------------
            # Case 2: External deposit (EXT_ -> ACC_)
            # -------------------------------------------------------------
            if is_from_ext and not is_to_ext:
                bal_before = balances[to_acc]
                balances[to_acc] += amount
                bal_after = balances[to_acc]

                attr_before = sum(attributed_suspected[to_acc].values())
                # Under LIBR No-Replenishment Rule:
                # Later legitimate deposit does NOT increase or replenish suspected attribution!
                attr_after = attr_before

                explanation = (
                    f"External deposit: {amount:,} paise credited to '{to_acc}' from '{from_acc}'. "
                    f"Balance increased: {bal_before:,} -> {bal_after:,} paise. "
                    f"Under LIBR No-Replenishment rule, existing suspected attribution remains {attr_after:,} paise."
                )

                lowest_val = lowest_intermediate.get(to_acc, bal_after)

                events.append(
                    LIBRAttributionEvent(
                        transaction_id=tx_id,
                        timestamp=ts,
                        account_id=to_acc,
                        counterparty_account=from_acc,
                        transaction_type=tx_type,
                        total_amount_paise=amount,
                        balance_before_paise=bal_before,
                        balance_after_paise=bal_after,
                        attributed_before_paise=attr_before,
                        attributed_after_paise=attr_after,
                        lowest_intermediate_balance_paise=lowest_val,
                        attribution_reduction_paise=0,
                        propagated_amount_paise=0,
                        explanation_text=explanation,
                    )
                )
                continue

            # -------------------------------------------------------------
            # Case 3: Outflow (Internal transfer or External withdrawal)
            # -------------------------------------------------------------
            if not is_from_ext and from_acc in balances:
                bal_before = balances[from_acc]

                if amount > bal_before:
                    raise ValueError(
                        f"Account '{from_acc}' has insufficient balance ({bal_before} paise) "
                        f"for outgoing transaction '{tx_id}' of {amount} paise."
                    )

                # Total attributed suspected in sender before transfer
                attr_before = sum(attributed_suspected[from_acc].values())

                # Clean funds available in sender before transfer
                clean_available = max(0, bal_before - attr_before)

                # Fiduciary spends own funds first:
                # Clean funds absorb outflow first; remaining draws from suspected funds.
                clean_spent = min(amount, clean_available)
                suspected_spent = amount - clean_spent

                # Allocate suspected_spent across attributed categories in sender
                propagated_by_category: Dict[str, int] = {}
                if suspected_spent > 0:
                    needed_sus = suspected_spent
                    for cat in list(attributed_suspected[from_acc].keys()):
                        if needed_sus <= 0:
                            break
                        curr_cat_bal = attributed_suspected[from_acc][cat]
                        draw = min(needed_sus, curr_cat_bal)
                        attributed_suspected[from_acc][cat] -= draw
                        needed_sus -= draw
                        propagated_by_category[cat] = draw
                        if attributed_suspected[from_acc][cat] == 0:
                            del attributed_suspected[from_acc][cat]

                # Update sender balance
                balances[from_acc] -= amount
                bal_after = balances[from_acc]

                # Update lowest intermediate balance
                if from_acc in lowest_intermediate:
                    lowest_intermediate[from_acc] = min(
                        lowest_intermediate[from_acc], bal_after
                    )
                elif attr_before > 0:
                    lowest_intermediate[from_acc] = bal_after

                attr_after = sum(attributed_suspected[from_acc].values())

                # Enforce LIBR ceiling: attribution can never exceed running balance
                attribution_reduction = 0
                if attr_after > bal_after:
                    excess = attr_after - bal_after
                    attribution_reduction = excess
                    # Trim excess from attribution
                    trim_needed = excess
                    for cat in list(attributed_suspected[from_acc].keys()):
                        if trim_needed <= 0:
                            break
                        c_bal = attributed_suspected[from_acc][cat]
                        t = min(trim_needed, c_bal)
                        attributed_suspected[from_acc][cat] -= t
                        trim_needed -= t
                        if attributed_suspected[from_acc][cat] == 0:
                            del attributed_suspected[from_acc][cat]
                    attr_after = sum(attributed_suspected[from_acc].values())

                lowest_val = lowest_intermediate.get(from_acc, bal_after)

                explanation = (
                    f"Outflow {tx_id} ({ts}): Account '{from_acc}' transferred {amount:,} paise to '{to_acc}'. "
                    f"Clean funds absorbed {clean_spent:,} paise; suspected funds absorbed {suspected_spent:,} paise. "
                    f"Balance: {bal_before:,} -> {bal_after:,} paise. "
                    f"Attributed suspected: {attr_before:,} -> {attr_after:,} paise. "
                    f"Lowest intermediate balance: {lowest_val:,} paise."
                )

                events.append(
                    LIBRAttributionEvent(
                        transaction_id=tx_id,
                        timestamp=ts,
                        account_id=from_acc,
                        counterparty_account=to_acc,
                        transaction_type=tx_type,
                        total_amount_paise=amount,
                        balance_before_paise=bal_before,
                        balance_after_paise=bal_after,
                        attributed_before_paise=attr_before,
                        attributed_after_paise=attr_after,
                        lowest_intermediate_balance_paise=lowest_val,
                        attribution_reduction_paise=attribution_reduction,
                        propagated_amount_paise=suspected_spent,
                        explanation_text=explanation,
                    )
                )

                # Subcase 3a: External withdrawal
                if is_to_ext:
                    if to_acc not in external_outflows:
                        external_outflows[to_acc] = {}
                    for cat, amt in propagated_by_category.items():
                        external_outflows[to_acc][cat] = (
                            external_outflows[to_acc].get(cat, 0) + amt
                        )

                # Subcase 3b: Internal transfer
                else:
                    bal_before_rec = balances[to_acc]
                    balances[to_acc] += amount
                    bal_after_rec = balances[to_acc]

                    if suspected_spent > 0:
                        for cat, amt in propagated_by_category.items():
                            attributed_suspected[to_acc][cat] = (
                                attributed_suspected[to_acc].get(cat, 0) + amt
                            )
                        if to_acc not in lowest_intermediate:
                            lowest_intermediate[to_acc] = bal_after_rec
                        else:
                            lowest_intermediate[to_acc] = min(
                                lowest_intermediate[to_acc], bal_after_rec
                            )

                        hop_counter += 1
                        transfer_hops.append(
                            TracingHop(
                                hop_index=hop_counter,
                                transaction_id=tx_id,
                                timestamp=ts,
                                from_account=from_acc,
                                to_account=to_acc,
                                total_amount_paise=amount,
                                suspected_amount_paise=suspected_spent,
                                allocated_by_category=dict(propagated_by_category),
                                case_id=tx_case or primary_case_id,
                                evidence_status=evidence_status,
                            )
                        )

        # Collect retained suspected funds per account
        retained: Dict[str, int] = {}
        for acc_id, cat_map in attributed_suspected.items():
            tot = sum(
                amt
                for cat, amt in cat_map.items()
                if cat in suspected_categories
            )
            if tot > 0:
                retained[acc_id] = tot

        # Collect external outflows containing suspected funds
        withdrawn: Dict[str, int] = {}
        for ext_acc, cat_map in external_outflows.items():
            tot = sum(
                amt
                for cat, amt in cat_map.items()
                if cat in suspected_categories
            )
            if tot > 0:
                withdrawn[ext_acc] = tot

        # Identify accounts with incomplete history holding suspected funds
        incomplete_accounts = [
            acc_id
            for acc_id in retained
            if not self.account_meta.get(acc_id, {}).get("history_complete", True)
        ]

        assumptions = [
            "LIBR Tracing Assumption: Clean and non-suspected funds are presumed withdrawn first "
            "(fiduciary spends own funds first). Suspected funds are only dissipated when clean funds are exhausted.",
            "Lowest Intermediate Balance: The attributable source amount in any account is strictly capped "
            "at the lowest balance reached after the source inflow.",
            "No-Replenishment Rule: Subsequent deposits of clean funds from third parties increase the available "
            "balance, but do NOT restore or replenish suspected attribution previously lost.",
            "Propagation: Internal transfers only propagate suspected funds to the extent that clean funds were "
            "insufficient to cover the transfer amount.",
            "Decision-Support Notice: LIBR is an investigative accounting convention; it does not represent a universal "
            "judicial ruling or proof of guilt.",
        ]

        return LIBRTraceResult(
            source_transaction_id=primary_tx_id,
            source_case_id=primary_case_id,
            initial_suspected_amount_paise=total_initial_suspected,
            retained_suspected_paise=retained,
            withdrawn_suspected_paise=withdrawn,
            lowest_intermediate_balances=lowest_intermediate,
            transfer_hops=transfer_hops,
            events=events,
            incomplete_history_accounts=incomplete_accounts,
            assumptions_and_limitations=assumptions,
        )
