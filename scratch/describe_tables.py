import os
import sys
import django
from django.db import connections

# Add the project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'settings')
django.setup()

def describe_table(table_name):
    conn = connections['aryza']
    with conn.cursor() as cursor:
        cursor.execute(f"DESCRIBE {table_name}")
        for row in cursor.fetchall():
            print(f"{row[0]} ({row[1]})")

if __name__ == "__main__":
    print("COLUMNS IN td_client_debt:")
    describe_table('td_client_debt')
    print("\nCOLUMNS IN td_client:")
    describe_table('td_client')
