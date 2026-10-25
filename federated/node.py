"""BankNode implementation for federated multi-institution fund tracing.

Each BankNode holds ONLY its own accounts, transactions, and verified incoming passports.
Generates genuine Ed25519 keypairs at startup (non-seed derived), maintains a local replay store,
and enforces cryptographic verification, expiration, and case binding on all cross-institution passports.
"""

from __future__ import annotations

import datetime
import uuid
from typing import Any, Dict, List, Optional, Set, Tuple
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.exceptions import InvalidSignature

from engine.tracing_models import (
    CATEGORY_LEGITIMATE,
    CATEGORY_UNKNOWN,
    make_suspected_category,
)
from federated.schemas import (
    AccountEvidenceRange,
    Passport,
    PassportVerificationResult,
    PassportVerificationStatus,
)


class BankNode:
    """Simulated Financial Institution Rail Node.

    Holds exclusively local ledger state (accounts and balances belonging to this institution)
    and verified incoming passports. Generates unique Ed25519 keys at startup.
    """

    def __init__(self, institution_id: str, display_name: Optional[str] = None):
        self.institution_id = institution_id
        self.display_name = display_name or institution_id

        # Security: Generate fresh Ed25519 keypair at startup (no seed-derived keys)
        self._private_key = ed25519.Ed25519PrivateKey.generate()
        self._public_key = self._private_key.public_key()
        self.public_key_hex = self._public_key.public_bytes_raw().hex()

        # Replay store: record of consumed passport nonces
        self.replay_store: Set[str] = set()

        # Local accounts metadata: account_id -> {opening_balance_paise, history_complete}
        self.accounts: Dict[str, Dict[str, Any]] = {}

        # Local ledger balances & tracing state
        self.balances: Dict[str, int] = {}
        self.fifo_lots: Dict[str, List[Dict[str, Any]]] = {}
        self.proportional_pools: Dict[str, Dict[str, int]] = {}
        self.libr_balances: Dict[str, int] = {}
        self.libr_attributed: Dict[str, int] = {}
        self.libr_lowest: Dict[str, int] = {}

        # Uncertainty / range tracking for accounts affected by unverified inflows
        self.unverified_inflows_by_acc: Dict[str, int] = {}

        # Verified incoming passports: transfer_ref -> Passport
        self.verified_passports: Dict[str, Passport] = {}
        self.passport_verification_log: List[PassportVerificationResult] = []

    @property
    def public_key(self) -> ed25519.Ed25519PublicKey:
        """Expose public key for registration in peer verification registries."""
        return self._public_key

    def register_account(
        self,
        account_id: str,
        opening_balance_paise: int,
        history_complete: bool = True,
    ) -> None:
        """Register a local account belonging to this institution."""
        self.accounts[account_id] = {
            "opening_balance_paise": opening_balance_paise,
            "history_complete": history_complete,
        }
        self.balances[account_id] = opening_balance_paise

        # Initialize FIFO lots
        self.fifo_lots[account_id] = []
        if opening_balance_paise > 0:
            classification = CATEGORY_LEGITIMATE if history_complete else CATEGORY_UNKNOWN
            self.fifo_lots[account_id].append({
                "lot_id": f"OPENING_{account_id}",
                "amount": opening_balance_paise,
                "remaining": opening_balance_paise,
                "classification": classification,
                "is_stolen": False,
                "timestamp": "1970-01-01T00:00:00Z",
                "seq": 0,
            })

        # Initialize Proportional pools
        initial_cat = CATEGORY_LEGITIMATE if history_complete else CATEGORY_UNKNOWN
        self.proportional_pools[account_id] = {
            CATEGORY_LEGITIMATE: opening_balance_paise if initial_cat == CATEGORY_LEGITIMATE else 0,
            CATEGORY_UNKNOWN: opening_balance_paise if initial_cat == CATEGORY_UNKNOWN else 0,
        }

        # Initialize LIBR
        self.libr_balances[account_id] = opening_balance_paise
        self.libr_attributed[account_id] = 0
        self.libr_lowest[account_id] = opening_balance_paise
        self.unverified_inflows_by_acc[account_id] = 0

    def sign_passport(
        self,
        case_id: str,
        to_institution: str,
        transfer_ref: str,
        amount_minor: int,
        fifo_segments: List[Tuple[int, int]],
        proportional_stolen: int,
        libr_stolen: int,
        proportional_categories: Optional[Dict[str, int]] = None,
        expires_in_seconds: int = 3600,
        now_dt: Optional[datetime.datetime] = None,
        custom_nonce: Optional[str] = None,
    ) -> Passport:
        """Create and digitally sign an outbound Passport for a cross-institution transfer."""
        now = now_dt or datetime.datetime.now(datetime.timezone.utc)
        issued_at_str = now.isoformat()
        expires_at_str = (now + datetime.timedelta(seconds=expires_in_seconds)).isoformat()
        nonce = custom_nonce or str(uuid.uuid4())

        signable_dict = {
            "case_id": case_id,
            "from_institution": self.institution_id,
            "to_institution": to_institution,
            "transfer_ref": transfer_ref,
            "amount_minor": amount_minor,
            "nonce": nonce,
            "issued_at": issued_at_str,
            "expires_at": expires_at_str,
            "fifo_segments": fifo_segments,
            "proportional_stolen": proportional_stolen,
            "libr_stolen": libr_stolen,
        }
        if proportional_categories is not None:
            signable_dict["proportional_categories"] = proportional_categories

        passport_obj = Passport(
            case_id=case_id,
            from_institution=self.institution_id,
            to_institution=to_institution,
            transfer_ref=transfer_ref,
            amount_minor=amount_minor,
            nonce=nonce,
            issued_at=issued_at_str,
            expires_at=expires_at_str,
            signature="",
            fifo_segments=fifo_segments,
            proportional_stolen=proportional_stolen,
            libr_stolen=libr_stolen,
            proportional_categories=proportional_categories,
        )

        # Ed25519 signature over canonical signable bytes
        signable_bytes = passport_obj.to_signable_bytes()
        sig_bytes = self._private_key.sign(signable_bytes)
        passport_obj.signature = sig_bytes.hex()

        return passport_obj

    def verify_and_ingest_passport(
        self,
        passport: Passport,
        active_case_id: str,
        public_key_registry: Dict[str, ed25519.Ed25519PublicKey],
        current_time: Optional[datetime.datetime] = None,
    ) -> PassportVerificationResult:
        """Verify an incoming passport against replay, expiry, tampering, and key binding."""
        now = current_time or datetime.datetime.now(datetime.timezone.utc)
        ref = passport.transfer_ref
        from_inst = passport.from_institution
        to_inst = passport.to_institution

        # 1. Institution binding
        if to_inst != self.institution_id:
            res = PassportVerificationResult(
                is_valid=False,
                status=PassportVerificationStatus.INSTITUTION_MISMATCH,
                detail=f"Passport destination '{to_inst}' does not match recipient node '{self.institution_id}'",
                transfer_ref=ref,
                from_institution=from_inst,
                to_institution=to_inst,
            )
            self.passport_verification_log.append(res)
            return res

        # 2. Case binding
        if passport.case_id != active_case_id:
            res = PassportVerificationResult(
                is_valid=False,
                status=PassportVerificationStatus.CASE_MISMATCH,
                detail=f"Passport case '{passport.case_id}' does not match active case '{active_case_id}'",
                transfer_ref=ref,
                from_institution=from_inst,
                to_institution=to_inst,
            )
            self.passport_verification_log.append(res)
            return res

        # 3. Replay protection
        if passport.nonce in self.replay_store:
            res = PassportVerificationResult(
                is_valid=False,
                status=PassportVerificationStatus.REPLAY_DETECTED,
                detail=f"Passport nonce '{passport.nonce}' has already been consumed (replay attack)",
                transfer_ref=ref,
                from_institution=from_inst,
                to_institution=to_inst,
            )
            self.passport_verification_log.append(res)
            return res

        # 4. Expiration check
        try:
            exp_dt = datetime.datetime.fromisoformat(passport.expires_at)
            if now > exp_dt:
                res = PassportVerificationResult(
                    is_valid=False,
                    status=PassportVerificationStatus.EXPIRED,
                    detail=f"Passport expired at {passport.expires_at} (current time: {now.isoformat()})",
                    transfer_ref=ref,
                    from_institution=from_inst,
                    to_institution=to_inst,
                )
                self.passport_verification_log.append(res)
                return res
        except Exception as e:
            res = PassportVerificationResult(
                is_valid=False,
                status=PassportVerificationStatus.CORRUPTED_PAYLOAD,
                detail=f"Invalid expires_at timestamp: {e}",
                transfer_ref=ref,
                from_institution=from_inst,
                to_institution=to_inst,
            )
            self.passport_verification_log.append(res)
            return res

        # 5. Public key lookup
        sender_pub_key = public_key_registry.get(from_inst)
        if sender_pub_key is None:
            res = PassportVerificationResult(
                is_valid=False,
                status=PassportVerificationStatus.WRONG_KEY,
                detail=f"No trusted public key registered for sender institution '{from_inst}'",
                transfer_ref=ref,
                from_institution=from_inst,
                to_institution=to_inst,
            )
            self.passport_verification_log.append(res)
            return res

        # 6. Cryptographic signature verification
        try:
            signable_bytes = passport.to_signable_bytes()
            sig_bytes = bytes.fromhex(passport.signature)
            sender_pub_key.verify(sig_bytes, signable_bytes)
        except InvalidSignature:
            res = PassportVerificationResult(
                is_valid=False,
                status=PassportVerificationStatus.INVALID_SIGNATURE,
                detail="Ed25519 signature verification failed (payload tampered or wrong key)",
                transfer_ref=ref,
                from_institution=from_inst,
                to_institution=to_inst,
            )
            self.passport_verification_log.append(res)
            return res
        except Exception as e:
            res = PassportVerificationResult(
                is_valid=False,
                status=PassportVerificationStatus.CORRUPTED_PAYLOAD,
                detail=f"Signature decoding error: {e}",
                transfer_ref=ref,
                from_institution=from_inst,
                to_institution=to_inst,
            )
            self.passport_verification_log.append(res)
            return res

        # Passed all checks: record in replay store and verified passports
        self.replay_store.add(passport.nonce)
        self.verified_passports[ref] = passport

        res = PassportVerificationResult(
            is_valid=True,
            status=PassportVerificationStatus.VALID,
            detail="Passport signature and provenance verified successfully",
            transfer_ref=ref,
            from_institution=from_inst,
            to_institution=to_inst,
        )
        self.passport_verification_log.append(res)
        return res

    def process_source_fraud(
        self,
        transaction_id: str,
        timestamp: str,
        victim_account: str,
        destination_account: str,
        total_amount_paise: int,
        suspected_amount_paise: int,
        case_id: str,
        suspected_category: Optional[str] = None,
    ) -> None:
        """Process the initial fraud event starting within this node's accounts."""
        sus_cat = suspected_category or make_suspected_category(transaction_id, case_id)

        # Debit victim if local
        if victim_account in self.accounts:
            self._consume_local_fifo(victim_account, total_amount_paise)
            self._consume_local_proportional(victim_account, total_amount_paise, sus_cat)
            self._consume_local_libr(victim_account, total_amount_paise, sus_cat)
            self.balances[victim_account] -= total_amount_paise

        # Credit destination if local
        if destination_account in self.accounts:
            self.balances[destination_account] += total_amount_paise

            # FIFO credit: designated suspected lot + excess
            self.fifo_lots[destination_account].append({
                "lot_id": f"LOT_SRC_{transaction_id}",
                "amount": suspected_amount_paise,
                "remaining": suspected_amount_paise,
                "classification": sus_cat,
                "is_stolen": True,
                "timestamp": timestamp,
                "seq": 1,
            })
            excess = total_amount_paise - suspected_amount_paise
            if excess > 0:
                self.fifo_lots[destination_account].append({
                    "lot_id": f"LOT_{transaction_id}_EXCESS",
                    "amount": excess,
                    "remaining": excess,
                    "classification": CATEGORY_LEGITIMATE,
                    "is_stolen": False,
                    "timestamp": timestamp,
                    "seq": 1,
                })

            # Proportional credit
            self.proportional_pools[destination_account][sus_cat] = (
                self.proportional_pools[destination_account].get(sus_cat, 0) + suspected_amount_paise
            )
            if excess > 0:
                self.proportional_pools[destination_account][CATEGORY_LEGITIMATE] = (
                    self.proportional_pools[destination_account].get(CATEGORY_LEGITIMATE, 0) + excess
                )

            # LIBR credit
            self.libr_balances[destination_account] += total_amount_paise
            self.libr_attributed[destination_account] += suspected_amount_paise
            self.libr_lowest[destination_account] = self.libr_balances[destination_account]

    def process_outbound_transfer(
        self,
        transaction_id: str,
        timestamp: str,
        from_account: str,
        to_account: str,
        amount_paise: int,
        case_id: str,
        to_institution: str,
        suspected_category: Optional[str] = None,
    ) -> Passport:
        """Process an outbound transfer from a local account to an external/peer institution."""
        sus_cat = suspected_category or make_suspected_category("", case_id)

        # 1. FIFO Outflow: consume lots and produce ordered slices
        fifo_slices = self._consume_local_fifo(from_account, amount_paise)

        # 2. Proportional Outflow
        prop_stolen, prop_cats = self._consume_local_proportional(from_account, amount_paise, sus_cat)

        # 3. LIBR Outflow
        libr_stolen = self._consume_local_libr(from_account, amount_paise, sus_cat)

        self.balances[from_account] -= amount_paise

        # Issue and sign the Passport for the destination node
        return self.sign_passport(
            case_id=case_id,
            to_institution=to_institution,
            transfer_ref=transaction_id,
            amount_minor=amount_paise,
            fifo_segments=fifo_slices,
            proportional_stolen=prop_stolen,
            libr_stolen=libr_stolen,
            proportional_categories=prop_cats,
        )

    def process_inbound_transfer(
        self,
        transaction_id: str,
        timestamp: str,
        to_account: str,
        amount_paise: int,
        case_id: str,
        passport: Optional[Passport],
        suspected_category: Optional[str] = None,
    ) -> None:
        """Process an inbound transfer into a local account with a verified (or missing/unverified) passport."""
        sus_cat = suspected_category or make_suspected_category("", case_id)
        self.balances[to_account] += amount_paise

        is_verified = (passport is not None and passport.transfer_ref in self.verified_passports)

        if is_verified:
            # 1. FIFO: Reconstruct destination lots in the exact order of received segments
            for s_idx, (s_amt, s_stolen) in enumerate(passport.fifo_segments, start=1):
                is_stolen = (s_stolen > 0)
                classification = sus_cat if is_stolen else CATEGORY_LEGITIMATE
                self.fifo_lots[to_account].append({
                    "lot_id": f"LOT_{transaction_id}_{s_idx}",
                    "amount": s_amt,
                    "remaining": s_amt,
                    "classification": classification,
                    "is_stolen": is_stolen,
                    "timestamp": timestamp,
                    "seq": 2,
                })

            # 2. Proportional: Credit suspected category and legitimate remainder
            stolen_p = passport.proportional_stolen
            legit_p = amount_paise - stolen_p
            self.proportional_pools[to_account][sus_cat] = (
                self.proportional_pools[to_account].get(sus_cat, 0) + stolen_p
            )
            self.proportional_pools[to_account][CATEGORY_LEGITIMATE] = (
                self.proportional_pools[to_account].get(CATEGORY_LEGITIMATE, 0) + legit_p
            )

            # 3. LIBR: Update attributed suspected and intermediate balance
            self.libr_balances[to_account] += amount_paise
            if passport.libr_stolen > 0:
                self.libr_attributed[to_account] += passport.libr_stolen
                bal_after = self.libr_balances[to_account]
                if to_account not in self.libr_lowest:
                    self.libr_lowest[to_account] = bal_after
                else:
                    self.libr_lowest[to_account] = min(self.libr_lowest[to_account], bal_after)

        else:
            # MISSING / UNVERIFIED PASSPORT:
            # "Missing passport => stolen share unknown => widen the range, never fake precision."
            # FIFO: classify inflow as CATEGORY_UNKNOWN
            self.fifo_lots[to_account].append({
                "lot_id": f"LOT_{transaction_id}_UNKNOWN",
                "amount": amount_paise,
                "remaining": amount_paise,
                "classification": CATEGORY_UNKNOWN,
                "is_stolen": False,
                "timestamp": timestamp,
                "seq": 2,
            })

            # Proportional: credit to CATEGORY_UNKNOWN
            self.proportional_pools[to_account][CATEGORY_UNKNOWN] = (
                self.proportional_pools[to_account].get(CATEGORY_UNKNOWN, 0) + amount_paise
            )

            # LIBR: balance increases without confirmed suspected attribution
            self.libr_balances[to_account] += amount_paise

            # Record unverified uncertainty band for evidence-bounded range
            self.unverified_inflows_by_acc[to_account] += amount_paise

    def process_internal_transfer(
        self,
        transaction_id: str,
        timestamp: str,
        from_account: str,
        to_account: str,
        amount_paise: int,
        case_id: str,
        suspected_category: Optional[str] = None,
    ) -> None:
        """Process an internal transfer between two accounts within this same node."""
        sus_cat = suspected_category or make_suspected_category("", case_id)

        # 1. FIFO
        fifo_slices = self._consume_local_fifo(from_account, amount_paise)
        for s_idx, (s_amt, s_stolen) in enumerate(fifo_slices, start=1):
            is_stolen = (s_stolen > 0)
            classification = sus_cat if is_stolen else CATEGORY_LEGITIMATE
            self.fifo_lots[to_account].append({
                "lot_id": f"LOT_{transaction_id}_{s_idx}",
                "amount": s_amt,
                "remaining": s_amt,
                "classification": classification,
                "is_stolen": is_stolen,
                "timestamp": timestamp,
                "seq": 2,
            })

        # 2. Proportional
        prop_stolen, _ = self._consume_local_proportional(from_account, amount_paise, sus_cat)
        prop_legit = amount_paise - prop_stolen
        self.proportional_pools[to_account][sus_cat] = (
            self.proportional_pools[to_account].get(sus_cat, 0) + prop_stolen
        )
        self.proportional_pools[to_account][CATEGORY_LEGITIMATE] = (
            self.proportional_pools[to_account].get(CATEGORY_LEGITIMATE, 0) + prop_legit
        )

        # 3. LIBR
        libr_stolen = self._consume_local_libr(from_account, amount_paise, sus_cat)
        self.libr_balances[to_account] += amount_paise
        if libr_stolen > 0:
            self.libr_attributed[to_account] += libr_stolen
            bal_after = self.libr_balances[to_account]
            if to_account not in self.libr_lowest:
                self.libr_lowest[to_account] = bal_after
            else:
                self.libr_lowest[to_account] = min(self.libr_lowest[to_account], bal_after)

        self.balances[from_account] -= amount_paise
        self.balances[to_account] += amount_paise

    def _consume_local_fifo(self, account_id: str, amount_paise: int) -> List[Tuple[int, int]]:
        """Consume lots in strict FIFO order, returning ordered [(segment_amt, stolen_amt), ...]."""
        lots = sorted(
            [l for l in self.fifo_lots[account_id] if l["remaining"] > 0],
            key=lambda l: (str(l["timestamp"]), int(l["seq"]), str(l["lot_id"])),
        )
        needed = amount_paise
        slices: List[Tuple[int, int]] = []

        for l in lots:
            if needed <= 0:
                break
            rem = l["remaining"]
            if rem <= 0:
                continue
            take = min(needed, rem)
            l["remaining"] -= take
            needed -= take
            stolen_part = take if l["is_stolen"] else 0
            slices.append((take, stolen_part))

        if needed > 0:
            raise ValueError(f"Insufficient funds in account '{account_id}' for FIFO withdrawal of {amount_paise}")

        return slices

    def _consume_local_proportional(
        self,
        account_id: str,
        amount_paise: int,
        suspected_category: str,
    ) -> Tuple[int, Dict[str, int]]:
        """Proportionally allocate outgoing amount across categories using deterministic integer remainders."""
        pool = self.proportional_pools[account_id]
        total_balance = sum(pool.values())
        if amount_paise > total_balance:
            raise ValueError(f"Insufficient funds in account '{account_id}' for proportional allocation")

        base_allocations: Dict[str, int] = {}
        remainders: Dict[str, int] = {}

        for cat, cat_bal in pool.items():
            product = amount_paise * cat_bal
            base_allocations[cat] = product // total_balance
            remainders[cat] = product % total_balance

        allocated_sum = sum(base_allocations.values())
        rem_paise = amount_paise - allocated_sum

        awarded: Dict[str, int] = {cat: 0 for cat in pool}
        if rem_paise > 0:
            sorted_cats = sorted(pool.keys(), key=lambda c: (-remainders[c], c))
            for cat in sorted_cats:
                if rem_paise <= 0:
                    break
                awarded[cat] += 1
                rem_paise -= 1

        final_allocations: Dict[str, int] = {}
        for cat in pool:
            final_allocations[cat] = base_allocations[cat] + awarded[cat]
            pool[cat] -= final_allocations[cat]

        stolen_allocated = 0
        for cat, amt in final_allocations.items():
            if cat.startswith("SUSPECTED:") or cat == suspected_category:
                stolen_allocated += amt

        return stolen_allocated, final_allocations

    def _consume_local_libr(self, account_id: str, amount_paise: int, suspected_category: str) -> int:
        """Consume under Lowest Intermediate Balance Rule: clean funds absorbed first."""
        bal_before = self.libr_balances[account_id]
        if amount_paise > bal_before:
            raise ValueError(f"Insufficient funds in account '{account_id}' for LIBR withdrawal")

        attr_before = self.libr_attributed.get(account_id, 0)
        clean_available = max(0, bal_before - attr_before)
        clean_spent = min(amount_paise, clean_available)
        suspected_spent = amount_paise - clean_spent

        # Deduct from attributed
        self.libr_attributed[account_id] -= suspected_spent
        self.libr_balances[account_id] -= amount_paise
        bal_after = self.libr_balances[account_id]

        # Enforce LIBR ceiling
        if self.libr_attributed[account_id] > bal_after:
            self.libr_attributed[account_id] = bal_after

        # Update lowest intermediate
        if account_id in self.libr_lowest:
            self.libr_lowest[account_id] = min(self.libr_lowest[account_id], bal_after)
        elif attr_before > 0:
            self.libr_lowest[account_id] = bal_after

        return suspected_spent

    def get_retained_suspected(self) -> Dict[str, Dict[str, int]]:
        """Compute final retained suspected paise for all accounts on this node across all 3 methods."""
        fifo_ret: Dict[str, int] = {}
        for acc, lots in self.fifo_lots.items():
            ret = sum(l["remaining"] for l in lots if l["is_stolen"] and l["remaining"] > 0)
            if ret > 0:
                fifo_ret[acc] = ret

        prop_ret: Dict[str, int] = {}
        for acc, pool in self.proportional_pools.items():
            ret = sum(amt for cat, amt in pool.items() if cat.startswith("SUSPECTED:") and amt > 0)
            if ret > 0:
                prop_ret[acc] = ret

        libr_ret: Dict[str, int] = {}
        for acc, attr in self.libr_attributed.items():
            if attr > 0:
                libr_ret[acc] = attr

        return {
            "fifo": fifo_ret,
            "proportional": prop_ret,
            "libr": libr_ret,
        }

    def get_account_ranges(self) -> Dict[str, AccountEvidenceRange]:
        """Compute evidence-bounded uncertainty ranges for each account on this node."""
        ranges: Dict[str, AccountEvidenceRange] = {}
        retained = self.get_retained_suspected()

        for acc in self.accounts:
            fifo_val = retained["fifo"].get(acc, 0)
            prop_val = retained["proportional"].get(acc, 0)
            libr_val = retained["libr"].get(acc, 0)

            # Consensus baseline from verified methods
            vals = [fifo_val, prop_val, libr_val]
            min_confirmed = min(vals)
            max_confirmed = max(vals)

            unverified = self.unverified_inflows_by_acc.get(acc, 0)
            has_unverified = unverified > 0

            # Missing passport => widen range, never fake precision
            # Lower bound remains confirmed, upper bound expands to encompass unverified share
            ranges[acc] = AccountEvidenceRange(
                account_id=acc,
                institution_id=self.institution_id,
                min_suspected_paise=min_confirmed,
                max_suspected_paise=max_confirmed + unverified,
                widened_by_missing_paise=unverified,
                has_unverified_inflow=has_unverified,
            )

        return ranges
