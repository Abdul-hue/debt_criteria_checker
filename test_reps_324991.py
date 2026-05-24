#!/usr/bin/env python
"""
Detailed verification of case 324991 with representatives detection.
"""
import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "debt_project.settings")
django.setup()

from debt_app.views.criteria_views import AssessCaseView
from debt_app.aryza_client import fetch_case_by_reference
from debt_app.criteria_engine import assess_case

# Test case 324991
print("=== CASE 324991 REPRESENTATIVES DETECTION ===\n")
obj = fetch_case_by_reference('324991')
view = AssessCaseView()
payload, prepared_creditors = view._prepare_engine_payload(obj)
result = assess_case(payload)

# Show representatives detected
reps = result.get("representatives_detected", set())
print(f"Representatives detected: {sorted(reps)}")

# Show all creditors in case
print(f"\nCreditors in payload:")
for c in payload.get("creditors", []):
    print(f"  - {c.get('creditor_name')}")

# Show creditor positions
print(f"\nCreditor positions from engine:")
positions = result.get("creditor_positions", [])
for pos in positions:
    status = pos.get("effective_status", "unknown")
    print(f"  - {pos.get('creditor_name'):<40} status={status}")

# Check TIG-21.1 for Link Financial
print(f"\nTIG-21 rules (Link Financial detection):")
for rule in result.get("passed", []):
    if "TIG-21" in rule.rule_id:
        print(f"  [{rule.rule_id}] {rule.message}")
for rule in result.get("flags", []):
    if "TIG-21" in rule.rule_id:
        print(f"  [{rule.rule_id}] {rule.message}")

# Check hard blocks
print(f"\nHard blocks triggered:")
for rule in result.get("hard_blocks", []):
    print(f"  [{rule.rule_id}] {rule.message[:100]}...")
