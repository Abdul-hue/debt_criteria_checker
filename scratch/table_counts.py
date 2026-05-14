import os
import sys
import django
from django.db import connections

# Add the project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'settings')
django.setup()

def table_counts():
    conn = connections['aryza']
    tables = [
        'client', 'td_client', 'td_client_debt', 
        'slam_revolving_fixed_creditor', 'slam_other_creditor', 
        'slam_other_income', 'slam_expenditure'
    ]
    with conn.cursor() as cursor:
        for t in tables:
            try:
                cursor.execute(f"SELECT COUNT(*) FROM {t}")
                print(f"Table '{t}': {cursor.fetchone()[0]} rows")
            except Exception as e:
                print(f"Table '{t}': ERROR {e}")

if __name__ == "__main__":
    table_counts()
