
import os
import django
import logging

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'debt_project.settings')
django.setup()

from debt_app.criteria_engine import assess_case
from debt_app.helpers import CREDITOR_ALIAS_MAP

# Setup logging to see the PASS TO ENGINE logs if any (though they are in views)
logging.basicConfig(level=logging.WARNING)

# Test data reflecting Case 324991 issues
raw_creditors = [
    {'name': 'Natwest Group Plc', 'balance': 500000, 'type': 'unsecured'},
    {'name': 'Lloyds Banking Group', 'balance': 300000, 'type': 'unsecured'},
    {'name': 'MBNA', 'balance': 200000, 'type': 'unsecured'},
    {'name': 'Link Financial Outsourcing Limited', 'balance': 150000, 'type': 'unsecured'},
    {'name': 'JD Williams (N Brown Group)', 'balance': 100000, 'type': 'unsecured'},
    {'name': 'Lloyds Bank Plc HP', 'balance': 50000, 'type': 'unsecured'}, # kept as unsecured
]

# Simulate _prepare_engine_payload logic
prepared_creditors = []
for c in raw_creditors:
    raw_name = c['name']
    raw_lower = raw_name.lower()
    resolved_name = CREDITOR_ALIAS_MAP.get(raw_lower, raw_name)
    balance_pounds = float(c['balance']) / 100.0
    
    prepared_creditors.append({
        'creditor_name': resolved_name,
        'original_name': raw_name,
        'crm_balance': balance_pounds,
        'balance': balance_pounds,
        'debt_type_normalised': c['type']
    })
    print(f"[SIMULATED PASS TO ENGINE] '{raw_name}' -> '{resolved_name}' balance=£{balance_pounds:.2f}")

# Build engine payload
payload = {
    "application_id": "TEST-324991",
    "client_name": "Test Client",
    "employment_status": "employed",
    "disposable_income": 150.0, # Low DI to trigger WATCH-22.2
    "total_unsecured_debt": sum(c['balance'] for c in prepared_creditors),
    "financial_summary": {
        "net_balance": 150.0,
        "total_income": 2000.0,
        "income_source": "employed",
    },
    "creditors": prepared_creditors,
    "income": {"total": 2000.0},
    "expenditure": {"total": 1850.0},
    "property": {"owns_property": False},
    "vehicle": {"has_vehicle": False},
    "flags": {},
    "dependants": 0,
}

# Run assessment
result = assess_case(payload)

# Verification
print("\n--- VERIFICATION ---")

# 1. TIG-21.1
tig_21_1 = next((r for r in result['flags'] if r.rule_id == 'TIG-21.1'), None)
if tig_21_1:
    print(f"TIG-21.1 found: {tig_21_1.message}")
else:
    print("TIG-21.1 NOT found in flags")

# 2. Representatives detected
reps = result['representatives_detected']
print(f"Representatives detected: {reps}")

# 3. Creditor positions names
print("Creditor positions names:")
for pos in result['creditor_positions']:
    print(f"  - {pos['creditor_name']}")

# 4. WATCH-22.2
watch_22_2 = next((r for r in result['hard_blocks'] if r.rule_id == 'WATCH-22.2'), None)
if watch_22_2:
    print(f"WATCH-22.2 found: {watch_22_2.message}")
else:
    print("WATCH-22.2 NOT found in hard_blocks")
