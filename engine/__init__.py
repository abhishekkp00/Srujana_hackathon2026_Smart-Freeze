"""FairHold Core Engine Package.

Contains modules for ledger reconstruction, balance tracking,
transaction graph construction, and proportional fund-tracing algorithms.
"""

from engine.balances import (
    BalanceConservationError,
    BalanceReconstructionError,
    BalanceTracker,
    NegativeBalanceError,
)
from engine.fifo import FIFOTracer
from engine.ledger import LedgerReconstructionEngine
from engine.models import (
    AccountState,
    BalanceEvent,
    GraphSummary,
    LedgerValidationReport,
)
from engine.proportional import ProportionalTracer
from engine.tracing_explanations import TracingExplanationBuilder
from engine.tracing_models import (
    CATEGORY_LEGITIMATE,
    CATEGORY_UNKNOWN,
    AccountSourcePool,
    AllocationExplanation,
    FIFOAllocationExplanation,
    FIFOConsumptionEvent,
    FIFOLot,
    FIFOTraceResult,
    ProportionalTraceResult,
    TracingHop,
    make_suspected_category,
)
from engine.transaction_graph import TransactionGraphEngine

__all__ = [
    "AccountState",
    "BalanceEvent",
    "LedgerValidationReport",
    "GraphSummary",
    "BalanceTracker",
    "BalanceReconstructionError",
    "NegativeBalanceError",
    "BalanceConservationError",
    "TransactionGraphEngine",
    "LedgerReconstructionEngine",
    "CATEGORY_LEGITIMATE",
    "CATEGORY_UNKNOWN",
    "make_suspected_category",
    "AccountSourcePool",
    "TracingHop",
    "AllocationExplanation",
    "ProportionalTraceResult",
    "TracingExplanationBuilder",
    "ProportionalTracer",
    "FIFOLot",
    "FIFOConsumptionEvent",
    "FIFOAllocationExplanation",
    "FIFOTraceResult",
    "FIFOTracer",
]

