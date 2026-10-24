"""FairHold SynthAML and AMLNet Dataset Adapters.

Handles external AML datasets with strict provenance tracking:
- SynthAMLAdapter: Handles synthetic_alerts.csv and explicitly checks for the
  companion synthetic_transactions.csv file. Never fabricates missing transaction journals.
- AMLNetAdapter: Handles the separate AMLNet Australian banking transaction dataset,
  preserving original fields and typologies without conflating it with SynthAML.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple
import pandas as pd

from pipeline.schemas import AMLNET_COLUMNS, SYNTHAML_ALERTS_COLUMNS
from pipeline.validation import validate_synthaml_alerts


@dataclass(frozen=True)
class SynthAMLStatus:
    alerts_present: bool
    transactions_present: bool
    is_complete: bool
    message: str


class SynthAMLAdapter:
    """Adapter for the SynthAML benchmark dataset."""

    def __init__(self, data_dir: Path | str):
        self.data_dir = Path(data_dir)
        self.alerts_path = self.data_dir / "synthetic_alerts.csv"
        self.transactions_path = self.data_dir / "synthetic_transactions.csv"

    def check_availability(self) -> SynthAMLStatus:
        """Inspect file availability and detect missing companion transaction file."""
        alerts_ok = self.alerts_path.exists()
        txns_ok = self.transactions_path.exists()

        if alerts_ok and txns_ok:
            return SynthAMLStatus(
                alerts_present=True,
                transactions_present=True,
                is_complete=True,
                message="SynthAML alerts and transactions files both available.",
            )
        elif alerts_ok and not txns_ok:
            return SynthAMLStatus(
                alerts_present=True,
                transactions_present=False,
                is_complete=False,
                message=(
                    "SynthAML partial: 'synthetic_alerts.csv' is present, but companion "
                    "'synthetic_transactions.csv' is missing. Alerts cannot be linked to transactions."
                ),
            )
        else:
            return SynthAMLStatus(
                alerts_present=False,
                transactions_present=False,
                is_complete=False,
                message=f"SynthAML dataset files not found at '{self.data_dir}'.",
            )

    def load_alerts(self, limit: Optional[int] = None) -> pd.DataFrame:
        """Load synthetic_alerts.csv preserving source schema."""
        if not self.alerts_path.exists():
            raise FileNotFoundError(f"SynthAML alerts file missing: {self.alerts_path}")

        df = pd.read_csv(self.alerts_path, nrows=limit)
        v_res = validate_synthaml_alerts(df, transactions_file_present=self.transactions_path.exists())
        if not v_res.is_valid:
            raise ValueError(f"SynthAML alerts validation failed: {v_res.errors}")

        df["AlertID"] = df["AlertID"].astype("int64")
        df["Date"] = df["Date"].astype(str)
        df["Outcome"] = df["Outcome"].astype(str)
        return df

    def load_transactions(self, limit: Optional[int] = None) -> pd.DataFrame:
        """Load companion synthetic_transactions.csv if present. Never fabricate records."""
        if not self.transactions_path.exists():
            raise FileNotFoundError(
                f"SynthAML companion transactions file not found: {self.transactions_path}. "
                "FairHold will not fabricate or invent missing transaction records."
            )
        return pd.read_csv(self.transactions_path, nrows=limit)


class AMLNetAdapter:
    """Adapter for the separate AMLNet Australian banking transaction dataset."""

    def __init__(self, file_path: Path | str):
        self.file_path = Path(file_path)

    def exists(self) -> bool:
        return self.file_path.exists()

    def load_sample(self, nrows: int = 5000) -> pd.DataFrame:
        """Load a sample of AMLNet preserving all 17 source fields."""
        if not self.file_path.exists():
            raise FileNotFoundError(f"AMLNet file not found: {self.file_path}")

        df = pd.read_csv(self.file_path, nrows=nrows)
        return df

    def stream_chunks(self, chunksize: int = 100000) -> Iterator[pd.DataFrame]:
        """Stream chunks from AMLNet without loading entire file into memory."""
        if not self.file_path.exists():
            raise FileNotFoundError(f"AMLNet file not found: {self.file_path}")

        for chunk in pd.read_csv(self.file_path, chunksize=chunksize):
            yield chunk
