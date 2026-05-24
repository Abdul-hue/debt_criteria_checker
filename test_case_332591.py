#!/usr/bin/env python
"""
Detailed verification of case 332591.
"""
import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "debt_project.settings")
django.setup()

from debt_app.views.criteria_views import AssessCaseView
from debt_app.aryza_client import fetch_case_by_reference
from debt_app.criteria_engine import assess_case

# Test case 332591
print("=== CASE 332591 LINK FINANCIAL CHECK ===\n")
obj = fetch_case_by_reference('332591')
view = AssessCaseView()
payload, prepared_creditors = view._prepare_engine_payload(obj)
result = assess_case(payload)

# Show all creditors in case
print(f"Creditors in payload:")
for c in payload.get("creditors", []):
    print(f"  - {c.get('creditor_name')}")

# Check TIG-21.1 for Link Financial
print(f"\nTIG-21 rules (Link Financial detection):")
found_tig21 = False
for rule in result.get("passed", []):
    if "TIG-21" in rule.rule_id:
        print(f"  [{rule.rule_id}] {rule.message}")
        found_tig21 = True
for rule in result.get("flags", []):
    if "TIG-21" in rule.rule_id:
        print(f"  [{rule.rule_id}] {rule.message}")
        found_tig21 = True

if not found_tig21:
    print("  No TIG-21 rules found in output.")
