"""Smart-Freeze Elliptic Bitcoin Dataset Adapter.

Loads and normalizes the Elliptic cryptocurrency transaction graph benchmark.
Treats Elliptic strictly as a cryptocurrency graph dataset, preserving original
transaction IDs, directed edges, and labels as separate structures.
Does NOT fabricate INR balances, bank account ownership, or source-lot recoverability.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
import networkx as nx
import pandas as pd

from pipeline.schemas import (
    ELLIPTIC_CLASS_LABELS,
    ELLIPTIC_CLASSES_COLUMNS,
    ELLIPTIC_EDGELIST_COLUMNS,
)
from pipeline.validation import validate_elliptic_dataset


@dataclass(frozen=True)
class EllipticDatasetStatus:
    is_available: bool
    classes_present: bool
    edges_present: bool
    features_present: bool
    message: str


class EllipticAdapter:
    """Adapter for Elliptic Bitcoin transaction graph benchmark."""

    def __init__(self, dataset_dir: Path | str):
        self.dataset_dir = Path(dataset_dir)
        self.classes_path = self.dataset_dir / "elliptic_txs_classes.csv"
        self.edgelist_path = self.dataset_dir / "elliptic_txs_edgelist.csv"
        self.features_path = self.dataset_dir / "elliptic_txs_features.csv"

    def check_availability(self) -> EllipticDatasetStatus:
        """Inspect file availability without loading data."""
        c_ok = self.classes_path.exists()
        e_ok = self.edgelist_path.exists()
        f_ok = self.features_path.exists()

        if c_ok and e_ok:
            msg = "Elliptic dataset available (classes and edgelist detected)."
            if not f_ok:
                msg += " Optional features file is missing."
            return EllipticDatasetStatus(
                is_available=True,
                classes_present=c_ok,
                edges_present=e_ok,
                features_present=f_ok,
                message=msg,
            )
        else:
            return EllipticDatasetStatus(
                is_available=False,
                classes_present=c_ok,
                edges_present=e_ok,
                features_present=f_ok,
                message=(
                    f"Elliptic dataset missing at '{self.dataset_dir}'. "
                    "Skipping optional cryptocurrency benchmark."
                ),
            )

    def load_classes(self, limit: Optional[int] = None) -> pd.DataFrame:
        """Load transaction classes keeping original labels and adding label documentation."""
        if not self.classes_path.exists():
            raise FileNotFoundError(
                f"Elliptic classes file not found at: {self.classes_path}"
            )

        df = pd.read_csv(self.classes_path, nrows=limit)
        df["txId"] = df["txId"].astype("int64")
        df["class"] = df["class"].astype(str)
        df["label_meaning"] = df["class"].map(ELLIPTIC_CLASS_LABELS).fillna("unknown")
        return df

    def load_edges(self, limit: Optional[int] = None) -> pd.DataFrame:
        """Load directed transaction edges (txId1 -> txId2)."""
        if not self.edgelist_path.exists():
            raise FileNotFoundError(
                f"Elliptic edgelist file not found at: {self.edgelist_path}"
            )

        df = pd.read_csv(self.edgelist_path, nrows=limit)
        df["txId1"] = df["txId1"].astype("int64")
        df["txId2"] = df["txId2"].astype("int64")
        return df

    def load_features_metadata(self, limit: Optional[int] = None) -> pd.DataFrame:
        """Load transaction ID and time step (first 2 columns of features)."""
        if not self.features_path.exists():
            raise FileNotFoundError(
                f"Elliptic features file not found at: {self.features_path}"
            )

        df = pd.read_csv(
            self.features_path,
            usecols=[0, 1],
            header=None,
            names=["txId", "time_step"],
            nrows=limit,
        )
        df["txId"] = df["txId"].astype("int64")
        df["time_step"] = df["time_step"].astype("int32")
        return df

    def build_network_graph(
        self,
        time_step: Optional[int] = None,
        max_edges: Optional[int] = None,
    ) -> nx.DiGraph:
        """Construct directed NetworkX graph of Bitcoin transaction flows."""
        status = self.check_availability()
        if not status.is_available:
            raise FileNotFoundError(status.message)

        df_classes = self.load_classes()
        df_edges = self.load_edges(limit=max_edges)

        if time_step is not None and self.features_path.exists():
            df_time = self.load_features_metadata()
            allowed_txs = set(df_time[df_time["time_step"] == time_step]["txId"])
            df_edges = df_edges[
                df_edges["txId1"].isin(allowed_txs) & df_edges["txId2"].isin(allowed_txs)
            ]

        g = nx.DiGraph()
        class_map = dict(zip(df_classes["txId"], df_classes["class"]))
        meaning_map = dict(zip(df_classes["txId"], df_classes["label_meaning"]))

        edge_nodes = set(df_edges["txId1"]).union(set(df_edges["txId2"]))
        for node_id in edge_nodes:
            raw_c = class_map.get(node_id, "unknown")
            g.add_node(
                node_id,
                raw_class=raw_c,
                label_meaning=meaning_map.get(node_id, "unknown"),
                is_illicit=(raw_c == "1"),
            )

        for _, row in df_edges.iterrows():
            g.add_edge(int(row["txId1"]), int(row["txId2"]))

        return g
