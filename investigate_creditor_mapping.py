
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "debt_project.settings")
import django
django.setup()

from django.db import connections
from debt_app.models import CreditorCriteria, CouncilRule, CountyCouncil

print("="*80)
print("1. Find row with multiple CRM names (with '|')")
print("="*80)
with open("reconciliation_output/_matched_creditor_raw.json", "r", encoding="utf-8") as f:
    raw_data = json.load(f)

for m in raw_data["matched"]:
    if "|" in m["CRM Creditor Name"]:
        print(f"\nFound row:")
        print(f"  Local Creditor Name: {m['Local Creditor Name']}")
        print(f"  CRM Creditor Name: {m['CRM Creditor Name']}")
        print(f"  Vote Volume: {m['Vote Volume']}")
        target_row = m
        break

print("\n" + "="*80)
print("2. Query aryza DB for those individual CRM names (without GROUP BY)")
print("="*80)
crm_names = [n.strip() for n in target_row["CRM Creditor Name"].split("|")]
print(f"Looking for CRM names: {crm_names}")

cur = connections["aryza"].cursor()
cur.execute("SET SESSION MAX_EXECUTION_TIME=60000")
# Query without grouping to get each individual CRM row
cur.execute("""
    SELECT c.id, c.name,
           SUM(CASE WHEN mra.first_vote = 'rejected' THEN 1 ELSE 0 END) AS rejected,
           SUM(CASE WHEN mra.first_vote = 'accepted' THEN 1 ELSE 0 END) AS accepted,
           SUM(CASE WHEN mra.first_vote = 'modified' THEN 1 ELSE 0 END) AS modified,
           SUM(CASE WHEN mra.first_vote = 'pod' THEN 1 ELSE 0 END) AS pod
    FROM theinsolvencygroup.iva_client_meeting_attendee mra
    INNER JOIN theinsolvencygroup.iva_client_debt cd ON cd.id = mra.attendee_id
    INNER JOIN theinsolvencygroup.creditor c ON c.id = cd.creditorid
    WHERE mra.attendee_type IN ('creditor', 'associate_creditor')
      AND mra.first_vote IN ('accepted', 'rejected', 'modified', 'pod')
    GROUP BY c.id, c.name
    HAVING c.name IN %s
""", (tuple(crm_names),))

crm_individual = []
for cid, name, rejected, accepted, modified, pod in cur.fetchall():
    rejected, accepted, modified, pod = int(rejected), int(accepted), int(modified), int(pod)
    total = rejected + accepted + modified + pod
    crm_individual.append({
        "id": cid, "name": name, "total": total,
        "accepted": accepted, "rejected": rejected
    })

print("\nIndividual CRM rows found:")
sum_total = 0
sum_accepted = 0
sum_rejected = 0
for row in crm_individual:
    print(f"  - Name: {row['name']}, ID: {row['id']}, Total: {row['total']}, Accepted: {row['accepted']}, Rejected: {row['rejected']}")
    sum_total += row['total']
    sum_accepted += row['accepted']
    sum_rejected += row['rejected']

print("\n" + "="*80)
print("3. Compare sum vs Vote Volume")
print("="*80)
print(f"  Sum of individual total votes: {sum_total}")
print(f"  Vote Volume from matched_creditor: {target_row['Vote Volume']}")
print(f"  Matches? {sum_total == target_row['Vote Volume']}")

print("\n" + "="*80)
print("4. Inspect local DB table structure for CreditorCriteria/CouncilRule/CountyCouncil")
print("="*80)
from django.db import connection
with connection.cursor() as cur_local:
    # Check CreditorCriteria columns
    print("\nCreditorCriteria columns:")
    cur_local.execute("PRAGMA table_info(debt_app_creditorcriteria)")
    for row in cur_local.fetchall():
        print(f"  - {row[1]} ({row[2]})")
    # Check if any column contains 'aryza' or 'crm' or 'creditor_id'
    print("\nChecking for CRM/aryza/creditor_id columns in CreditorCriteria:")
    cur_local.execute("PRAGMA table_info(debt_app_creditorcriteria)")
    has_crm_link = False
    for row in cur_local.fetchall():
        col_name = row[1].lower()
        if "crm" in col_name or "aryza" in col_name or "creditor_id" in col_name or "external" in col_name:
            print(f"  Found potential link column: {row[1]}")
            has_crm_link = True
    if not has_crm_link:
        print("  No columns storing CRM creditor_id/aryza foreign key found!")

print("\n" + "="*80)
print("5. Check for existing mapping tables in codebase/models.py")
print("="*80)
from django.apps import apps
all_models = apps.get_models()
for model in all_models:
    model_name = model.__name__.lower()
    if "alias" in model_name or "map" in model_name or "mapping" in model_name or "creditorlink" in model_name:
        print(f"Found potential mapping model: {model.__name__}")
