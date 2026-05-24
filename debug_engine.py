#!/usr/bin/env python
import os
import django
import json

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "debt_project.settings")
django.setup()

from debt_app.aryza_client import fetch_case_by_reference
from debt_app.views.criteria_views import AssessCaseView
from debt_app.criteria_engine import assess_case
from debt_app.helpers import get_creditor_by_trading_name

obj = fetch_case_by_reference('324991')
view = AssessCaseView()
payload, prepared_creditors = view._prepare_engine_payload(obj)

print("=== PAYLOAD CREDITORS ===")
for c in payload['creditors'][:3]:
    print(f"  creditor_name={c.get('creditor_name', c.get('name'))!r}, type={c['debt_type_normalised']!r}")

# Now let's manually check what the engine sees
print("\n=== MANUAL ENGINE TEST ===")

for c in payload['creditors'][:3]:
    name = c['name']
    try:
        cred = get_creditor_by_trading_name(name)
        print(f"{name!r} -> FOUND: {cred.creditor_name!r}")
    except Exception as e:
        print(f"{name!r} -> ERROR: {str(e)[:80]}")

print("\n=== RUNNING ENGINE ===")
result = assess_case(payload)

print(f"Engine returned {len(result['creditor_positions'])} positions")
for p in result['creditor_positions'][:3]:
    print(f"  creditor_name={p.get('creditor_name')!r}, status={p.get('effective_status')!r}")

print("\n=== CHECKING ENGINE RESULT ===")
print(f"representatives_detected: {result.get('representatives_detected')}")
