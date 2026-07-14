import json
from datetime import datetime, timedelta
from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from debt_app.models import (
    CreditorCriteria,
    CreditorVoteSummary,
    CreditorVoteChangeEvent,
    CrmSyncRun,
)
from debt_app.services.crm_vote_sync import get_last_5_tally
from debt_app.views.criteria_views import _vote_summary_to_dict


class Last5TallyTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username="testuser_tally", password="pass")
        self.client.force_authenticate(user=self.user)

        # Create a Creditor
        self.creditor = CreditorCriteria.objects.create(
            creditor_name="Big Lifetime Creditor",
            is_active=True
        )

        # Create a vote summary
        self.summary = CreditorVoteSummary.objects.create(
            creditor_criteria=self.creditor,
            total_votes=130,
            accepted_count=123,
            rejected_count=6,
            modified_count=1,
            pod_count=0,
        )

        # Create a sync run
        self.sync_run = CrmSyncRun.objects.create(
            status="SUCCESS",
            trigger_source="CLI",
        )

    def test_last_5_tally_slice_and_annotate_gotcha(self):
        # We need to simulate the lifetime history:
        # 125 older events (121 accepted, 3 rejected, 1 modified)
        # 5 new events (2 accepted, 3 rejected)
        # Let's ensure the detected_at timestamps order the new events AFTER the old ones.
        
        base_time = timezone.now() - timedelta(days=10)
        
        # 1. Create the older 125 events (let's insert them with older timestamps)
        old_events = []
        # 121 accepted
        for i in range(121):
            old_events.append(
                CreditorVoteChangeEvent(
                    vote_summary=self.summary,
                    sync_run=self.sync_run,
                    status="accepted",
                )
            )
        # 3 rejected
        for i in range(3):
            old_events.append(
                CreditorVoteChangeEvent(
                    vote_summary=self.summary,
                    sync_run=self.sync_run,
                    status="rejected",
                )
            )
        # 1 modified
        old_events.append(
            CreditorVoteChangeEvent(
                vote_summary=self.summary,
                sync_run=self.sync_run,
                status="modified",
            )
        )
        
        # Save old events
        CreditorVoteChangeEvent.objects.bulk_create(old_events)
        
        # For testing chronological sorting, let's update their detected_at to be in the past
        CreditorVoteChangeEvent.objects.all().update(detected_at=base_time)

        # 2. Add the 5 NEW events (2 accepted, 3 rejected) with the current timestamp (which is newer)
        new_time = timezone.now()
        new_events = [
            # 2 accepted
            CreditorVoteChangeEvent(
                vote_summary=self.summary,
                sync_run=self.sync_run,
                status="accepted",
            ),
            CreditorVoteChangeEvent(
                vote_summary=self.summary,
                sync_run=self.sync_run,
                status="accepted",
            ),
            # 3 rejected
            CreditorVoteChangeEvent(
                vote_summary=self.summary,
                sync_run=self.sync_run,
                status="rejected",
            ),
            CreditorVoteChangeEvent(
                vote_summary=self.summary,
                sync_run=self.sync_run,
                status="rejected",
            ),
            CreditorVoteChangeEvent(
                vote_summary=self.summary,
                sync_run=self.sync_run,
                status="rejected",
            ),
        ]
        
        CreditorVoteChangeEvent.objects.bulk_create(new_events)
        
        # Set detected_at for the last 5 specifically to make sure they are distinct and newest
        # Let's fetch them back and set their detected_at to new_time
        new_event_ids = [e.id for e in new_events]
        CreditorVoteChangeEvent.objects.filter(id__in=new_event_ids).update(detected_at=new_time)

        # Verify get_last_5_tally() output
        tally = get_last_5_tally(self.summary)
        print("TALLY RESULT:", tally)
        
        expected_tally = {
            "accepted": 2,
            "rejected": 3,
            "modified": 0,
            "pod": 0,
            "total": 5,
            "sequence": ["rejected", "rejected", "rejected", "accepted", "accepted"],
        }
        self.assertEqual(tally, expected_tally)

        # Verify serializer dictionary keys and structure
        serialized = _vote_summary_to_dict(self.summary)
        print("SERIALIZED RESULT:", serialized)
        
        # Ensure only the new key was added and all other keys are unchanged
        self.assertIn("last_5_tally", serialized)
        self.assertEqual(serialized["last_5_tally"], expected_tally)

    def test_last_5_tally_reconciles_with_stale_event_log(self):
        # Reproduces the reported bug: latest_vote_outcome is freshly computed
        # from CRM every sync and says "rejected", but the CreditorVoteChangeEvent
        # log is stale/incomplete (e.g. the creditor's baseline vote history
        # predates event tracking, or rows were written before real-vote-date
        # stamping existed) and only shows "modified" x5. The tally must not
        # contradict the live latest_vote_outcome.
        self.summary.latest_vote_outcome = "rejected"
        self.summary.save(update_fields=["latest_vote_outcome"])

        stale_events = [
            CreditorVoteChangeEvent(
                vote_summary=self.summary,
                sync_run=self.sync_run,
                status="modified",
            )
            for _ in range(5)
        ]
        CreditorVoteChangeEvent.objects.bulk_create(stale_events)

        tally = get_last_5_tally(self.summary)

        self.assertEqual(tally["sequence"][0], "rejected")
        self.assertEqual(tally["rejected"], 1)
        self.assertEqual(tally["modified"], 4)
        self.assertEqual(tally["total"], 5)

    def test_last_5_tally_matches_when_event_log_already_agrees(self):
        # No reconciliation needed/no-op when the event log's newest entry
        # already agrees with latest_vote_outcome.
        self.summary.latest_vote_outcome = "rejected"
        self.summary.save(update_fields=["latest_vote_outcome"])

        CreditorVoteChangeEvent.objects.create(
            vote_summary=self.summary,
            sync_run=self.sync_run,
            status="rejected",
        )

        tally = get_last_5_tally(self.summary)

        self.assertEqual(tally["sequence"], ["rejected"])
        self.assertEqual(tally["total"], 1)
