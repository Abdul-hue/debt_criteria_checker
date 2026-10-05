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

from debt_app.engine.criteria import _enrich_from_credit_report
from debt_app.models import CreditReport
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

    def test_unrecognised_agency_with_no_accounts_fails(self):
        # An "Unknown" agency with 0 accounts is not a credit report the
        # parser can read (ref 411322: saved as "extracted", it read as
        # "client has no debts"). It must fail -- `success: False` is what
        # stops the case-assessment-tool replacing the case's creditors with
        # nothing -- and nothing it extracted may be saved as a report.
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
        self.assertFalse(body["success"])
        self.assertEqual(body["extraction_status"], "failed")
        self.assertEqual(body["code"], "NOT_A_CREDIT_REPORT")
        self.assertIn("not recognised as a credit report", body["error"])
        record = CreditReport.objects.get(id=body["credit_report_id"])
        self.assertEqual(record.extraction_status, "failed")
        self.assertFalse(record.extracted_data)

    def test_unrecognised_agency_with_accounts_is_extracted(self):
        resp = self._post({
            "agency": "Unknown",
            "client_name": "",
            "report_date": "",
            "accounts": [{"raw_name": "HALIFAX", "matched_creditor": "Halifax", "type_code": "CC", "current_balance": 100}],
            "mortgage_accounts": [],
            "other_accounts": [],
            "unmatched_accounts": [],
            "public_information": {},
            "has_ccj": False,
            "aoe_in_place": False,
        })
        body = resp.json()
        self.assertTrue(body["success"])
        self.assertEqual(body["extraction_status"], "extracted")
        self.assertEqual(body["accounts_found"], 1)

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


class EnrichSkipsEmptyReportTests(TestCase):
    """`_enrich_from_credit_report` uses the newest extracted report that HAS
    accounts -- an empty "extracted" upload made after a real report must not
    hide it (ref 411322, report 218)."""

    REF = "TEST-REF-EMPTY-AFTER-REAL"

    def _report(self, extracted_data, created_at):
        r = CreditReport.objects.create(
            aryza_reference=self.REF, uploaded_file="x.pdf",
            extraction_status="extracted", extracted_data=extracted_data,
        )
        CreditReport.objects.filter(id=r.id).update(created_at=created_at)
        return r

    def test_newer_empty_report_does_not_hide_the_real_one(self):
        from datetime import datetime, timezone
        from debt_app.engine.criteria import _parse_case
        self._report({
            "accounts": [{"raw_name": "HALIFAX", "matched_creditor": "Halifax",
                          "type_code": "CC", "current_balance": 10000}],
            "mortgage_accounts": [], "has_ccj": True,
            "public_information": {"has_ccj": True},
        }, datetime(2026, 9, 1, tzinfo=timezone.utc))
        self._report({
            "accounts": [], "mortgage_accounts": [], "has_ccj": False,
            "public_information": {"has_ccj": False},
        }, datetime(2026, 10, 5, tzinfo=timezone.utc))

        c = _parse_case({"aryza_reference": self.REF,
                         "creditors": [{"creditor_name": "Halifax", "balance": 100}]})
        self.assertEqual("present", _enrich_from_credit_report(c))
        self.assertTrue(c["has_ccj"])

    def test_only_empty_reports_is_still_extraction_failed(self):
        from datetime import datetime, timezone
        from debt_app.engine.criteria import _parse_case
        self._report({"accounts": [], "mortgage_accounts": []},
                     datetime(2026, 10, 5, tzinfo=timezone.utc))
        c = _parse_case({"aryza_reference": self.REF, "creditors": []})
        self.assertEqual("extraction_failed", _enrich_from_credit_report(c))
