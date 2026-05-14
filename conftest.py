# conftest.py
# Project-root pytest configuration.
# Boots Django before any test is collected.

import sys
import os

# Allow bare imports like `from criteria_engine import ...`
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "debt_app"))

import django
from django.conf import settings


def pytest_configure(config):
    """Called by pytest before collection begins."""
    import os
    os.environ.setdefault(
        "DJANGO_SETTINGS_MODULE",
        "debt_project.settings"
    )
    django.setup()