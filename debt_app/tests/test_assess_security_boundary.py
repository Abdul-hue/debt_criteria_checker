"""
The access contract of the criteria endpoints, as approved:

  * POST /api/v1/criteria/assess/ (AssessCaseView), POST /api/v1/assess/
    (DirectAssessView) and POST /api/v1/criteria/upload-credit-report/ need no
    authentication and no API header. An X-Internal-Key / X-API-Key header is
    neither required nor checked.
  * /api/v1/criteria/assess/ ignores a supplied JWT (request.user stays
    anonymous), and with EXPERIAN_AUTO_CREDIT_REPORT on it imports and uses
    Experian data -- an accepted part of the architecture.
  * The Lead Gen check, its report-status endpoint and case evaluation still
    require a logged-in user.

Experian is faked; the Aryza fetch is mocked. No live system is used.
"""
from datetime import datetime
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from debt_app.integrations.experian_db import CandidateSearch
from debt_app.models import CreditorCriteria, CreditReport, CriteriaDecision
from debt_app.services import experian_credit_report as service
from debt_app.tests.test_experian_assessment_wiring import REF, URL, _case, _is_cr_only, _positions
from debt_app.tests.test_experian_credit_report import FakeClient
from debt_app.tests.test_experian_mapper import _detail, _doc
from debt_app.views import criteria_views

API_HEADERS = ({}, {"HTTP_X_INTERNAL_KEY": "anything"}, {"HTTP_X_API_KEY": "anything"})

DIRECT_ASSESS_PAYLOAD = {
    "aryza_reference": REF, "client_name": "x", "disposable_income": 300, "total_income": 2000,
    "creditors": [{"name": "Alpha Bank", "creditor_name": "Alpha Bank", "balance": 6000, "debt_type": "personal_loan"}],
}


def _experian_client():
    document = _doc([
        _detail(SupplyCompanyName="ALPHA BANK PLC", AccountType="02", AccountStatus="F", WorstStatus="8",
                AccountBalances=[{"AccountBalance": "0006000", "Status": "8"}]),
        _detail(SupplyCompanyName="UNDECLARED LENDER LTD", AccountType="05",
                AccountBalances=[{"AccountBalance": "0000750", "Status": "0"}]),
    ])
    return FakeClient(
        [CandidateSearch(912, datetime(2026, 10, 1), "ZEPHYRINA", "QUILLFEATHER", "1980-07-15", False)],
        {912: document})


def _stored_experian_report():
    return CreditReport.objects.create(
        aryza_reference=REF, source="experian_db", source_report_id=912, agency="Experian",
        extraction_status="extracted", extracted_data={"agency": "Experian", "accounts": [{
            "raw_name": "ALPHA BANK PLC", "matched_creditor": "Alpha Bank", "type_code": "PL",
            "current_balance": 600000, "account_status": "Default"}], "mortgage_accounts": [], "other_accounts": []})


class SecurityBoundaryBase(TestCase):
    def setUp(self):
        for name in ("Alpha Bank", "Beta Loans"):
            CreditorCriteria.objects.create(creditor_name=name, representative="NONE", status="ACCEPT", is_active=True)

    def _post_assess(self, client, **extra):
        with patch("debt_app.views.criteria_views.fetch_case_by_reference", return_value=_case()):
            return client.post(URL, data={"aryza_reference": REF}, format="json", **extra)

    def _upload(self, **headers):
        original = criteria_views.extract_credit_report
        criteria_views.extract_credit_report = lambda path: {
            "agency": "Experian", "client_name": "", "client_address": "",
            "accounts": [{"raw_name": "OTHER LENDER", "matched_creditor": "OTHER LENDER"}],
            "mortgage_accounts": [], "other_accounts": [], "unmatched_accounts": []}
        try:
            with patch("django.core.files.storage.FileSystemStorage.save", return_value="credit_reports/x.pdf"):
                return APIClient().post("/api/v1/criteria/upload-credit-report/", data={
                    "aryza_reference": REF,
                    "credit_report": SimpleUploadedFile("r.pdf", b"%PDF-1.4", content_type="application/pdf"),
                }, format="multipart", **headers)
        finally:
            criteria_views.extract_credit_report = original


