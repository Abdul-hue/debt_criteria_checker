#!/usr/bin/env python
"""Debug creditor resolution for case 324991."""
import django
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'debt_project.settings')
django.setup()

from debt_app.helpers import get_creditor_by_trading_name
from debt_app.models import CreditorCriteria

test_names = [
    "Natwest Group Plc",
    "Lloyds Banking Group",
    "MBNA",
    "Link Financial Outsourcing Limited",
    "JD WIlliams (N Brown Group)",
    "Lloyds Bank Plc HP",
]

print("=== CREDITOR RESOLUTION TEST ===\n")
for name in test_names:
    try:
        result = get_creditor_by_trading_name(name)
        print(f"{name:<40} -> {result.creditor_name:<50} [{result.representative}]")
    except CreditorCriteria.DoesNotExist as e:
        print(f"{name:<40} -> ERROR: {e}")
