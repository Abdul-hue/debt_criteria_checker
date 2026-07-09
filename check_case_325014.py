
import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "debt_project.settings")
django.setup()

from debt_app.models import CriteriaDecision

# Check for case 325014
decision = CriteriaDecision.objects.filter(application_id="325014").first()
if decision:
    print("Found case 325014:")
    print(f"  Triggered at: {decision.triggered_at}")
    print(f"  Input creditors: {decision.input_snapshot.get('creditors', [])}")
    print(f"  Output creditor positions: {decision.decision_output.get('creditor_positions', [])}")
else:
    print("No case 325014 found")