class NoApiHeaderNeededTests(SecurityBoundaryBase):

    def test_cat_assess_works_with_or_without_any_api_header(self):
        for headers in API_HEADERS:
            self.assertEqual(self._post_assess(APIClient(), **headers).status_code, 200, headers)

    def test_direct_assess_works_with_or_without_any_api_header(self):
        for headers in API_HEADERS:
            resp = APIClient().post("/api/v1/assess/", data=DIRECT_ASSESS_PAYLOAD, format="json", **headers)
            self.assertEqual(resp.status_code, 200, headers)

    def test_upload_works_with_or_without_any_api_header(self):
        for headers in API_HEADERS:
            resp = self._upload(**headers)
            self.assertEqual(resp.status_code, 200, headers)
            self.assertTrue(resp.json()["success"], headers)

    def test_no_key_based_permission_remains(self):
        from debt_app.views.assess_view import DirectAssessView
        for view in (criteria_views.AssessCaseView, DirectAssessView, criteria_views.CreditReportUploadView):
            self.assertEqual(view.authentication_classes, [], view.__name__)
            self.assertEqual([p.__name__ for p in view.permission_classes], ["AllowAny"], view.__name__)
        self.assertFalse(hasattr(criteria_views, "_InternalKeyOrAuthenticated"))


class CatAssessIsPublicTests(SecurityBoundaryBase):

    def test_anonymous_request_is_served(self):
        resp = self._post_assess(APIClient())
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["aryza_reference"], REF)

    def test_a_valid_jwt_is_not_read(self):
        user = User.objects.create_user(username="caseworker", password="x")
        token = str(RefreshToken.for_user(user).access_token)
        resp = self._post_assess(APIClient(), HTTP_AUTHORIZATION=f"Bearer {token}")
        self.assertEqual(resp.status_code, 200)
        self.assertIsNone(CriteriaDecision.objects.get(application_id=REF).triggered_by)

    @override_settings(EXPERIAN_AUTO_CREDIT_REPORT=True)
    def test_anonymous_cat_request_imports_and_uses_experian(self):
        client = _experian_client()
        with patch.object(service, "ExperianDBClient", return_value=client):
            resp = self._post_assess(APIClient())
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(client.sessions, 1)
        report = CreditReport.objects.get(source="experian_db")
        self.assertEqual((report.aryza_reference, report.source_report_id, report.uploaded_by), (REF, 912, None))
        body = resp.json()
        alpha = _positions(body)["Alpha Bank"]
        self.assertEqual((alpha["cr_raw_name"], alpha["cr_balance"], alpha["cr_account_status"]),
                         ("ALPHA BANK PLC", 600000, "Default"))
        cr_only = [p for p in body["creditor_positions"] if _is_cr_only(p)]
        self.assertEqual([(p["cr_raw_name"], p["cr_balance"]) for p in cr_only], [("UNDECLARED LENDER LTD", 75000)])

    @override_settings(EXPERIAN_AUTO_CREDIT_REPORT=True)
    def test_account_numbers_and_dates_of_birth_are_not_in_the_response(self):
        with patch.object(service, "ExperianDBClient", return_value=_experian_client()):
            text = self._post_assess(APIClient()).content.decode()
        self.assertNotIn("4462000011112222", text)   # the fixture's account number
        self.assertNotIn("1980-07-15", text)          # the applicant's date of birth


class OtherEndpointsTests(SecurityBoundaryBase):

    def test_direct_assess_reads_the_stored_report_but_never_imports(self):
        _stored_experian_report()
        with override_settings(EXPERIAN_AUTO_CREDIT_REPORT=True), \
                patch("debt_app.views.criteria_views.ensure_experian_credit_report") as ensure, \
                patch.object(service, "ExperianDBClient") as client_class:
            resp = APIClient().post("/api/v1/assess/", data=DIRECT_ASSESS_PAYLOAD, format="json")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("ALPHA BANK PLC", resp.content.decode())
        ensure.assert_not_called()
        client_class.assert_not_called()

    def test_upload_does_not_return_another_report(self):
        _stored_experian_report()
        self.assertNotIn("ALPHA BANK PLC", self._upload().content.decode())

    def test_lead_gen_check_requires_a_jwt_user(self):
        for headers in API_HEADERS:
            resp = APIClient().post("/api/v1/criteria/lead-gen/check/", data={"aryza_reference": REF},
                                    format="json", **headers)
            self.assertEqual(resp.status_code, 401, headers)

    def test_lead_gen_report_status_requires_a_jwt_user(self):
        resp = APIClient().get("/api/v1/criteria/lead-gen/credit-report-status/", {"aryza_reference": REF})
        self.assertEqual(resp.status_code, 401)

    def test_evaluate_requires_a_jwt_user(self):
        self.assertEqual(APIClient().post(f"/api/v1/criteria/cases/{REF}/evaluate", {}, format="json").status_code, 401)
