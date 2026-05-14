import os
import sys
import django
from django.db import connections

# Add the project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'settings')
django.setup()

def check_324991():
    conn = connections['aryza']
    reference = '324991'
    with conn.cursor() as cursor:
        # Check client table
        cursor.execute("SELECT id, firstname, lastname FROM client WHERE id = %s OR alt_ref = %s OR import_reference = %s", [reference, reference, reference])
        row = cursor.fetchone()
        if row:
            print(f"FOUND 324991 in 'client': ID={row[0]}, Name={row[1]} {row[2]}")
            clientid = row[0]
            
            # Check td_client
            cursor.execute("SELECT td_total_debt, td_contribution FROM td_client WHERE clientid = %s", [clientid])
            td_row = cursor.fetchone()
            if td_row:
                print(f"  - FOUND in 'td_client': Debt={td_row[0]}, Contribution={td_row[1]}")
            else:
                print(f"  - NOT FOUND in 'td_client' for clientid {clientid}")
        else:
            print(f"NOT FOUND 324991 anywhere.")

if __name__ == "__main__":
    check_324991()
