"""
rebuild_vote_change_events.py
------------------------------------------------------------------------------
Forces every CreditorVoteSummary's CreditorVoteChangeEvent history to be
regenerated from scratch on the next CRM vote sync, using real-vote-date
stamping (see crm_vote_sync.py's _sync_vote_summary / process_local).

Why this is needed
-------------------
_sync_vote_summary() only creates new CreditorVoteChangeEvent rows when a
creditor's vote counts change since the last sync. Events written BEFORE the
real-date-stamping fix carry the sync run's wall-clock time as detected_at,
not the vote's actual meeting_date - for representative creditors (WATCH/TIX/
EVOLVE) that aggregate many underlying real creditors, this can make
last_5_tally disagree with latest_vote_outcome even though neither value is
individually wrong. Those pre-fix events aren't "tainted clusters" (they don't
share an identical instant - see cleanup_tainted_vote_events), so nothing
short of regenerating them will correct the ordering. Deltas only fire when
counts move, so simply waiting for future syncs won't touch a creditor whose
vote counts have stopped changing.

What this does
---------------
For each targeted CreditorVoteSummary:
  1. Delete its existing CreditorVoteChangeEvent rows (they can't be trusted
     to reflect real vote chronology).
  2. Zero its count fields (accepted/rejected/modified/pod/total_votes).
This does NOT touch latest_vote_outcome/latest_vote_date (already correct,
computed fresh from CRM every sync) or any other summary field.

The next `sync_creditor_vote_summaries` run then sees every current vote as
a "new" delta (old count 0 vs. true current count) and recreates the full
event history in one pass, each status stamped with its own real latest
meeting_date via vote_data["latest_date_by_status"] - restoring correct
cross-status ordering.

Usage
-----
  python manage.py rebuild_vote_change_events --dry-run
  python manage.py rebuild_vote_change_events                 # all creditors
  python manage.py rebuild_vote_change_events --creditor-name "Lantern"
  python manage.py sync_creditor_vote_summaries                # then re-sync
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from debt_app.models import CreditorVoteChangeEvent, CreditorVoteSummary


class Command(BaseCommand):
    help = (
        "Delete CreditorVoteChangeEvent history and zero vote counts for the "
        "targeted CreditorVoteSummary rows, so the next CRM vote sync rebuilds "
        "them from scratch with real-vote-date-stamped events."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print what would be reset without making any changes.",
        )
        parser.add_argument(
            "--creditor-name",
            default=None,
            help=(
                "Only reset summaries whose linked creditor/council/county name "
                "contains this substring (case-insensitive). Omit to target all "
                "CreditorVoteSummary rows."
            ),
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        name_filter = options["creditor_name"]
        w = self.stdout.write
        style = self.style

        if dry_run:
            w(style.WARNING("DRY RUN - no changes will be made\n"))

        qs = CreditorVoteSummary.objects.all()
        if name_filter:
            from django.db.models import Q
            qs = qs.filter(
                Q(creditor_criteria__creditor_name__icontains=name_filter)
                | Q(council_rule__council_name__icontains=name_filter)
                | Q(county_council__county_name__icontains=name_filter)
            )

        summaries = list(qs)
        if not summaries:
            w(style.SUCCESS("No matching CreditorVoteSummary rows found.\n"))
            return

        w(f"Targeting {len(summaries)} CreditorVoteSummary row(s):")
        total_events = 0
        for s in summaries:
            event_count = CreditorVoteChangeEvent.objects.filter(vote_summary=s).count()
            total_events += event_count
            label = s.creditor_criteria or s.council_rule or s.county_council
            w(
                f"  {label!s}: {event_count} event(s), current counts "
                f"accepted={s.accepted_count} rejected={s.rejected_count} "
                f"modified={s.modified_count} pod={s.pod_count}"
            )

        w(f"\nTotal CreditorVoteChangeEvent rows to delete: {total_events}")

        if dry_run:
            w(style.WARNING(
                "\n[DRY RUN] Would delete the above events and zero vote counts. "
                "Re-run without --dry-run to apply, then run "
                "sync_creditor_vote_summaries to rebuild.\n"
            ))
            return

        with transaction.atomic():
            deleted, _ = CreditorVoteChangeEvent.objects.filter(vote_summary__in=summaries).delete()
            updated = CreditorVoteSummary.objects.filter(
                pk__in=[s.pk for s in summaries]
            ).update(accepted_count=0, rejected_count=0, modified_count=0, pod_count=0, total_votes=0)

        w(style.SUCCESS(f"\nDeleted {deleted} event row(s). Reset counts on {updated} summary row(s)."))
        w(style.WARNING(
            "\nNow run: python manage.py sync_creditor_vote_summaries\n"
            "to rebuild each summary's history with real-vote-date-stamped events."
        ))
