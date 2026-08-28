import os
import django
from django.utils import timezone
from datetime import timedelta

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "debt_project.settings")
django.setup()

from django.db import transaction
from debt_app.models import CreditorCriteria, CreditorVoteSummary, CreditorVoteChangeEvent, CrmSyncRun
from debt_app.services.crm_vote_sync import get_last_5_tally


def main():
    print("Starting get_last_5_tally newest-first sequence verification...")

    with transaction.atomic():
        try:
            sync_run = CrmSyncRun.objects.create(
                status="SUCCESS",
                stage="Done — TEST VERIFICATION RUN, SAFE TO DELETE"
            )

            creditor_criteria, _ = CreditorCriteria.objects.get_or_create(
                creditor_name="Test Creditor Sequence Verification"
            )
            vote_summary, _ = CreditorVoteSummary.objects.get_or_create(
                creditor_criteria=creditor_criteria
            )

            CreditorVoteChangeEvent.objects.filter(vote_summary=vote_summary).delete()

            now = timezone.now()

            # --- Scenario 1: fewer than 5 events (3 total) ---
            # Oldest -> newest: modified, accepted, rejected
            statuses_1 = ["modified", "accepted", "rejected"]
            for i, status in enumerate(statuses_1):
                e = CreditorVoteChangeEvent.objects.create(
                    vote_summary=vote_summary, sync_run=sync_run, status=status
                )
                e.detected_at = now - timedelta(minutes=(len(statuses_1) - i) * 10)
                e.save()

            tally_1 = get_last_5_tally(vote_summary)
            expected_sequence_1 = ["rejected", "accepted", "modified"]  # newest -> oldest
            print(f"Scenario 1 (3 events): sequence={tally_1['sequence']} total={tally_1['total']}")
            assert tally_1["sequence"] == expected_sequence_1, (
                f"Expected {expected_sequence_1}, got {tally_1['sequence']}"
            )
            assert tally_1["total"] == 3
            assert tally_1["rejected"] == 1 and tally_1["accepted"] == 1 and tally_1["modified"] == 1
            assert tally_1["pod"] == 0
            print("Scenario 1 PASSED\n")

            CreditorVoteChangeEvent.objects.filter(vote_summary=vote_summary).delete()

            # --- Scenario 2: exactly 6 events, only last 5 (newest) should count ---
            # Oldest -> newest
            statuses_2 = ["accepted", "rejected", "rejected", "modified", "pod", "rejected"]
            for i, status in enumerate(statuses_2):
                e = CreditorVoteChangeEvent.objects.create(
                    vote_summary=vote_summary, sync_run=sync_run, status=status
                )
                e.detected_at = now - timedelta(minutes=(len(statuses_2) - i) * 10)
                e.save()

            tally_2 = get_last_5_tally(vote_summary)
            # Newest 5 (excluding the oldest "accepted"), newest -> oldest:
            expected_sequence_2 = ["rejected", "pod", "modified", "rejected", "rejected"]
            print(f"Scenario 2 (6 events, capped at 5): sequence={tally_2['sequence']} total={tally_2['total']}")
            assert tally_2["sequence"] == expected_sequence_2, (
                f"Expected {expected_sequence_2}, got {tally_2['sequence']}"
            )
            assert tally_2["total"] == 5
            assert tally_2["rejected"] == 3
            assert tally_2["modified"] == 1
            assert tally_2["pod"] == 1
            assert tally_2["accepted"] == 0  # the oldest "accepted" event fell outside the last-5 window
            print("Scenario 2 PASSED\n")

            print("All scenarios passed.")
        finally:
            transaction.set_rollback(True)
            print("Rolled back all test data.")


if __name__ == "__main__":
    main()
