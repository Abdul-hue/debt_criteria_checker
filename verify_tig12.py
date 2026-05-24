#!/usr/bin/env python
import os
import django
import json

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "debt_project.settings")
django.setup()

from debt_app.views.criteria_views import AssessCaseView
from debt_app.aryza_client import fetch_case_by_reference
from debt_app.criteria_engine import assess_case

# Test case 324991
obj = fetch_case_by_reference('324991')
print(f"DEBUG: Case 324991 TPC in obj.income: {obj.income.get('third_party_contribution')}")

view = AssessCaseView()
payload, prepared_creditors = view._prepare_engine_payload(obj)
print(f"DEBUG: Case 324991 TPC in payload: {payload.get('third_party_contribution')}")

result = assess_case(payload)

print("\n=== RULE EVALUATION FOR TIG-12 ===")
all_rules = result.get('hard_blocks', []) + result.get('flags', []) + result.get('info', []) + result.get('passed', [])
tig12 = next((r for r in all_rules if r.rule_id == 'TIG-12'), None)

if tig12:
    print(f"Rule ID: {tig12.rule_id}")
    print(f"Severity: {tig12.severity}")
    print(f"Triggered: {tig12.triggered}")
    print(f"Message: {tig12.message}")
    
    if "RULE-CANNOT-EVALUATE" in tig12.message:
        print("\n[VERIFICATION] ✗ FAIL: TIG-12 still shows RULE-CANNOT-EVALUATE")
    else:
        print("\n[VERIFICATION] ✓ PASS: TIG-12 evaluated successfully")
else:
    print("\n[VERIFICATION] ✗ FAIL: TIG-12 not found in results")
