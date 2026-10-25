"""Smart-Freeze Behavioural and Trail Feature Engineering.

Extracts verifiable behavioural, transaction-trail, and historical/contextual
features from the transaction ledger, account records, and directed transaction
graph. Strictly enforces temporal cutoff boundaries and operates without access
to hidden evaluation ground truth.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import datetime
import math
from typing import Any, Dict, List, Optional, Set, Tuple
import pandas as pd

from pipeline.schemas import EXTERNAL_ACCOUNT_PREFIX


def _parse_iso_timestamp(ts_str: str) -> datetime.datetime:
    """Parse ISO 8601 UTC timestamp string safely."""
    s = str(ts_str).strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    return datetime.datetime.fromisoformat(s)


@dataclass
class CaseFeatures:
    """Extracted features for an individual case and its associated transaction trail."""
    case_id: str
    reported_date: str
    reported_amount_paise: int

    # Behavioural indicators (Component B)
    rapid_movement_ratio: float
    amount_deviation_ratio: float
    drain_rate: float
    b_score: Optional[float]
    b_available: bool
    b_reason: str
    b_subfactors: Dict[str, float]

    # Transaction trail indicators (Component T)
    graph_depth: int
    fan_out_degree: int
    has_cash_withdrawal: bool
    trail_transaction_count: int
    t_score: Optional[float]
    t_available: bool
    t_reason: str
    t_subfactors: Dict[str, float]

    # Historical & contextual indicators (Component H)
    suspected_status_ratio: float
    has_incomplete_history: bool
    incomplete_account_count: int
    h_score: Optional[float]
    h_available: bool
    h_reason: str
    h_subfactors: Dict[str, float]

    # Traceability and evidence provenance
    supporting_transaction_ids: List[str] = field(default_factory=list)
    supporting_account_ids: List[str] = field(default_factory=list)
    positive_factors: List[str] = field(default_factory=list)
    mitigating_factors: List[str] = field(default_factory=list)
    data_quality_warnings: List[str] = field(default_factory=list)


class BehaviouralFeatureExtractor:
    """Extracts features for cases from chronological transaction ledgers and accounts.

    All feature calculations are deterministic, auditable, and isolated from ground-truth labels.
    """

    def __init__(
        self,
        rapid_hop_seconds: int = 7200,  # 2 hours threshold for rapid onward transfers
        baseline_median_default_paise: int = 1000000,  # ₹10,000 fallback if baseline missing
    ):
        self.rapid_hop_seconds = rapid_hop_seconds
        self.baseline_median_default_paise = baseline_median_default_paise

    def extract_features(
        self,
        case: Dict[str, Any] | Any,
        transactions: List[Dict[str, Any]] | pd.DataFrame,
        accounts: List[Dict[str, Any]] | pd.DataFrame,
        cutoff_timestamp: Optional[str] = None,
        baseline_transactions: Optional[List[Dict[str, Any]] | pd.DataFrame] = None,
    ) -> CaseFeatures:
        """Extract all behavioural, graph trail, and contextual features for a case.

        Args:
            case: Dict or object with case_id, reported_date, reported_amount_paise.
            transactions: Chronological transaction ledger.
            accounts: Account ledger.
            cutoff_timestamp: Optional cutoff string (ISO 8601). Transactions after this
                              are strictly excluded to avoid future leakage.
            baseline_transactions: Optional global transactions used to compute baseline
                                   amount statistics.
        """
        # 1. Normalize case metadata
        case_id = str(case.get("case_id") if isinstance(case, dict) else getattr(case, "case_id", "")).strip()
        rep_date = str(case.get("reported_date") if isinstance(case, dict) else getattr(case, "reported_date", "")).strip()
        raw_rep_amt = case.get("reported_amount_paise") if isinstance(case, dict) else getattr(case, "reported_amount_paise", 0)

        warnings: List[str] = []
        try:
            reported_amount_paise = int(raw_rep_amt)
            if reported_amount_paise < 0:
                warnings.append(f"Negative reported amount {reported_amount_paise} paise clamped to 0.")
                reported_amount_paise = 0
        except (ValueError, TypeError):
            warnings.append(f"Invalid non-integer reported amount '{raw_rep_amt}'; defaulted to 0.")
            reported_amount_paise = 0

        # Parse cutoff
        effective_cutoff_dt: Optional[datetime.datetime] = None
        if cutoff_timestamp:
            try:
                effective_cutoff_dt = _parse_iso_timestamp(cutoff_timestamp)
            except Exception as e:
                warnings.append(f"Invalid cutoff_timestamp '{cutoff_timestamp}': {e}; ignored cutoff.")

        # 2. Normalize accounts into dict
        acc_dict: Dict[str, Dict[str, Any]] = {}
        if isinstance(accounts, pd.DataFrame):
            acc_list = accounts.to_dict(orient="records")
        else:
            acc_list = accounts

        for a in acc_list:
            aid = str(a.get("account_id", "")).strip()
            if aid:
                acc_dict[aid] = a

        # 3. Normalize transactions and apply temporal cutoff filter
        if isinstance(transactions, pd.DataFrame):
            tx_list = transactions.to_dict(orient="records")
        else:
            tx_list = transactions

        valid_txs: List[Dict[str, Any]] = []
        for tx in tx_list:
            ts_str = str(tx.get("timestamp", "")).strip()
            if not ts_str:
                continue
            try:
                tx_dt = _parse_iso_timestamp(ts_str)
            except Exception:
                continue

            # Strict future transaction exclusion
            if effective_cutoff_dt and tx_dt > effective_cutoff_dt:
                continue

            valid_txs.append(tx)

        # 4. Filter transactions matching this case
        case_txs = [tx for tx in valid_txs if str(tx.get("case_id", "")).strip() == case_id]

        # Sort case transactions chronologically with deterministic secondary key
        case_txs.sort(key=lambda x: (str(x.get("timestamp", "")), str(x.get("transaction_id", ""))))

        supporting_tx_ids = [str(tx.get("transaction_id", "")).strip() for tx in case_txs]
        involved_accounts: Set[str] = set()
        for tx in case_txs:
            fa = str(tx.get("from_account", "")).strip()
            ta = str(tx.get("to_account", "")).strip()
            if fa:
                involved_accounts.add(fa)
            if ta:
                involved_accounts.add(ta)

        supporting_acc_ids = sorted(list(involved_accounts))

        # Check incomplete account histories
        incomplete_accounts = [
            aid for aid in supporting_acc_ids
            if aid in acc_dict and not bool(acc_dict[aid].get("history_complete", True))
        ]
        has_incomplete_history = len(incomplete_accounts) > 0
        for inc_id in incomplete_accounts:
            warnings.append(
                f"Account '{inc_id}' has incomplete historical statement records; "
                "transaction trail may omit earlier fund origins or subsequent transfers."
            )

        # 5. Baseline transaction amount calculation
        if baseline_transactions is not None:
            if isinstance(baseline_transactions, pd.DataFrame):
                base_list = baseline_transactions.to_dict(orient="records")
            else:
                base_list = baseline_transactions
        else:
            base_list = valid_txs

        base_amounts: List[int] = []
        for btx in base_list:
            try:
                amt = int(btx.get("amount_paise", 0))
                if amt > 0:
                    base_amounts.append(amt)
            except (ValueError, TypeError):
                continue

        if len(base_amounts) >= 3:
            sorted_base = sorted(base_amounts)
            baseline_median_paise = sorted_base[len(sorted_base) // 2]
        else:
            baseline_median_paise = self.baseline_median_default_paise
            warnings.append(
                f"Insufficient baseline transactions ({len(base_amounts)}); "
                f"using default median baseline of ₹{self.baseline_median_default_paise / 100:,.2f}."
            )

        # ==============================================================================
        # Component B: Behavioural Anomalies
        # ==============================================================================
        positive_factors: List[str] = []
        mitigating_factors: List[str] = []
        b_subfactors: Dict[str, float] = {}

        if len(case_txs) == 0:
            b_available = False
            b_score = None
            b_reason = "No transactions linked to case to calculate behavioural patterns."
            rapid_movement_ratio = 0.0
            amount_deviation_ratio = 0.0
            drain_rate = 0.0
        else:
            # 1. Rapid onward movement in intermediary accounts
            # Map inflows to internal accounts and subsequent outflows
            inflows: Dict[str, List[Tuple[datetime.datetime, int, str]]] = {}
            outflows: Dict[str, List[Tuple[datetime.datetime, int, str]]] = {}

            for tx in case_txs:
                ts = _parse_iso_timestamp(str(tx.get("timestamp", "")))
                fa = str(tx.get("from_account", "")).strip()
                ta = str(tx.get("to_account", "")).strip()
                amt = int(tx.get("amount_paise", 0))
                tx_id = str(tx.get("transaction_id", "")).strip()

                if not ta.startswith(EXTERNAL_ACCOUNT_PREFIX):
                    inflows.setdefault(ta, []).append((ts, amt, tx_id))
                if not fa.startswith(EXTERNAL_ACCOUNT_PREFIX):
                    outflows.setdefault(fa, []).append((ts, amt, tx_id))

            # Intermediary accounts have both inflow and outflow in this trail
            intermediary_accounts = set(inflows.keys()).intersection(set(outflows.keys()))
            rapid_hop_count = 0
            total_intermediary_hops = 0

            for acc in intermediary_accounts:
                acc_in = sorted(inflows[acc], key=lambda x: x[0])
                acc_out = sorted(outflows[acc], key=lambda x: x[0])

                for in_ts, _, in_id in acc_in:
                    # Look for subsequent outflows
                    subsequent_outs = [out for out in acc_out if out[0] >= in_ts]
                    if subsequent_outs:
                        total_intermediary_hops += 1
                        first_out_ts, _, out_id = subsequent_outs[0]
                        delta_sec = (first_out_ts - in_ts).total_seconds()
                        if delta_sec <= self.rapid_hop_seconds:
                            rapid_hop_count += 1
                            minutes = int(delta_sec // 60)
                            positive_factors.append(
                                f"Rapid pass-through in '{acc}': funds transferred out {minutes}m "
                                f"after arrival ({in_id} -> {out_id})."
                            )

            rapid_movement_ratio = (
                rapid_hop_count / max(1, total_intermediary_hops)
                if total_intermediary_hops > 0
                else 0.0
            )

            # 2. Amount deviation relative to baseline median
            case_amounts = [int(tx.get("amount_paise", 0)) for tx in case_txs if int(tx.get("amount_paise", 0)) > 0]
            mean_case_amt = sum(case_amounts) / len(case_amounts) if case_amounts else 0
            amount_deviation_ratio = (
                round(mean_case_amt / max(1, baseline_median_paise), 2)
                if baseline_median_paise > 0
                else 1.0
            )

            # 3. Intermediary drain rate
            total_interm_in = sum(sum(amt for _, amt, _ in inflows[acc]) for acc in intermediary_accounts)
            total_interm_out = sum(sum(amt for _, amt, _ in outflows[acc]) for acc in intermediary_accounts)
            drain_rate = (
                min(1.0, total_interm_out / total_interm_in)
                if total_interm_in > 0
                else 0.0
            )

            # Compute B subscore (normalized 0 to 100)
            rapid_pts = rapid_movement_ratio * 40.0
            amount_pts = min(35.0, max(0.0, (amount_deviation_ratio - 1.0) * 7.0))
            drain_pts = drain_rate * 25.0

            b_subfactors = {
                "rapid_movement_pts": round(rapid_pts, 2),
                "amount_deviation_pts": round(amount_pts, 2),
                "drain_pts": round(drain_pts, 2),
            }
            raw_b = rapid_pts + amount_pts + drain_pts
            b_score = round(min(100.0, max(0.0, raw_b)), 2)
            b_available = True
            b_reason = (
                f"Rapid movement ratio: {rapid_movement_ratio:.1%}, "
                f"Amount deviation: {amount_deviation_ratio:.1f}x baseline median, "
                f"Intermediary drain rate: {drain_rate:.1%}."
            )

            if rapid_movement_ratio == 0.0 and total_intermediary_hops > 0:
                mitigating_factors.append("No rapid (<2h) pass-through detected in intermediary accounts.")
            if amount_deviation_ratio <= 1.0:
                mitigating_factors.append("Average case transaction size is within ordinary ledger baseline.")

        # ==============================================================================
        # Component T: Transaction-Trail Evidence
        # ==============================================================================
        t_subfactors: Dict[str, float] = {}
        if len(case_txs) == 0:
            t_available = False
            t_score = None
            t_reason = "No transaction trail available for graph traversal."
            graph_depth = 0
            fan_out_degree = 0
            has_cash_withdrawal = False
        else:
            # Build directed graph of case transfers
            out_neighbors: Dict[str, Set[str]] = {}
            for tx in case_txs:
                fa = str(tx.get("from_account", "")).strip()
                ta = str(tx.get("to_account", "")).strip()
                out_neighbors.setdefault(fa, set()).add(ta)

            # Max fan-out among internal accounts
            fan_out_degree = 0
            for acc, neighbors in out_neighbors.items():
                if not acc.startswith(EXTERNAL_ACCOUNT_PREFIX):
                    fan_out_degree = max(fan_out_degree, len(neighbors))

            # Approximate graph depth (longest simple path length via DAG traversal)
            # Find source node(s): nodes with no incoming transfers in case_txs
            in_degrees: Dict[str, int] = {}
            all_trail_nodes: Set[str] = set()
            for tx in case_txs:
                fa = str(tx.get("from_account", "")).strip()
                ta = str(tx.get("to_account", "")).strip()
                all_trail_nodes.add(fa)
                all_trail_nodes.add(ta)
                in_degrees[ta] = in_degrees.get(ta, 0) + 1
                in_degrees.setdefault(fa, 0)

            sources = [node for node in all_trail_nodes if in_degrees.get(node, 0) == 0]
            if not sources:
                sources = list(all_trail_nodes)[:1]

            # Longest path via BFS/DFS from sources
            def get_max_depth(current_node: str, visited: Set[str]) -> int:
                max_d = 0
                for nxt in out_neighbors.get(current_node, set()):
                    if nxt not in visited:
                        d = 1 + get_max_depth(nxt, visited.union({nxt}))
                        max_d = max(max_d, d)
                return max_d

            graph_depth = max(get_max_depth(s, {s}) for s in sources) if sources else 0

            # Check cash exit / withdrawal
            withdrawal_txs = [
                str(tx.get("transaction_id", "")).strip()
                for tx in case_txs
                if str(tx.get("to_account", "")).strip().startswith("EXT_CASH")
                or str(tx.get("transaction_type", "")).strip().lower() == "withdrawal"
            ]
            has_cash_withdrawal = len(withdrawal_txs) > 0

            # Points calculation for T
            if graph_depth == 1:
                depth_pts = 15.0
            elif graph_depth == 2:
                depth_pts = 35.0
            elif graph_depth >= 3:
                depth_pts = 50.0
            else:
                depth_pts = 0.0

            if fan_out_degree <= 1:
                fan_out_pts = 5.0
            elif fan_out_degree == 2:
                fan_out_pts = 15.0
            else:
                fan_out_pts = 30.0

            withdrawal_pts = 20.0 if has_cash_withdrawal else 0.0

            t_subfactors = {
                "graph_depth_pts": depth_pts,
                "fan_out_pts": fan_out_pts,
                "withdrawal_pts": withdrawal_pts,
            }
            raw_t = depth_pts + fan_out_pts + withdrawal_pts
            t_score = round(min(100.0, max(0.0, raw_t)), 2)
            t_available = True
            t_reason = (
                f"Graph depth: {graph_depth} hops, "
                f"Fan-out degree: {fan_out_degree}, "
                f"Cash exit present: {has_cash_withdrawal}."
            )

            if graph_depth >= 3:
                positive_factors.append(f"Extended multi-hop layering ({graph_depth} sequential hops in trail).")
            elif graph_depth == 1:
                mitigating_factors.append("Direct single-hop transfer without downstream layering.")

            if fan_out_degree >= 2:
                positive_factors.append(f"Structuring / fan-out observed (account disbursed to {fan_out_degree} counterparties).")
            else:
                mitigating_factors.append("Linear transfer trail without split disbursements.")

            if has_cash_withdrawal:
                positive_factors.append(f"Cash withdrawal identified ({', '.join(withdrawal_txs)}), interrupting digital tracing.")

        # ==============================================================================
        # Component H: Historical / Contextual Evidence
        # ==============================================================================
        h_subfactors: Dict[str, float] = {}
        if reported_amount_paise <= 0 and len(case_txs) == 0:
            h_available = False
            h_score = None
            h_reason = "No reported amount or case transactions to evaluate historical context."
            suspected_status_ratio = 0.0
        else:
            suspected_txs = [
                tx for tx in case_txs
                if "suspected" in str(tx.get("evidence_status", "")).lower()
            ]
            suspected_status_ratio = (
                len(suspected_txs) / len(case_txs)
                if len(case_txs) > 0
                else 1.0  # If case filed with reported amount but no txs tagged yet
            )

            # Suspected status points (up to 50 pts)
            suspected_pts = suspected_status_ratio * 50.0

            # Loss scale points normalized against ₹200,000 (20,000,000 paise) (up to 50 pts)
            amount_scale_pts = min(50.0, (reported_amount_paise / 20000000.0) * 50.0)

            h_subfactors = {
                "suspected_status_pts": round(suspected_pts, 2),
                "amount_scale_pts": round(amount_scale_pts, 2),
            }
            raw_h = suspected_pts + amount_scale_pts
            h_score = round(min(100.0, max(0.0, raw_h)), 2)
            h_available = True
            h_reason = (
                f"Suspected status ratio: {suspected_status_ratio:.1%}, "
                f"Reported loss scale: ₹{reported_amount_paise / 100:,.2f}."
            )

            if suspected_status_ratio >= 0.80:
                positive_factors.append(f"High evidence concordance ({suspected_status_ratio:.0%} transactions flagged suspected fraud).")
            if reported_amount_paise >= 15000000:
                positive_factors.append(f"High reported loss scale (₹{reported_amount_paise / 100:,.2f}).")

        return CaseFeatures(
            case_id=case_id,
            reported_date=rep_date,
            reported_amount_paise=reported_amount_paise,
            rapid_movement_ratio=rapid_movement_ratio,
            amount_deviation_ratio=amount_deviation_ratio,
            drain_rate=drain_rate,
            b_score=b_score,
            b_available=b_available,
            b_reason=b_reason,
            b_subfactors=b_subfactors,
            graph_depth=graph_depth,
            fan_out_degree=fan_out_degree,
            has_cash_withdrawal=has_cash_withdrawal,
            trail_transaction_count=len(case_txs),
            t_score=t_score,
            t_available=t_available,
            t_reason=t_reason,
            t_subfactors=t_subfactors,
            suspected_status_ratio=suspected_status_ratio,
            has_incomplete_history=has_incomplete_history,
            incomplete_account_count=len(incomplete_accounts),
            h_score=h_score,
            h_available=h_available,
            h_reason=h_reason,
            h_subfactors=h_subfactors,
            supporting_transaction_ids=supporting_tx_ids,
            supporting_account_ids=supporting_acc_ids,
            positive_factors=positive_factors,
            mitigating_factors=mitigating_factors,
            data_quality_warnings=warnings,
        )


MULE_FEATURE_NAMES = [
    "rapid_pass_through_ratio",
    "drain_rate",
    "amount_deviation_ratio",
    "fan_out_degree",
    "fan_in_degree",
    "cash_exit_ratio",
    "clean_balance_ratio",
    "merchant_settlement_ratio",
    "inbound_velocity",
    "has_incomplete_history",
]


@dataclass
class AccountBehaviouralFeatures:
    """Interpretable behavioural feature set for an account within a fraud case or investigation window.
    
    All features are derived deterministically from visible ledger and account records,
    without referencing ground truth or hidden lot allocations.
    """
    account_id: str
    case_id: str
    rapid_pass_through_ratio: float
    drain_rate: float
    amount_deviation_ratio: float
    fan_out_degree: float
    fan_in_degree: float
    cash_exit_ratio: float
    clean_balance_ratio: float
    merchant_settlement_ratio: float
    inbound_velocity: float
    has_incomplete_history: float

    def to_dict(self) -> Dict[str, float]:
        return {
            "rapid_pass_through_ratio": self.rapid_pass_through_ratio,
            "drain_rate": self.drain_rate,
            "amount_deviation_ratio": self.amount_deviation_ratio,
            "fan_out_degree": self.fan_out_degree,
            "fan_in_degree": self.fan_in_degree,
            "cash_exit_ratio": self.cash_exit_ratio,
            "clean_balance_ratio": self.clean_balance_ratio,
            "merchant_settlement_ratio": self.merchant_settlement_ratio,
            "inbound_velocity": self.inbound_velocity,
            "has_incomplete_history": self.has_incomplete_history,
        }

    def to_feature_vector(self) -> List[float]:
        return [
            self.rapid_pass_through_ratio,
            self.drain_rate,
            self.amount_deviation_ratio,
            self.fan_out_degree,
            self.fan_in_degree,
            self.cash_exit_ratio,
            self.clean_balance_ratio,
            self.merchant_settlement_ratio,
            self.inbound_velocity,
            self.has_incomplete_history,
        ]


class AccountFeatureExtractor:
    """Extracts verifiable account-level behavioural features from ledgers and account histories."""

    def __init__(
        self,
        rapid_hop_seconds: int = 7200,
        baseline_median_default_paise: int = 1_000_000,
    ):
        self.rapid_hop_seconds = rapid_hop_seconds
        self.baseline_median_default_paise = baseline_median_default_paise

    def extract_account_features(
        self,
        account_id: str,
        case_id: str,
        transactions: List[Dict[str, Any]] | pd.DataFrame,
        accounts: List[Dict[str, Any]] | pd.DataFrame,
        baseline_median_paise: Optional[int] = None,
    ) -> AccountBehaviouralFeatures:
        """Extract features for a specific account within the scope of a case.
        
        Zero feature is derived from ground truth.
        """
        # 1. Normalize accounts
        acc_dict: Dict[str, Any] = {}
        if isinstance(accounts, pd.DataFrame):
            acc_list = accounts.to_dict(orient="records")
        else:
            acc_list = accounts
        for a in acc_list:
            aid = str(a.get("account_id", "")).strip()
            if aid:
                acc_dict[aid] = a

        acc_meta = acc_dict.get(account_id, {})
        opening_bal = int(acc_meta.get("opening_balance_paise", 0))
        history_complete = bool(acc_meta.get("history_complete", True))

        # 2. Normalize transactions
        if isinstance(transactions, pd.DataFrame):
            tx_list = transactions.to_dict(orient="records")
        else:
            tx_list = transactions

        # Filter transactions matching this case (or account if case_id empty)
        case_id_clean = str(case_id).strip()
        if case_id_clean:
            relevant_txs = [t for t in tx_list if str(t.get("case_id", "")).strip() == case_id_clean]
        else:
            relevant_txs = [
                t for t in tx_list
                if str(t.get("from_account", "")).strip() == account_id
                or str(t.get("to_account", "")).strip() == account_id
            ]

        # 3. Partition into inflows and outflows for account_id
        inflows: List[Tuple[datetime.datetime, int, str]] = []
        outflows: List[Tuple[datetime.datetime, int, str]] = []

        for t in relevant_txs:
            fa = str(t.get("from_account", "")).strip()
            ta = str(t.get("to_account", "")).strip()
            amt = int(t.get("amount_paise", 0))
            ts_str = str(t.get("timestamp", "")).strip()
            if not ts_str:
                continue
            try:
                ts = _parse_iso_timestamp(ts_str)
            except Exception:
                continue

            if ta == account_id:
                inflows.append((ts, amt, fa))
            if fa == account_id:
                outflows.append((ts, amt, ta))

        total_in = sum(amt for _, amt, _ in inflows)
        total_out = sum(amt for _, amt, _ in outflows)

        # Baseline median
        eff_baseline = baseline_median_paise or self.baseline_median_default_paise

        # 1. Rapid pass-through ratio
        rapid_count = 0
        total_in_count = len(inflows)
        for in_ts, in_amt, _ in inflows:
            subsequent = [o for o in outflows if o[0] >= in_ts]
            if subsequent:
                delta = (subsequent[0][0] - in_ts).total_seconds()
                if delta <= self.rapid_hop_seconds:
                    rapid_count += 1
        rapid_ratio = (rapid_count / max(1, total_in_count)) if total_in_count > 0 else 0.0

        # 2. Drain rate
        drain_rate = min(1.0, total_out / max(1, total_in)) if total_in > 0 else 0.0

        # 3. Amount deviation ratio
        all_amts = [amt for _, amt, _ in inflows] + [amt for _, amt, _ in outflows]
        mean_amt = (sum(all_amts) / len(all_amts)) if all_amts else 0.0
        amt_dev = round(mean_amt / max(1, eff_baseline), 2)

        # 4. Fan-out degree (distinct destinations)
        dest_set = set(ta for _, _, ta in outflows if not ta.startswith(EXTERNAL_ACCOUNT_PREFIX))
        fan_out = float(len(dest_set))

        # 5. Fan-in degree (distinct sources)
        src_set = set(fa for _, _, fa in inflows if not fa.startswith(EXTERNAL_ACCOUNT_PREFIX))
        fan_in = float(len(src_set))

        # 6. Cash exit ratio
        cash_out = sum(
            amt for _, amt, ta in outflows
            if ta.startswith("EXT_CASH") or "crypto" in ta.lower() or "atm" in ta.lower()
        )
        cash_ratio = (cash_out / max(1, total_out)) if total_out > 0 else 0.0

        # 7. Clean balance ratio
        clean_ratio = opening_bal / max(1, opening_bal + total_in)

        # 8. Merchant settlement ratio
        merch_out = sum(
            amt for _, amt, ta in outflows
            if "merch" in ta.lower() or "corp" in ta.lower() or "salary" in ta.lower()
        )
        merch_ratio = (merch_out / max(1, total_out)) if total_out > 0 else 0.0

        # 9. Inbound velocity
        inbound_velocity = min(50.0, total_in / max(100_000, opening_bal))

        # 10. Has incomplete history
        incomplete_hist = 0.0 if history_complete else 1.0

        return AccountBehaviouralFeatures(
            account_id=account_id,
            case_id=case_id_clean,
            rapid_pass_through_ratio=round(rapid_ratio, 4),
            drain_rate=round(drain_rate, 4),
            amount_deviation_ratio=round(amt_dev, 4),
            fan_out_degree=fan_out,
            fan_in_degree=fan_in,
            cash_exit_ratio=round(cash_ratio, 4),
            clean_balance_ratio=round(clean_ratio, 4),
            merchant_settlement_ratio=round(merch_ratio, 4),
            inbound_velocity=round(inbound_velocity, 4),
            has_incomplete_history=incomplete_hist,
        )

    def extract_case_accounts_features(
        self,
        case_id: str,
        transactions: List[Dict[str, Any]] | pd.DataFrame,
        accounts: List[Dict[str, Any]] | pd.DataFrame,
        baseline_median_paise: Optional[int] = None,
    ) -> Dict[str, AccountBehaviouralFeatures]:
        """Extract features for all internal accounts involved in a case trail."""
        case_id_clean = str(case_id).strip()
        if isinstance(transactions, pd.DataFrame):
            tx_list = transactions.to_dict(orient="records")
        else:
            tx_list = transactions

        involved_accounts: Set[str] = set()
        for t in tx_list:
            if str(t.get("case_id", "")).strip() == case_id_clean:
                fa = str(t.get("from_account", "")).strip()
                ta = str(t.get("to_account", "")).strip()
                if fa and not fa.startswith(EXTERNAL_ACCOUNT_PREFIX):
                    involved_accounts.add(fa)
                if ta and not ta.startswith(EXTERNAL_ACCOUNT_PREFIX):
                    involved_accounts.add(ta)

        results: Dict[str, AccountBehaviouralFeatures] = {}
        for aid in sorted(involved_accounts):
            results[aid] = self.extract_account_features(
                account_id=aid,
                case_id=case_id_clean,
                transactions=tx_list,
                accounts=accounts,
                baseline_median_paise=baseline_median_paise,
            )
        return results
