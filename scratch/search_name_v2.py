import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'settings')
sys.path.append(os.getcwd())
django.setup()

from django.db import connections

def search_name_correctly():
    conn = connections['aryza']
    with conn.cursor() as cursor:
        cursor.execute("SELECT id, firstname, lastname, import_reference, alt_ref FROM client WHERE firstname LIKE '%Theresa%'")
        rows = cursor.fetchall()
        for row in rows:
            print(f"FOUND: ID={row[0]}, Name={row[1]} {row[2]}, ImportRef={row[3]}, AltRef={row[4]}")

if __name__ == "__main__":
    search_name_correctly()
