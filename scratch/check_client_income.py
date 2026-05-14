import os
import sys
import django
from django.db import connections

sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'settings')
django.setup()

def check_client_income(clientid):
    conn = connections['aryza']
    with conn.cursor() as cursor:
        # client_income
        cursor.execute("DESCRIBE client_income")
        cols = [r[0] for r in cursor.fetchall()]
        print(f"Columns in client_income: {cols}\n")
        
        cursor.execute("SELECT * FROM client_income WHERE clientid = %s", [clientid])
        rows = cursor.fetchall()
        print(f"Records in client_income for client {clientid}:")
        for row in rows:
            data = dict(zip(cols, row))
            print(f"  {data}")

        print("\n---\n")
        
        # client_custom_income
        cursor.execute("DESCRIBE client_custom_income")
        cols2 = [r[0] for r in cursor.fetchall()]
        print(f"Columns in client_custom_income: {cols2}\n")
        
        cursor.execute("SELECT * FROM client_custom_income WHERE clientid = %s", [clientid])
        rows2 = cursor.fetchall()
        print(f"Records in client_custom_income for client {clientid}:")
        for row in rows2:
            data = dict(zip(cols2, row))
            print(f"  {data}")

if __name__ == "__main__":
    check_client_income(319197)
