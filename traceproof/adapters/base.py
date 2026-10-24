"""Abstract base class for independent financial institution adapters in TraceProof."""

import time
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional

from traceproof.crypto import InstitutionKeyManager
from traceproof.schemas import (
    CanonicalFinancialEvent,
    SignedEvidenceEnvelope,
)


class AdapterTimeoutException(Exception):
    """Raised when an institution adapter simulates a network/service timeout."""
    pass


class AdapterAccessDeniedException(Exception):
    """Raised when the query exceeds the authorized case scope."""
    pass


class InstitutionAdapter(ABC):
    """Base institution adapter enforcing scoped queries and evidence envelope signing."""

    def __init__(self, institution_id: str, display_name: str):
        self.institution_id = institution_id
        self.display_name = display_name
        self.key_manager = InstitutionKeyManager.get_instance()

        # Simulated operational anomaly flags for test scenarios
        self.simulate_timeout: bool = False
        self.simulate_missing: bool = False
        self.simulate_tampered: bool = False

    @abstractmethod
    def get_event_by_reference(self, reference: str) -> Optional[CanonicalFinancialEvent]:
        """Internal repository lookup."""
        pass

    @abstractmethod
    def get_events_for_token(self, token: str) -> List[CanonicalFinancialEvent]:
        """Internal repository lookup for account/wallet token."""
        pass

    def query_by_reference(
        self,
        reference: str,
        trace_request_id: str,
        case_id: str,
    ) -> Optional[SignedEvidenceEnvelope]:
        """Scoped query for an event matching a transaction reference.
        
        Returns a signed evidence envelope or None if not found or unresolved.
        """
        if self.simulate_timeout:
            raise AdapterTimeoutException(
                f"Institution '{self.institution_id}' connection timed out after 5000ms."
            )

        if self.simulate_missing:
            return None

        event = self.get_event_by_reference(reference)
        if event is None:
            return None

        # Build approved payload dictionary (excluding internal raw DB timestamps/unscoped data)
        payload = {
            "event_id": event.event_id,
            "institution_id": event.institution_id,
            "event_type": event.event_type.value,
            "source_record_id": event.source_record_id,
            "transaction_reference": event.transaction_reference,
            "sender_token": event.sender_token,
            "recipient_token": event.recipient_token,
            "amount_minor": event.amount_minor,
            "currency": event.currency,
            "timestamp": event.timestamp,
            "event_status": event.event_status,
            "related_event_ids": event.related_event_ids,
            "related_reference": event.related_reference,
            "is_settled": event.is_settled,
            "history_complete": event.history_complete,
            "fee_minor": event.fee_minor,
        }

        envelope = self.key_manager.sign_payload(
            institution_id=self.institution_id,
            trace_request_id=trace_request_id,
            source_record_id=event.source_record_id,
            approved_payload=payload,
        )

        if self.simulate_tampered:
            # Simulate adversarial tampering in transit (modify amount without re-signing)
            tampered_payload = dict(envelope.approved_payload)
            tampered_payload["amount_minor"] = tampered_payload["amount_minor"] + 500000
            envelope.approved_payload = tampered_payload

        return envelope

    def query_forward_events(
        self,
        recipient_token: str,
        trace_request_id: str,
        case_id: str,
        after_timestamp: Optional[str] = None,
    ) -> List[SignedEvidenceEnvelope]:
        """Query subsequent forward flows from an account token within authorized scope."""
        if self.simulate_timeout:
            raise AdapterTimeoutException(
                f"Institution '{self.institution_id}' connection timed out during forward hop query."
            )

        if self.simulate_missing:
            return []

        events = self.get_events_for_token(recipient_token)
        envelopes = []

        for ev in events:
            # Only consider forward outflows from the recipient token
            if ev.sender_token == recipient_token:
                if after_timestamp and ev.timestamp < after_timestamp:
                    continue

                payload = {
                    "event_id": ev.event_id,
                    "institution_id": ev.institution_id,
                    "event_type": ev.event_type.value,
                    "source_record_id": ev.source_record_id,
                    "transaction_reference": ev.transaction_reference,
                    "sender_token": ev.sender_token,
                    "recipient_token": ev.recipient_token,
                    "amount_minor": ev.amount_minor,
                    "currency": ev.currency,
                    "timestamp": ev.timestamp,
                    "event_status": ev.event_status,
                    "related_event_ids": ev.related_event_ids,
                    "related_reference": ev.related_reference,
                    "is_settled": ev.is_settled,
                    "history_complete": ev.history_complete,
                    "fee_minor": ev.fee_minor,
                }

                env = self.key_manager.sign_payload(
                    institution_id=self.institution_id,
                    trace_request_id=trace_request_id,
                    source_record_id=ev.source_record_id,
                    approved_payload=payload,
                )
                envelopes.append(env)

        return envelopes
