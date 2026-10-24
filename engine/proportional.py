"""FairHold Proportional Fund-Tracing Engine.

Implements deterministic, explainable proportional fund tracing across commingled
accounts. Tracks suspected-source lots through multi-hop downstream transfers,
external deposits, and withdrawals using exact integer-paise arithmetic.

Guarantees:
- Exact balance conservation with zero floating-point approximation.
- Deterministic remainder distribution with documented tie-breakers.
- Explicit distinction between suspected, legitimate, and unknown-origin funds.
- Strict isolation from hidden ground-truth labels.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, Tuple
import pandas as pd

from engine.models import AccountState
from engine.tracing_explanations import TracingExplanationBuilder
from engine.tracing_models import (
    CATEGORY_LEGITIMATE,
    CATEGORY_UNKNOWN,
    AccountSourcePool,
    AllocationExplanation,
    ProportionalTraceResult,
    TracingHop,
    make_suspected_category,
)
from pipeline.schemas import EXTERNAL_ACCOUNT_PREFIX


class ProportionalTracer:
    """Deterministic proportional fund-tracing engine."""

    def __init__(
        self,
        accounts: List[Dict[str, Any]] | pd.DataFrame,
        transactions: List[Dict[str, Any]] | pd.DataFrame,
    ):
        self.accounts_raw = (
            accounts.to_dict(orient="records") if isinstance(accounts, pd.DataFrame) else list(accounts)
        )
        self.transactions_raw = (
            transactions.to_dict(orient="records") if isinstance(transactions, pd.DataFrame) else list(transactions)
        )
        # Sort transactions deterministically by (timestamp, transaction_id)
        self.transactions = sorted(
            self.transactions_raw,
            key=lambda t: (str(t["timestamp"]), str(t["transaction_id"])),
        )

    def _initialize_pools(self) -> Dict[str, AccountSourcePool]:
        """Initialize account source pools from opening balances.

        Accounts with history_complete=True place opening balance in CATEGORY_LEGITIMATE.
        Accounts with history_complete=False place opening balance in CATEGORY_UNKNOWN.
        """
        pools: Dict[str, AccountSourcePool] = {}
        for acc in self.accounts_raw:
            acc_id = str(acc["account_id"]).strip()
            opening = int(acc["opening_balance_paise"])
            hist_complete = bool(acc.get("history_complete", True))

            pool = AccountSourcePool(account_id=acc_id, history_complete=hist_complete)
            if opening > 0:
                cat = CATEGORY_LEGITIMATE if hist_complete else CATEGORY_UNKNOWN
                pool.credit(cat, opening)

            pools[acc_id] = pool
        return pools

    @staticmethod
    def allocate_proportionally(
        pool: AccountSourcePool,
        amount_paise: int,
    ) -> Tuple[Dict[str, int], Dict[str, int], Dict[str, int], Dict[str, int]]:
        """Allocate an outgoing amount proportionally across available source categories.

        Uses exact integer arithmetic with deterministic remainder distribution:
        - base_k = floor((amount * b_k) / B)
        - remainder_k = (amount * b_k) % B
        - remainder paise R = amount - sum(base_k)
        - Sort categories by (remainder_k descending, category_name ascending)
        - Award +1 paise to the top R categories

        Returns:
            Tuple of (final_allocations, base_allocations, remainders, awarded_paise).
        """
        total_balance = pool.total_balance_paise()
        if amount_paise > total_balance:
            raise ValueError(
                f"Account '{pool.account_id}' has insufficient balance ({total_balance} paise) "
                f"to allocate outgoing amount {amount_paise} paise"
            )
        if amount_paise <= 0:
            raise ValueError(f"Outgoing amount must be strictly positive: {amount_paise}")

        # If spending entire balance, allocate exact pools directly
        if amount_paise == total_balance:
            final_alloc = dict(pool.pools)
            base_alloc = dict(pool.pools)
            rems = {k: 0 for k in pool.pools}
            awarded = {k: 0 for k in pool.pools}
            return final_alloc, base_alloc, rems, awarded

        base_allocations: Dict[str, int] = {}
        remainders: Dict[str, int] = {}

        for cat, b_k in pool.pools.items():
            product = amount_paise * b_k
            base_allocations[cat] = product // total_balance
            remainders[cat] = product % total_balance

        allocated_sum = sum(base_allocations.values())
        paise_to_distribute = amount_paise - allocated_sum

        # Deterministic remainder distribution: sort by (remainder desc, category name asc)
        awarded_paise: Dict[str, int] = {cat: 0 for cat in pool.pools}
        sorted_cats = sorted(
            pool.pools.keys(),
            key=lambda c: (-remainders[c], c),
        )

        for i in range(paise_to_distribute):
            target_cat = sorted_cats[i % len(sorted_cats)]
            awarded_paise[target_cat] += 1

        final_allocations: Dict[str, int] = {}
        for cat in pool.pools.keys():
            final_allocations[cat] = base_allocations[cat] + awarded_paise[cat]

        # Invariant checks
        if sum(final_allocations.values()) != amount_paise:
            raise RuntimeError(
                f"Allocation sum mismatch: {sum(final_allocations.values())} != {amount_paise}"
            )
        for cat, alloc in final_allocations.items():
            if alloc > pool.pools[cat]:
                raise RuntimeError(
                    f"Category '{cat}' allocated {alloc} paise exceeding pool balance {pool.pools[cat]}"
                )

        return final_allocations, base_allocations, remainders, awarded_paise

    def trace_source_transaction(
        self,
        source_transaction_id: str,
        source_case_id: Optional[str] = None,
        suspected_amount_paise: Optional[int] = None,
    ) -> ProportionalTraceResult:
        """Execute proportional fund tracing from a designated source transaction.

        Args:
            source_transaction_id: Transaction ID designated as the suspected fraud origin.
            source_case_id: Associated case ID (inferred from transaction if None).
            suspected_amount_paise: Disputed amount in paise (inferred from transaction if None).
        """
        # Find the source transaction
        source_tx = None
        for tx in self.transactions:
            if tx["transaction_id"] == source_transaction_id:
                source_tx = tx
                break

        if source_tx is None:
            raise KeyError(f"Source transaction '{source_transaction_id}' not found in ledger.")

        case_id = (source_case_id or source_tx.get("case_id") or "UNKNOWN_CASE").strip()
        suspected_amt = int(
            suspected_amount_paise if suspected_amount_paise is not None else source_tx["amount_paise"]
        )
        if suspected_amt <= 0:
            raise ValueError(f"Suspected amount must be strictly positive: {suspected_amt}")

        suspected_category = make_suspected_category(source_transaction_id, case_id)

        pools = self._initialize_pools()
        transfer_hops: List[TracingHop] = []
        explanations: List[AllocationExplanation] = []
        external_outflows: Dict[str, Dict[str, int]] = {}

        source_processed = False
        hop_counter = 0

        # Sequentially process transactions in deterministic chronological order
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

            # -------------------------------------------------------------
            # Case 1: Designated suspected source transaction
            # -------------------------------------------------------------
            if tx_id == source_transaction_id:
                source_processed = True
                # Inflow arrives at to_acc
                # Debit from sender (if internal) from legitimate pool
                if not is_from_ext and from_acc in pools:
                    # Allocate deduction from sender
                    sender_pool = pools[from_acc]
                    allocs, base_a, rems, awarded = self.allocate_proportionally(sender_pool, amount)
                    for cat, debit_amt in allocs.items():
                        sender_pool.debit(cat, debit_amt)

                # Credit receiver with designated suspected funds
                if to_acc in pools:
                    receiver_pool = pools[to_acc]
                    # Credit suspected category
                    receiver_pool.credit(suspected_category, suspected_amt)
                    # Any remaining excess of transaction amount over suspected is legitimate
                    excess = amount - suspected_amt
                    if excess > 0:
                        receiver_pool.credit(CATEGORY_LEGITIMATE, excess)

                # Record hop
                hop_counter += 1
                transfer_hops.append(TracingHop(
                    hop_index=hop_counter,
                    transaction_id=tx_id,
                    timestamp=ts,
                    from_account=from_acc,
                    to_account=to_acc,
                    total_amount_paise=amount,
                    suspected_amount_paise=suspected_amt,
                    allocated_by_category={suspected_category: suspected_amt},
                    case_id=case_id,
                    evidence_status=evidence_status,
                ))
                continue

            # -------------------------------------------------------------
            # Case 2: External deposit (EXT_ -> ACC_)
            # -------------------------------------------------------------
            if is_from_ext and not is_to_ext:
                if to_acc in pools:
                    # External deposits are treated as legitimate new capital
                    pools[to_acc].credit(CATEGORY_LEGITIMATE, amount)
                continue

            # -------------------------------------------------------------
            # Case 3: Outflow (Internal transfer or External withdrawal)
            # -------------------------------------------------------------
            if not is_from_ext and from_acc in pools:
                sender_pool = pools[from_acc]
                pre_balance = sender_pool.total_balance_paise()
                pre_snapshot = sender_pool.snapshot()

                # Allocate proportionally across available source pools
                final_alloc, base_alloc, rems, awarded = self.allocate_proportionally(
                    sender_pool, amount
                )

                # Deduct allocations from sender
                for cat, alloc_amt in final_alloc.items():
                    sender_pool.debit(cat, alloc_amt)

                post_snapshot = sender_pool.snapshot()

                # Generate explanation
                explanation = TracingExplanationBuilder.build_allocation_explanation(
                    transaction_id=tx_id,
                    timestamp=ts,
                    account_id=from_acc,
                    counterparty_account=to_acc,
                    transaction_type=tx_type,
                    total_amount_paise=amount,
                    balance_before_paise=pre_balance,
                    pools_before=pre_snapshot,
                    base_allocations=base_alloc,
                    remainders=rems,
                    remainder_paise_awarded=awarded,
                    final_allocations=final_alloc,
                    pools_after=post_snapshot,
                )
                explanations.append(explanation)

                suspected_allocated = final_alloc.get(suspected_category, 0)

                # Subcase 3a: External withdrawal (ACC_ -> EXT_)
                if is_to_ext:
                    if to_acc not in external_outflows:
                        external_outflows[to_acc] = {}
                    for cat, amt in final_alloc.items():
                        external_outflows[to_acc][cat] = (
                            external_outflows[to_acc].get(cat, 0) + amt
                        )

                # Subcase 3b: Internal transfer (ACC_ -> ACC_)
                else:
                    if to_acc in pools:
                        recipient_pool = pools[to_acc]
                        for cat, alloc_amt in final_alloc.items():
                            recipient_pool.credit(cat, alloc_amt)

                    # If suspected funds flowed, record hop
                    if suspected_allocated > 0:
                        hop_counter += 1
                        transfer_hops.append(TracingHop(
                            hop_index=hop_counter,
                            transaction_id=tx_id,
                            timestamp=ts,
                            from_account=from_acc,
                            to_account=to_acc,
                            total_amount_paise=amount,
                            suspected_amount_paise=suspected_allocated,
                            allocated_by_category=dict(final_alloc),
                            case_id=tx_case or case_id,
                            evidence_status=evidence_status,
                        ))

        # Collect retained suspected funds per account
        retained: Dict[str, int] = {}
        for acc_id, pool in pools.items():
            sus_bal = pool.get_balance(suspected_category)
            if sus_bal > 0:
                retained[acc_id] = sus_bal

        # Collect external outflows containing suspected funds
        withdrawn: Dict[str, int] = {}
        for ext_acc, cat_map in external_outflows.items():
            sus_wth = cat_map.get(suspected_category, 0)
            if sus_wth > 0:
                withdrawn[ext_acc] = sus_wth

        # Identify incomplete history accounts that received suspected funds
        incomplete_accounts = [
            acc_id
            for acc_id in retained
            if not pools[acc_id].history_complete
        ]

        assumptions = [
            "Proportional Tracing Assumption: Every outgoing payment from an account draws equally "
            "from all available source funds in proportion to their balance at the time of transfer.",
            "Commingling Convention: Clean and suspected funds are treated as fungible at each transfer.",
            "Integer Paise Precision: Remainder fractions are deterministically awarded based on highest "
            "fractional remainder with category name tie-breaker.",
            "Decision-Support Notice: Traced amounts represent method-dependent estimates, not judicial proof of liability.",
        ]

        return ProportionalTraceResult(
            source_transaction_id=source_transaction_id,
            source_case_id=case_id,
            initial_suspected_amount_paise=suspected_amt,
            account_pools={acc_id: pool.snapshot() for acc_id, pool in pools.items()},
            retained_suspected_paise=retained,
            withdrawn_suspected_paise=withdrawn,
            transfer_hops=transfer_hops,
            explanations=explanations,
            incomplete_history_accounts=incomplete_accounts,
            assumptions_and_limitations=assumptions,
        )
