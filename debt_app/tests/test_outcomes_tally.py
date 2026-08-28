import json
from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient
from debt_app.models import CreditorCriteria
from debt_app.models import CreditorOutcome
from debt_app.views.criteria import enrich_positions_with_tallies

class OutcomesTallyTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username="testuser_tally", password="pass")
        self.client.force_authenticate(user=self.user)

        # 1. Create a creditor with outcomes
        self.creditor1 = CreditorCriteria.objects.create(
            creditor_name="Test Creditor 1",
            is_active=True
        )
        # Add 2 approved and 1 disapproved outcomes
        CreditorOutcome.objects.create(
            creditor=self.creditor1,
            case_reference="CASE123",
            outcome="approved",
            outcome_date="2026-06-01",
            comment="Approved outcome 1",
            submitted_by=self.user
        )
        CreditorOutcome.objects.create(
            creditor=self.creditor1,
            case_reference="CASE124",
            outcome="approved",
            outcome_date="2026-06-02",
            comment="Approved outcome 2",
            submitted_by=self.user
        )
        CreditorOutcome.objects.create(
            creditor=self.creditor1,
            case_reference="CASE125",
            outcome="disapproved",
            outcome_date="2026-06-03",
            comment="Disapproved outcome 1",
            submitted_by=self.user
        )

        # 2. Create a creditor with no outcomes
        self.creditor2 = CreditorCriteria.objects.create(
            creditor_name="Test Creditor 2",
            is_active=True
        )

    def test_enrich_positions_with_tallies(self):
        positions = [
            # Creditor with outcomes
            {"criteria_id": self.creditor1.id, "creditor_name": "Test Creditor 1"},
            # Creditor with no outcomes
            {"criteria_id": self.creditor2.id, "creditor_name": "Test Creditor 2"},
            # Creditor with no criteria_id (e.g. council or unmatched)
            {"creditor_name": "Brighton and Hove City Council"}
        ]

        enrich_positions_with_tallies(positions)

        # Assertions for Creditor 1 (with outcomes)
        self.assertEqual(positions[0]["outcomes_approved"], 2)
        self.assertEqual(positions[0]["outcomes_disapproved"], 1)
        self.assertEqual(positions[0]["outcomes_total"], 3)

        # Assertions for Creditor 2 (no outcomes)
        self.assertEqual(positions[1]["outcomes_approved"], 0)
        self.assertEqual(positions[1]["outcomes_disapproved"], 0)
        self.assertEqual(positions[1]["outcomes_total"], 0)

        # Assertions for Creditor with no criteria_id
        self.assertEqual(positions[2]["outcomes_approved"], 0)
        self.assertEqual(positions[2]["outcomes_disapproved"], 0)
        self.assertEqual(positions[2]["outcomes_total"], 0)

    def test_tally_endpoint_returns_404_or_spa_fallback(self):
        # Call the removed endpoint and assert it either returns 404 or falls back to the SPA index page
        response = self.client.get(
            f"/api/v1/criteria/creditors/{self.creditor1.id}/outcomes/tally/"
        )
        if response.status_code == 200:
            self.assertIn("text/html", response.get("Content-Type", ""))
        else:
            self.assertEqual(response.status_code, 404)
