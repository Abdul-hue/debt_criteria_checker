#!/usr/bin/env python
import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "debt_project.settings")
django.setup()

from debt_app.views.criteria_views import AssessCaseView
from debt_app.aryza_client import fetch_case_by_reference
from debt_app.criteria_engine import assess_case

# Test case 324991
obj = fetch_case_by_reference('324991')
view = AssessCaseView()
payload, prepared_creditors = view._prepare_engine_payload(obj)

print("=== PAYLOAD SUMMARY ===")
print(f"Creditors in payload: {len(payload['creditors'])}")
for c in payload['creditors']:
    print(f"  creditor_name={c.get('creditor_name')!r} balance={c.get('crm_balance')}")

result = assess_case(payload)

print("\n=== ENGINE RESULT SUMMARY ===")
print(f"creditor_positions: {len(result.get('creditor_positions', []))}")
for p in result.get('creditor_positions', []):
    print(f"  {p.get('creditor_name')!r} status={p.get('effective_status')}")

print(f"\nrepresentatives_detected: {result.get('representatives_detected')}")

print(f"\nhard_blocks triggered:")
for r in result.get('hard_blocks', []):
    if r.triggered:
        print(f"  {r.rule_id}")

# Restore ACCEPT creditors
engine_positions = result.get("creditor_positions", [])
positioned_names = {
    p.get("creditor_name", "").strip().lower()
    for p in engine_positions
}

accept_positions = []
for c in prepared_creditors:
    cname = (c.get("creditor_name") or "").strip()
    if not cname:
        continue
    if cname.lower() not in positioned_names:
        accept_positions.append({
            "creditor_name": cname,
            "resolved_canonical_name": cname,
            "effective_status": "ACCEPT",
            "findings": [],
            "reason": "Creditor accepted - no conditions apply",
            "rule_ids": [],
            "balance": float(c.get("crm_balance") or c.get("balance") or 0),
        })

result["creditor_positions"] = engine_positions + accept_positions

print("\n=== FINAL POSITIONS ===")
for p in result.get('creditor_positions', []):
    print(f"  {p.get('creditor_name')!r} status={p.get('effective_status')}")

print("\n=== VERIFICATION ===")
# Check 1: First creditor name (not empty)
first = result.get('creditor_positions', [{}])[0].get('creditor_name', '')
print(f"1. First creditor: {first!r} - PASS" if first and 'PRA' not in first else "1. First creditor: FAIL")

# Check 2: Link Financial found
link_found = any('link' in str(c.get('creditor_name', '')).lower() for c in result.get('creditor_positions', []))
print(f"2. Link Financial found: PASS" if link_found else "2. Link Financial found: FAIL")

# Check 3: WATCH detected
watch_detected = 'WATCH' in result.get('representatives_detected', [])
print(f"3. WATCH detected: PASS" if watch_detected else "3. WATCH detected: FAIL")

# Check 4: WATCH-22.2 hard block
watch_22_2 = any(r.rule_id == 'WATCH-22.2' and r.triggered for r in result.get('hard_blocks', []))
print(f"4. WATCH-22.2 hard block: PASS" if watch_22_2 else "4. WATCH-22.2 hard block: FAIL")

# Check 5: No duplicates
names = [c.get('creditor_name', '') for c in result.get('creditor_positions', [])]
duplicates = [n for n in names if names.count(n) > 1 and n != '']
print(f"5. No duplicates: PASS" if not duplicates else f"5. No duplicates: FAIL - {duplicates}")

# Check 6: No wrong creditors (PRA from fuzzy matching)
wrong = [c.get('creditor_name', '') for c in result.get('creditor_positions', []) if 'PRA' in c.get('creditor_name', '')]
print(f"6. No PRA false matches: PASS" if not wrong else f"6. No PRA false matches: FAIL - {wrong}")
