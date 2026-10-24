"""Pytest environment defaults. Keep mock identities enabled only inside the test process."""
import os

# Set these before test modules import app.main / security.auth.
os.environ["SMART_FREEZE_ENV"] = "test"
os.environ["ENABLE_DEMO_AUTH"] = "true"
