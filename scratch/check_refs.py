import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'settings')
sys.path.append(os.getcwd())
django.setup()

from django.db import connections

def check_tables():
    conn = connections['aryza']
    with conn.cursor() as cursor:
        for t in ['client', 'td_client']:
            cursor.execute(f"SHOW TABLES LIKE '{t}'")
            exists = cursor.fetchone()
            print(f"Table {t}: {'EXISTS' if exists else 'MISSING'}")
            
            if exists:
                # Check for the references
                refs = ["319197", "324991"]
                for ref in refs:
                    if t == 'client':
                        cursor.execute("SELECT id FROM client WHERE reference = %s", [ref])
                        res = cursor.fetchone()
                        print(f"  client.reference {ref} -> {res}")
                        
                        if not res:
                            cursor.execute("SELECT id FROM client WHERE id = %s", [ref])
                            res = cursor.fetchone()
                            print(f"  client.id {ref} -> {res}")
                    else:
                        cursor.execute("SELECT clientid FROM td_client WHERE td_case_code = %s", [ref])
                        res = cursor.fetchone()
                        print(f"  td_client.td_case_code {ref} -> {res}")
                        
                        if not res:
                            cursor.execute("SELECT clientid FROM td_client WHERE clientid = %s", [ref])
                            res = cursor.fetchone()
                            print(f"  td_client.clientid {ref} -> {res}")

if __name__ == "__main__":
    check_tables()
