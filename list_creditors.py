
import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "debt_project.settings")
django.setup()

from debt_app.models import CreditorCriteria

print("Active CreditorCriteria entries:")
for creditor in CreditorCriteria.objects.filter(is_active=True).order_by("creditor_name"):
    print(f"  {creditor.creditor_name!r} (rep: {creditor.representative!r}, status: {creditor.status!r})")
