import os
import sys
import django
from django.db import connections

# Add the project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'settings')
django.setup()

def find_data_heavy_tables():
    conn = connections['aryza']
    with conn.cursor() as cursor:
        cursor.execute("SELECT table_name, table_rows FROM information_schema.tables WHERE table_schema = DATABASE() ORDER BY table_rows DESC LIMIT 20")
        results = cursor.fetchall()
        
    print("TOP 20 DATA-HEAVY TABLES IN DATABASE:")
    for table, rows in results:
        print(f"  - {table}: {rows} rows")

if __name__ == "__main__":
    find_data_heavy_tables()
