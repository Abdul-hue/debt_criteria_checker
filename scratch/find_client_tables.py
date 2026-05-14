import os
import sys
import django
from django.db import connections

# Add the project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'settings')
django.setup()

def find_client_tables():
    conn = connections['aryza']
    with conn.cursor() as cursor:
        # Get current database name
        cursor.execute("SELECT DATABASE()")
        db_name = cursor.fetchone()[0]
        
        cursor.execute(f"""
            SELECT table_name, column_name 
            FROM information_schema.columns 
            WHERE column_name IN ('clientid', 'client_id', 'id') 
            AND table_schema = '{db_name}'
        """)
        results = cursor.fetchall()
        
    print(f"TABLES WITH CLIENT REFERENCE COLUMNS IN '{db_name}':")
    for table, column in sorted(results):
        print(f"  - {table} ({column})")

if __name__ == "__main__":
    find_client_tables()
