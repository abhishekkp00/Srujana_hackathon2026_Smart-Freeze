"""Wallet B simulated adapter: PPI / e-money wallet provider rail."""

from typing import List, Optional
from traceproof.adapters.base import InstitutionAdapter
from traceproof.schemas import CanonicalFinancialEvent, FinancialEventType


class WalletBAdapter(InstitutionAdapter):
    """Adapter for Wallet B managing prepaid digital wallets, P2P transfers, and merchant checkouts."""

    def __init__(self):
        super().__init__(institution_id="WALLET_B", display_name="Wallet B (PPI / E-Money Provider)")
        self._events: List[CanonicalFinancialEvent] = []
        self._initialize_synthetic_records()

    def _initialize_synthetic_records(self) -> None:
        """Seed realistic synthetic records for Wallet B."""
        self._events = [
            # Event 1: Wallet Load corresponding to Bank A's outward transfer
            CanonicalFinancialEvent(
                event_id="EVT_WLTB_201",
                institution_id="WALLET_B",
                event_type=FinancialEventType.WALLET_LOAD,
                source_record_id="PPI_TXN_WB_5501",
                transaction_reference="REF_PAY_2026_001_HOP1",
                sender_token="TOK_BANKA_WALLETB_NODAL_POOL",
                recipient_token="TOK_WLTB_MULE_USER_01",
                amount_minor=10000000,  # ₹100,000.00
                currency="INR",
                timestamp="2026-03-01T10:04:12Z",
                event_status="SUCCESS",
                related_reference="REF_PAY_2026_001_HOP1",
                notes="Inbound nodal load credited to user prepaid wallet.",
            ),
            # Event 2: Internal P2P wallet transfer
            CanonicalFinancialEvent(
                event_id="EVT_WLTB_202",
                institution_id="WALLET_B",
                event_type=FinancialEventType.INTERNAL_WALLET_TRANSFER,
                source_record_id="PPI_TXN_WB_5502",
                transaction_reference="REF_PAY_2026_001_HOP2",
                sender_token="TOK_WLTB_MULE_USER_01",
                recipient_token="TOK_WLTB_MERCHANT_AGENT_02",
                amount_minor=7500000,  # ₹75,000.00
                currency="INR",
                timestamp="2026-03-01T10:18:45Z",
                event_status="SUCCESS",
                related_reference="REF_PAY_2026_001_HOP1",
                notes="Internal instantaneous P2P wallet transfer between users.",
            ),
            # Event 3: Platform convenience fee deducted
            CanonicalFinancialEvent(
                event_id="EVT_WLTB_203",
                institution_id="WALLET_B",
                event_type=FinancialEventType.FEE,
                source_record_id="PPI_TXN_WB_5503",
                transaction_reference="REF_FEE_WLTB_01",
                sender_token="TOK_WLTB_MERCHANT_AGENT_02",
                recipient_token="TOK_WLTB_REVENUE_POOL",
                amount_minor=15000,  # ₹150.00
                currency="INR",
                timestamp="2026-03-01T10:20:00Z",
                event_status="SUCCESS",
                related_event_ids=["EVT_WLTB_202"],
                notes="Platform processing and anti-fraud verification fee.",
            ),
            # Event 4: Merchant Payment request routed to Bank C settlement rail
            CanonicalFinancialEvent(
                event_id="EVT_WLTB_204",
                institution_id="WALLET_B",
                event_type=FinancialEventType.MERCHANT_PAYMENT,
                source_record_id="PPI_TXN_WB_5504",
                transaction_reference="REF_PAY_2026_001_HOP3",
                sender_token="TOK_WLTB_MERCHANT_AGENT_02",
                recipient_token="TOK_SETTLE_BANKC_GATEWAY_POOL",
                amount_minor=7000000,  # ₹70,000.00
                currency="INR",
                timestamp="2026-03-01T11:05:30Z",
                event_status="SUCCESS",
                related_reference="REF_PAY_2026_001_HOP2",
                notes="QR/API merchant checkout forwarded to settlement acquirer.",
            ),
            # Event 5: Partial refund reversal
            CanonicalFinancialEvent(
                event_id="EVT_WLTB_205",
                institution_id="WALLET_B",
                event_type=FinancialEventType.REFUND_REVERSAL,
                source_record_id="PPI_TXN_WB_5505",
                transaction_reference="REF_REFUND_WLTB_01",
                sender_token="TOK_SETTLE_BANKC_GATEWAY_POOL",
                recipient_token="TOK_WLTB_MERCHANT_AGENT_02",
                amount_minor=500000,  # ₹5,000.00
                currency="INR",
                timestamp="2026-03-01T12:00:00Z",
                event_status="SUCCESS",
                related_event_ids=["EVT_WLTB_204"],
                notes="Partial merchant refund reversal back to wallet.",
            ),
        ]

    def get_event_by_reference(self, reference: str) -> Optional[CanonicalFinancialEvent]:
        for ev in self._events:
            if ev.transaction_reference == reference or ev.related_reference == reference:
                return ev
        return None

    def get_events_for_token(self, token: str) -> List[CanonicalFinancialEvent]:
        return [ev for ev in self._events if ev.sender_token == token or ev.recipient_token == token]
