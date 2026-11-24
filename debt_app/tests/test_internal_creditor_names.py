"""GET /api/v1/criteria/internal/creditor-names/ (2026-11-25): the names CA
learns trading names from -- open, read only, active rows with trading names."""
from django.test import TestCase
from rest_framework.test import APIClient

from debt_app.models import CreditorCriteria

URL = "/api/v1/criteria/internal/creditor-names/"


class InternalCreditorNamesTests(TestCase):

    def setUp(self):
        # Made-up names: the migrations seed the real directory into the test DB.
        CreditorCriteria.objects.create(creditor_name="Zz Test Bank", trading_names=["ZTB", "ZTB PLC", " "])
        CreditorCriteria.objects.create(creditor_name="Zz No Brands", trading_names=[])
        CreditorCriteria.objects.create(creditor_name="Zz Old Lender", trading_names=["ZOL"], is_active=False)
        self.client = APIClient()

    def test_active_rows_with_trading_names_without_a_token(self):
        response = self.client.get(URL)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        ours = [r for r in body["results"] if r["name"].startswith("Zz ")]
        self.assertEqual(ours, [{"name": "Zz Test Bank", "trading_names": ["ZTB", "ZTB PLC"]}])
        self.assertEqual(body["count"], len(body["results"]))
        self.assertTrue(all(r["trading_names"] for r in body["results"]))

    def test_read_only(self):
        for method in (self.client.post, self.client.put, self.client.patch, self.client.delete):
            self.assertEqual(method(URL, {}).status_code, 405)
