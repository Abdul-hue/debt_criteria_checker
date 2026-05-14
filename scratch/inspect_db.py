import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'settings')
sys.path.append(os.getcwd())
django.setup()

from django.db import connections

def list_tables():
    try:
        conn = connections['aryza']
        with conn.cursor() as cursor:
            cursor.execute("SHOW TABLES")
            tables = [row[0] for row in cursor.fetchall()]
            print(f"Tables in aryza: {tables}")
            
            # Check for generic client tables
            for t in tables:
                if 'client' in t.lower():
                    cursor.execute(f"DESCRIBE {t}")
                    cols = [row[0] for row in cursor.fetchall()]
                    print(f"Table {t} columns: {cols}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    list_tables()
