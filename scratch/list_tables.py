import os
import django
from django.db import connections

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'settings')
django.setup()

def list_relevant_tables():
    conn = connections['aryza']
    with conn.cursor() as cursor:
        cursor.execute("SHOW TABLES")
        tables = [row[0] for row in cursor.fetchall()]
        
    keywords = ['debt', 'creditor', 'income', 'expenditure', 'budget', 'finance', 'amount', 'case', 'client']
    relevant = [t for t in tables if any(kw in t.lower() for kw in keywords)]
    
    print("RELEVANT TABLES IN TIG DATABASE:")
    for t in sorted(relevant):
        print(f"  - {t}")

if __name__ == "__main__":
    list_relevant_tables()
