"""Smart-Freeze Dataset Adapters Package.

Contains dataset-specific adapters for ingestion, validation, and normalization:
- SyntheticAdapter: Smart-Freeze internal deterministic synthetic financial ledger
- EllipticAdapter: Elliptic Bitcoin transaction graph benchmark
- SynthAMLAdapter: SynthAML alerts and transactions adapter (reports missing companion)
- AMLNetAdapter: AMLNet Australian banking transaction dataset
"""

from pipeline.adapters.elliptic_adapter import EllipticAdapter
from pipeline.adapters.synthaml_adapter import AMLNetAdapter, SynthAMLAdapter
from pipeline.adapters.synthetic_adapter import SyntheticAdapter

__all__ = [
    "SyntheticAdapter",
    "EllipticAdapter",
    "SynthAMLAdapter",
    "AMLNetAdapter",
]
