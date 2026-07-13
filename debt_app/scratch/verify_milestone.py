import os
import django
from django.utils import timezone
from datetime import timedelta

# Setup Django environment
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "debt_project.settings")
django.setup()

from django.db import transaction
from debt_app.models import CreditorCriteria, CreditorVoteSummary, CreditorVoteChangeEvent, CreditorNonAcceptMilestone, CrmSyncRun
from debt_app.views.criteria_views import check_non_accept_milestone
from debt_app.helpers import get_london_day_boundary

def main():
    print("Starting milestone detection verification...")

    with transaction.atomic():
        try:
            # Ensure we have a sync run
            sync_run = CrmSyncRun.objects.create(
                status="SUCCESS",
                stage="Done — TEST VERIFICATION RUN, SAFE TO DELETE"
            )

            # Get or create a dummy CreditorCriteria
            creditor_criteria, _ = CreditorCriteria.objects.get_or_create(
                creditor_name="Test Creditor Verification"
            )

            # Get or create a dummy Vote Summary
            vote_summary, _ = CreditorVoteSummary.objects.get_or_create(
                creditor_criteria=creditor_criteria
            )

            # Clean up any existing milestone for today for this vote summary to keep test pure
            _, _, today_date = get_london_day_boundary()
            CreditorNonAcceptMilestone.objects.filter(
                vote_summary=vote_summary,
                milestone_date=today_date
            ).delete()

            # Clean up today's non-accepted events for this summary
            day_start, day_end, _ = get_london_day_boundary()
            CreditorVoteChangeEvent.objects.filter(
                vote_summary=vote_summary,
                detected_at__gte=day_start,
                detected_at__lt=day_end
            ).exclude(status='accepted').delete()

            # Synthesize 3 non-accepted events
            # We will create them with slightly different times to confirm first and third event ordering
            now = timezone.now()
            e1 = CreditorVoteChangeEvent.objects.create(
                vote_summary=vote_summary,
                sync_run=sync_run,
                status="rejected",
            )
            # Force detected_at order if django auto_now_add is set
            e1.detected_at = now - timedelta(minutes=10)
            e1.save()

            e2 = CreditorVoteChangeEvent.objects.create(
                vote_summary=vote_summary,
                sync_run=sync_run,
                status="modified",
            )
            e2.detected_at = now - timedelta(minutes=5)
            e2.save()

            e3 = CreditorVoteChangeEvent.objects.create(
                vote_summary=vote_summary,
                sync_run=sync_run,
                status="rejected",
            )
            e3.detected_at = now
            e3.save()

            # Also let's create a 4th event to ensure only the first 3 are used
            e4 = CreditorVoteChangeEvent.objects.create(
                vote_summary=vote_summary,
                sync_run=sync_run,
                status="pod",
            )
            e4.detected_at = now + timedelta(minutes=5)
            e4.save()

            print(f"Synthesized events: {e1.status} ({e1.detected_at}), {e2.status} ({e2.detected_at}), {e3.status} ({e3.detected_at}), {e4.status} ({e4.detected_at})")

            # First call: should succeed and create a milestone
            milestone1 = check_non_accept_milestone(vote_summary, sync_run)
            if milestone1 is None:
                print("FAIL: check_non_accept_milestone returned None on first call")
                return

            print("SUCCESS: First call created milestone:")
            print(f"  Milestone Date: {milestone1.milestone_date}")
            print(f"  First Event At: {milestone1.first_event_at}")
            print(f"  Third Event At: {milestone1.third_event_at}")
            print(f"  Status Breakdown: {milestone1.status_breakdown}")

            # Assert correct values
            assert milestone1.first_event_at == e1.detected_at, "first_event_at mismatch"
            assert milestone1.third_event_at == e3.detected_at, "third_event_at mismatch"
            assert milestone1.status_breakdown == {"rejected": 2, "modified": 1}, "status_breakdown mismatch"
            print("ASSERTIONS PASSED: first_event_at, third_event_at, and status_breakdown are correct!")

            # Second call: should return None (dedup working)
            milestone2 = check_non_accept_milestone(vote_summary, sync_run)
            if milestone2 is not None:
                print("FAIL: Second call created duplicate milestone!")
                return

            print("SUCCESS: Second call returned None (dedup working)")
        finally:
            transaction.set_rollback(True)
            print("Transaction rolled back successfully.")

if __name__ == "__main__":
    main()
