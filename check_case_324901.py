
import os
import django
import json

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "debt_project.settings")
django.setup()

from debt_app.models import CriteriaDecision

cd = CriteriaDecision.objects.filter(application_id="324901").first()
if cd:
    print(f"Case: {cd.application_id}")
    print(f"\n--- Input creditors (raw):")
    input_creditors = cd.input_snapshot.get("creditors", [])
    for c in input_creditors:
        print(f"  {json.dumps(c, indent=4)}")

    print(f"\n--- Output creditor positions:")
    output_creditors = cd.decision_output.get("creditor_positions", [])
    for c in output_creditors:
        print(f"  {json.dumps(c, indent=4)}")
