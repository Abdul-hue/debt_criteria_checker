import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'settings')
sys.path.append(os.getcwd())
django.setup()

from django.db import connections

def check_tig():
    conn = connections['aryza']
    with conn.cursor() as cursor:
        cursor.execute("USE tig")
        cursor.execute("SHOW TABLES LIKE 'client'")
        if cursor.fetchone():
            cursor.execute("SELECT MAX(id) FROM client")
            print(f"Max ID in tig.client: {cursor.fetchone()[0]}")
            
            val = "319197"
            cursor.execute("SELECT id FROM client WHERE id = %s", [val])
            if cursor.fetchone():
                print(f"FOUND {val} in tig.client.id!")
        else:
            print("Table client NOT in tig database")

if __name__ == "__main__":
    check_tig()
