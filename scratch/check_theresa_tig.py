import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'settings')
sys.path.append(os.getcwd())
django.setup()

from django.db import connections

def check_theresa_in_tig():
    conn = connections['aryza']
    with conn.cursor() as cursor:
        cursor.execute("USE tig")
        cursor.execute("SELECT id, firstname, lastname FROM client WHERE id = 324991")
        row = cursor.fetchone()
        if row:
            print(f"ID 324991 in tig: {row[1]} {row[2]}")
        else:
            print("ID 324991 NOT in tig")

if __name__ == "__main__":
    check_theresa_in_tig()
