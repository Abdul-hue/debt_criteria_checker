
import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "debt_project.settings")
django.setup()

from debt_app.models import CreditorCriteria

# Check some representative creditors
examples = [
    "1:Many",
    "1:Many - TD",
    "AA (Bank of Ireland) - IVA",
    "AA (Bank of Ireland) - TD",
    "AA Bank of Ireland",
]

print("Checking representative creditors...")
for name in examples:
    try:
        creditor = CreditorCriteria.objects.get(creditor_name=name)
        print(f"OK {name}:")
        print(f"   - Representative: {creditor.representative}")
        print(f"   - Status: {creditor.status}")
        print(f"   - Source: {creditor.source_sheet}")
        print()
    except CreditorCriteria.DoesNotExist:
        print(f"NOT FOUND {name}: Not found in DB")
        print()

print("All done!")
