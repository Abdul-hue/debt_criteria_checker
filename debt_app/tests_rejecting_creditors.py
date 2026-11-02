"""
GET /api/v1/criteria/rejecting/ (RejectingCreditorsView), called by the
Drafter tool. Open like the other Drafter endpoints. One endpoint, a `type`
flag: general creditors or councils whose standing status is REJECT.
"""
from django.test import TestCase
from rest_framework.test import APIClient

from debt_app.models import CouncilRule, CreditorCriteria

URL = "/api/v1/criteria/rejecting/"


class RejectingCreditorsViewTests(TestCase):

    def setUp(self):
        CreditorCriteria.objects.create(creditor_name="Gen Reject", status="REJECT", source_sheet="GENERAL_CREDITOR")
        CreditorCriteria.objects.create(creditor_name="Gen Accept", status="ACCEPT", source_sheet="GENERAL_CREDITOR")
        CreditorCriteria.objects.create(creditor_name="Gen Inactive", status="REJECT", source_sheet="GENERAL_CREDITOR",
                                        is_active=False)
        CreditorCriteria.objects.create(creditor_name="Rep Reject", status="REJECT", source_sheet="REPRESENTATIVE")
        CouncilRule.objects.create(council_name="Reject Council", status="REJECT")
        CouncilRule.objects.create(council_name="Accept Council", status="ACCEPT")

    def _get(self, **params):
        return APIClient().get(URL, params)

    # Migrations seed real creditors and councils (e.g. Slough = REJECT), so
    # these check membership rather than an exact list.
    def test_general_returns_only_active_rejecting_general_creditors(self):
        resp = self._get(type="general")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["type"], "general")
        names = [r["creditor_name"] for r in resp.data["results"]]
        self.assertIn("Gen Reject", names)
        self.assertNotIn("Gen Accept", names)
        self.assertNotIn("Gen Inactive", names)
        self.assertNotIn("Rep Reject", names)
        self.assertEqual(resp.data["count"], len(names))
        for r in resp.data["results"]:
            self.assertEqual((r["status"], r["source_sheet"], r["is_active"]), ("REJECT", "GENERAL_CREDITOR", True))

    def test_councils_returns_only_rejecting_councils(self):
        resp = self._get(type="councils")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["type"], "councils")
        names = [r["council_name"] for r in resp.data["results"]]
        self.assertIn("Reject Council", names)
        self.assertNotIn("Accept Council", names)
        self.assertEqual(resp.data["count"], CouncilRule.objects.filter(status="REJECT").count())
        self.assertTrue(all(r["status"] == "REJECT" for r in resp.data["results"]))

    def test_type_is_case_insensitive(self):
        resp = self._get(type="Councils")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["type"], "councils")

    def test_search_narrows_results(self):
        CouncilRule.objects.create(council_name="Other Reject Council", status="REJECT")
        resp = self._get(type="councils", search="other")
        self.assertEqual([r["council_name"] for r in resp.data["results"]], ["Other Reject Council"])

    def test_missing_type_is_422(self):
        resp = self._get()
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(resp.data["code"], "INVALID_TYPE")

    def test_unknown_type_is_422(self):
        resp = self._get(type="representative")
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(resp.data["code"], "INVALID_TYPE")

    def test_no_token_needed(self):
        # APIClient sends no credentials; a JWT-protected view would return 401.
        self.assertEqual(self._get(type="general").status_code, 200)
