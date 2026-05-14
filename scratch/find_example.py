import os
import sys
import django
from django.db import connections

# Add the project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'settings')
django.setup()

def find_working_example():
    conn = connections['aryza']
    with conn.cursor() as cursor:
        # 1. Find a client with debts
        cursor.execute("SELECT clientid, COUNT(*) as c FROM td_client_debt GROUP BY clientid ORDER BY c DESC LIMIT 1")
        row = cursor.fetchone()
        if not row:
            print("No debts found in td_client_debt.")
            return

        clientid = row[0]
        count = row[1]
        print(f"Sample Client with most debts: ID={clientid} ({count} debts)")
        
        # 2. See how they appear in client table
        cursor.execute("SELECT id, firstname, lastname, alt_ref, import_reference FROM client WHERE id = %s", [clientid])
        c_row = cursor.fetchone()
        if c_row:
            print(f"  - In 'client': Name={c_row[1]} {c_row[2]}, AltRef={c_row[3]}, ImportRef={c_row[4]}")
        else:
            print(f"  - NOT FOUND in 'client' table by ID {clientid}")

        # 3. See how they appear in td_client
        cursor.execute("SELECT td_case_code, td_total_debt FROM td_client WHERE clientid = %s", [clientid])
        td_row = cursor.fetchone()
        if td_row:
            print(f"  - In 'td_client': Code={td_row[0]}, TotalDebt={td_row[1]}")
        else:
            print(f"  - NOT FOUND in 'td_client' by clientid {clientid}")

if __name__ == "__main__":
    find_working_example()
