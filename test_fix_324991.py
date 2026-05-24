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
view = AssessCaseView()
payload, prepared_creditors = view._prepare_engine_payload(obj)
result = assess_case(payload)

# STEP 7 — Restore ACCEPT creditors
engine_positions = result.get("creditor_positions", [])

print(f"[ENGINE OUTPUT] {len(engine_positions)} positions from engine")

# Collect names already in engine output
positioned_names = {
    p.get("creditor_name", "").strip().lower()
    for p in engine_positions
}

# Add back creditors that engine filtered (ACCEPT, no findings)
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
            "reason": "Creditor accepted — no conditions apply",
            "rule_ids": [],
            "balance": float(c.get("crm_balance") or c.get("balance") or 0),
        })
        print(f"[ACCEPT RESTORED] '{cname}'")

print(f"[ACCEPT RESTORED] {len(accept_positions)} positions restored")

all_creditor_positions = engine_positions + accept_positions
result["creditor_positions"] = all_creditor_positions

print("=== CREDITOR POSITIONS (all) ===")
for p in result.get('creditor_positions', []):
    print(f"  {p.get('creditor_name')!r} status={p.get('effective_status')!r}")

print("\n=== REPRESENTATIVES DETECTED ===")
print(result.get('representatives_detected'))

print("\n=== HARD BLOCKS ===")
for r in result.get('hard_blocks', []):
    print(f"  {r.rule_id}: {r.triggered}")

print("\n=== VERIFY CHECKS ===")
# Check 1: First creditor must be NatWest
first_creditor = result.get('creditor_positions', [{}])[0].get('creditor_name', '')
print(f"1. First creditor is '{first_creditor}' - {'✓ PASS' if 'atwest' in first_creditor.lower() and 'PRA' not in first_creditor else '✗ FAIL'}")

# Check 2: Link Financial should be detected
link_found = any('link' in str(c.get('creditor_name', '')).lower() for c in result.get('creditor_positions', []))
print(f"2. Link Financial found: {link_found} - {'✓ PASS' if link_found else '✗ FAIL'}")

# Check 3: WATCH should be in representatives
watch_found = 'WATCH' in result.get('representatives_detected', [])
print(f"3. WATCH in representatives: {watch_found} - {'✓ PASS' if watch_found else '✗ FAIL'}")

# Check 4: No duplicate creditor names
creditor_names = [c.get('creditor_name', '') for c in result.get('creditor_positions', [])]
duplicates = [name for name in creditor_names if creditor_names.count(name) > 1 and name != '']
print(f"4. No duplicate creditor names: {len(duplicates) == 0} - {'✓ PASS' if len(duplicates) == 0 else f'✗ FAIL: {duplicates}'}")

# Check 5: WATCH-22.2 hard block present
watch_22_2_found = any(r.rule_id == 'WATCH-22.2' and r.triggered for r in result.get('hard_blocks', []))
print(f"5. WATCH-22.2 (debt repayable 0.7y) found: {watch_22_2_found} - {'✓ PASS' if watch_22_2_found else '✗ FAIL'}")

# Check 6: No PRA Group or wrong creditors due to fuzzy matching
has_pra = any('PRA' in c.get('creditor_name', '') for c in result.get('creditor_positions', []) if c.get('creditor_name') != 'Link Financial - IVA')
print(f"6. No PRA Group false matches: {not has_pra} - {'✓ PASS' if not has_pra else '✗ FAIL'}")


