
import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "debt_project.settings")
django.setup()

from debt_app.helpers import (
    get_creditor_by_trading_name,
    normalise_creditor_name,
    CREDITOR_ALIAS_MAP,
    fuzzy_lookup_creditor
)
from debt_app.models import CreditorCriteria

test_names = ["Newday LTD", "NewDay", "Zilch Technology Limited", "Zilch"]

for name in test_names:
    print(f"\nTesting name: {name!r}")
    normalized = normalise_creditor_name(name)
    print(f"  Normalized: {normalized!r}")
    alias = CREDITOR_ALIAS_MAP.get(normalized)
    print(f"  Alias: {alias!r}")
    
    try:
        cc = get_creditor_by_trading_name(name)
        print(f"  Found via get_creditor_by_trading_name: {cc.creditor_name!r}, status={cc.status!r}, rep={cc.representative!r}")
    except CreditorCriteria.DoesNotExist:
        print(f"  get_creditor_by_trading_name: not found")
        try:
            fuzzy = fuzzy_lookup_creditor(name)
            if fuzzy:
                print(f"  Fuzzy match: {fuzzy.creditor_name!r}")
            else:
                print(f"  Fuzzy lookup: no match")
        except Exception as e:
            print(f"  Fuzzy lookup error: {e}")

print("\n--- All CreditorCriteria:")
for cc in CreditorCriteria.objects.filter(is_active=True):
    print(f"  {cc.creditor_name!r}, rep={cc.representative!r}")
