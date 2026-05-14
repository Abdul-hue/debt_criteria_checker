import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'settings')
sys.path.append(os.getcwd())
django.setup()

from django.db import connections

def check_iva_client():
    conn = connections['aryza']
    clientid = 112601
    with conn.cursor() as cursor:
        cursor.execute("SHOW TABLES LIKE 'iva_client'")
        if not cursor.fetchone():
            print("Table iva_client does not exist")
            return
            
        cursor.execute("DESCRIBE iva_client")
        cols = [r[0] for r in cursor.fetchall()]
        
        cursor.execute("SELECT * FROM iva_client WHERE clientid = %s", [clientid])
        row = cursor.fetchone()
        if row:
            data = dict(zip(cols, row))
            print(f"IVA Client for 112601: iva_ref={data.get('iva_ref')}, aryza_ref={data.get('aryza_ref')}")
        else:
            print("Not found in iva_client")

if __name__ == "__main__":
    check_iva_client()
