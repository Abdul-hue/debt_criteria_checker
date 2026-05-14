import os
import sys
import django
from django.db import connections

# Add the project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'settings')
django.setup()

def search_reference(reference):
    conn = connections['aryza']
    with conn.cursor() as cursor:
        # Get all tables
        cursor.execute("SHOW TABLES")
        tables = [row[0] for row in cursor.fetchall()]
        
        for table in tables:
            try:
                # Find columns that might contain the reference
                cursor.execute(f"DESCRIBE {table}")
                columns = [row[0] for row in cursor.fetchall() if 'char' in row[1] or 'int' in row[1] or 'text' in row[1]]
                
                for col in columns:
                    cursor.execute(f"SELECT COUNT(*) FROM {table} WHERE {col} = %s", [reference])
                    if cursor.fetchone()[0] > 0:
                        print(f"MATCH FOUND in table '{table}', column '{col}'")
                        # Show some info
                        cursor.execute(f"SELECT * FROM {table} WHERE {col} = %s LIMIT 1", [reference])
                        print(f"  Sample row: {cursor.fetchone()}")
            except Exception:
                continue

if __name__ == "__main__":
    search_reference('319197')
