import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'settings')
sys.path.append(os.getcwd())
django.setup()

from django.db import connections
from debt_app.aryza_client import AryzaClient

def test_aryza():
    client = AryzaClient()
    try:
        conn = client._get_connection()
        print(f"Successfully connected to {client.db_alias}")
        
        refs = ["319197", "324991"]
        for ref in refs:
            cid = client._find_client_id(conn, ref)
            print(f"Reference {ref} -> ClientID: {cid}")
            
            if cid:
                # Let's see which table found it
                with conn.cursor() as cursor:
                    cursor.execute("SELECT clientid FROM client WHERE reference = %s", [ref])
                    if cursor.fetchone(): print(f"  Found in client.reference")
                    
                    cursor.execute("SELECT clientid FROM td_client WHERE td_case_code = %s", [ref])
                    if cursor.fetchone(): print(f"  Found in td_client.td_case_code")
                    
                    if ref.isdigit():
                        cursor.execute("SELECT id FROM client WHERE id = %s", [int(ref)])
                        if cursor.fetchone(): print(f"  Found in client.id")
                        
                        cursor.execute("SELECT clientid FROM td_client WHERE clientid = %s", [int(ref)])
                        if cursor.fetchone(): print(f"  Found in td_client.clientid")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_aryza()
