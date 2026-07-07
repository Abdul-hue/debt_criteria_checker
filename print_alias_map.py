
import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "debt_project.settings")
django.setup()

from debt_app.helpers import CREDITOR_ALIAS_MAP, _RAW_CREDITOR_ALIAS_MAP

print("_RAW_CREDITOR_ALIAS_MAP entries with 'zilch' or 'newday':")
for k, v in _RAW_CREDITOR_ALIAS_MAP.items():
    if "zilch" in k.lower() or "newday" in k.lower():
        print(f"  {k!r} -> {v!r}")

print("\nCREDITOR_ALIAS_MAP entries with 'zilch' or 'newday':")
for k, v in CREDITOR_ALIAS_MAP.items():
    if "zilch" in k.lower() or "newday" in k.lower():
        print(f"  {k!r} -> {v!r}")

print("\nTesting lookup for 'Zilch Technology Limited':")
from debt_app.helpers import normalise_creditor_name
test_name = "Zilch Technology Limited"
normalized = normalise_creditor_name(test_name)
print(f"  normalized: {normalized!r}")
print(f"  in CREDITOR_ALIAS_MAP: {normalized in CREDITOR_ALIAS_MAP}")
if normalized in CREDITOR_ALIAS_MAP:
    print(f"  value: {CREDITOR_ALIAS_MAP[normalized]!r}")
