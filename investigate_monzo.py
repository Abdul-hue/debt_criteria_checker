
import os
import sys
import django
from django.db import connections

# Set up Django
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "debt_project.settings")
django.setup()

from debt_app.models import CreditorCriteria
from debt_app.management.commands.sync_creditor_vote_summaries import Command
from debt_app.helpers import normalise_creditor_name, CREDITOR_ALIAS_MAP


def main():
    print("=" * 80)
    print("1. Find local Monzo creditor")
    print("=" * 80)
    try:
        monzo = CreditorCriteria.objects.get(creditor_name="Monzo")
        print(f"Found local creditor: {monzo.creditor_name}")
    except CreditorCriteria.DoesNotExist:
        print("ERROR: Local Monzo creditor not found!")
        return

    print("\n" + "=" * 80)
    print("2. Fetch CRM data using sync command's _fetch_crm_vote_data()")
    print("=" * 80)
    cmd = Command()
    crm_data = cmd._fetch_crm_vote_data()
    monzo_vote_data = crm_data.get("creditor_criteria", {}).get("Monzo")
    if monzo_vote_data:
        print(f"Vote data found: {monzo_vote_data}")
    else:
        print("ERROR: No vote data found for Monzo!")

    print("\n" + "=" * 80)
    print("3. Get ALL CRM creditors from crm_data and search for Monzo matches")
    print("=" * 80)
    # Let's manually run the process_local logic for Monzo
    # First, let's get all CRM rows by recreating the indexes
    crm_exact_index = {}
    crm_norm_index = {}
    crm_tie_index = {}
    crm_alias_index = {}
    crm_county_suffix_index = {}
    crm_by_id = {}

    # We need to re-execute the queries to get all CRM data again for more details
    cursor = connections["aryza"].cursor()
    cursor.execute("SET SESSION MAX_EXECUTION_TIME=120000")
    cursor.execute("""
        SELECT 
            c.id, 
            c.name,
            SUM(CASE WHEN mra.first_vote = 'rejected' THEN 1 ELSE 0 END) AS rejected_count,
            SUM(CASE WHEN mra.first_vote = 'accepted' THEN 1 ELSE 0 END) AS accepted_count,
            SUM(CASE WHEN mra.first_vote IN ('accepted', 'rejected', 'modified', 'pod') THEN 1 ELSE 0 END) AS total_votes
        FROM theinsolvencygroup.iva_client_meeting_attendee mra
        INNER JOIN theinsolvencygroup.iva_client_debt cd ON cd.id = mra.attendee_id
        INNER JOIN theinsolvencygroup.creditor c ON c.id = cd.creditorid
        WHERE mra.attendee_type IN ('creditor', 'associate_creditor')
          AND mra.first_vote IN ('accepted', 'rejected', 'modified', 'pod')
        GROUP BY c.id, c.name
    """)
    crm_aggregate = {}
    for crm_id, name, rejected_count, accepted_count, total_votes in cursor.fetchall():
        crm_aggregate[crm_id] = {
            "crm_id": crm_id,
            "name": name,
            "accepted_count": accepted_count,
            "rejected_count": rejected_count,
            "total_votes": total_votes,
        }
        crm_by_id[crm_id] = crm_aggregate[crm_id]
        # Build indexes
        ek = cmd.key_of(name)
        crm_exact_index.setdefault(ek, []).append(crm_aggregate[crm_id])
        nk = normalise_creditor_name(name)
        if nk:
            crm_norm_index.setdefault(nk, []).append(crm_aggregate[crm_id])
        for seg in cmd.extract_tie_segments(name):
            sk = cmd.key_of(seg)
            if sk == ek:
                continue
            crm_tie_index.setdefault(sk, []).append(crm_aggregate[crm_id])
        alias_target = CREDITOR_ALIAS_MAP.get(nk)
        if alias_target:
            crm_alias_index.setdefault(cmd.key_of(alias_target), []).append(crm_aggregate[crm_id])
        stripped = cmd.strip_county_council_suffix(name)
        if stripped and cmd.key_of(stripped) != ek:
            crm_county_suffix_index.setdefault(cmd.key_of(stripped), []).append(crm_aggregate[crm_id])

    # Now find matches for Monzo
    local_name = "Monzo"
    ek = cmd.key_of(local_name)
    nk = normalise_creditor_name(local_name)
    hits = {}
    for r in crm_exact_index.get(ek, []):
        hits[r["crm_id"]] = True
    if nk:
        for r in crm_norm_index.get(nk, []):
            hits[r["crm_id"]] = True
    for r in crm_alias_index.get(ek, []):
        hits[r["crm_id"]] = True
    for r in crm_tie_index.get(ek, []):
        hits[r["crm_id"]] = True
    matched_ids = list(hits.keys())
    print(f"Matched CRM IDs: {matched_ids}")
    for crm_id in matched_ids:
        print(f"  - {crm_by_id[crm_id]}")

    print("\n" + "=" * 80)
    print("4. Raw per-row data (unaggregated) for matched CRM creditors")
    print("=" * 80)
    if matched_ids:
        placeholders = ", ".join(["%s"] * len(matched_ids))
        cursor.execute("""
            SELECT 
                c.id, 
                c.name,
                mra.first_vote,
                m.meeting_date
            FROM theinsolvencygroup.iva_client_meeting_attendee mra
            INNER JOIN theinsolvencygroup.iva_client_debt cd ON cd.id = mra.attendee_id
            INNER JOIN theinsolvencygroup.creditor c ON c.id = cd.creditorid
            INNER JOIN theinsolvencygroup.iva_client_meeting m ON m.id = mra.iva_client_meeting_id
            WHERE mra.attendee_type IN ('creditor', 'associate_creditor')
              AND c.id IN (%s)
        """ % placeholders, matched_ids)
        raw_rows = cursor.fetchall()
        print(f"Found {len(raw_rows)} raw rows")
        total_accepted = 0
        total_rejected = 0
        total_modified = 0
        total_pod = 0
        for row in raw_rows:
            crm_id, crm_name, vote, meeting_date = row
            print(f"  - {crm_name} (ID: {crm_id}): {vote} on {meeting_date}")
            if vote == "accepted":
                total_accepted +=1
            elif vote == "rejected":
                total_rejected +=1
            elif vote == "modified":
                total_modified +=1
            elif vote == "pod":
                total_pod +=1
        print(f"\nRaw totals:")
        print(f"  accepted: {total_accepted}")
        print(f"  rejected: {total_rejected}")
        print(f"  modified: {total_modified}")
        print(f"  pod: {total_pod}")
        print(f"  TOTAL (sum of above): {total_accepted + total_rejected + total_modified + total_pod}")


if __name__ == "__main__":
    main()
