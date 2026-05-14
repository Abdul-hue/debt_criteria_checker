import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'settings')
sys.path.append(os.getcwd())
django.setup()

from django.db import connections

def search_more_tables():
    conn = connections['aryza']
    refs = ["319197", "324991"]
    
    # Tables to search
    tables_to_check = [
        'iva_client', 'tp_client', 'client', 'td_client', 'iva_client_debt'
    ]
    
    with conn.cursor() as cursor:
        for ref in refs:
            print(f"Searching for {ref}...")
            found = False
            for table in tables_to_check:
                try:
                    # Check for generic ID columns
                    cursor.execute(f"DESCRIBE {table}")
                    cols = [row[0] for row in cursor.fetchall()]
                    
                    search_cols = [c for c in cols if any(x in c.lower() for x in ['id', 'ref', 'code'])]
                    
                    for col in search_cols:
                        try:
                            query = f"SELECT * FROM {table} WHERE {col} = %s"
                            cursor.execute(query, [ref])
                            row = cursor.fetchone()
                            if row:
                                print(f"  FOUND in {table}.{col}")
                                found = True
                        except Exception:
                            continue
                except Exception:
                    continue
            if not found:
                print(f"  NOT FOUND in basic tables.")

if __name__ == "__main__":
    search_more_tables()
