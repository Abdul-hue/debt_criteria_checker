import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'settings')
sys.path.append(os.getcwd())
django.setup()

from django.db import connections

def search_refs():
    conn = connections['aryza']
    refs = ["319197", "324991"]
    
    search_targets = [
        ('client', ['id', 'import_reference', 'alt_ref', 'aryza_cms_id', 'lead_urn']),
        ('td_client', ['id', 'clientid', 'td_case_code', 'td_ptd_ref', 'td_aib_ref', 'td_alternative_reference_no'])
    ]
    
    with conn.cursor() as cursor:
        for ref in refs:
            print(f"Searching for {ref}...")
            found = False
            for table, cols in search_targets:
                for col in cols:
                    try:
                        query = f"SELECT * FROM {table} WHERE {col} = %s"
                        cursor.execute(query, [ref])
                        row = cursor.fetchone()
                        if row:
                            print(f"  FOUND in {table}.{col}")
                            found = True
                    except Exception:
                        continue
            if not found:
                print(f"  NOT FOUND in any target columns.")

if __name__ == "__main__":
    search_refs()
