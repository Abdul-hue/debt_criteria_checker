"""
cleanup_tainted_vote_events.py
------------------------------------------------------------------------------
Deletes CreditorVoteChangeEvent rows created by the pre-fix backfill bug in
_sync_vote_summary() (debt_app/services/crm_vote_sync.py).

Background
----------
Before the fix, a CreditorVoteSummary's FIRST-EVER sync treated its entire
existing CRM vote history as a "delta" (old counts were 0 by definition) and
bulk-created one CreditorVoteChangeEvent per vote, all sharing the same
detected_at instant. get_last_5_tally() orders by -detected_at with no
secondary tiebreak, so among same-instant rows the last-inserted status
(pod, then modified - see VOTE_OUTCOME_CHOICES order) sorted as "most
recent", even when the true latest vote (from CRM meeting_date data,
recorded separately in latest_vote_outcome/latest_vote_date) was something
else entirely. This produced last_5_tally sequences that contradicted
latest_vote_outcome.

This command deletes rows that are part of any (vote_summary, detected_at)
cluster with more than one row - those are exactly the batches that could
only have come from the backfill bug (a single real vote transition is
logged as exactly one row per sync run). Singleton-timestamp rows (real,
one-at-a-time incremental updates) are left untouched.

After cleanup, affected creditors' last_5_tally will read 0/0 (no data)
until the next real CRM vote sync records genuine incremental events -
that's expected and correct; it replaces fabricated history with "no
history" until real data accumulates again.

Usage
-----
  python manage.py cleanup_tainted_vote_events --dry-run
  python manage.py cleanup_tainted_vote_events
"""

from collections import defaultdict

from django.core.management.base import BaseCommand
from django.db.models import Count

from debt_app.models import CreditorVoteChangeEvent


class Command(BaseCommand):
    help = (
        "Delete CreditorVoteChangeEvent rows from the pre-fix backfill bug: "
        "any (vote_summary, detected_at) cluster with more than one row."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print what would be deleted without making any changes.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        w = self.stdout.write
        style = self.style

        if dry_run:
            w(style.WARNING("DRY RUN - no changes will be made\n"))

        total_before = CreditorVoteChangeEvent.objects.count()
        w(f"Total CreditorVoteChangeEvent rows: {total_before}")

        # Find (vote_summary_id, detected_at) clusters with >1 row.
        tainted_clusters = (
            CreditorVoteChangeEvent.objects.values("vote_summary_id", "detected_at")
            .annotate(n=Count("id"))
            .filter(n__gt=1)
        )
        tainted_clusters = list(tainted_clusters)

        if not tainted_clusters:
            w(style.SUCCESS("No tainted (same-instant, multi-row) clusters found - nothing to clean up.\n"))
            return

        affected_summaries = set()
        ids_to_delete = []
        cluster_sizes = defaultdict(int)

        for cluster in tainted_clusters:
            vs_id = cluster["vote_summary_id"]
            ts = cluster["detected_at"]
            affected_summaries.add(vs_id)
            row_ids = list(
                CreditorVoteChangeEvent.objects.filter(
                    vote_summary_id=vs_id, detected_at=ts
                ).values_list("id", flat=True)
            )
            ids_to_delete.extend(row_ids)
            cluster_sizes[vs_id] += len(row_ids)

        w(f"Vote summaries with tainted clusters: {len(affected_summaries)}")
        w(f"Rows to delete: {len(ids_to_delete)}")
        w("")
        w("Breakdown by vote_summary_id (rows to delete):")
        for vs_id, count in sorted(cluster_sizes.items(), key=lambda kv: -kv[1]):
            w(f"  vote_summary_id={vs_id}: {count} row(s)")

        if dry_run:
            w(style.WARNING(f"\n[DRY RUN] Would delete {len(ids_to_delete)} row(s). Re-run without --dry-run to apply.\n"))
            return

        deleted, _ = CreditorVoteChangeEvent.objects.filter(id__in=ids_to_delete).delete()
        remaining = CreditorVoteChangeEvent.objects.count()
        w(style.SUCCESS(f"\nDeleted {deleted} row(s)."))
        w(f"Remaining CreditorVoteChangeEvent rows: {remaining}")
        w(
            "\nAffected creditors will show last_5_tally as 0/0 (no data) until "
            "the next real CRM vote sync records genuine incremental events."
        )
