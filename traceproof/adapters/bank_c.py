"""Bank C simulated adapter: acquiring bank & settlement processor rail."""

from typing import List, Optional
from traceproof.adapters.base import InstitutionAdapter
from traceproof.schemas import CanonicalFinancialEvent, FinancialEventType


class BankCAdapter(InstitutionAdapter):
    """Adapter for Bank C / Settlement Provider managing merchant settlement allocations and cash-out boundaries."""

    def __init__(self):
        super().__init__(institution_id="BANK_C", display_name="Bank C / Settlement Rail")
        self._events: List[CanonicalFinancialEvent] = []
        self._initialize_synthetic_records()

    def _initialize_synthetic_records(self) -> None:
        """Seed realistic synthetic records for Bank C / Settlement Processor."""
        self._events = [
            # Event 1: Settlement Allocation matching Wallet B's merchant payment
            CanonicalFinancialEvent(
                event_id="EVT_BANKC_301",
                institution_id="BANK_C",
                event_type=FinancialEventType.SETTLEMENT_ALLOCATION,
                source_record_id="SETTLE_TXN_BC_8801",
                transaction_reference="REF_PAY_2026_001_HOP3",
                sender_token="TOK_SETTLE_BANKC_GATEWAY_POOL",
                recipient_token="TOK_BANKC_MERCHANT_CORP_ACCT",
                amount_minor=7000000,  # ₹70,000.00
                currency="INR",
                timestamp="2026-03-01T11:45:00Z",
                event_status="SUCCESS",
                related_reference="REF_BATCH_BANKC_7701",
                notes="Cleared settlement allocation for checkout reference.",
            ),
            # Event 2: Aggregate Settlement Batch record (economic representation vs accounting batch)
            CanonicalFinancialEvent(
                event_id="EVT_BANKC_302",
                institution_id="BANK_C",
                event_type=FinancialEventType.SETTLEMENT_BATCH,
                source_record_id="SETTLE_BATCH_BC_7701",
                transaction_reference="REF_BATCH_BANKC_7701",
                sender_token="TOK_SETTLE_BANKC_GATEWAY_POOL",
                recipient_token="TOK_BANKC_MERCHANT_CORP_ACCT",
                amount_minor=15000000,  # ₹150,000.00 batch total containing multiple txns
                currency="INR",
                timestamp="2026-03-01T12:30:00Z",
                event_status="SUCCESS",
                related_event_ids=["EVT_BANKC_301"],
                notes="Batched RTGS multilateral net settlement pool.",
            ),
            # Event 3: Cash withdrawal boundary (terminal cash-out node)
            CanonicalFinancialEvent(
                event_id="EVT_BANKC_303",
                institution_id="BANK_C",
                event_type=FinancialEventType.CASH_WITHDRAWAL,
                source_record_id="CORE_ATM_BC_8803",
                transaction_reference="REF_ATM_CASHOUT_01",
                sender_token="TOK_BANKC_MERCHANT_CORP_ACCT",
                recipient_token="EXT_ATM_CASH_OUT",
                amount_minor=5000000,  # ₹50,000.00
                currency="INR",
                timestamp="2026-03-01T13:10:00Z",
                event_status="SUCCESS",
                related_reference="REF_PAY_2026_001_HOP3",
                notes="ATM debit card instant cash withdrawal (physical boundary).",
            ),
        ]

    def get_event_by_reference(self, reference: str) -> Optional[CanonicalFinancialEvent]:
        for ev in self._events:
            if ev.transaction_reference == reference or ev.related_reference == reference:
                return ev
        return None

    def get_events_for_token(self, token: str) -> List[CanonicalFinancialEvent]:
        return [ev for ev in self._events if ev.sender_token == token or ev.recipient_token == token]
