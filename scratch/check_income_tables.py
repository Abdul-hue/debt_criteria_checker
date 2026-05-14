import os
import sys
import django
from django.db import connections

sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'settings')
django.setup()

def check_income_tables(clientid):
    conn = connections['aryza']
    with conn.cursor() as cursor:
        # Check all distinct types in client_expenses for this client
        cursor.execute("SELECT DISTINCT type, field FROM client_expenses WHERE clientid = %s ORDER BY type", [clientid])
        rows = cursor.fetchall()
        print(f"Distinct types/fields in client_expenses for client {clientid}:")
        for r in rows:
            print(f"  type={r[0]}, field={r[1]}")
        
        # Check if there's a separate income table
        cursor.execute("SHOW TABLES LIKE '%income%'")
        print("\nTables with 'income' in name:")
        for r in cursor.fetchall():
            print(f"  {r[0]}")

        # Check iva_client
        cursor.execute("SHOW TABLES LIKE 'iva_client'")
        if cursor.fetchone():
            cursor.execute("SELECT * FROM iva_client WHERE clientid = %s", [clientid])
            row = cursor.fetchone()
            cursor.execute("DESCRIBE iva_client")
            cols = [r[0] for r in cursor.fetchall()]
            if row:
                data = dict(zip(cols, row))
                print(f"\niva_client data for client {clientid}:")
                for k, v in data.items():
                    if v is not None and v != '' and v != 0:
                        print(f"  {k}: {v}")

if __name__ == "__main__":
    check_income_tables(319197)
