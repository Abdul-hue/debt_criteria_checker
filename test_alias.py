
import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "debt_project.settings")
django.setup()

from debt_app.helpers import normalise_creditor_name, CREDITOR_ALIAS_MAP

test_names = [
    "Newday LTD",
    "NewDay",
    "Zilch Technology Limited",
    "Zilch",
]

for name in test_names:
    normalized = normalise_creditor_name(name)
    alias = CREDITOR_ALIAS_MAP.get(normalized, "NO ALIAS")
    print(f"Original: {name!r}")
    print(f"Normalized: {normalized!r}")
    print(f"Alias: {alias!r}")
    print()
