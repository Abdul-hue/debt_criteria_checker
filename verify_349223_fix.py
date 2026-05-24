import os, sys, django
from decimal import Decimal

# Setup Django
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'debt_project.settings')
django.setup()

from debt_app.aryza_client import CaseData
from debt_app.views.criteria_views import AssessCaseView

def verify_fix_349223():
    # Mock CaseData for 349223 based on the payload we saw earlier
    case = CaseData()
    case.aryza_reference = "349223"
    case.client_name = "Daniel Gallagher"
    case.disposable_income = 0
    case.income = {"total": 0}
    case.expenditure = {"total": 0}
    case.property = {"owns_property": False}
    case.vehicle = {"has_vehicle": False}
    case.flags = {"previous_iva": True}
    case.dependants = []
    
    # Add the creditors, including the ones that were previously deduplicated
    case.creditors = [
        {"name": "FRASERS GRP FINANCIAL SERVICES", "balance": 11700, "creditor_type": "credit_card", "ref": ""},
        {"name": "Secure Trust Bank Plc", "balance": 135200, "creditor_type": "unsecured_loan", "ref": ""},
        {"name": "Secure Trust Bank Plc", "balance": 178100, "creditor_type": "unsecured_loan", "ref": ""}, # Previously dropped
        {"name": "Shop Direct Finance Company LTD", "balance": 35000, "creditor_type": "catalogue", "ref": ""},
        {"name": "Halifax", "balance": 235300, "creditor_type": "current_account", "ref": ""},
        {"name": "HOME RETAIL GROUP CARD SERVICES", "balance": 46500, "creditor_type": "credit_card", "ref": ""},
        {"name": "Capital One", "balance": 145500, "creditor_type": "credit_card", "ref": ""},
        {"name": "Zopa Limited", "balance": 128600, "creditor_type": "unsecured_loan", "ref": ""},
        {"name": "EE", "balance": 35700, "creditor_type": "communications_supply_account", "ref": ""},
        {"name": "ID MOBILE", "balance": 5200, "creditor_type": "communications_supply_account", "ref": ""},
        {"name": "ZOPA BANK LIMITED", "balance": 91500, "creditor_type": "credit_card", "ref": ""},
        {"name": "Halifax Credit Card", "balance": 131700, "creditor_type": "credit_card", "ref": ""},
        {"name": "Admiral Financial Services LTD", "balance": 433100, "creditor_type": "unsecured_loan", "ref": ""},
        {"name": "EE FLEX PAY", "balance": 119200, "creditor_type": "unsecured_loan", "ref": ""},
        {"name": "V12 Finance", "balance": 178132, "creditor_type": "unsecured_loan", "ref": ""},
        {"name": "V12 Finance", "balance": 132731, "creditor_type": "unsecured_loan", "ref": ""}, # Previously dropped
        {"name": "Pay Later Group Limited", "balance": 200000, "creditor_type": "unsecured", "ref": ""},
        {"name": "STELLANTIS FINANCIAL SERVICES UK LIMITED", "balance": 496100, "creditor_type": "car_hp", "ref": ""},
        {"name": "STELLANTIS FINANCIAL SERVICES UK LIMITED", "balance": 1188200, "creditor_type": "associate_creditor", "ref": ""},
    ]

    view = AssessCaseView()
    payload, prepared = view._prepare_engine_payload(case)
    
    total_debt = payload['total_unsecured_debt']
    print(f"Total Unsecured Debt: £{total_debt:,.2f}")
    
    # Expected total for these creditors (excluding car_hp and associate_creditor if they are secured)
    # Actually _prepare_engine_payload excludes _SECURED_DEBT_TYPES = {'mortgage', 'hire_purchase', 'hp', ...}
    # car_hp should be excluded.
    
    unsecured_list = [c for c in prepared]
    print(f"Number of prepared creditors: {len(unsecured_list)}")
    for c in unsecured_list:
        print(f" - {c['creditor_name']}: £{c['balance']:,.2f}")

if __name__ == "__main__":
    verify_fix_349223()
