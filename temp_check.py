
import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "debt_project.settings")
django.setup()

from debt_app.models import CreditorCriteria

for name in [
    "1:Many",
    "1:Many - TD",
    "AA (Bank of Ireland) - IVA",
    "118 118 Money",
    "118 Money",
]:
    try:
        c = CreditorCriteria.objects.get(creditor_name=name)
        print(f"{name}: rep={c.representative}, status={c.status}, source={c.source_sheet}")
    except CreditorCriteria.DoesNotExist:
        print(f"{name}: not found")
