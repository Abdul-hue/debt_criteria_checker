import os
import sys
import django
from django.db import connections

# Add the project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'settings')
django.setup()

def find_any_data(client_id):
    conn = connections['aryza']
    with conn.cursor() as cursor:
        cursor.execute("SHOW TABLES")
        tables = [row[0] for row in cursor.fetchall()]
        
        found = False
        for table in tables:
            try:
                # Check for clientid or client_id column
                cursor.execute(f"DESCRIBE {table}")
                cols = [row[0] for row in cursor.fetchall() if row[0].lower() in ('clientid', 'client_id')]
                
                for col in cols:
                    cursor.execute(f"SELECT COUNT(*) FROM {table} WHERE {col} = %s", [client_id])
                    count = cursor.fetchone()[0]
                    if count > 0:
                        print(f"Table '{table}' has {count} rows for client ID {client_id}")
                        found = True
            except Exception:
                continue
        
        if not found:
            print(f"No data found for client ID {client_id} in any table.")

if __name__ == "__main__":
    find_any_data(319197)
