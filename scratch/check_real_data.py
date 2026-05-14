import os
import sys
import django
from django.db import connections

sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'settings')
django.setup()

from django.db import connections

def check_real_tables(clientid):
    conn = connections['aryza']
    with conn.cursor() as cursor:
        
        # 1. client_debt_new
        print(f"\n=== client_debt_new for clientid={clientid} ===")
        cursor.execute("""
            SELECT cd.id, cd.creditorid, cd.ref, cd.total, cd.monthly, cd.type,
                   c.name as creditor_name
            FROM client_debt_new cd
            LEFT JOIN creditor c ON c.id = cd.creditorid
            WHERE cd.clientid = %s AND (cd.deleted IS NULL OR cd.deleted = 0)
        """, [clientid])
        rows = cursor.fetchall()
        if rows:
            for r in rows:
                print(f"  debt_id={r[0]}, creditor={r[6]}({r[1]}), ref={r[2]}, total={r[3]}, monthly={r[4]}, type={r[5]}")
        else:
            print("  No records found.")

        # 2. iva_client_debt
        print(f"\n=== iva_client_debt for clientid={clientid} ===")
        cursor.execute("""
            SELECT id.id, id.creditorid, id.account_ref, id.starting_balance, id.creditor_claim_amount, id.type,
                   c.name as creditor_name
            FROM iva_client_debt id
            LEFT JOIN creditor c ON c.id = id.creditorid
            WHERE id.clientid = %s AND (id.deleted IS NULL OR id.deleted = 0)
        """, [clientid])
        rows = cursor.fetchall()
        if rows:
            for r in rows:
                print(f"  debt_id={r[0]}, creditor={r[6]}({r[1]}), ref={r[2]}, start_bal={r[3]}, claim={r[4]}, type={r[5]}")
        else:
            print("  No records found.")

        # 3. client_expenses - income types
        print(f"\n=== client_expenses (INCOME) for clientid={clientid} ===")
        cursor.execute("""
            SELECT type, field, `key`, value, frequency
            FROM client_expenses
            WHERE clientid = %s AND type = 'income'
        """, [clientid])
        rows = cursor.fetchall()
        if rows:
            for r in rows:
                print(f"  type={r[0]}, field={r[1]}, key={r[2]}, value={r[3]}, freq={r[4]}")
        else:
            print("  No income records found.")

        # 4. client_expenses - expenditure types
        print(f"\n=== client_expenses (EXPENDITURE) for clientid={clientid} ===")
        cursor.execute("""
            SELECT type, field, `key`, value, frequency
            FROM client_expenses
            WHERE clientid = %s AND type != 'income'
            LIMIT 10
        """, [clientid])
        rows = cursor.fetchall()
        if rows:
            for r in rows:
                print(f"  type={r[0]}, field={r[1]}, key={r[2]}, value={r[3]}, freq={r[4]}")
        else:
            print("  No expenditure records found.")

if __name__ == "__main__":
    check_real_tables(319197)
