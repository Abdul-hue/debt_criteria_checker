import os
import sys
import django

sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'settings')
django.setup()

from debt_app.aryza_client import fetch_case_by_reference

def test_case(reference):
    print(f"\nTesting case: {reference}")
    try:
        case = fetch_case_by_reference(reference)
        print(f"  Name:        {case.client_name}")
        print(f"  Total Debt:  £{case.total_unsecured_debt / 100:,.2f}")
        print(f"  Disposable:  £{case.disposable_income / 100:,.2f}/month")
        print(f"  Employment:  {case.employment_status}")
        print(f"  Creditors:   {len(case.creditors)}")
        for c in case.creditors[:5]:
            print(f"    - {c['name']}: £{c['balance'] / 100:,.2f} ({c['creditor_type']})")
        if len(case.creditors) > 5:
            print(f"    ... and {len(case.creditors) - 5} more")
        print(f"  Income breakdown:")
        for k, v in case.income.items():
            if v > 0:
                print(f"    {k}: £{v/100:,.2f}")
    except Exception as e:
        print(f"  ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_case('319197')
    test_case('324991')
