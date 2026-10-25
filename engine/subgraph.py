"""Smart-Freeze Bounded-Subgraph Extractor.

Extracts a time-respecting, hop-bounded transaction subgraph rooted at a specific
fraud source transaction. Restricts the analysis scope to:
1. Hop Limit: maximum outbound transfer steps from the fraud origin.
2. Time Window: transactions occurring strictly within [source_timestamp, source_timestamp + window].
3. Edge Cap: safety limit on total edges to prevent unbounded traversal.

Used for fast, scalable investigations on large ledgers and benchmark evaluations.
"""

from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple
import networkx as nx
import pandas as pd

from pipeline.schemas import EXTERNAL_ACCOUNT_PREFIX


@dataclass
class BoundedSubgraphResult:
    """Outcome of bounded-subgraph extraction."""
    source_transaction_id: str
    source_account: str
    source_timestamp: str
    cutoff_timestamp: Optional[str]
    max_hops: int
    time_window_hours: Optional[float]
    node_count: int
    edge_count: int
    hop_distances: Dict[str, int]
    accounts: List[Dict[str, Any]]
    transactions: List[Dict[str, Any]]
    graph: Optional[nx.MultiDiGraph] = field(default=None, repr=False)

    def to_dict(self) -> Dict[str, Any]:
        """Convert result to a JSON-serializable dictionary."""
        return {
            "source_transaction_id": self.source_transaction_id,
            "source_account": self.source_account,
            "source_timestamp": self.source_timestamp,
            "cutoff_timestamp": self.cutoff_timestamp,
            "max_hops": self.max_hops,
            "time_window_hours": self.time_window_hours,
            "node_count": self.node_count,
            "edge_count": self.edge_count,
            "hop_distances": self.hop_distances,
            "accounts_count": len(self.accounts),
            "transactions_count": len(self.transactions),
        }


