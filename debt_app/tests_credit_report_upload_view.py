"""
Tests for CreditReportUploadView's extracted_empty flagging (Phase 2 of the
Valid8IP-format fix — see integrations/credit_report.py and models.py
EXTRACTION_STATUS_CHOICES).

extract_credit_report() is monkeypatched here so these exercise the VIEW's
own decision logic (recognised-bureau + nothing-found -> extracted_empty +
warning) in isolation from the PDF parser itself, which already has its
own coverage in tests_valid8_credit_search.py and
debt_app/tests/test_credit_report_type_codes.py.
"""
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from debt_app.views import criteria_views


def _fake_pdf(name="report.pdf"):
    return SimpleUploadedFile(name, b"%PDF-1.4\n%%EOF", content_type="application/pdf")


class CreditReportUploadEmptyFlagTests(TestCase):
    url = "/api/v1/criteria/upload-credit-report/"

    def _post(self, monkeypatch_result):
        original = criteria_views.extract_credit_report
        criteria_views.extract_credit_report = lambda path: monkeypatch_result
        try:
            return self.client.post(
                self.url,
                data={"aryza_reference": "TEST-REF-1", "credit_report": _fake_pdf()},
                format="multipart",
            )
        finally:
            criteria_views.extract_credit_report = original

    def test_recognised_bureau_with_no_accounts_is_flagged(self):
        resp = self._post({
            "agency": "Experian",
            "client_name": "Jane Doe",
            "report_date": "2026-01-01",
            "accounts": [],
            "mortgage_accounts": [],
            "other_accounts": [],
            "unmatched_accounts": [],
            "public_information": {},
            "has_ccj": False,
            "aoe_in_place": False,
        })
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["success"])
        self.assertEqual(body["extraction_status"], "extracted_empty")
        self.assertIn("warning", body)
        self.assertEqual(body["accounts_found"], 0)

    def test_recognised_bureau_with_accounts_is_not_flagged(self):
        resp = self._post({
            "agency": "Aryza Advize",
            "client_name": "Jane Doe",
            "report_date": "2026-01-01",
            "accounts": [{"raw_name": "HALIFAX", "matched_creditor": "Halifax", "type_code": "CC", "current_balance": 100}],
            "mortgage_accounts": [],
            "other_accounts": [],
            "unmatched_accounts": [],
            "public_information": {},
            "has_ccj": False,
            "aoe_in_place": False,
        })
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["extraction_status"], "extracted")
        self.assertNotIn("warning", body)
        self.assertEqual(body["accounts_found"], 1)

    def test_unrecognised_agency_with_no_accounts_is_not_flagged(self):
        # An "Unknown" agency with 0 accounts is not a format the parser
        # claims to understand in the first place — nothing distinctive to
        # flag beyond the ordinary "extracted" status.
        resp = self._post({
            "agency": "Unknown",
            "client_name": "",
            "report_date": "",
            "accounts": [],
            "mortgage_accounts": [],
            "other_accounts": [],
            "unmatched_accounts": [],
            "public_information": {},
            "has_ccj": False,
            "aoe_in_place": False,
        })
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["extraction_status"], "extracted")
        self.assertNotIn("warning", body)

    def test_recognised_bureau_with_only_mortgage_accounts_is_not_flagged(self):
        # Mortgage-only extraction is a legitimate non-empty outcome (e.g. a
        # client whose only credit-report tradeline is a mortgage) — must
        # not be misflagged as "found nothing".
        resp = self._post({
            "agency": "Experian",
            "client_name": "Jane Doe",
            "report_date": "2026-01-01",
            "accounts": [],
            "mortgage_accounts": [{"raw_name": "NATIONWIDE", "type_code": "MG", "current_balance": 100000}],
            "other_accounts": [],
            "unmatched_accounts": [],
            "public_information": {},
            "has_ccj": False,
            "aoe_in_place": False,
        })
        body = resp.json()
        self.assertEqual(body["extraction_status"], "extracted")
        self.assertNotIn("warning", body)
