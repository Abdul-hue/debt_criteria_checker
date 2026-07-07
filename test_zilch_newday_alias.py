
import os
import django
import json

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "debt_project.settings")
django.setup()

from debt_app.helpers import CREDITOR_ALIAS_MAP, normalise_creditor_name, get_creditor_by_trading_name
from debt_app.models import CreditorCriteria

# Test cases
test_names = [
    "Newday LTD",
    "NewDay",
    "Zilch Technology Limited",
    "Zilch",
]

print("Testing alias resolution:")
for name in test_names:
    normalized = normalise_creditor_name(name)
    alias = CREDITOR_ALIAS_MAP.get(normalized, "No alias found")
    print(f"\n  Name: {name!r}")
    print(f"  Normalized: {normalized!r}")
    print(f"  Alias: {alias!r}")
    
    # Try to get creditor
    try:
        creditor = get_creditor_by_trading_name(alias if alias != "No alias found" else name)
        print(f"  Found creditor: {creditor.creditor_name!r}")
        print(f"  Status: {creditor.status!r}")
        print(f"  Representative: {creditor.representative!r}")
    except CreditorCriteria.DoesNotExist:
        print(f"  Creditor not found in DB")
