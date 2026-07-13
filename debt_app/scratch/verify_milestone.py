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
from debt_app.services.crm_vote_sync import _send_non_accept_milestone_email
from debt_app.helpers import get_london_day_boundary


def _clear_today(vote_summary, today_date, day_start, day_end):
    CreditorNonAcceptMilestone.objects.filter(
        vote_summary=vote_summary,
        milestone_date=today_date
    ).delete()
    CreditorVoteChangeEvent.objects.filter(
        vote_summary=vote_summary,
        detected_at__gte=day_start,
        detected_at__lt=day_end
    ).delete()


def main():
    print("Starting per-status milestone detection verification...")

    with transaction.atomic():
        try:
            sync_run = CrmSyncRun.objects.create(
                status="SUCCESS",
                stage="Done — TEST VERIFICATION RUN, SAFE TO DELETE"
            )

            creditor_criteria, _ = CreditorCriteria.objects.get_or_create(
                creditor_name="Test Creditor Verification"
            )
            vote_summary, _ = CreditorVoteSummary.objects.get_or_create(
                creditor_criteria=creditor_criteria
            )

            day_start, day_end, today_date = get_london_day_boundary()
            _clear_today(vote_summary, today_date, day_start, day_end)

            now = timezone.now()

            # --- Scenario 1: 3 rejected + 1 modified (modified must NOT trigger) ---
            r1 = CreditorVoteChangeEvent.objects.create(vote_summary=vote_summary, sync_run=sync_run, status="rejected")
            r1.detected_at = now - timedelta(minutes=20); r1.save()

            m1 = CreditorVoteChangeEvent.objects.create(vote_summary=vote_summary, sync_run=sync_run, status="modified")
            m1.detected_at = now - timedelta(minutes=15); m1.save()

            r2 = CreditorVoteChangeEvent.objects.create(vote_summary=vote_summary, sync_run=sync_run, status="rejected")
            r2.detected_at = now - timedelta(minutes=10); r2.save()

            r3 = CreditorVoteChangeEvent.objects.create(vote_summary=vote_summary, sync_run=sync_run, status="rejected")
            r3.detected_at = now - timedelta(minutes=5); r3.save()

            print(f"Scenario 1 events: rejected@{r1.detected_at}, modified@{m1.detected_at}, "
                  f"rejected@{r2.detected_at}, rejected@{r3.detected_at}")

            created = check_non_accept_milestone(vote_summary, sync_run)
            print(f"First call created {len(created)} milestone(s): {[ (c.status, c.count) for c in created ]}")

            assert len(created) == 1, f"Expected exactly 1 milestone, got {len(created)}"
            milestone = created[0]
            assert milestone.status == "rejected", f"Expected status='rejected', got {milestone.status!r}"
            assert milestone.count == 3, f"Expected count=3, got {milestone.count}"
            assert milestone.first_event_at == r1.detected_at, "first_event_at mismatch"
            assert milestone.third_event_at == r3.detected_at, "third_event_at mismatch"
            print("ASSERTIONS PASSED: exactly one 'rejected' milestone, count=3, correct first/third timestamps.")

            # Confirm no milestone exists for 'modified' yet (only 1 modified event so far)
            assert not CreditorNonAcceptMilestone.objects.filter(
                vote_summary=vote_summary, milestone_date=today_date, status="modified"
            ).exists(), "FAIL: a 'modified' milestone should not exist yet"
            print("CONFIRMED: no premature 'modified' milestone.")

            # Repeat call same day: rejected must not re-trigger (unique constraint / dedup)
            created_again = check_non_accept_milestone(vote_summary, sync_run)
            assert created_again == [], f"Expected no new milestones on repeat call, got {created_again}"
            print("CONFIRMED: repeat call creates no duplicate 'rejected' milestone (per-status uniqueness holds).")

            # Render the email content for scenario 1 and check the sentence
            import debt_app.services.crm_vote_sync as sync_mod
            sent_bodies = []
            original_send_mail = sync_mod.send_mail

            def fake_send_mail(subject, message, from_email, recipient_list):
                sent_bodies.append((subject, message))

            sync_mod.send_mail = fake_send_mail
            try:
                _send_non_accept_milestone_email(created)
            finally:
                sync_mod.send_mail = original_send_mail

            assert len(sent_bodies) == 1, "Expected exactly one email to be sent"
            subject, body = sent_bodies[0]
            print("\n--- EMAIL SUBJECT ---")
            print(subject)
            print("--- EMAIL BODY ---")
            print(body)

            expected_sentence = (
                f"This creditor has achieved 3 rejected between "
                f"{timezone.localtime(r1.detected_at).strftime('%d/%m/%Y %H:%M:%S')} and "
                f"{timezone.localtime(r3.detected_at).strftime('%d/%m/%Y %H:%M:%S')}"
            )
            assert expected_sentence in body, f"Expected sentence not found in email body:\n{expected_sentence}"
            assert "modified" not in body.lower(), "Email must not mention the unrelated modified event"
            print("ASSERTIONS PASSED: email sentence matches single-status wording, no mention of modified event.")

            # --- Scenario 2: same creditor now separately hits 3 modified today ---
            m2 = CreditorVoteChangeEvent.objects.create(vote_summary=vote_summary, sync_run=sync_run, status="modified")
            m2.detected_at = now; m2.save()

            m3 = CreditorVoteChangeEvent.objects.create(vote_summary=vote_summary, sync_run=sync_run, status="modified")
            m3.detected_at = now + timedelta(minutes=5); m3.save()

            print(f"\nScenario 2 additional events: modified@{m2.detected_at}, modified@{m3.detected_at}")

            created2 = check_non_accept_milestone(vote_summary, sync_run)
            print(f"Second check created {len(created2)} milestone(s): {[ (c.status, c.count) for c in created2 ]}")

            assert len(created2) == 1, f"Expected exactly 1 new milestone, got {len(created2)}"
            milestone2 = created2[0]
            assert milestone2.status == "modified", f"Expected status='modified', got {milestone2.status!r}"
            assert milestone2.count == 3, f"Expected count=3, got {milestone2.count}"
            assert milestone2.first_event_at == m1.detected_at, "first_event_at mismatch for modified milestone"
            assert milestone2.third_event_at == m3.detected_at, "third_event_at mismatch for modified milestone"
            print("ASSERTIONS PASSED: independent 'modified' milestone created without conflicting with 'rejected' one.")

            # Both milestone rows now coexist for the same (vote_summary, day)
            all_today = CreditorNonAcceptMilestone.objects.filter(
                vote_summary=vote_summary, milestone_date=today_date
            ).order_by("status")
            statuses_today = list(all_today.values_list("status", flat=True))
            assert statuses_today == ["modified", "rejected"], f"Unexpected milestone set: {statuses_today}"
            print(f"CONFIRMED: both milestones coexist for today: {statuses_today}")

            print("\nALL VERIFICATIONS PASSED.")
        finally:
            transaction.set_rollback(True)
            print("\nTransaction rolled back successfully.")


if __name__ == "__main__":
    main()
