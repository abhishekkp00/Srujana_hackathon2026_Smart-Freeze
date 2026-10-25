"""Pytest environment defaults. Keep mock identities enabled only inside the test process."""
import os
from pathlib import Path

WORKSPACE_DIR = Path(__file__).resolve().parent.parent

# Set these before test modules import app.main / security.auth.
os.environ["SMART_FREEZE_ENV"] = "test"
os.environ["ENABLE_DEMO_AUTH"] = "true"
if not os.environ.get("SMART_FREEZE_DATA_DIR"):
    demo_fixture = WORKSPACE_DIR / "data" / "fixtures" / "demo_3case"
    if demo_fixture.exists():
        os.environ["SMART_FREEZE_DATA_DIR"] = str(demo_fixture)

