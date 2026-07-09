
import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "debt_project.settings")
django.setup()

from debt_app.models import CriteriaDecision

print(f"Total CriteriaDecision: {CriteriaDecision.objects.count()}")
if CriteriaDecision.objects.exists():
    latest = CriteriaDecision.objects.order_by("-triggered_at").first()
    print(f"\nLatest decision: {latest.application_id} at {latest.triggered_at}")
    print(f"  Input data keys: {list(latest.input_snapshot.keys())}")
    print(f"  Output data keys: {list(latest.decision_output.keys())}")
