import os
import sys
import django
from django.db import connections

# Add the project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'settings')
django.setup()

def check_client_data(reference):
    conn = connections['aryza']
    clientid = None
    
    with conn.cursor() as cursor:
        # 1. Find clientid
        cursor.execute("SELECT clientid FROM td_client WHERE td_case_code = %s", [reference])
        row = cursor.fetchone()
        if row:
            clientid = row[0]
            print(f"FOUND clientid: {clientid} for reference {reference}")
        else:
            print(f"NOT FOUND in td_client for reference {reference}")
            return

        # 2. Check td_client_debt
        cursor.execute("SELECT COUNT(*) FROM td_client_debt WHERE clientid = %s", [clientid])
        debt_count = cursor.fetchone()[0]
        print(f"  - td_client_debt count: {debt_count}")
        
        if debt_count > 0:
            cursor.execute("SELECT creditor_name, balance, monthly_payment FROM td_client_debt WHERE clientid = %s LIMIT 5", [clientid])
            for d in cursor.fetchall():
                print(f"    * Debt: {d[0]}, Balance: {d[1]}, Payment: {d[2]}")

        # 3. Check slam_revolving_fixed_creditor
        cursor.execute("SELECT COUNT(*) FROM slam_revolving_fixed_creditor WHERE clientid = %s", [clientid])
        slam_count = cursor.fetchone()[0]
        print(f"  - slam_revolving_fixed_creditor count: {slam_count}")

        # 4. Check income
        cursor.execute("SELECT COUNT(*) FROM slam_other_income WHERE clientid = %s", [clientid])
        income_count = cursor.fetchone()[0]
        print(f"  - slam_other_income count: {income_count}")
        
        # 5. Check td_client totals
        cursor.execute("SELECT td_total_debt, td_contribution FROM td_client WHERE clientid = %s", [clientid])
        totals = cursor.fetchone()
        print(f"  - td_client totals: Debt={totals[0]}, Contribution={totals[1]}")

if __name__ == "__main__":
    check_client_data('319197')
