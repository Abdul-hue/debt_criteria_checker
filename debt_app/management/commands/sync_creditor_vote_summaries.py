import os
import re
from datetime import datetime
from django.core.management.base import BaseCommand
from django.db import transaction, connections
from django.conf import settings
from debt_app.models import (
    CreditorCriteria,
    CouncilRule,
    CountyCouncil,
    CreditorVoteSummary,
)
from debt_app.helpers import normalise_creditor_name, CREDITOR_ALIAS_MAP


class Command(BaseCommand):
    help = "Sync CRM vote summaries to CreditorVoteSummary model"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print what would be changed without writing to the database.",
        )
        parser.add_argument(
            "--log-file",
            type=str,
            default=os.path.join(settings.BASE_DIR, "creditor_vote_sync.log"),
            help="Path to the log file for audit purposes.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        log_file = options["log_file"]

        # Initialize log file
        if not dry_run:
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(f"\n=== Sync started at {datetime.now().isoformat()} ===\n")

        try:
            # Step 1: Fetch CRM vote data (placeholder — replace with actual CRM data retrieval)
            crm_vote_data = self._fetch_crm_vote_data()

            # Step 2: Process and sync data for each creditor type
            with transaction.atomic():
                self._sync_creditor_criteria(crm_vote_data, dry_run, log_file)
                self._sync_council_rules(crm_vote_data, dry_run, log_file)
                self._sync_county_councils(crm_vote_data, dry_run, log_file)

            self.stdout.write(self.style.SUCCESS("Sync completed successfully!"))

        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Error during sync: {e}"))
            raise

    def extract_tie_segments(self, name):
        segments = []

        for part in re.split(r"\s+t/a\s+|\s+trading as\s+", name, flags=re.IGNORECASE):
            segments.append(part)

        for part in re.split(r"\s+c/o\s+", name, flags=re.IGNORECASE):
            segments.append(part)

        for part in re.split(r"\bformerly\b", name, flags=re.IGNORECASE):
            segments.append(part)

        for m in re.finditer(r"\(([^)]+)\)", name):
            segments.append(m.group(1))
        no_paren = re.sub(r"\s*\([^)]*\)", "", name).strip()
        if no_paren:
            segments.append(no_paren)

        for part in re.split(r"\s+/\s+", name):
            segments.append(part)

        cleaned = []
        for s in segments:
            s = s.strip()
            if s and len(s) >= 3:
                cleaned.append(s)
        return cleaned

    def key_of(self, s):
        return s.strip().lower()

    def strip_county_council_suffix(self, name):
        s = re.sub(r"\s*\([^)]*\)\s*$", "", name).strip()
        s = re.sub(r"\s+county council$", "", s, flags=re.IGNORECASE).strip()
        return s

    def _fetch_crm_vote_data(self):
        """
        Fetch CRM vote data and return a structured dictionary mapping creditor names
        (for all 3 types) to their vote summary data.
        """
        self.stdout.write("Fetching CRM vote data...")

        # Step 1: Fetch aggregate vote counts per creditor
        cursor = connections["aryza"].cursor()
        cursor.execute("SET SESSION MAX_EXECUTION_TIME=120000")
        cursor.execute("""
            SELECT 
                c.id, 
                c.name,
                SUM(CASE WHEN mra.first_vote = 'rejected' THEN 1 ELSE 0 END) AS rejected_count,
                SUM(CASE WHEN mra.first_vote = 'accepted' THEN 1 ELSE 0 END) AS accepted_count,
                SUM(CASE WHEN mra.first_vote = 'modified' THEN 1 ELSE 0 END) AS modified_count,
                SUM(CASE WHEN mra.first_vote = 'pod' THEN 1 ELSE 0 END) AS pod_count,
                SUM(CASE WHEN mra.first_vote IN ('accepted', 'rejected', 'modified', 'pod') THEN 1 ELSE 0 END) AS total_votes
            FROM theinsolvencygroup.iva_client_meeting_attendee mra
            INNER JOIN theinsolvencygroup.iva_client_debt cd ON cd.id = mra.attendee_id
            INNER JOIN theinsolvencygroup.creditor c ON c.id = cd.creditorid
            WHERE mra.attendee_type IN ('creditor', 'associate_creditor')
              AND mra.first_vote IN ('accepted', 'rejected', 'modified', 'pod')
            GROUP BY c.id, c.name
        """)

        crm_aggregate = {}
        for crm_id, name, rejected_count, accepted_count, modified_count, pod_count, total_votes in cursor.fetchall():
            crm_aggregate[crm_id] = {
                "crm_id": crm_id,
                "name": name,
                "accepted_count": accepted_count,
                "rejected_count": rejected_count,
                "modified_count": modified_count,
                "pod_count": pod_count,
                "total_votes": total_votes,
            }

        # Step 2: Fetch all individual vote rows with dates for latest vote calculation
        cursor.execute("""
            SELECT 
                c.id,
                m.meeting_date,
                mra.first_vote
            FROM theinsolvencygroup.iva_client_meeting_attendee mra
            INNER JOIN theinsolvencygroup.iva_client_debt cd ON cd.id = mra.attendee_id
            INNER JOIN theinsolvencygroup.creditor c ON c.id = cd.creditorid
            INNER JOIN theinsolvencygroup.iva_client_meeting m ON m.id = mra.iva_client_meeting_id
            WHERE mra.attendee_type IN ('creditor', 'associate_creditor')
              AND mra.first_vote IN ('accepted', 'rejected', 'modified', 'pod')
        """)

        crm_vote_rows_by_id = {crm_id: {**data, "vote_rows": []} for crm_id, data in crm_aggregate.items()}
        from datetime import datetime
        for crm_id, meeting_date_ts, first_vote in cursor.fetchall():
            if crm_id in crm_vote_rows_by_id and meeting_date_ts and first_vote:
                try:
                    meeting_date = datetime.fromtimestamp(meeting_date_ts).date()
                except (ValueError, TypeError, OverflowError):
                    meeting_date = None
                crm_vote_rows_by_id[crm_id]["vote_rows"].append({
                    "meeting_date": meeting_date,
                    "first_vote": first_vote
                })
        crm_rows = list(crm_vote_rows_by_id.values())

        # Step 3: Build CRM indexes for O(1) lookups
        crm_exact_index = {}
        crm_norm_index = {}
        crm_tie_index = {}
        crm_alias_index = {}
        crm_county_suffix_index = {}
        crm_by_id = {r["crm_id"]: r for r in crm_rows}

        for row in crm_rows:
            ek = self.key_of(row["name"])
            crm_exact_index.setdefault(ek, []).append(row)

            nk = normalise_creditor_name(row["name"])
            if nk:
                crm_norm_index.setdefault(nk, []).append(row)

            for seg in self.extract_tie_segments(row["name"]):
                sk = self.key_of(seg)
                if sk == ek:
                    continue
                crm_tie_index.setdefault(sk, []).append(row)

            alias_target = CREDITOR_ALIAS_MAP.get(nk)
            if alias_target:
                crm_alias_index.setdefault(self.key_of(alias_target), []).append(row)

            stripped = self.strip_county_council_suffix(row["name"])
            if stripped and self.key_of(stripped) != ek:
                crm_county_suffix_index.setdefault(self.key_of(stripped), []).append(row)

        # Step 4: Prepare result structure
        result = {
            "creditor_criteria": {},
            "council_rule": {},
            "county_council": {},
        }

        # Helper to process a local creditor and get matched CRM creditors
        def process_local(name, is_county_council=False):
            ek = self.key_of(name)
            nk = normalise_creditor_name(name)

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
            if is_county_council:
                for r in crm_county_suffix_index.get(ek, []):
                    hits[r["crm_id"]] = True
            matched_ids = list(hits.keys())
            if not matched_ids:
                return None
            matched_crm = [crm_by_id[cid] for cid in matched_ids]

            total_votes = 0
            accepted_count = 0
            rejected_count = 0
            modified_count = 0
            pod_count = 0
            all_vote_rows = []
            for crm in matched_crm:
                total_votes += crm["total_votes"]
                accepted_count += crm["accepted_count"]
                rejected_count += crm["rejected_count"]
                modified_count += crm["modified_count"]
                pod_count += crm["pod_count"]
                all_vote_rows.extend(crm["vote_rows"])

            # Find latest vote
            latest_vote_date = None
            latest_vote_outcome = None
            if all_vote_rows:
                # Sort by meeting_date descending (handle possible None dates)
                sorted_votes = sorted(all_vote_rows, key=lambda x: (x["meeting_date"] is None, x["meeting_date"]), reverse=True)
                latest = sorted_votes[0]
                latest_vote_date = latest["meeting_date"]
                latest_vote_outcome = latest["first_vote"]

            return {
                "total_votes": total_votes,
                "accepted_count": accepted_count,
                "rejected_count": rejected_count,
                "modified_count": modified_count,
                "pod_count": pod_count,
                "latest_vote_date": latest_vote_date,
                "latest_vote_outcome": latest_vote_outcome,
                "crm_rows_covered": len(matched_ids),
            }

        # Process CreditorCriteria
        self.stdout.write("Processing CreditorCriteria...")
        for creditor in CreditorCriteria.objects.filter(is_active=True):
            summary = process_local(creditor.creditor_name, is_county_council=False)
            if summary:
                result["creditor_criteria"][creditor.creditor_name] = summary

        # Process CouncilRule
        self.stdout.write("Processing CouncilRule...")
        for council in CouncilRule.objects.all():
            summary = process_local(council.council_name, is_county_council=False)
            if summary:
                result["council_rule"][council.council_name] = summary

        # Process CountyCouncil
        self.stdout.write("Processing CountyCouncil...")
        for county in CountyCouncil.objects.all():
            summary = process_local(county.county_name, is_county_council=True)
            if summary:
                result["county_council"][county.county_name] = summary

        self.stdout.write(self.style.SUCCESS("CRM vote data fetched successfully!"))
        return result

    def _sync_creditor_criteria(self, crm_data, dry_run, log_file):
        """Sync CreditorVoteSummary for CreditorCriteria records."""
        for name, vote_data in crm_data.get("creditor_criteria", {}).items():
            try:
                creditor = CreditorCriteria.objects.get(creditor_name=name)
                self._sync_vote_summary(
                    creditor_type="creditor_criteria",
                    creditor_obj=creditor,
                    vote_data=vote_data,
                    dry_run=dry_run,
                    log_file=log_file,
                )
            except CreditorCriteria.DoesNotExist:
                self.stdout.write(self.style.WARNING(f"CreditorCriteria not found: {name}"))
                continue

    def _sync_council_rules(self, crm_data, dry_run, log_file):
        """Sync CreditorVoteSummary for CouncilRule records."""
        for name, vote_data in crm_data.get("council_rule", {}).items():
            try:
                council = CouncilRule.objects.get(council_name=name)
                self._sync_vote_summary(
                    creditor_type="council_rule",
                    creditor_obj=council,
                    vote_data=vote_data,
                    dry_run=dry_run,
                    log_file=log_file,
                )
            except CouncilRule.DoesNotExist:
                self.stdout.write(self.style.WARNING(f"CouncilRule not found: {name}"))
                continue

    def _sync_county_councils(self, crm_data, dry_run, log_file):
        """Sync CreditorVoteSummary for CountyCouncil records."""
        for name, vote_data in crm_data.get("county_council", {}).items():
            try:
                county = CountyCouncil.objects.get(county_name=name)
                self._sync_vote_summary(
                    creditor_type="county_council",
                    creditor_obj=county,
                    vote_data=vote_data,
                    dry_run=dry_run,
                    log_file=log_file,
                )
            except CountyCouncil.DoesNotExist:
                self.stdout.write(self.style.WARNING(f"CountyCouncil not found: {name}"))
                continue

    def _sync_vote_summary(self, creditor_type, creditor_obj, vote_data, dry_run, log_file):
        """
        Create or update a CreditorVoteSummary record for the given creditor object.
        """
        # Get the existing summary if it exists
        lookup_kwargs = {creditor_type: creditor_obj}
        summary, created = CreditorVoteSummary.objects.get_or_create(**lookup_kwargs)

        # Prepare old values for logging/dry-run
        old_values = {
            "total_votes": summary.total_votes,
            "accepted_count": summary.accepted_count,
            "rejected_count": summary.rejected_count,
            "modified_count": summary.modified_count,
            "pod_count": summary.pod_count,
            "latest_vote_date": summary.latest_vote_date,
            "latest_vote_outcome": summary.latest_vote_outcome,
            "crm_rows_covered": summary.crm_rows_covered,
        }

        # Prepare new values from vote_data
        new_values = {
            "total_votes": vote_data.get("total_votes", 0),
            "accepted_count": vote_data.get("accepted_count"),
            "rejected_count": vote_data.get("rejected_count"),
            "modified_count": vote_data.get("modified_count"),
            "pod_count": vote_data.get("pod_count"),
            "latest_vote_date": vote_data.get("latest_vote_date"),
            "latest_vote_outcome": vote_data.get("latest_vote_outcome"),
            "crm_rows_covered": vote_data.get("crm_rows_covered", 1),
        }

        # Check if changes are needed
        changes = {}
        for key, old_val in old_values.items():
            new_val = new_values[key]
            if old_val != new_val:
                changes[key] = (old_val, new_val)

        creditor_name = str(creditor_obj)
        if changes:
            # Log/dry-run output
            if dry_run:
                self.stdout.write(self.style.NOTICE(f"  [DRY-RUN] Would update {creditor_type}: {creditor_name}"))
                for key, (old, new) in changes.items():
                    self.stdout.write(f"    {key}: {old} -> {new}")
            else:
                # Update the summary
                for key, value in new_values.items():
                    setattr(summary, key, value)
                summary.save()
                self._log_change(log_file, creditor_type, creditor_name, old_values, new_values)
                self.stdout.write(self.style.SUCCESS(f"  Updated {creditor_type}: {creditor_name}"))
        elif created:
            # New record created with default values
            if dry_run:
                self.stdout.write(self.style.NOTICE(f"  [DRY-RUN] Would create {creditor_type}: {creditor_name}"))
            else:
                self._log_change(log_file, creditor_type, creditor_name, {}, new_values)
                self.stdout.write(self.style.SUCCESS(f"  Created {creditor_type}: {creditor_name}"))
        else:
            # No changes needed
            self.stdout.write(f"  No changes for {creditor_type}: {creditor_name}")

    def _log_change(self, log_file, creditor_type, creditor_name, old_values, new_values):
        """Write a change entry to the audit log file."""
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now().isoformat()}] {creditor_type} - {creditor_name}\n")
            f.write(f"  OLD: {old_values}\n")
            f.write(f"  NEW: {new_values}\n")
            f.write("---\n")
