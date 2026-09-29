"""
The date a credit report PRINTS as its own issue / search date
(`printed_report_date`), and that the upload view returns it.

The case-assessment-tool shows this as "credit search completed on" in its
Drafter, so it must be the printed date or nothing -- never `report_date`'s
latest-tradeline-update fallback. Page text below is copied from real reports'
pdfplumber output (media/ is gitignored, so no PDF fixtures).
"""
from unittest.mock import MagicMock, patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase

from debt_app.integrations.credit_report import (
    _extract_printed_report_date,
    extract_credit_report,
)
from debt_app.views import criteria_views


def _fake_pdf_open(*page_texts):
    pages = []
    for text in page_texts:
        page = MagicMock()
        page.extract_text.return_value = text
        pages.append(page)
    pdf = MagicMock()
    pdf.pages = pages
    pdf.__enter__.return_value = pdf
    pdf.__exit__.return_value = False
    return pdf


EXPERIAN_PAGE_ONE = "\n".join([
    "Consumer Credit Report",
    "ADAM OSBORNE",
    "Experian Reference ACZT4CWL4Q",
    "Issue Date and Time 04/03/2026 17:26:04",
    "Summary",
])

VALID8_PAGE_ONE = "\n".join([
    "Consumer Credit Report",
    "Table Of Contents",
    "1) Summary",
    "Summary",
    "Search Date: 23/08/2026",
    "Search Details",
    "Provider: Experian",
    "Date of Birth: 28/09/1953",
])

ARYZA_PAGE_ONE = "\n".join([
    "Credit Report",
    "Client Details",
    "Name: Miss Jody Stone",
    "Date of Birth: 2000-10-19",
    "Debt Overview",
    "Mortgages: 0 CCJs and Insolvencies: 0",
    "Zilch Technology LTD BD",
    "Current Balance: N/A Last Update: 2026-01-01",
    "Start Balance: N/A Start Date: 2021-03-23",
])


class ExtractPrintedReportDateTests(SimpleTestCase):
    def test_experian_issue_date(self):
        self.assertEqual(_extract_printed_report_date(EXPERIAN_PAGE_ONE), "2026-03-04")

    def test_valid8_search_date(self):
        self.assertEqual(_extract_printed_report_date(VALID8_PAGE_ONE), "2026-08-23")

    def test_aryza_prints_no_date(self):
        # "Last Update" and "Date of Birth" are not the report's date.
        self.assertEqual(_extract_printed_report_date(ARYZA_PAGE_ONE), "")

    def test_impossible_date_is_empty_not_coerced(self):
        self.assertEqual(_extract_printed_report_date("Search Date: 31/02/2026"), "")

    def test_empty_text(self):
        self.assertEqual(_extract_printed_report_date(""), "")
        self.assertEqual(_extract_printed_report_date(None), "")


class ExtractCreditReportPrintedDateTests(SimpleTestCase):
    def _extract(self, *pages):
        with patch("pdfplumber.open", return_value=_fake_pdf_open(*pages)):
            return extract_credit_report("fake.pdf")

    def test_experian_report_carries_its_issue_date(self):
        result = self._extract(EXPERIAN_PAGE_ONE)
        self.assertEqual(result["printed_report_date"], "2026-03-04")
        self.assertEqual(result["report_date"], "2026-03-04")

    def test_valid8_search_date_now_also_fills_report_date(self):
        # Before 2026-09-30 only "Issue Date and Time" was recognised and
        # every Valid8 report came back with report_date "".
        result = self._extract(VALID8_PAGE_ONE)
        self.assertEqual(result["printed_report_date"], "2026-08-23")
        self.assertEqual(result["report_date"], "2026-08-23")

    def test_aryza_keeps_derived_report_date_but_no_printed_date(self):
        result = self._extract(ARYZA_PAGE_ONE)
        self.assertEqual(result["printed_report_date"], "")
        self.assertEqual(result["report_date"], "2026-01-01")   # unchanged

    def test_a_search_date_after_page_one_is_not_the_reports(self):
        page_two = "7) CAPS (Credit Application Previous Search)\nSearch Date: 01/01/2025"
        result = self._extract("Consumer Credit Report\nProvider: Experian", page_two)
        self.assertEqual(result["printed_report_date"], "")


class UploadViewReturnsPrintedDateTests(TestCase):
    url = "/api/v1/criteria/upload-credit-report/"

    def _post(self, result):
        original = criteria_views.extract_credit_report
        criteria_views.extract_credit_report = lambda path: result
        try:
            return self.client.post(self.url, data={
                "aryza_reference": "TEST-REF-1",
                "credit_report": SimpleUploadedFile(
                    "report.pdf", b"%PDF-1.4\n%%EOF", content_type="application/pdf"),
            }, format="multipart")
        finally:
            criteria_views.extract_credit_report = original

    def _result(self, **overrides):
        base = {"agency": "Experian", "client_name": "Jane Doe", "report_date": "2026-01-01",
                "accounts": [{"raw_name": "HALIFAX", "matched_creditor": "Halifax",
                              "type_code": "CC", "current_balance": 100}],
                "mortgage_accounts": [], "other_accounts": [], "unmatched_accounts": [],
                "public_information": {}, "has_ccj": False, "aoe_in_place": False}
        base.update(overrides)
        return base

    def test_printed_date_is_returned(self):
        body = self._post(self._result(printed_report_date="2026-08-23")).json()
        self.assertEqual(body["printed_report_date"], "2026-08-23")

    def test_no_printed_date_is_empty_even_when_report_date_is_derived(self):
        body = self._post(self._result(printed_report_date="")).json()
        self.assertEqual(body["printed_report_date"], "")

    def test_failed_extraction_returns_empty_printed_date(self):
        body = self._post({"extraction_error": "boom"}).json()
        self.assertFalse(body["success"])
        self.assertEqual(body["printed_report_date"], "")
