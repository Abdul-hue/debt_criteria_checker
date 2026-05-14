import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'settings')
sys.path.append(os.getcwd())
django.setup()

from django.db import connections

def global_search():
    conn = connections['aryza']
    val = "319197"
    with conn.cursor() as cursor:
        cursor.execute("SHOW TABLES")
        tables = [row[0] for row in cursor.fetchall()]
        
        for table in tables:
            try:
                # Basic check if val exists in any column
                cursor.execute(f"DESCRIBE `{table}`")
                cols = [row[0] for row in cursor.fetchall()]
                
                # Filter for identifying columns
                search_cols = [c for c in cols if any(x in c.lower() for x in ['id', 'ref', 'code', 'urn', 'reference'])]
                
                if not search_cols: continue
                
                where_clause = " OR ".join([f"`{c}` = %s" for c in search_cols])
                query = f"SELECT COUNT(*) FROM `{table}` WHERE {where_clause}"
                cursor.execute(query, [val] * len(search_cols))
                count = cursor.fetchone()[0]
                
                if count > 0:
                    print(f"FOUND {val} in table `{table}` (count: {count})")
                    # Show which column
                    for c in search_cols:
                        cursor.execute(f"SELECT `{c}` FROM `{table}` WHERE `{c}` = %s LIMIT 1", [val])
                        if cursor.fetchone():
                            print(f"  Column: {c}")
                            
            except Exception:
                continue

if __name__ == "__main__":
    global_search()
