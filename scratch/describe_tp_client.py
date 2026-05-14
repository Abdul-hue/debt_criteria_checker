import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'settings')
sys.path.append(os.getcwd())
django.setup()

from django.db import connections

def describe_tp_client():
    conn = connections['aryza']
    with conn.cursor() as cursor:
        cursor.execute("SHOW TABLES LIKE 'tp_client'")
        if not cursor.fetchone():
            print("Table tp_client does not exist")
            return
        cursor.execute("DESCRIBE tp_client")
        cols = [row[0] for row in cursor.fetchall()]
        print(f"Columns in tp_client: {cols}")
        
        # Search for the refs
        refs = ["319197", "324991"]
        for ref in refs:
            for col in cols:
                try:
                    cursor.execute(f"SELECT * FROM tp_client WHERE {col} = %s", [ref])
                    if cursor.fetchone():
                        print(f"  FOUND {ref} in tp_client.{col}")
                except Exception:
                    continue

if __name__ == "__main__":
    describe_tp_client()
