import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'settings')
sys.path.append(os.getcwd())
django.setup()

from django.db import connections

def check_iva_detail():
    conn = connections['aryza']
    clientid = 112601
    with conn.cursor() as cursor:
        cursor.execute("DESCRIBE iva_client")
        cols = [r[0] for r in cursor.fetchall()]
        
        cursor.execute("SELECT * FROM iva_client WHERE clientid = %s", [clientid])
        row = cursor.fetchone()
        if row:
            data = dict(zip(cols, row))
            for k, v in data.items():
                if v: print(f"  {k}: {v}")
        else:
            print("Not found in iva_client")

if __name__ == "__main__":
    check_iva_detail()
