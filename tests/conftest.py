"""
pytest configuration — shared fixtures and settings overrides for tests.
"""
import os
import sys
from pathlib import Path

import pytest

# Ensure project root is importable
sys.path.insert(0, str(Path(__file__).parent.parent))

# Override config path before any app imports
os.environ.setdefault("CONFIG_PATH", "config/config.example.yaml")


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line("markers", "unit: fast unit tests (no I/O)")
    config.addinivalue_line("markers", "integration: integration tests (SQLite in-memory)")
    config.addinivalue_line("markers", "e2e: end-to-end tests (require external services)")
