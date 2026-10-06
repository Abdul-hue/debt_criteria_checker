"""
Characterisation tests for the EXISTING open endpoints (security review,
2026-10-05). They pin today's behaviour so that any future authentication
change is a deliberate, reviewed decision. They do not endorse it.

  /api/v1/assess/                 (DirectAssessView)  AllowAny, no auth classes
      caller: case-assessment backend CriteriaClient.check(), sends NO credentials
      (already covered by tests_assess_auth.DirectAssessViewAuthTests)
  /api/v1/criteria/assess/        (AssessCaseView)    AllowAny, no auth classes
      caller: CAT frontend useAssessCase (sends a JWT, which is ignored)
  /api/v1/criteria/upload-credit-report/  AllowAny, no auth classes
      callers: case-assessment backend (sends X-Internal-Key, not validated),
               CAT frontend CaseSearch (sends a JWT, ignored)
"""

from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from debt_app.models import Application, CreditorCriteria, CriteriaDecision, Department, UserProfile
from debt_app.tests_cat_assessment_golden import _case, _creditor, _FixedDate
from debt_app.views import criteria_views

FETCH = "debt_app.views.criteria_views.fetch_case_by_reference"


class OpenEndpointContractTests(TestCase):

    def setUp(self):
        p = patch("debt_app.engine.criteria.date", _FixedDate)
        p.start()
        self.addCleanup(p.stop)
        CreditorCriteria.objects.create(creditor_name="Alpha Bank", representative="NONE",
                                        status="ACCEPT", is_active=True)

    def test_cat_assess_ignores_a_valid_jwt_so_user_and_department_are_not_recorded(self):
        dept = Department.objects.create(name="Lead Generation", slug="lead-generation")
        user = User.objects.create_user("cat-jwt", password=None)
        UserProfile.objects.create(user=user, department=dept)
        Application.objects.create(aryza_reference="OE-1", client_name="X")
        api = APIClient()
        api.credentials(HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(user)}")
        with patch(FETCH, return_value=_case("OE-1", [_creditor("Alpha Bank", 700_000)])):
            resp = api.post("/api/v1/criteria/assess/", data={"aryza_reference": "OE-1"}, format="json")
        self.assertEqual(resp.status_code, 200)
        # authentication_classes = [] -> AnonymousUser, even with a valid token.
        self.assertIsNone(CriteriaDecision.objects.get(application_id="OE-1").triggered_by)
        self.assertNotEqual(Application.objects.get(aryza_reference="OE-1").source_department, "Lead Generation")

    def test_cat_assess_is_callable_without_credentials(self):
        with patch(FETCH, return_value=_case("OE-2", [_creditor("Alpha Bank", 700_000)])):
            resp = APIClient().post("/api/v1/criteria/assess/", data={"aryza_reference": "OE-2"}, format="json")
        self.assertEqual(resp.status_code, 200)

    def test_upload_does_not_validate_internal_key(self):
        original = criteria_views.extract_credit_report
        criteria_views.extract_credit_report = lambda p: {
            "agency": "Experian", "accounts": [{"raw_name": "A"}], "mortgage_accounts": [], "other_accounts": [],
        }
        try:
            for headers in ({}, {"HTTP_X_INTERNAL_KEY": "definitely-wrong"}):
                resp = APIClient().post("/api/v1/criteria/upload-credit-report/", data={
                    "aryza_reference": "OE-3",
                    "credit_report": SimpleUploadedFile("r.pdf", b"%PDF-1.4", content_type="application/pdf"),
                }, format="multipart", **headers)
                self.assertEqual(resp.status_code, 200, headers)
        finally:
            criteria_views.extract_credit_report = original
