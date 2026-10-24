"""Bank A simulated adapter: originating retail banking institution rail."""

from typing import List, Optional
from traceproof.adapters.base import InstitutionAdapter
from traceproof.schemas import CanonicalFinancialEvent, FinancialEventType


class BankAAdapter(InstitutionAdapter):
    """Adapter for Bank A managing retail customer deposit accounts and outward transfers."""

    def __init__(self):
        super().__init__(institution_id="BANK_A", display_name="Bank A (Retail Banking Rail)")
        self._events: List[CanonicalFinancialEvent] = []
        self._initialize_synthetic_records()

    def _initialize_synthetic_records(self) -> None:
        """Seed realistic synthetic records for Bank A."""
        self._events = [
            # Scenario 1 & 2 & 3 seed transfer: Victim -> Mule Wallet Loading
            CanonicalFinancialEvent(
                event_id="EVT_BANKA_101",
                institution_id="BANK_A",
                event_type=FinancialEventType.BANK_TRANSFER,
                source_record_id="CORE_TXN_BA_9901",
                transaction_reference="REF_PAY_2026_001_HOP1",
                sender_token="TOK_BANKA_VICTIM_ACCT_01",
                recipient_token="TOK_BANKA_WALLETB_NODAL_POOL",
                amount_minor=10000000,  # ₹100,000.00
                currency="INR",
                timestamp="2026-03-01T10:00:00Z",
                event_status="SUCCESS",
                related_reference="WALLET_LOAD_REF_WLTB_5501",
                notes="Netbanking outward NEFT transfer to PPI nodal account.",
            ),
            # Additional ordinary background transfer (unrelated customer, must not leak)
            CanonicalFinancialEvent(
                event_id="EVT_BANKA_102",
                institution_id="BANK_A",
                event_type=FinancialEventType.BANK_TRANSFER,
                source_record_id="CORE_TXN_BA_9902",
                transaction_reference="REF_ORDINARY_SALARY_01",
                sender_token="TOK_BANKA_CORP_PAYROLL",
                recipient_token="TOK_BANKA_EMP_441",
                amount_minor=4500000,  # ₹45,000.00
                currency="INR",
                timestamp="2026-03-01T08:00:00Z",
                event_status="SUCCESS",
                notes="Legitimate corporate salary credit.",
            ),
        ]

    def get_event_by_reference(self, reference: str) -> Optional[CanonicalFinancialEvent]:
        for ev in self._events:
            if ev.transaction_reference == reference or ev.related_reference == reference:
                return ev
        return None

    def get_events_for_token(self, token: str) -> List[CanonicalFinancialEvent]:
        return [ev for ev in self._events if ev.sender_token == token or ev.recipient_token == token]
