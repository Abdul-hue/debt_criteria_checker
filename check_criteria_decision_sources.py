
import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "debt_project.settings")
django.setup()

from debt_app.models import CriteriaDecision

print("All CriteriaDecision sources:")
for cd in CriteriaDecision.objects.all().order_by("-triggered_at")[:10]:
    print(f"  {cd.application_id}: {cd.source} at {cd.triggered_at}")
