"""Pytest defaults that satisfy startup checks without throttling clients."""

import os

os.environ["SECRET_KEY"] = "valid-long-signing-key-for-pytest-testing-environment-32"
os.environ.setdefault("ALGORITHM", "HS256")

from app.api.limiter import limiter

limiter.enabled = False
