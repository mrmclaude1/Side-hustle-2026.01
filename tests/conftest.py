"""Test environment defaults. Must run before `app.main` is imported so the
module-level DB connection uses an in-memory store and the data source uses the
bundled fixture (no network, no on-disk DB file)."""

import os

os.environ.setdefault("BASISPULSE_DB", ":memory:")
os.environ.setdefault("BASISPULSE_DEMO", "1")
os.environ.setdefault("BASISPULSE_DISABLE_RATELIMIT", "1")
os.environ.setdefault("BASISPULSE_ADMIN_TOKEN", "test-admin")
