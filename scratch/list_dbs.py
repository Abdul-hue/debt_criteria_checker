import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'settings')
sys.path.append(os.getcwd())
django.setup()

from django.db import connections

def list_dbs():
    conn = connections['aryza']
    with conn.cursor() as cursor:
        cursor.execute("SHOW DATABASES")
        dbs = [row[0] for row in cursor.fetchall()]
        print(f"Databases on host: {dbs}")

if __name__ == "__main__":
    list_dbs()
