
import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "debt_project.settings")
django.setup()

from debt_app.models import CreditorCriteria

print("Checking CreditorCriteria for NewDay and Zilch:")
for name in ["NewDay", "Zilch"]:
    try:
        cc = CreditorCriteria.objects.get(creditor_name__iexact=name, is_active=True)
        print(f"\n{name} found!")
        print(f"  creditor_name: {cc.creditor_name}")
        print(f"  status: {cc.status}")
        print(f"  representative: {cc.representative}")
        print(f"  source_sheet: {cc.source_sheet}")
    except CreditorCriteria.DoesNotExist:
        print(f"\n{name} NOT found in CreditorCriteria!")
    except CreditorCriteria.MultipleObjectsReturned:
        print(f"\nMultiple entries for {name}!")
        for cc in CreditorCriteria.objects.filter(creditor_name__iexact=name, is_active=True):
            print(f"  - {cc.creditor_name} (id: {cc.id})")

print("\nSearching CreditorCriteria for any 'zilch' (case insensitive):")
for cc in CreditorCriteria.objects.filter(creditor_name__icontains="zilch", is_active=True):
    print(f"  - {cc.creditor_name} (status: {cc.status}, rep: {cc.representative})")
