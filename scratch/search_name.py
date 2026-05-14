import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'settings')
sys.path.append(os.getcwd())
django.setup()

from django.db import connections

def search_name():
    conn = connections['aryza']
    with conn.cursor() as cursor:
        cursor.execute("SELECT id, name, import_reference, alt_ref FROM client WHERE name LIKE '%Theresa%'")
        rows = cursor.fetchall()
        for row in rows:
            print(f"FOUND: ID={row[0]}, Name={row[1]}, ImportRef={row[2]}, AltRef={row[3]}")

if __name__ == "__main__":
    search_name()
