
import os
import django
import json

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "debt_project.settings")
django.setup()

from django.test import Client
from debt_app.models import CriteriaDecision

# Get the input from case 324901
cd = CriteriaDecision.objects.filter(application_id="324901").first()
if not cd:
    print("Case 324901 not found")
    exit(1)

# Use the input snapshot as the request body
case_json = cd.input_snapshot

# Test DirectAssessView
client = Client()
response = client.post(
    "/api/v1/assess/",
    json.dumps(case_json),
    content_type="application/json"
)

print(f"Response status code: {response.status_code}")
if response.status_code == 200:
    data = response.json()
    print("\n--- Creditor positions in response:")
    for pos in data.get("creditor_positions", []):
        print(f"  {pos['creditor_name']}:")
        print(f"    cr_raw_name: {pos.get('cr_raw_name')}")
        print(f"    type_code: {pos.get('type_code')}")
        print(f"    cr_balance: {pos.get('cr_balance')}")
else:
    print(f"Response error: {response.content}")
