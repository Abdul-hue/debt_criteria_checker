import os
import sys
import django
from django.db import connections

# Add the project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'settings')
django.setup()

def search_johnson_anywhere(reference):
    conn = connections['aryza']
    with conn.cursor() as cursor:
        # Check 'client' table
        cursor.execute("SELECT id, firstname, lastname, alt_ref, import_reference FROM client WHERE alt_ref = %s OR import_reference = %s OR id = %s", [reference, reference, reference])
        client_rows = cursor.fetchall()
        for row in client_rows:
            print(f"FOUND in 'client' table: ID={row[0]}, Name={row[1]} {row[2]}, AltRef={row[3]}, ImportRef={row[4]}")
            client_id = row[0]
            
            # Now check if this client_id exists in td_client
            cursor.execute("SELECT id, td_case_code FROM td_client WHERE clientid = %s", [client_id])
            td_row = cursor.fetchone()
            if td_row:
                print(f"  - ALSO FOUND in 'td_client': TD_ID={td_row[0]}, Code={td_row[1]}")
            else:
                print(f"  - NOT FOUND in 'td_client' by clientid {client_id}")

if __name__ == "__main__":
    search_johnson_anywhere('319197')
