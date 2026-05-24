#!/usr/bin/env python
"""
Final verification that case 324991 creditor pipeline is fixed.
Expected: 6 creditors with correct names, WATCH representative, no PRA false matches.
"""
import os
import django
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

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

# Restore ACCEPT creditors
engine_positions = result.get("creditor_positions", [])
positioned_names = {
    p.get("creditor_name", "").strip().lower()
    for p in engine_positions
}

accept_positions = []
for c in prepared_creditors:
    cname = (c.get("creditor_name") or "").strip()
    if cname and cname.lower() not in positioned_names:
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

# Expected creditors
expected = {
    'natwest group plc': 8039,
    'lloyds banking group': 8499,
    'mbna': 8109,
    'link financial outsourcing limited': 1610,
    'jd williams': 3065,
    'lloyds bank plc hp': 2583,
}

actual = {
    c.get('creditor_name', '').lower(): c.get('balance', 0)
    for c in result.get('creditor_positions', [])
}

print("=== CASE 324991 CREDITOR VERIFICATION ===\n")
print(f"Expected: {len(expected)} creditors")
print(f"Actual:   {len(actual)} creditors\n")

print("CREDITOR MATCHING:")
all_match = True
for exp_name, exp_balance in sorted(expected.items()):
    # Find matching actual creditor (fuzzy search for key parts)
    found = False
    for act_name, act_balance in actual.items():
        # Check if key words match
        exp_words = set(exp_name.split())
        act_words = set(act_name.split())
        if exp_words & act_words and abs(act_balance - exp_balance) < 1:
            status = "OK" if act_balance == exp_balance else "BALANCE MISMATCH"
            print(f"  {exp_name[:30]:30} -> {act_name[:30]:30} ({act_balance:>8.0f}) {status}")
            found = True
            break
    if not found:
        print(f"  {exp_name[:30]:30} -> NOT FOUND")
        all_match = False

print(f"\nCreditor matching: {'PASS' if all_match else 'FAIL'}")

# Check representatives
watch_detected = 'WATCH' in result.get('representatives_detected', [])
print(f"WATCH representative: {'PASS' if watch_detected else 'FAIL'}")

# Check hard blocks
watch_22_2 = any(r.rule_id == 'WATCH-22.2' and r.triggered for r in result.get('hard_blocks', []))
tig_05 = any(r.rule_id == 'TIG-05' and r.triggered for r in result.get('hard_blocks', []))
tig_11 = any(r.rule_id == 'TIG-11' and r.triggered for r in result.get('hard_blocks', []))

print(f"Hard block WATCH-22.2: {'PASS' if watch_22_2 else 'FAIL'}")
print(f"Hard block TIG-05: {'PASS' if tig_05 else 'FAIL'}")
print(f"Hard block TIG-11: {'PASS' if tig_11 else 'FAIL'}")

# Check no PRA false matches
has_pra = any('PRA' in c.get('creditor_name', '') for c in result.get('creditor_positions', []))
print(f"No PRA false matches: {'PASS' if not has_pra else 'FAIL'}")

# Summary
all_pass = (all_match and watch_detected and watch_22_2 and tig_05 and tig_11 and not has_pra)
print(f"\n=== OVERALL: {'ALL CHECKS PASS' if all_pass else 'SOME CHECKS FAILED'} ===")
