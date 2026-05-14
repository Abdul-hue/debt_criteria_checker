import os
import sys
import django
from django.db import connections

# Add the project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'settings')
django.setup()

def describe_new_tables():
    conn = connections['aryza']
    tables = ['client_debt_new', 'client_expenses', 'iva_client_debt', 'client_extra']
    with conn.cursor() as cursor:
        for t in tables:
            print(f"\nCOLUMNS IN {t}:")
            cursor.execute(f"DESCRIBE {t}")
            for row in cursor.fetchall():
                print(f"  {row[0]} ({row[1]})")

if __name__ == "__main__":
    describe_new_tables()
