"""CLI entrypoint for standalone receipt verification.

Usage:
    python -m verifier receipt.json
    python -m verifier path/to/receipt.json

Zero imports from web framework or app modules.
"""

from __future__ import annotations

import sys
from pathlib import Path

from verifier.verify import verify_receipt_file


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print("Usage: python -m verifier <receipt.json>")
        print("Recomputes hold core/margin and verifies Ed25519 signature & ledger slice hash.")
        return 2

    target_path = Path(sys.argv[1])
    report = verify_receipt_file(target_path)
    report.print_summary()

    return 0 if report.is_valid else 1


if __name__ == "__main__":
    sys.exit(main())
