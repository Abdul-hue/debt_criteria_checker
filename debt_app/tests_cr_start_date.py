"""
Regression tests for the credit-report Start Date reaching creditor_positions.

The date was extracted (account_age_months was derived from it) but never
stamped onto the positions the CA Tool renders, so the verification table's
START DATE column was blank for any row built from creditor_positions.
"""
import json

from django.test import TestCase, Client

from debt_app.credit_report_extractor import normalise_start_date_iso
from debt_app.models import CreditReport


class NormaliseStartDateIsoTests(TestCase):
    def test_aryza_iso_passes_through(self):
        self.assertEqual(normalise_start_date_iso("2021-09-16"), "2021-09-16")

    def test_experian_day_first_is_converted(self):
        self.assertEqual(normalise_start_date_iso("16-09-2021"), "2021-09-16")

    def test_slash_separated_day_first_is_converted(self):
        self.assertEqual(normalise_start_date_iso("16/09/2021"), "2021-09-16")

    def test_blank_and_unparseable_become_none(self):
        for value in ("", None, "   ", "garbage", "2021-13-45"):
            self.assertIsNone(normalise_start_date_iso(value), value)


class DirectAssessCrStartDateTests(TestCase):
    """POST /api/v1/assess/ — the endpoint the CA Tool calls."""

    def setUp(self):
        self.client = Client()
        CreditReport.objects.create(
            aryza_reference="TEST-CR-START",
            extraction_status="extracted",
            extracted_data={
                "accounts": [
                    {
                        "raw_name": "MBNA LTD",
                        # As the extractor emits it: the alias-map resolved name,
                        # which is what the enrichment matches the case creditor on.
                        "matched_creditor": "MBNA - IVA",
                        "type_code": "CC",
                        "current_balance": 810900,      # pence
                        "account_status": "Delinquent",
                        "account_age_months": 64,
                        "start_date": "2021-03-19",     # already ISO (Aryza)
                    },
                    {
                        "raw_name": "JD WILLIAMS",
                        "matched_creditor": "JD Williams",
                        "type_code": "MO",
                        "current_balance": 306500,
                        "account_status": "Active",
                        "account_age_months": 115,
                        "start_date": "06-12-2016",     # day-first (Experian, pre-fix data)
                    },
                ]
            },
        )

    def _assess(self):
        response = self.client.post(
            "/api/v1/assess/",
            data=json.dumps({
                "application_id": "TEST-CR-START",
                "creditors": [
                    {"name": "MBNA LTD", "balance": 8109.00},
                    {"name": "JD WILLIAMS", "balance": 3065.00},
                ],
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content[:400])
        return {
            (p.get("cr_raw_name") or p.get("creditor_name")): p
            for p in response.json()["creditor_positions"]
        }

    def test_positions_carry_cr_start_date(self):
        by_name = self._assess()
        self.assertEqual(by_name["MBNA LTD"]["cr_start_date"], "2021-03-19")

    def test_day_first_stored_date_is_normalised_on_read(self):
        """Reports extracted before the extractor normalised dates still render."""
        by_name = self._assess()
        self.assertEqual(by_name["JD WILLIAMS"]["cr_start_date"], "2016-12-06")

    def test_cr_start_date_key_always_present(self):
        """A creditor with no CR match must expose the key as None, not omit it."""
        for position in self._assess().values():
            self.assertIn("cr_start_date", position)
