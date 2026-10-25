"""Federated Tracing Coordinator.

Partitions accounts across 3 banks plus one wallet rail, manages public key registries,
and coordinates cross-institution Passport issuance, transmission, and verification.
Provides side-by-side federated vs centralized comparisons.
"""

from __future__ import annotations

import datetime
import hashlib
from typing import Any, Dict, List, Optional, Set, Tuple
import pandas as pd
from cryptography.hazmat.primitives.asymmetric import ed25519

from engine.fifo import FIFOTracer
from engine.libr import LIBRTracer
from engine.proportional import ProportionalTracer
from engine.tracing_models import (
    CATEGORY_LEGITIMATE,
    CATEGORY_UNKNOWN,
    make_suspected_category,
)
from federated.node import BankNode
from federated.schemas import (
    AccountEvidenceRange,
    FederatedComparisonResponse,
    Passport,
    PassportVerificationResult,
    PassportVerificationStatus,
)
from pipeline.schemas import EXTERNAL_ACCOUNT_PREFIX

FEDERATED_RAILS = ["BANK_A", "BANK_B", "BANK_C", "WALLET_W"]


class FederatedCoordinator:
    """Coordinator that partitions ledgers into 3 banks and 1 wallet rail."""

    def __init__(
        self,
        rails: Optional[List[str]] = None,
        custom_partition_map: Optional[Dict[str, str]] = None,
    ):
        self.rails = rails or list(FEDERATED_RAILS)
        self.custom_partition_map = custom_partition_map or {}

        # Instantiate BankNodes (each generating fresh Ed25519 keys at startup)
        self.nodes: Dict[str, BankNode] = {
            rail: BankNode(institution_id=rail) for rail in self.rails
        }

        # Shared public key registry
        self.public_key_registry: Dict[str, ed25519.Ed25519PublicKey] = {
            rail: node.public_key for rail, node in self.nodes.items()
        }

        # Account -> Institution partition mapping
        self.account_institution_map: Dict[str, str] = {}
        self.passports_issued: List[Passport] = []
        self.verification_results: List[PassportVerificationResult] = []

    def partition_accounts(self, accounts: List[Dict[str, Any]] | pd.DataFrame) -> Dict[str, List[str]]:
        """Partition accounts into 3 banks plus 1 wallet rail.

        Uses explicit metadata (bank_id) if present; otherwise applies a deterministic
        hash-partitioning function to ensure reproducible multi-rail distribution.
        """
        acc_list = (
            accounts.to_dict(orient="records")
            if isinstance(accounts, pd.DataFrame)
            else list(accounts)
        )

        partitions: Dict[str, List[str]] = {rail: [] for rail in self.rails}

        for acc in acc_list:
            aid = str(acc["account_id"]).strip()
            opening = int(acc.get("opening_balance_paise", 0))
            hist_comp = bool(acc.get("history_complete", True))

            assigned_rail: Optional[str] = None

            # 1. Custom partition override
            if aid in self.custom_partition_map:
                assigned_rail = self.custom_partition_map[aid]

            # 2. Bank ID in metadata
            elif "bank_id" in acc and str(acc["bank_id"]).strip().upper() in self.rails:
                assigned_rail = str(acc["bank_id"]).strip().upper()

            # 3. Wallet heuristic (e.g. PPI, aggregator, or gig workers assigned to WALLET_W)
            elif "WALLET" in aid.upper() or acc.get("account_type") in ("gig", "wallet", "ppi"):
                assigned_rail = "WALLET_W"

            # 4. Deterministic hash partition across rails
            else:
                digest = hashlib.sha256(aid.encode("utf-8")).hexdigest()
                idx = int(digest, 16) % len(self.rails)
                assigned_rail = self.rails[idx]

            self.account_institution_map[aid] = assigned_rail
            partitions[assigned_rail].append(aid)

            # Register account on the owning BankNode ONLY
            self.nodes[assigned_rail].register_account(
                account_id=aid,
                opening_balance_paise=opening,
                history_complete=hist_comp,
            )

        return partitions

    def get_institution(self, account_id: str) -> Optional[str]:
        """Look up the owning institution for an account, or None if external."""
        if account_id.startswith(EXTERNAL_ACCOUNT_PREFIX):
            return None
        return self.account_institution_map.get(account_id)

    def run_trace(
        self,
        accounts: List[Dict[str, Any]] | pd.DataFrame,
        transactions: List[Dict[str, Any]] | pd.DataFrame,
        source_transaction_id: str,
        case_id: Optional[str] = None,
        suspected_amount_paise: Optional[int] = None,
        # Fault injection controls for security testing
        fault_missing_transfers: Optional[Set[str]] = None,
        fault_tamper_transfers: Optional[Set[str]] = None,
        fault_expire_transfers: Optional[Set[str]] = None,
        fault_replay_transfers: Optional[Set[str]] = None,
        fault_wrong_key_transfers: Optional[Set[str]] = None,
    ) -> FederatedComparisonResponse:
        """Execute both centralized and federated fund tracing side-by-side."""
        acc_list = (
            accounts.to_dict(orient="records")
            if isinstance(accounts, pd.DataFrame)
            else list(accounts)
        )
        tx_list = (
            transactions.to_dict(orient="records")
            if isinstance(transactions, pd.DataFrame)
            else list(transactions)
        )

        # Sort transactions deterministically
        sorted_txs = sorted(
            tx_list,
            key=lambda t: (str(t["timestamp"]), str(t["transaction_id"])),
        )

        # Locate source transaction
        source_tx = None
        for tx in sorted_txs:
            if tx["transaction_id"] == source_transaction_id:
                source_tx = tx
                break

        if source_tx is None:
            raise KeyError(f"Source transaction '{source_transaction_id}' not found in ledger.")

        active_case_id = (case_id or source_tx.get("case_id") or "CASE_FEDERATED").strip()
        suspected_amt = int(
            suspected_amount_paise
            if suspected_amount_paise is not None
            else source_tx["amount_paise"]
        )
        sus_cat = make_suspected_category(source_transaction_id, active_case_id)

        # -------------------------------------------------------------
        # 1. Run Centralized Baseline
        # -------------------------------------------------------------
        cent_fifo_res = FIFOTracer(acc_list, sorted_txs).trace_source_transaction(
            source_transaction_id, active_case_id, suspected_amt
        )
        cent_prop_res = ProportionalTracer(acc_list, sorted_txs).trace_source_transaction(
            source_transaction_id, active_case_id, suspected_amt
        )
        cent_libr_res = LIBRTracer(acc_list, sorted_txs).trace_source_transaction(
            source_transaction_id, active_case_id, suspected_amt
        )

        centralized_results = {
            "fifo": cent_fifo_res.retained_suspected_paise,
            "proportional": cent_prop_res.retained_suspected_paise,
            "libr": cent_libr_res.retained_suspected_paise,
        }

        # -------------------------------------------------------------
        # 2. Partition Accounts Across the 4 Rails
        # -------------------------------------------------------------
        partitions = self.partition_accounts(acc_list)

        # -------------------------------------------------------------
        # 3. Run Federated Trace
        # -------------------------------------------------------------
        missing_set = fault_missing_transfers or set()
        tamper_set = fault_tamper_transfers or set()
        expire_set = fault_expire_transfers or set()
        replay_set = fault_replay_transfers or set()
        wrong_key_set = fault_wrong_key_transfers or set()

        # Temporary key for wrong key fault simulation
        adversary_priv_key = ed25519.Ed25519PrivateKey.generate()

        unverified_transfers_count = 0
        passport_records: List[Dict[str, Any]] = []

        for tx in sorted_txs:
            tid = str(tx["transaction_id"]).strip()
            ts = str(tx["timestamp"]).strip()
            fa = str(tx["from_account"]).strip()
            ta = str(tx["to_account"]).strip()
            amt = int(tx["amount_paise"])

            from_inst = self.get_institution(fa)
            to_inst = self.get_institution(ta)

            # Designated source fraud transaction
            if tid == source_transaction_id:
                if from_inst and from_inst in self.nodes:
                    self.nodes[from_inst].process_source_fraud(
                        tid, ts, fa, ta, amt, suspected_amt, active_case_id, suspected_category=sus_cat
                    )
                if to_inst and to_inst in self.nodes and to_inst != from_inst:
                    self.nodes[to_inst].process_source_fraud(
                        tid, ts, fa, ta, amt, suspected_amt, active_case_id, suspected_category=sus_cat
                    )
                continue

            # Case A: External deposit (EXT_ -> Node)
            if from_inst is None and to_inst is not None:
                # Treated as clean deposit on destination node
                node = self.nodes[to_inst]
                node.balances[ta] += amt
                node.proportional_pools[ta][CATEGORY_LEGITIMATE] = (
                    node.proportional_pools[ta].get(CATEGORY_LEGITIMATE, 0) + amt
                )
                node.libr_balances[ta] += amt
                node.fifo_lots[ta].append({
                    "lot_id": f"LOT_{tid}_EXT_DEP",
                    "amount": amt,
                    "remaining": amt,
                    "classification": CATEGORY_LEGITIMATE,
                    "is_stolen": False,
                    "timestamp": ts,
                    "seq": 2,
                })
                continue

            # Case B: External withdrawal (Node -> EXT_)
            if from_inst is not None and to_inst is None:
                node = self.nodes[from_inst]
                node._consume_local_fifo(fa, amt)
                node._consume_local_proportional(fa, amt, sus_cat)
                node._consume_local_libr(fa, amt, sus_cat)
                node.balances[fa] -= amt
                continue

            # Case C: Internal transfer on the same node
            if from_inst is not None and to_inst is not None and from_inst == to_inst:
                self.nodes[from_inst].process_internal_transfer(
                    tid, ts, fa, ta, amt, active_case_id, suspected_category=sus_cat
                )
                continue

            # Case D: Cross-institution transfer (from_inst != to_inst)
            if from_inst is not None and to_inst is not None and from_inst != to_inst:
                origin_node = self.nodes[from_inst]
                dest_node = self.nodes[to_inst]

                # Origin node signs and issues Passport
                passport = origin_node.process_outbound_transfer(
                    transaction_id=tid,
                    timestamp=ts,
                    from_account=fa,
                    to_account=ta,
                    amount_paise=amt,
                    case_id=active_case_id,
                    to_institution=to_inst,
                    suspected_category=sus_cat,
                )
                self.passports_issued.append(passport)

                # Fault injection simulations
                if tid in missing_set:
                    # Missing passport: simulate lost transmission
                    unverified_transfers_count += 1
                    dest_node.process_inbound_transfer(
                        tid, ts, ta, amt, active_case_id, passport=None, suspected_category=sus_cat
                    )
                    passport_records.append({
                        "transfer_ref": tid,
                        "status": "missing_passport",
                        "is_valid": False,
                        "from_institution": from_inst,
                        "to_institution": to_inst,
                        "amount_minor": amt,
                        "detail": "Passport was missing or dropped in transit",
                    })
                    continue

                passport_to_verify = passport

                if tid in tamper_set:
                    # Tamper with amount or segments
                    tampered_dict = passport.model_dump()
                    tampered_dict["amount_minor"] = amt + 100_000
                    passport_to_verify = Passport(**tampered_dict)

                if tid in expire_set:
                    # Expire passport: set expires_at in the past
                    exp_dict = passport.model_dump()
                    exp_dict["expires_at"] = "2020-01-01T00:00:00Z"
                    passport_to_verify = Passport(**exp_dict)

                if tid in wrong_key_set:
                    # Sign with adversary key
                    w_dict = passport.model_dump()
                    signable = passport.to_signable_bytes()
                    w_dict["signature"] = adversary_priv_key.sign(signable).hex()
                    passport_to_verify = Passport(**w_dict)

                if tid in replay_set:
                    # Simulate replay attack by pre-consuming nonce in destination replay store
                    dest_node.replay_store.add(passport.nonce)

                # Destination node verifies passport
                v_res = dest_node.verify_and_ingest_passport(
                    passport=passport_to_verify,
                    active_case_id=active_case_id,
                    public_key_registry=self.public_key_registry,
                )
                self.verification_results.append(v_res)

                if v_res.is_valid:
                    dest_node.process_inbound_transfer(
                        tid, ts, ta, amt, active_case_id, passport=passport_to_verify, suspected_category=sus_cat
                    )
                else:
                    unverified_transfers_count += 1
                    dest_node.process_inbound_transfer(
                        tid, ts, ta, amt, active_case_id, passport=None, suspected_category=sus_cat
                    )

                passport_records.append({
                    "transfer_ref": tid,
                    "status": v_res.status.value,
                    "is_valid": v_res.is_valid,
                    "from_institution": from_inst,
                    "to_institution": to_inst,
                    "amount_minor": amt,
                    "detail": v_res.detail,
                    "signature_verified": v_res.is_valid,
                })

        # -------------------------------------------------------------
        # 4. Aggregate Federated Results across all Nodes
        # -------------------------------------------------------------
        fed_fifo: Dict[str, int] = {}
        fed_prop: Dict[str, int] = {}
        fed_libr: Dict[str, int] = {}
        all_account_ranges: Dict[str, AccountEvidenceRange] = {}

        for rail, node in self.nodes.items():
            node_ret = node.get_retained_suspected()
            fed_fifo.update(node_ret["fifo"])
            fed_prop.update(node_ret["proportional"])
            fed_libr.update(node_ret["libr"])
            all_account_ranges.update(node.get_account_ranges())

        federated_results = {
            "fifo": fed_fifo,
            "proportional": fed_prop,
            "libr": fed_libr,
        }

        # Check equality between centralized and federated
        methods_match = {
            "fifo": (centralized_results["fifo"] == federated_results["fifo"]),
            "proportional": (centralized_results["proportional"] == federated_results["proportional"]),
            "libr": (centralized_results["libr"] == federated_results["libr"]),
        }

        return FederatedComparisonResponse(
            case_id=active_case_id,
            institutions=self.rails,
            account_partitions=partitions,
            centralized_results=centralized_results,
            federated_results=federated_results,
            methods_match=methods_match,
            passports=passport_records,
            account_ranges=all_account_ranges,
            unverified_transfers_count=unverified_transfers_count,
        )
