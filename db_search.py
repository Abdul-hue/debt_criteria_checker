
from django.db import connections
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'debt_project.settings')
django.setup()

def query_db():
    with connections['aryza'].cursor() as cursor:
        cursor.execute("""
            SELECT table_name, column_name 
            FROM information_schema.columns 
            WHERE column_name LIKE '%third%' 
            OR column_name LIKE '%contribution%' 
            OR column_name LIKE '%guarantor%'
        """)
        for row in cursor.fetchall():
            print(f"{row[0]}: {row[1]}")

if __name__ == "__main__":
    query_db()
