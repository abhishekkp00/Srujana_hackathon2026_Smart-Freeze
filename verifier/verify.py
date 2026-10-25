"""Smart-Freeze Standalone Receipt Verifier.

Recomputes core and margin bounds from the receipt's minimal ledger slice using
engine algorithms, checks the Ed25519 digital signature and ledger slice hash,
and confirms mathematical reproducibility.

CRITICAL ARCHITECTURE CONSTRAINT:
This verifier has ZERO imports from the web application (no FastAPI, no Starlette, no app.*).
It relies solely on the core financial tracing engines, standard cryptography, and python libraries.

Governance Limitation Notice:
Cryptographic verification and hash-chaining prove algorithmic reproducibility and tamper-evident
integrity of the receipt; they do NOT prove that the underlying input ledger records, transaction
events, or external banking claims are objectively true in the real world.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional, Tuple

from cryptography.hazmat.primitives.asymmetric import ed25519

# Pure engine imports — ZERO imports from app / web framework
from engine.consensus_lien import ConsensusLienEngine, ConsensusLienResult
from engine.decision import DecisionEngine


STANDALONE_GOVERNANCE_NOTICE = (
    "NOTICE: Cryptographic verification proves algorithmic reproducibility and mathematical "
    "integrity under Smart-Freeze decision rules. It does NOT prove that the input ledger records, "
    "transaction events, or external banking claims are objectively true in the real world."
)


@dataclass
class VerificationReport:
    """Detailed verification outcome for an offline hold receipt."""
    is_valid: bool
    receipt_id: str
    case_id: str
    account_id: str
    signature_valid: bool
    slice_hash_valid: bool
    core_matches: bool
    margin_matches: bool
    recorded_core_paise: int
    recomputed_core_paise: int
    recorded_margin_paise: int
    recomputed_margin_paise: int
    recorded_per_method: Dict[str, Any]
    recomputed_per_method: Dict[str, Any]
    error_message: Optional[str] = None
    governance_notice: str = STANDALONE_GOVERNANCE_NOTICE

    def print_summary(self) -> None:
        """Print human-readable report to stdout."""
        print("=" * 72)
        print("SMART-FREEZE CRYPTOGRAPHIC RECEIPT VERIFIER")
        print("=" * 72)
        print(f"Receipt ID : {self.receipt_id}")
        print(f"Case ID    : {self.case_id}")
        print(f"Account ID : {self.account_id}")
        print("-" * 72)

        # 1. Signature
        sig_icon = "[PASS]" if self.signature_valid else "[FAIL]"
        print(f"{sig_icon} Ed25519 Digital Signature: {'VERIFIED' if self.signature_valid else 'INVALID OR FORGED'}")

        # 2. Ledger slice hash
        hash_icon = "[PASS]" if self.slice_hash_valid else "[FAIL]"
        print(f"{hash_icon} Ledger Slice SHA-256 Digest: {'INTEGRITY VERIFIED' if self.slice_hash_valid else 'MISMATCH / TAMPERED'}")

        # 3. Tracing Methods Recomputed
        print("-" * 72)
        print("RECOMPUTED TRACING & CONSENSUS METHOD BOUNDS:")
        for method, bounds in self.recomputed_per_method.items():
            print(f"  * {method.upper():12}: Lower = ₹{bounds.get('lower_paise', 0) / 100:,.2f}  |  Upper = ₹{bounds.get('upper_paise', 0) / 100:,.2f}")

        # 4. Core & Margin bounds check
        print("-" * 72)
        core_icon = "[PASS]" if self.core_matches else "[FAIL]"
        margin_icon = "[PASS]" if self.margin_matches else "[FAIL]"

        print(f"{core_icon} Core Hold Bound   : Recorded ₹{self.recorded_core_paise / 100:,.2f} | Recomputed ₹{self.recomputed_core_paise / 100:,.2f}")
        print(f"{margin_icon} Margin Hold Bound : Recorded ₹{self.recorded_margin_paise / 100:,.2f} | Recomputed ₹{self.recomputed_margin_paise / 100:,.2f}")
        print("-" * 72)

        if self.is_valid:
            print("OVERALL RESULT: [VERIFIED] All cryptographic signatures, hashes, and decision bounds MATCH.")
        else:
            print(f"OVERALL RESULT: [FAILED] {self.error_message}")

        print("\nLIMITATION & GOVERNANCE NOTICE:")
        print(self.governance_notice)
        print("=" * 72)


def canonical_json_bytes(obj: Any) -> bytes:
    """Return deterministic canonical UTF-8 JSON bytes."""
    return json.dumps(
        obj,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")


def verify_receipt_dict(receipt: Dict[str, Any]) -> VerificationReport:
    """Verify an in-memory receipt dictionary without web app dependencies."""
    receipt_id = str(receipt.get("receipt_id", "UNKNOWN"))
    case_id = str(receipt.get("case_id", "UNKNOWN"))
    account_id = str(receipt.get("account_id", "UNKNOWN"))

    rec_core = int(receipt.get("core", 0))
    rec_margin = int(receipt.get("margin", 0))
    rec_per_method = dict(receipt.get("per_method_results", {}))

    # 1. Cryptographic Signature Verification
    signature_hex = receipt.get("signature")
    public_key_hex = receipt.get("public_key")

    if not signature_hex or not public_key_hex:
        return VerificationReport(
            is_valid=False,
            receipt_id=receipt_id,
            case_id=case_id,
            account_id=account_id,
            signature_valid=False,
            slice_hash_valid=False,
            core_matches=False,
            margin_matches=False,
            recorded_core_paise=rec_core,
            recomputed_core_paise=0,
            recorded_margin_paise=rec_margin,
            recomputed_margin_paise=0,
            recorded_per_method=rec_per_method,
            recomputed_per_method={},
            error_message="Missing signature or public key in receipt.",
        )

    try:
        sig_bytes = bytes.fromhex(signature_hex)
        pub_bytes = bytes.fromhex(public_key_hex)
        pub_key = ed25519.Ed25519PublicKey.from_public_bytes(pub_bytes)

        payload_to_verify = {k: v for k, v in receipt.items() if k not in ("signature", "public_key")}
        pub_key.verify(sig_bytes, canonical_json_bytes(payload_to_verify))
        sig_valid = True
    except Exception as e:
        return VerificationReport(
            is_valid=False,
            receipt_id=receipt_id,
            case_id=case_id,
            account_id=account_id,
            signature_valid=False,
            slice_hash_valid=False,
            core_matches=False,
            margin_matches=False,
            recorded_core_paise=rec_core,
            recomputed_core_paise=0,
            recorded_margin_paise=rec_margin,
            recomputed_margin_paise=0,
            recorded_per_method=rec_per_method,
            recomputed_per_method={},
            error_message=f"Ed25519 digital signature verification failed: {e}",
        )

    # 2. Ledger Slice SHA-256 Digest Verification
    ledger_slice = receipt.get("ledger_slice", {})
    recorded_slice_hash = receipt.get("ledger_slice_hash", "")
    computed_slice_hash = hashlib.sha256(canonical_json_bytes(ledger_slice)).hexdigest()

    slice_hash_valid = (recorded_slice_hash == computed_slice_hash)
    if not slice_hash_valid:
        return VerificationReport(
            is_valid=False,
            receipt_id=receipt_id,
            case_id=case_id,
            account_id=account_id,
            signature_valid=sig_valid,
            slice_hash_valid=False,
            core_matches=False,
            margin_matches=False,
            recorded_core_paise=rec_core,
            recomputed_core_paise=0,
            recorded_margin_paise=rec_margin,
            recomputed_margin_paise=0,
            recorded_per_method=rec_per_method,
            recomputed_per_method={},
            error_message=f"Ledger slice hash mismatch: recorded '{recorded_slice_hash}', computed '{computed_slice_hash}'.",
        )

    # 3. Algorithmic Recomputation from Minimal Ledger Slice
    accounts_data = ledger_slice.get("accounts", [])
    transactions_data = ledger_slice.get("transactions", [])
    source_tx_id = receipt.get("source_transaction_id", "")

    if not accounts_data or not transactions_data:
        return VerificationReport(
            is_valid=False,
            receipt_id=receipt_id,
            case_id=case_id,
            account_id=account_id,
            signature_valid=sig_valid,
            slice_hash_valid=slice_hash_valid,
            core_matches=False,
            margin_matches=False,
            recorded_core_paise=rec_core,
            recomputed_core_paise=0,
            recorded_margin_paise=rec_margin,
            recomputed_margin_paise=0,
            recorded_per_method=rec_per_method,
            recomputed_per_method={},
            error_message="Receipt ledger slice has empty accounts or transactions.",
        )

    try:
        # Recompute Consensus Lien across methods
        lien_result: ConsensusLienResult = ConsensusLienEngine.run_all_methods(
            accounts=accounts_data,
            transactions=transactions_data,
            source_transaction_id=source_tx_id,
            source_case_id=case_id,
        )

        acc_lien = lien_result.account_liens.get(account_id)
        if acc_lien is None:
            return VerificationReport(
                is_valid=False,
                receipt_id=receipt_id,
                case_id=case_id,
                account_id=account_id,
                signature_valid=sig_valid,
                slice_hash_valid=slice_hash_valid,
                core_matches=False,
                margin_matches=False,
                recorded_core_paise=rec_core,
                recomputed_core_paise=0,
                recorded_margin_paise=rec_margin,
                recomputed_margin_paise=0,
                recorded_per_method=rec_per_method,
                recomputed_per_method={},
                error_message=f"Account '{account_id}' not found in recomputed consensus results.",
            )

        recomputed_per_method = {
            "proportional": {"lower_paise": acc_lien.proportional_paise, "upper_paise": acc_lien.proportional_paise},
            "fifo": {"lower_paise": acc_lien.fifo_paise, "upper_paise": acc_lien.fifo_paise},
            "libr": {"lower_paise": acc_lien.libr_paise, "upper_paise": acc_lien.libr_paise},
        }

        # Recompute Decision Recommendation using DecisionEngine
        policy_name = receipt.get("policy_name", "balanced")
        engine = DecisionEngine()
        case_res = engine.evaluate_case(
            case_id=case_id,
            accounts=accounts_data,
            transactions=transactions_data,
            source_transaction_id=source_tx_id,
            policy_name=policy_name,
        )

        target_rec = next((r for r in case_res.recommendations if r.account_id == account_id), None)
        if target_rec:
            recomputed_core = target_rec.core
            recomputed_margin = target_rec.margin
        else:
            # Fallback to direct raw consensus bounds
            recomputed_core = acc_lien.lower_estimate_paise
            recomputed_margin = acc_lien.disagreement_paise

    except Exception as e:
        return VerificationReport(
            is_valid=False,
            receipt_id=receipt_id,
            case_id=case_id,
            account_id=account_id,
            signature_valid=sig_valid,
            slice_hash_valid=slice_hash_valid,
            core_matches=False,
            margin_matches=False,
            recorded_core_paise=rec_core,
            recomputed_core_paise=0,
            recorded_margin_paise=rec_margin,
            recomputed_margin_paise=0,
            recorded_per_method=rec_per_method,
            recomputed_per_method={},
            error_message=f"Failed during algorithmic recomputation: {e}",
        )

    core_matches = (rec_core == recomputed_core)
    margin_matches = (rec_margin == recomputed_margin)
    is_valid = sig_valid and slice_hash_valid and core_matches and margin_matches

    error_msg = None
    if not is_valid:
        diffs = []
        if not core_matches:
            diffs.append(f"core mismatch (recorded: {rec_core}, recomputed: {recomputed_core})")
        if not margin_matches:
            diffs.append(f"margin mismatch (recorded: {rec_margin}, recomputed: {recomputed_margin})")
        error_msg = "Discrepancy detected: " + "; ".join(diffs)

    return VerificationReport(
        is_valid=is_valid,
        receipt_id=receipt_id,
        case_id=case_id,
        account_id=account_id,
        signature_valid=sig_valid,
        slice_hash_valid=slice_hash_valid,
        core_matches=core_matches,
        margin_matches=margin_matches,
        recorded_core_paise=rec_core,
        recomputed_core_paise=recomputed_core,
        recorded_margin_paise=rec_margin,
        recomputed_margin_paise=recomputed_margin,
        recorded_per_method=rec_per_method,
        recomputed_per_method=recomputed_per_method,
        error_message=error_msg,
    )


def verify_receipt_file(file_path: Path | str) -> VerificationReport:
    """Load JSON from path and run full standalone verification."""
    path = Path(file_path)
    if not path.exists():
        return VerificationReport(
            is_valid=False,
            receipt_id="N/A",
            case_id="N/A",
            account_id="N/A",
            signature_valid=False,
            slice_hash_valid=False,
            core_matches=False,
            margin_matches=False,
            recorded_core_paise=0,
            recomputed_core_paise=0,
            recorded_margin_paise=0,
            recomputed_margin_paise=0,
            recorded_per_method={},
            recomputed_per_method={},
            error_message=f"File not found: '{file_path}'",
        )

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    return verify_receipt_dict(data)
