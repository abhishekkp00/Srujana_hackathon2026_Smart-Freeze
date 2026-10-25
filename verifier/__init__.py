"""Smart-Freeze Standalone Receipt Verifier Package.

Exports:
- VerificationReport
- verify_receipt_dict
- verify_receipt_file
- STANDALONE_GOVERNANCE_NOTICE

Zero imports from web framework or app modules.
"""

from verifier.verify import (
    STANDALONE_GOVERNANCE_NOTICE,
    VerificationReport,
    verify_receipt_dict,
    verify_receipt_file,
)

__all__ = [
    "STANDALONE_GOVERNANCE_NOTICE",
    "VerificationReport",
    "verify_receipt_dict",
    "verify_receipt_file",
]
