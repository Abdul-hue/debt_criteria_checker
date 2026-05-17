import os
import sys
import django

# Add the project root to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "debt_project.settings")
django.setup()

from debt_app.criteria_engine import assess_case
from debt_app.models import CreditorCriteria

# Test 1: Barclaycard -> WATCH
print("--- TEST 1: Barclaycard -> WATCH ---")
payload_1 = {
    "total_debt": 10000,
    "disposable_income": 200,
    "creditors": [
        {"creditor_name": "Barclaycard", "balance": 10000}
    ]
}

result_1 = assess_case(payload_1)
print(f"Detected Reps: {result_1['representatives_detected']}")
watch_detected = "WATCH" in result_1['representatives_detected']
print(f"WATCH Detected: {watch_detected}")

# Test 2: NatWest x3 -> EVOLVE-02 single creditor rule
print("\n--- TEST 2: NatWest x3 -> EVOLVE-02 ---")
payload_2 = {
    "total_debt": 10000,
    "disposable_income": 200,
    "creditors": [
        {"creditor_name": "NatWest Loan", "balance": 4000},
        {"creditor_name": "NatWest Credit Card", "balance": 4000},
        {"creditor_name": "NatWest Overdraft", "balance": 2000},
    ]
}

result_2 = assess_case(payload_2)
print(f"Detected Reps: {result_2['representatives_detected']}")
evolve_blocks = [b.rule_id for b in result_2["hard_blocks"] if "EVOLVE" in b.rule_id]
print(f"EVOLVE Blocks: {evolve_blocks}")

# Test 3: Check DB for min_dividend_pence
print("\n--- TEST 3: min_dividend_pence ---")
try:
    barclaycard = CreditorCriteria.objects.get(creditor_name="Barclaycard")
    print(f"Barclaycard min_dividend_pence: {barclaycard.min_dividend_pence}")
except Exception as e:
    print(f"Error checking DB: {e}")