class BoundedSubgraphExtractor:
    """Extracts a bounded subgraph based on hop limits and time windows."""

    @staticmethod
    def extract(
        accounts: List[Dict[str, Any]] | pd.DataFrame,
        transactions: List[Dict[str, Any]] | pd.DataFrame,
        source_transaction_id: str,
        max_hops: int = 4,
        time_window_hours: Optional[float] = None,
        max_edges: int = 1000,
        include_account_context: bool = False,
    ) -> BoundedSubgraphResult:
        """Extract a bounded subgraph rooted at source_transaction_id.

        Args:
            accounts: Account records.
            transactions: Transaction records.
            source_transaction_id: Transaction ID of the root fraud/scam transfer.
            max_hops: Maximum traversal hop depth from source (default 4).
            time_window_hours: Optional time window (in hours) following source_ts.
            max_edges: Hard cap on total edges in the extracted subgraph.
            include_account_context: Whether to include later incoming context credits.

        Returns:
            BoundedSubgraphResult containing extracted accounts, transactions, and NetworkX graph.
        """
        acc_list = (
            accounts.to_dict(orient="records")
            if isinstance(accounts, pd.DataFrame)
            else list(accounts)
        )
        tx_list = (
            transactions.to_dict(orient="records")
            if isinstance(transactions, pd.DataFrame)
            else list(transactions)
        )

        acc_map = {str(a["account_id"]).strip(): a for a in acc_list}

        # Locate source transaction
        source_tx = None
        for tx in tx_list:
            if str(tx["transaction_id"]).strip() == source_transaction_id:
                source_tx = tx
                break

        if source_tx is None:
            raise KeyError(f"Source transaction '{source_transaction_id}' not found.")

        src_from = str(source_tx["from_account"]).strip()
        src_to = str(source_tx["to_account"]).strip()
        src_ts_str = str(source_tx["timestamp"]).strip()
        source_ts = pd.to_datetime(src_ts_str, utc=True)

        cutoff_ts = None
        cutoff_ts_str = None
        if time_window_hours is not None and time_window_hours > 0:
            cutoff_ts = source_ts + pd.Timedelta(hours=time_window_hours)
            cutoff_ts_str = cutoff_ts.isoformat()

        # Build chronological transaction table with parsed datetime
        tx_df = pd.DataFrame(tx_list)
        if "_ts" not in tx_df.columns:
            tx_df["_ts"] = pd.to_datetime(tx_df["timestamp"], utc=True, errors="coerce")

        # Initial root setup
        selected_txs: Dict[str, Dict[str, Any]] = {}
        node_levels: Dict[str, int] = {
            src_from: 0,
            src_to: 1,
        }

        # Include the source transaction itself
        selected_txs[source_transaction_id] = {
            **source_tx,
            "_flow_hop": 1,
            "_linkage_basis": "SOURCE_ROOT",
        }

        # Time-respecting BFS queue: (account_id, arrival_ts, current_hop_level)
        queue: deque[Tuple[str, pd.Timestamp, int]] = deque([
            (src_to, source_ts, 1)
        ])
        visited_steps: Set[Tuple[str, int]] = set()

        while queue and len(selected_txs) < max_edges:
            current_acc, arrived_at, current_level = queue.popleft()

            step_key = (current_acc, current_level)
            if step_key in visited_steps:
                continue
            visited_steps.add(step_key)

            if current_level >= max_hops:
                continue

            # Outgoing transfers from current_acc occurring at or after arrived_at
            out_mask = (
                (tx_df["from_account"].astype(str) == current_acc)
                & tx_df["_ts"].notna()
                & (tx_df["_ts"] >= arrived_at)
            )
            if cutoff_ts is not None:
                out_mask = out_mask & (tx_df["_ts"] <= cutoff_ts)

            outgoing_rows = tx_df[out_mask].sort_values(by="_ts")

            for _, tx in outgoing_rows.iterrows():
                if len(selected_txs) >= max_edges:
                    break

                tx_id = str(tx["transaction_id"]).strip()
                dest_acc = str(tx["to_account"]).strip()
                tx_ts = tx["_ts"]
                next_level = current_level + 1

                if tx_id not in selected_txs:
                    tx_dict = tx.drop(labels=["_ts"], errors="ignore").to_dict()
                    tx_dict["_flow_hop"] = next_level
                    tx_dict["_linkage_basis"] = "CHRONOLOGICAL_FLOW"
                    selected_txs[tx_id] = tx_dict

                # Record minimum distance from source
                prev_lvl = node_levels.get(dest_acc)
                if prev_lvl is None or next_level < prev_lvl:
                    node_levels[dest_acc] = next_level

                # Continue traversal if destination is internal and within hops
                if not dest_acc.startswith(EXTERNAL_ACCOUNT_PREFIX) and next_level < max_hops:
                    queue.append((dest_acc, tx_ts, next_level))

            # Optional later credits for commingling context
            if include_account_context and len(selected_txs) < max_edges:
                ctx_mask = (
                    (tx_df["to_account"].astype(str) == current_acc)
                    & tx_df["_ts"].notna()
                    & (tx_df["_ts"] > arrived_at)
                )
                if cutoff_ts is not None:
                    ctx_mask = ctx_mask & (tx_df["_ts"] <= cutoff_ts)

                context_rows = tx_df[ctx_mask].sort_values(by="_ts")
                for _, ctx_tx in context_rows.iterrows():
                    if len(selected_txs) >= max_edges:
                        break
                    ctx_id = str(ctx_tx["transaction_id"]).strip()
                    if ctx_id in selected_txs:
                        continue
                    ctx_dict = ctx_tx.drop(labels=["_ts"], errors="ignore").to_dict()
                    ctx_dict["_flow_hop"] = None
                    ctx_dict["_linkage_basis"] = "ACCOUNT_CONTEXT"
                    selected_txs[ctx_id] = ctx_dict

                    ctx_sender = str(ctx_tx["from_account"]).strip()
                    node_levels.setdefault(ctx_sender, max(0, current_level))

        # Compile final lists
        extracted_tx_list = sorted(
            list(selected_txs.values()),
            key=lambda t: (str(t.get("timestamp", "")), str(t.get("transaction_id", ""))),
        )

        involved_account_ids = set()
        for t in extracted_tx_list:
            involved_account_ids.add(str(t["from_account"]).strip())
            involved_account_ids.add(str(t["to_account"]).strip())

        extracted_acc_list = []
        for aid in sorted(involved_account_ids):
            if aid in acc_map:
                acc_copy = dict(acc_map[aid])
                if "opening_balance_paise" not in acc_copy:
                    acc_copy["opening_balance_paise"] = acc_copy.get("current_balance_paise", 0)
                extracted_acc_list.append(acc_copy)

        # Build NetworkX MultiDiGraph
        from engine.transaction_graph import TransactionGraphEngine
        g = TransactionGraphEngine.build_graph(
            accounts=extracted_acc_list,
            transactions=extracted_tx_list,
        )

        return BoundedSubgraphResult(
            source_transaction_id=source_transaction_id,
            source_account=src_from,
            source_timestamp=src_ts_str,
            cutoff_timestamp=cutoff_ts_str,
            max_hops=max_hops,
            time_window_hours=time_window_hours,
            node_count=len(extracted_acc_list),
            edge_count=len(extracted_tx_list),
            hop_distances=node_levels,
            accounts=extracted_acc_list,
            transactions=extracted_tx_list,
            graph=g,
        )
