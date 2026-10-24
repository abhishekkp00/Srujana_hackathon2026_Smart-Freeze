"""FairHold Directed Transaction Graph Engine.

Constructs and summarizes a directed multigraph (NetworkX MultiDiGraph) representing
inter-account fund flows. Preserves transaction provenance, multiple transfers
between the same counterparties, and strict boundaries between internal accounts
and external counterparties.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, Tuple
import networkx as nx
import pandas as pd

from engine.models import GraphSummary
from pipeline.schemas import EXTERNAL_ACCOUNT_PREFIX


class TransactionGraphEngine:
    """Constructs and analyzes the directed multi-graph of inter-account transfers."""

    @staticmethod
    def build_graph(
        accounts: List[Dict[str, Any]] | pd.DataFrame,
        transactions: List[Dict[str, Any]] | pd.DataFrame,
        final_balances: Optional[Dict[str, int]] = None,
    ) -> nx.MultiDiGraph:
        """Construct directed multigraph where internal accounts are nodes and transfers are edges.

        Args:
            accounts: Account records.
            transactions: Chronologically ordered transaction records.
            final_balances: Optional mapping of account_id to final balance in paise.
        """
        if isinstance(accounts, pd.DataFrame):
            acc_list = accounts.to_dict(orient="records")
        else:
            acc_list = accounts

        if isinstance(transactions, pd.DataFrame):
            tx_list = transactions.to_dict(orient="records")
        else:
            tx_list = transactions

        g = nx.MultiDiGraph()

        # 1. Add internal account nodes with metadata
        for acc in acc_list:
            acc_id = str(acc["account_id"]).strip()
            opening = int(acc["opening_balance_paise"])
            hist_complete = bool(acc.get("history_complete", True))
            acc_type = str(acc.get("account_type", "savings")).strip()

            final_bal = final_balances.get(acc_id, opening) if final_balances else opening

            g.add_node(
                acc_id,
                account_type=acc_type,
                opening_balance_paise=opening,
                final_balance_paise=final_bal,
                history_complete=hist_complete,
                external_deposits_paise=0,
                external_withdrawals_paise=0,
                internal_inflow_paise=0,
                internal_outflow_paise=0,
            )

        internal_nodes = set(g.nodes)

        # 2. Add edges for internal transfers; record external flows on internal nodes
        for tx in tx_list:
            tx_id = str(tx["transaction_id"]).strip()
            ts = str(tx["timestamp"]).strip()
            from_acc = str(tx["from_account"]).strip()
            to_acc = str(tx["to_account"]).strip()
            amount = int(tx["amount_paise"])
            tx_type = str(tx.get("transaction_type", "transfer")).strip()
            case_id = str(tx.get("case_id", "") or "").strip()
            evidence_status = str(tx.get("evidence_status", "unflagged")).strip()

            is_from_ext = from_acc.startswith(EXTERNAL_ACCOUNT_PREFIX)
            is_to_ext = to_acc.startswith(EXTERNAL_ACCOUNT_PREFIX)

            # External deposit: update node attribute on internal destination
            if is_from_ext and not is_to_ext:
                if to_acc in g.nodes:
                    g.nodes[to_acc]["external_deposits_paise"] += amount

            # External withdrawal: update node attribute on internal source
            elif not is_from_ext and is_to_ext:
                if from_acc in g.nodes:
                    g.nodes[from_acc]["external_withdrawals_paise"] += amount

            # Internal transfer: directed edge between internal accounts
            elif not is_from_ext and not is_to_ext:
                if from_acc in internal_nodes and to_acc in internal_nodes:
                    g.add_edge(
                        from_acc,
                        to_acc,
                        key=tx_id,
                        transaction_id=tx_id,
                        timestamp=ts,
                        amount_paise=amount,
                        transaction_type=tx_type,
                        case_id=case_id,
                        evidence_status=evidence_status,
                    )
                    g.nodes[from_acc]["internal_outflow_paise"] += amount
                    g.nodes[to_acc]["internal_inflow_paise"] += amount

        return g

    @staticmethod
    def summarize_graph(graph: nx.MultiDiGraph) -> GraphSummary:
        """Generate descriptive topological statistics of the transaction graph."""
        node_count = graph.number_of_nodes()
        edge_count = graph.number_of_edges()

        # Weakly connected components on internal accounts
        if node_count > 0:
            num_wcc = nx.number_weakly_connected_components(graph)
        else:
            num_wcc = 0

        # Isolated nodes (no incoming or outgoing internal transfers)
        isolated = [
            node for node, degree in graph.degree() if degree == 0
        ]

        # Top senders and receivers by volume (paise)
        senders_by_vol = sorted(
            [
                {"account_id": n, "outflow_paise": graph.nodes[n].get("internal_outflow_paise", 0)}
                for n in graph.nodes
                if graph.nodes[n].get("internal_outflow_paise", 0) > 0
            ],
            key=lambda x: x["outflow_paise"],
            reverse=True,
        )

        receivers_by_vol = sorted(
            [
                {"account_id": n, "inflow_paise": graph.nodes[n].get("internal_inflow_paise", 0)}
                for n in graph.nodes
                if graph.nodes[n].get("internal_inflow_paise", 0) > 0
            ],
            key=lambda x: x["inflow_paise"],
            reverse=True,
        )

        # Top senders and receivers by count
        senders_by_count = sorted(
            [
                {"account_id": n, "out_degree": graph.out_degree(n)}
                for n in graph.nodes
                if graph.out_degree(n) > 0
            ],
            key=lambda x: x["out_degree"],
            reverse=True,
        )

        receivers_by_count = sorted(
            [
                {"account_id": n, "in_degree": graph.in_degree(n)}
                for n in graph.nodes
                if graph.in_degree(n) > 0
            ],
            key=lambda x: x["in_degree"],
            reverse=True,
        )

        warnings: List[str] = []
        incomplete_accounts = [
            n for n in graph.nodes if not graph.nodes[n].get("history_complete", True)
        ]
        if incomplete_accounts:
            warnings.append(
                f"Graph contains {len(incomplete_accounts)} account(s) with incomplete statement histories: "
                f"{incomplete_accounts}"
            )

        return GraphSummary(
            internal_account_nodes=node_count,
            internal_transfer_edges=edge_count,
            weakly_connected_components=num_wcc,
            isolated_accounts=sorted(isolated),
            top_senders_by_volume=senders_by_vol[:5],
            top_receivers_by_volume=receivers_by_vol[:5],
            top_senders_by_count=senders_by_count[:5],
            top_receivers_by_count=receivers_by_count[:5],
            warnings=warnings,
        )

    @staticmethod
    def serialize_to_dict(graph: nx.MultiDiGraph) -> Dict[str, Any]:
        """Serialize graph nodes and edges to a documented JSON-compatible dictionary."""
        nodes_data = []
        for n, attrs in graph.nodes(data=True):
            node_dict = {"account_id": n}
            node_dict.update(attrs)
            nodes_data.append(node_dict)

        edges_data = []
        for u, v, key, attrs in graph.edges(data=True, keys=True):
            edge_dict = {
                "from_account": u,
                "to_account": v,
                "key": key,
            }
            edge_dict.update(attrs)
            edges_data.append(edge_dict)

        return {
            "node_count": len(nodes_data),
            "edge_count": len(edges_data),
            "nodes": nodes_data,
            "edges": edges_data,
        }
