import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'settings')
sys.path.append(os.getcwd())
django.setup()

from django.db import connections

def find_latest():
    conn = connections['aryza']
    with conn.cursor() as cursor:
        print("Latest in client table:")
        cursor.execute("SELECT id, firstname, lastname, date_created FROM client ORDER BY date_created DESC LIMIT 10")
        for row in cursor.fetchall():
            print(f"  ID: {row[0]}, Name: {row[1]} {row[2]}, Created: {row[3]}")
            
        print("\nLatest in td_client table:")
        cursor.execute("SELECT clientid, td_case_code, date_created FROM td_client ORDER BY date_created DESC LIMIT 10")
        for row in cursor.fetchall():
            print(f"  ClientID: {row[0]}, CaseCode: {row[1]}, Created: {row[2]}")
            
        print("\nLatest in iva_client table:")
        cursor.execute("SELECT clientid, payment_ref, date_created FROM iva_client ORDER BY date_created DESC LIMIT 10")
        for row in cursor.fetchall():
            print(f"  ClientID: {row[0]}, PaymentRef: {row[1]}, Created: {row[2]}")

if __name__ == "__main__":
    find_latest()
