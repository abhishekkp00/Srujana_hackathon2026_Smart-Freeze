#!/usr/bin/env python3
"""FairHold Dataset Profiling CLI Tool.

Profiles available datasets (FairHold synthetic ledger, Elliptic Bitcoin graph,
SynthAML alerts, and AMLNet), validates schemas, reports missing values, duplicate keys,
amount distributions, and data quality warnings.

Usage:
    python3 scripts/profile_datasets.py --dataset synthetic
    python3 scripts/profile_datasets.py --dataset all
    python3 scripts/profile_datasets.py --dataset synthetic --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List

# Ensure repository root is on sys.path
WORKSPACE_DIR = Path(__file__).resolve().parent.parent
if str(WORKSPACE_DIR) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_DIR))

from pipeline.profiling import (
    DatasetProfile,
    profile_amlnet_dataset,
    profile_elliptic_dataset,
    profile_synthaml_dataset,
    profile_synthetic_dataset,
)


def profile_datasets(
    dataset_choice: str,
    synthetic_dir: Path,
    raw_dir: Path,
) -> List[DatasetProfile]:
    """Execute profiling for the selected dataset(s)."""
    profiles: List[DatasetProfile] = []

    # 1. FairHold Synthetic
    if dataset_choice in ("synthetic", "all"):
        profiles.append(profile_synthetic_dataset(synthetic_dir))

    # 2. Elliptic Bitcoin
    if dataset_choice in ("elliptic", "all"):
        elliptic_dir = raw_dir / "elliptic_bitcoin_dataset"
        profiles.append(profile_elliptic_dataset(elliptic_dir))

    # 3. SynthAML Alerts
    if dataset_choice in ("synthaml", "all"):
        profiles.append(profile_synthaml_dataset(raw_dir))

    # 4. AMLNet
    if dataset_choice in ("amlnet", "all"):
        amlnet_path = raw_dir / "AMLNet_August 2025.csv"
        profiles.append(profile_amlnet_dataset(amlnet_path, sample_size=10000))

    return profiles


def main() -> int:
    parser = argparse.ArgumentParser(
        description="FairHold Dataset Profiling and Validation CLI"
    )
    parser.add_argument(
        "--dataset",
        choices=["synthetic", "elliptic", "synthaml", "amlnet", "all"],
        default="synthetic",
        help="Target dataset to profile (default: synthetic)",
    )
    parser.add_argument(
        "--synthetic-dir",
        type=Path,
        default=WORKSPACE_DIR / "data" / "synthetic",
        help="Directory containing synthetic CSV files (default: data/synthetic)",
    )
    parser.add_argument(
        "--raw-dir",
        type=Path,
        default=WORKSPACE_DIR / "data" / "raw",
        help="Directory containing raw external datasets (default: data/raw)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output profile report as JSON",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional file path to write profiling results",
    )

    args = parser.parse_args()

    profiles = profile_datasets(
        dataset_choice=args.dataset,
        synthetic_dir=args.synthetic_dir,
        raw_dir=args.raw_dir,
    )

    # Check for fatal errors
    has_fatal_error = False
    for p in profiles:
        if p.status == "error":
            has_fatal_error = True
        # If user explicitly requested a specific dataset and it is skipped because files are missing
        if args.dataset != "all" and p.status == "skipped":
            has_fatal_error = True

    if args.json:
        output_payload = [p.to_dict() for p in profiles]
        output_text = json.dumps(output_payload, indent=2)
    else:
        output_text = "\n\n".join(p.format_text() for p in profiles)

    print(output_text)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output_text, encoding="utf-8")
        print(f"\n[+] Profile report saved to: {args.output}")

    return 1 if has_fatal_error else 0


if __name__ == "__main__":
    sys.exit(main())
