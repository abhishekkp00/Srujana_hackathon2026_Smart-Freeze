#!/usr/bin/env python3
"""CLI runner for ML Model Training on real credit card fraud dataset."""

import sys
from pathlib import Path

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ml.train import run_training_pipeline

if __name__ == "__main__":
    result = run_training_pipeline()
    if result["status"] == "SUCCESS":
        print("\nTraining and evaluation pipeline completed successfully.")
        sys.exit(0)
    else:
        print("\nTraining pipeline failed.")
        sys.exit(1)
