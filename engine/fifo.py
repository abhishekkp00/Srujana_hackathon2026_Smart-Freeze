"""FairHold First-In, First-Out (FIFO) Fund-Tracing Engine.

Implements deterministic, explainable FIFO fund tracing using ordered source lots.
When funds leave an account, the oldest available source lots are consumed first
according to strictly documented chronological and sequential conventions.

Key Principles:
- Available funds in each account are partitioned into discrete, ordered source lots.
- Integer paise arithmetic throughout; zero floating-point approximation.
- Strict provenance tracking with parent-lot lineage across multi-hop transfers.
- Complete isolation from hidden ground-truth labels.
- Human-readable and structured mathematical explanations for every lot consumption.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, Tuple
import pandas as pd

from engine.tracing_models import (
    CATEGORY_LEGITIMATE,
    CATEGORY_UNKNOWN,
    FIFOConsumptionEvent,
    FIFOAllocationExplanation,
    FIFOLot,
    FIFOTraceResult,
    TracingHop,
    make_suspected_category,
)
from pipeline.schemas import EXTERNAL_ACCOUNT_PREFIX

OPENING_BALANCE_TIMESTAMP = "1970-01-01T00:00:00Z"


class FIFOTracer:
    """Deterministic First-In, First-Out (FIFO) fund-tracing engine."""

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

    def _initialize_lots(self) -> Dict[str, List[FIFOLot]]:
        """Initialize source lots for all accounts from opening balances.

        - If history_complete is True: Opening balance is classified as CATEGORY_LEGITIMATE.
        - If history_complete is False: Opening balance is classified as CATEGORY_UNKNOWN.
          Opening balance is never assumed legitimate when account history is incomplete.
        - Opening lots receive fixed earliest timestamp 1970-01-01T00:00:00Z and sequence 0.
        """
        lots_by_account: Dict[str, List[FIFOLot]] = {}

        for acc_id, meta in self.account_meta.items():
            lots: List[FIFOLot] = []
            opening_paise = meta["opening_balance_paise"]
            hist_complete = meta["history_complete"]

            if opening_paise > 0:
                classification = (
                    CATEGORY_LEGITIMATE if hist_complete else CATEGORY_UNKNOWN
                )
                lot = FIFOLot(
                    lot_id=f"LOT_OPENING_{acc_id}",
                    account_id=acc_id,
                    origin_transaction_id=f"OPENING:{acc_id}",
                    origin_timestamp=OPENING_BALANCE_TIMESTAMP,
                    origin_sequence=0,
                    original_amount_paise=opening_paise,
                    remaining_amount_paise=opening_paise,
                    source_classification=classification,
                    source_case_id="",
                    parent_lot_id=None,
                    history_complete=hist_complete,
                )
                lots.append(lot)

            lots_by_account[acc_id] = lots

        return lots_by_account

    @staticmethod
    def _sort_lots_fifo(lots: List[FIFOLot]) -> List[FIFOLot]:
        """Sort available lots according to strict FIFO convention.

        Ordering Rule:
        1. origin_timestamp ascending (oldest funds first).
        2. origin_sequence ascending (transaction ordering tie-breaker).
        3. lot_id ascending (deterministic alphabetical tie-breaker).
        """
        return sorted(
            [lot for lot in lots if lot.remaining_amount_paise > 0],
            key=lambda lot: (
                str(lot.origin_timestamp),
                int(lot.origin_sequence),
                str(lot.lot_id),
            ),
        )

    def trace_source_transaction(
        self,
        source_transaction_id: str,
        source_case_id: Optional[str] = None,
        suspected_amount_paise: Optional[int] = None,
    ) -> FIFOTraceResult:
        """Execute deterministic FIFO fund tracing for a single designated suspected transaction.

        Args:
            source_transaction_id: Transaction ID designated as fraud origin.
            source_case_id: Associated fraud case ID (inferred from transaction if None).
            suspected_amount_paise: Disputed amount in paise (inferred from transaction if None).
        """
        # Locate the source transaction
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
    ) -> FIFOTraceResult:
        """Execute deterministic FIFO fund tracing for one or more designated suspected sources.

        Args:
            designated_sources: List of dicts specifying transaction_id, case_id, amount_paise.
        """
        if not designated_sources:
            raise ValueError("At least one designated source transaction is required.")

        # Build mapping of designated source transactions
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

        lots_by_account = self._initialize_lots()
        transfer_hops: List[TracingHop] = []
        all_consumption_events: List[FIFOConsumptionEvent] = []
        explanations: List[FIFOAllocationExplanation] = []
        external_outflows: Dict[str, Dict[str, int]] = {}

        hop_counter = 0

        # Process transactions sequentially in deterministic chronological order
        for tx_seq, tx in enumerate(self.transactions, start=1):
            tx_id = str(tx["transaction_id"]).strip()
            ts = str(tx["timestamp"]).strip()
            from_acc = str(tx["from_account"]).strip()
            to_acc = str(tx["to_account"]).strip()
            amount = int(tx["amount_paise"])
            tx_case = str(tx.get("case_id", "") or "").strip()
            evidence_status = str(tx.get("evidence_status", "unflagged")).strip()

            is_from_ext = from_acc.startswith(EXTERNAL_ACCOUNT_PREFIX)
            is_to_ext = to_acc.startswith(EXTERNAL_ACCOUNT_PREFIX)

            # Ensure accounts exist in lot mapping
            if from_acc not in lots_by_account and not is_from_ext:
                lots_by_account[from_acc] = []
            if to_acc not in lots_by_account and not is_to_ext:
                lots_by_account[to_acc] = []

            # -------------------------------------------------------------
            # Case 1: Designated suspected source transaction
            # -------------------------------------------------------------
            if tx_id in source_map:
                src_info = source_map[tx_id]
                sus_amt = src_info["amount_paise"] or amount
                cid = src_info["case_id"]
                sus_cat = src_info["category"]

                # If sender is internal, deduct amount from sender using FIFO
                if not is_from_ext and from_acc in lots_by_account:
                    sender_lots = lots_by_account[from_acc]
                    available_before = sum(l.remaining_amount_paise for l in sender_lots)
                    if amount > available_before:
                        raise ValueError(
                            f"Account '{from_acc}' has insufficient balance ({available_before} paise) "
                            f"for source transaction '{tx_id}' of {amount} paise."
                        )
                    # Consume from sender lots
                    events, exp = self._consume_lots(
                        account_id=from_acc,
                        lots=sender_lots,
                        amount_to_consume=amount,
                        tx_id=tx_id,
                        timestamp=ts,
                        tx_seq=tx_seq,
                        counterparty_account=to_acc,
                        is_external_outflow=False,
                        recipient_lots=None,  # We create custom designated lots in to_acc below
                        external_outflows=external_outflows,
                    )
                    all_consumption_events.extend(events)
                    explanations.append(exp)

                # Credit receiver with designated suspected source lot
                if to_acc in lots_by_account:
                    sus_lot = FIFOLot(
                        lot_id=f"LOT_SRC_{tx_id}",
                        account_id=to_acc,
                        origin_transaction_id=tx_id,
                        origin_timestamp=ts,
                        origin_sequence=tx_seq,
                        original_amount_paise=sus_amt,
                        remaining_amount_paise=sus_amt,
                        source_classification=sus_cat,
                        source_case_id=cid,
                        parent_lot_id=None,
                        history_complete=self.account_meta.get(to_acc, {}).get("history_complete", True),
                    )
                    lots_by_account[to_acc].append(sus_lot)

                    # If transaction amount exceeds suspected amount, credit excess as legitimate
                    excess = amount - sus_amt
                    if excess > 0:
                        excess_lot = FIFOLot(
                            lot_id=f"LOT_{tx_id}_EXCESS",
                            account_id=to_acc,
                            origin_transaction_id=tx_id,
                            origin_timestamp=ts,
                            origin_sequence=tx_seq,
                            original_amount_paise=excess,
                            remaining_amount_paise=excess,
                            source_classification=CATEGORY_LEGITIMATE,
                            source_case_id=cid,
                            parent_lot_id=None,
                            history_complete=self.account_meta.get(to_acc, {}).get("history_complete", True),
                        )
                        lots_by_account[to_acc].append(excess_lot)

                # Record source hop
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
                if to_acc in lots_by_account:
                    dep_lot = FIFOLot(
                        lot_id=f"LOT_DEP_{tx_id}",
                        account_id=to_acc,
                        origin_transaction_id=tx_id,
                        origin_timestamp=ts,
                        origin_sequence=tx_seq,
                        original_amount_paise=amount,
                        remaining_amount_paise=amount,
                        source_classification=CATEGORY_LEGITIMATE,
                        source_case_id="",
                        parent_lot_id=None,
                        history_complete=self.account_meta.get(to_acc, {}).get("history_complete", True),
                    )
                    lots_by_account[to_acc].append(dep_lot)
                continue

            # -------------------------------------------------------------
            # Case 3: Outflow (Internal transfer or External withdrawal)
            # -------------------------------------------------------------
            if not is_from_ext and from_acc in lots_by_account:
                sender_lots = lots_by_account[from_acc]
                available_before = sum(l.remaining_amount_paise for l in sender_lots)

                if amount > available_before:
                    raise ValueError(
                        f"Account '{from_acc}' has insufficient balance ({available_before} paise) "
                        f"for outgoing transaction '{tx_id}' of {amount} paise."
                    )

                recipient_lots = (
                    lots_by_account[to_acc] if not is_to_ext else None
                )

                events, exp = self._consume_lots(
                    account_id=from_acc,
                    lots=sender_lots,
                    amount_to_consume=amount,
                    tx_id=tx_id,
                    timestamp=ts,
                    tx_seq=tx_seq,
                    counterparty_account=to_acc,
                    is_external_outflow=is_to_ext,
                    recipient_lots=recipient_lots,
                    external_outflows=external_outflows,
                )
                all_consumption_events.extend(events)
                explanations.append(exp)

                # Check if any suspected funds were transferred
                suspected_transferred = sum(
                    ev.amount_consumed_paise
                    for ev in events
                    if ev.source_classification in suspected_categories
                )

                if suspected_transferred > 0 and not is_to_ext:
                    cat_allocs: Dict[str, int] = {}
                    for ev in events:
                        cat_allocs[ev.source_classification] = (
                            cat_allocs.get(ev.source_classification, 0)
                            + ev.amount_consumed_paise
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
                            suspected_amount_paise=suspected_transferred,
                            allocated_by_category=cat_allocs,
                            case_id=tx_case or primary_case_id,
                            evidence_status=evidence_status,
                        )
                    )

        # Collect retained suspected funds per account
        retained: Dict[str, int] = {}
        for acc_id, lots in lots_by_account.items():
            sus_bal = sum(
                lot.remaining_amount_paise
                for lot in lots
                if lot.source_classification in suspected_categories
                and lot.remaining_amount_paise > 0
            )
            if sus_bal > 0:
                retained[acc_id] = sus_bal

        # Collect external outflows containing suspected funds
        withdrawn: Dict[str, int] = {}
        for ext_acc, cat_map in external_outflows.items():
            sus_wth = sum(
                amt
                for cat, amt in cat_map.items()
                if cat in suspected_categories
            )
            if sus_wth > 0:
                withdrawn[ext_acc] = sus_wth

        # Identify accounts with incomplete history holding suspected funds
        incomplete_accounts = [
            acc_id
            for acc_id in retained
            if not self.account_meta.get(acc_id, {}).get("history_complete", True)
        ]

        active_lots = {
            acc_id: [lot.to_dict() for lot in lots if lot.remaining_amount_paise > 0]
            for acc_id, lots in lots_by_account.items()
        }

        assumptions = [
            "FIFO Tracing Assumption: Outgoing transfers consume funds from available lots in strict "
            "First-In, First-Out chronological arrival order.",
            "Lot Lineage Conservation: Internal transfers create discrete destination lots preserving "
            "source classification, case reference, and parent lot ID.",
            "Deterministic Ordering: Ties in origin timestamp are deterministically broken using "
            "origin sequence followed by alphanumeric lot ID.",
            "Opening Balances: Complete history opening balances are classified as legitimate; incomplete "
            "history opening balances are classified as unknown origin and never assumed clean.",
            "Decision-Support Notice: Traced amounts represent method-dependent accounting estimates, "
            "not judicial proof of liability.",
        ]

        return FIFOTraceResult(
            source_transaction_id=primary_tx_id,
            source_case_id=primary_case_id,
            initial_suspected_amount_paise=total_initial_suspected,
            retained_suspected_paise=retained,
            withdrawn_suspected_paise=withdrawn,
            active_lots_by_account=active_lots,
            transfer_hops=transfer_hops,
            consumption_events=all_consumption_events,
            explanations=explanations,
            incomplete_history_accounts=incomplete_accounts,
            assumptions_and_limitations=assumptions,
        )

    def _consume_lots(
        self,
        account_id: str,
        lots: List[FIFOLot],
        amount_to_consume: int,
        tx_id: str,
        timestamp: str,
        tx_seq: int,
        counterparty_account: str,
        is_external_outflow: bool,
        recipient_lots: Optional[List[FIFOLot]],
        external_outflows: Dict[str, Dict[str, int]],
    ) -> Tuple[List[FIFOConsumptionEvent], FIFOAllocationExplanation]:
        """Consume amount_to_consume from lots in strict FIFO order."""
        eligible_lots = self._sort_lots_fifo(lots)
        needed = amount_to_consume
        consumption_events: List[FIFOConsumptionEvent] = []
        explanation_lines: List[str] = [
            f"Transaction {tx_id} ({timestamp}): Account '{account_id}' transferred {amount_to_consume:,} paise to '{counterparty_account}'.",
            f"FIFO lot consumption order (oldest arrival first):",
        ]

        lot_slice_idx = 0
        for lot in eligible_lots:
            if needed <= 0:
                break

            pre_bal = lot.remaining_amount_paise
            consumed = min(needed, pre_bal)
            lot.consume(consumed)
            post_bal = lot.remaining_amount_paise
            needed -= consumed
            lot_slice_idx += 1

            event = FIFOConsumptionEvent(
                transaction_id=tx_id,
                timestamp=timestamp,
                account_id=account_id,
                lot_id=lot.lot_id,
                origin_transaction_id=lot.origin_transaction_id,
                source_classification=lot.source_classification,
                source_case_id=lot.source_case_id,
                amount_consumed_paise=consumed,
                lot_balance_before_paise=pre_bal,
                lot_balance_after_paise=post_bal,
            )
            consumption_events.append(event)

            explanation_lines.append(
                f"  [{lot_slice_idx}] Consumed {consumed:,} paise from lot '{lot.lot_id}' "
                f"(origin: {lot.origin_transaction_id} at {lot.origin_timestamp}, class: {lot.source_classification}). "
                f"Lot balance: {pre_bal:,} -> {post_bal:,} paise."
            )

            # Internal transfer: propagate destination lot with parent lineage
            if not is_external_outflow and recipient_lots is not None:
                dest_lot = FIFOLot(
                    lot_id=f"LOT_{tx_id}_{lot_slice_idx}",
                    account_id=counterparty_account,
                    origin_transaction_id=tx_id,
                    origin_timestamp=timestamp,
                    origin_sequence=tx_seq,
                    original_amount_paise=consumed,
                    remaining_amount_paise=consumed,
                    source_classification=lot.source_classification,
                    source_case_id=lot.source_case_id,
                    parent_lot_id=lot.lot_id,
                    history_complete=lot.history_complete,
                )
                recipient_lots.append(dest_lot)
                explanation_lines.append(
                    f"      -> Created destination lot '{dest_lot.lot_id}' in '{counterparty_account}' "
                    f"with parent '{lot.lot_id}'."
                )

            # External withdrawal: record outflow
            elif is_external_outflow:
                if counterparty_account not in external_outflows:
                    external_outflows[counterparty_account] = {}
                cat = lot.source_classification
                external_outflows[counterparty_account][cat] = (
                    external_outflows[counterparty_account].get(cat, 0) + consumed
                )
                explanation_lines.append(
                    f"      -> Outflow recorded to external account '{counterparty_account}' ({cat})."
                )

        if needed > 0:
            raise RuntimeError(
                f"FIFO consumption underflow: unable to allocate remaining {needed} paise."
            )

        explanation = FIFOAllocationExplanation(
            transaction_id=tx_id,
            timestamp=timestamp,
            account_id=account_id,
            counterparty_account=counterparty_account,
            total_amount_paise=amount_to_consume,
            consumptions=consumption_events,
            explanation_text="\n".join(explanation_lines),
        )

        return consumption_events, explanation
