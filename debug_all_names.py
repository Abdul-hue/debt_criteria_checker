#!/usr/bin/env python
import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "debt_project.settings")
django.setup()

from debt_app.models import CreditorCriteria

# Check what _all_creditor_names would contain
all_names = list(
    CreditorCriteria.objects.filter(is_active=True)
    .values_list("creditor_name", flat=True)
)

print(f"Total active creditor names: {len(all_names)}")
print("\nSearching for NatWest variants:")
for name in all_names:
    if 'natwest' in name.lower():
        print(f"  {name!r}")

print("\nSearching for Lloyds variants:")
for name in all_names:
    if 'lloyds' in name.lower():
        print(f"  {name!r}")

print("\nSearching for MBNA variants:")
for name in all_names:
    if 'mbna' in name.lower():
        print(f"  {name!r}")

print("\nSearching for Shop Direct variants:")
for name in all_names:
    if 'shop direct' in name.lower() or 'jd williams' in name.lower():
        print(f"  {name!r}")

# Now test the fuzzy lookup
print("\n=== FUZZY LOOKUP TEST ===")
from debt_app.helpers import fuzzy_lookup_creditor

test_names = ['NatWest', 'Lloyds Bank', 'MBNA - IVA', 'Shop Direct']
for name in test_names:
    result = fuzzy_lookup_creditor(name, all_names=all_names, threshold=50)
    if result:
        print(f"'{name}' -> fuzzy found: '{result.creditor_name}'")
    else:
        print(f"'{name}' -> fuzzy NOT FOUND")
