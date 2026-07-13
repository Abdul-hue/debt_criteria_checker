import os
import django
from django.utils import timezone
from datetime import timedelta

# Setup Django environment
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "debt_project.settings")
django.setup()

from django.db import transaction
from django.core import mail
from django.test import override_settings
from debt_app.models import (
    CreditorCriteria,
    CreditorVoteSummary,
    CreditorVoteChangeEvent,
    CreditorNonAcceptMilestone,
    CrmSyncRun
)
from debt_app.services.crm_vote_sync import check_and_send_non_accept_milestones
from debt_app.helpers import get_london_day_boundary

@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
def main():
    print("Starting end-to-end milestone email verification...")

    with transaction.atomic():
        try:
            # 1. Create a dummy sync run
            sync_run = CrmSyncRun.objects.create(
                status="SUCCESS",
                stage="Done — TEST VERIFICATION RUN, SAFE TO DELETE"
            )

            # 2. Get or create a dummy CreditorCriteria with identifying details
            creditor_criteria, _ = CreditorCriteria.objects.get_or_create(
                creditor_name="Test Creditor Milestone Corp",
                representative="NONE",
                min_dividend_pence=10,
                source_sheet="DIVIDEND"
            )

            # 3. Get or create a dummy Vote Summary
            vote_summary, _ = CreditorVoteSummary.objects.get_or_create(
                creditor_criteria=creditor_criteria
            )

            # Clean up any existing milestone for today for this vote summary
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

            # 4. Synthesize 3 non-accepted events during this run within the day start/end
            now = timezone.now()
            # Spread events across different times to test ordering
            e1 = CreditorVoteChangeEvent.objects.create(
                vote_summary=vote_summary,
                sync_run=sync_run,
                status="rejected",
            )
            e1.detected_at = now - timedelta(minutes=30)
            e1.save()

            e2 = CreditorVoteChangeEvent.objects.create(
                vote_summary=vote_summary,
                sync_run=sync_run,
                status="modified",
            )
            e2.detected_at = now - timedelta(minutes=15)
            e2.save()

            e3 = CreditorVoteChangeEvent.objects.create(
                vote_summary=vote_summary,
                sync_run=sync_run,
                status="rejected",
            )
            e3.detected_at = now
            e3.save()

            # Confirm events created successfully
            print("Synthesized events:")
            for e in [e1, e2, e3]:
                print(f"  - ID: {e.id}, status: {e.status}, detected_at: {e.detected_at}")

            # Clear any emails in the outbox
            mail.outbox = []

            # 5. Run the wired-up pathway
            milestones = check_and_send_non_accept_milestones(sync_run)
            print(f"Successfully processed milestone check. Created {len(milestones)} milestones.")

            # 6. Verify Email Output
            if not mail.outbox:
                print("FAIL: No emails were sent!")
                return

            email = mail.outbox[0]
            print("\nCaptured Rendered Email Details:")
            print(f"Subject: {email.subject}")
            print("Body:")
            print(email.body)
            print("-" * 40)

            # 7. Assert email content details
            # Localize times for assertions
            first_event_local = timezone.localtime(e1.detected_at).strftime("%d/%m/%Y %H:%M:%S")
            third_event_local = timezone.localtime(e3.detected_at).strftime("%d/%m/%Y %H:%M:%S")

            assert "Test Creditor Milestone Corp" in email.body, "Creditor name not in email body!"
            assert "Dividend creditor" in email.body, "Creditor tags not in email body!"
            assert "This creditor has achieved 3 non-accepted votes (1 modified, 2 rejected)" in email.body, "Status breakdown sentence mismatch!"
            assert first_event_local in email.body, "First event time not in email body!"
            assert third_event_local in email.body, "Third event time not in email body!"
            assert "MOC Milestone Alert" in email.subject, "Subject line is incorrect!"

            print("\nALL ASSERTIONS PASSED SUCCESSFULLY!")

        finally:
            transaction.set_rollback(True)
            print("Database transaction rolled back safely.")

if __name__ == "__main__":
    main()
