import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'settings')
sys.path.append(os.getcwd())
django.setup()

from django.db import connections

def describe_client():
    conn = connections['aryza']
    with conn.cursor() as cursor:
        cursor.execute("DESCRIBE client")
        cols = [row[0] for row in cursor.fetchall()]
        print(f"Columns in client: {cols}")

if __name__ == "__main__":
    describe_client()
