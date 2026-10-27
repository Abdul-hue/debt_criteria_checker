"""
GET /api/v1/criteria/credit-report/ (CreditReportFetchView), called by the
Drafter tool. Open like the other CAT endpoints. Returns the report the
assessment would use, after running the Experian import. Aryza and the
Experian import are mocked at their boundary.
"""
from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIClient

from debt_app.aryza_client import AryzaCaseNotFoundError, AryzaConnectionError
from debt_app.integrations.experian_db import ExperianConnectionError, ExperianDataError
from debt_app.models import CREDIT_REPORT_SOURCE_EXPERIAN_DB, CreditReport
from debt_app.services.experian_credit_report import ExperianImportResult
from debt_app.tests.test_experian_assessment_wiring import REF, _case, _cr_account, _pdf_report

URL = "/api/v1/criteria/credit-report/"
FETCH = "debt_app.views.criteria_views.fetch_case_by_reference"
ENSURE = "debt_app.views.criteria_views.ensure_experian_credit_report"
HTML_QUERY = "debt_app.integrations.experian_db.ExperianSession.fetch_search_html"
CONNECT = "debt_app.integrations.experian_db.ExperianDBClient._connect"


class CreditReportFetchViewTests(TestCase):

    def _get(self, reference=REF, experian=ExperianImportResult(None, "flag_disabled"),
             html="<html>report</html>", html_error=None):
        html_patch = (patch(HTML_QUERY, side_effect=html_error) if html_error
                      else patch(HTML_QUERY, return_value=html))
        with patch(FETCH, return_value=_case()) as fetch, patch(ENSURE, return_value=experian) as ensure, \
                patch(CONNECT), html_patch as html_query:
            resp = APIClient().get(URL, {"aryza_reference": reference} if reference is not None else {})
        self.html_query = html_query
        return resp, fetch, ensure

    def _experian_report(self, **kwargs):
        return CreditReport.objects.create(
            aryza_reference=REF, source=CREDIT_REPORT_SOURCE_EXPERIAN_DB, source_report_id=77,
            agency="Experian", extraction_status="extracted",
            extracted_data={"accounts": [_cr_account("ALPHA BANK", "Alpha Bank", 600000)]}, **kwargs,
        )

    def test_experian_report_includes_its_rendered_html(self):
        self._experian_report()
        resp, _, _ = self._get()
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["report_html"], "<html>report</html>")
        self.assertEqual(resp.data["report_html_status"], "ok")
        # The search is read for THIS case only.
        self.html_query.assert_called_once_with(77, REF)

    def test_pdf_upload_has_no_html_and_never_reads_experian(self):
        _pdf_report()
        resp, _, _ = self._get()
        self.assertEqual(resp.status_code, 200)
        self.assertIsNone(resp.data["report_html"])
        self.assertEqual(resp.data["report_html_status"], "not_experian")
        self.html_query.assert_not_called()

    def test_html_failure_still_returns_the_json(self):
        self._experian_report()
        for exc, code in ((ExperianDataError("x"), "experian_data_error"),
                          (ExperianConnectionError("x"), "experian_unavailable")):
            with self.subTest(code=code):
                resp, _, _ = self._get(html_error=exc)
                self.assertEqual(resp.status_code, 200)
                self.assertEqual(resp.data["accounts_found"], 1)
                self.assertIsNone(resp.data["report_html"])
                self.assertEqual(resp.data["report_html_status"], code)

    def test_missing_reference_is_422(self):
        resp, fetch, _ = self._get(reference=None)
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(resp.data["code"], "MISSING_REFERENCE")
        fetch.assert_not_called()

    def test_returns_the_experian_report_after_running_the_import(self):
        report = CreditReport.objects.create(
            aryza_reference=REF, source=CREDIT_REPORT_SOURCE_EXPERIAN_DB, source_report_id=77,
            agency="Experian", extraction_status="extracted",
            extracted_data={"accounts": [_cr_account("ALPHA BANK", "Alpha Bank", 600000)],
                            "printed_report_date": "2026-10-20"},
        )
        resp, _, ensure = self._get()
        self.assertEqual(resp.status_code, 200)
        ensure.assert_called_once()
        self.assertEqual(ensure.call_args.args[0], REF)
        self.assertEqual(resp.data["credit_report_id"], report.id)
        self.assertEqual(resp.data["source"], CREDIT_REPORT_SOURCE_EXPERIAN_DB)
        self.assertEqual(resp.data["accounts_found"], 1)
        self.assertEqual(resp.data["accounts"][0]["matched_creditor"], "Alpha Bank")
        self.assertEqual(resp.data["printed_report_date"], "2026-10-20")

    def test_newest_usable_report_wins_like_the_assessment(self):
        _pdf_report()
        newer = _pdf_report(extracted_data={"accounts": [_cr_account("BETA", "Beta Loans", 450000)]})
        resp, _, _ = self._get()
        self.assertEqual(resp.data["credit_report_id"], newer.id)

    def test_identity_mismatch_report_is_never_returned(self):
        CreditReport.objects.create(
            aryza_reference=REF, source=CREDIT_REPORT_SOURCE_EXPERIAN_DB, source_report_id=78,
            agency="Experian", extraction_status="identity_mismatch",
            extracted_data={"accounts": [_cr_account("ALPHA BANK", "Alpha Bank", 600000)]},
        )
        resp, _, _ = self._get(experian=ExperianImportResult(None, "no_identity_match"))
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp.data["code"], "NO_CREDIT_REPORT")
        self.assertEqual(resp.data["experian_reason"], "no_identity_match")

    def test_another_cases_report_is_not_returned(self):
        _pdf_report(aryza_reference="OTHER")
        resp, _, _ = self._get()
        self.assertEqual(resp.status_code, 404)

    def test_aryza_errors_map_to_the_assess_codes(self):
        for exc, code, http in ((AryzaCaseNotFoundError("x"), "CASE_NOT_FOUND", 404),
                                (AryzaConnectionError("x"), "ARYZA_UNAVAILABLE", 503)):
            with self.subTest(code=code), patch(FETCH, side_effect=exc), patch(ENSURE) as ensure:
                resp = APIClient().get(URL, {"aryza_reference": REF})
            self.assertEqual(resp.status_code, http)
            self.assertEqual(resp.data["code"], code)
            ensure.assert_not_called()
