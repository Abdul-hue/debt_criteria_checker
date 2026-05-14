import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'settings')
sys.path.append(os.getcwd())
django.setup()

from django.db import connections

def check_max():
    conn = connections['aryza']
    with conn.cursor() as cursor:
        cursor.execute("SELECT MAX(id) FROM client")
        mid = cursor.fetchone()[0]
        print(f"Max ID in client: {mid}")
        
        cursor.execute("SELECT COUNT(*) FROM client")
        count = cursor.fetchone()[0]
        print(f"Total rows in client: {count}")
        
        cursor.execute("SELECT MAX(clientid) FROM iva_client")
        miva = cursor.fetchone()[0]
        print(f"Max ClientID in iva_client: {miva}")

if __name__ == "__main__":
    check_max()
