import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'settings')
sys.path.append(os.getcwd())
django.setup()

from django.db import connections

def check_td_client():
    conn = connections['aryza']
    clientid = 112601
    with conn.cursor() as cursor:
        cursor.execute("SELECT * FROM td_client WHERE clientid = %s", [clientid])
        row = cursor.fetchone()
        if row:
            # Let's see some key columns
            cursor.execute("DESCRIBE td_client")
            cols = [r[0] for r in cursor.fetchall()]
            data = dict(zip(cols, row))
            print(f"TD Client for 112601: td_case_code={data.get('td_case_code')}, ptd_ref={data.get('td_ptd_ref')}, alt_ref={data.get('td_alternative_reference_no')}")

if __name__ == "__main__":
    check_td_client()
