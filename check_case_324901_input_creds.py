
import os
import django
import json

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "debt_project.settings")
django.setup()

from debt_app.models import CriteriaDecision

cd = CriteriaDecision.objects.filter(application_id="324901").first()
if cd:
    print(f"Case: {cd.application_id}")
    print(f"\n--- Input creditors (checking for cr_* fields):")
    input_creditors = cd.input_snapshot.get("creditors", [])
    for idx, c in enumerate(input_creditors):
        cr_fields = {k: v for k, v in c.items() if k.startswith("cr_") or k == "type_code"}
        print(f"  Creditor {idx} - {c.get('name', c.get('creditor_name'))}:")
        print(f"    cr_fields: {json.dumps(cr_fields, indent=6)}")

    print(f"\n--- Output creditor positions (checking for cr_* fields):")
    output_creditors = cd.decision_output.get("creditor_positions", [])
    for idx, c in enumerate(output_creditors):
        cr_fields = {k: v for k, v in c.items() if k.startswith("cr_") or k == "type_code"}
        print(f"  Creditor {idx} - {c.get('creditor_name')}:")
        print(f"    cr_fields: {json.dumps(cr_fields, indent=6)}")
