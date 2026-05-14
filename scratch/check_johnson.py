import os
import sys
import django
from django.db import connections

# Add the project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'settings')
django.setup()

def check_johnson_data(reference):
    conn = connections['aryza']
    with conn.cursor() as cursor:
        cursor.execute("SELECT clientid, td_total_debt, td_contribution, td_income_total, td_expenditure_total FROM td_client WHERE td_case_code = %s", [reference])
        row = cursor.fetchone()
        if row:
            print(f"Michael Johnson (Ref: {reference}):")
            print(f"  Total Debt: {row[1]}")
            print(f"  Contribution: {row[2]}")
            print(f"  Income Total: {row[3]}")
            print(f"  Expenditure Total: {row[4]}")
        else:
            print(f"Not found in td_client: {reference}")

if __name__ == "__main__":
    check_johnson_data('319197')
