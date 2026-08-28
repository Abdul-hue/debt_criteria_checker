"""
Tests for Application.source_department tagging in AssessCaseView.post().

Confirms:
(a) first run by a Lead Generation user tags "Lead Generation", and a later
    re-run of the same case by a different-department user never overwrites it.
(b) an anonymous/unauthenticated request tags "Default" without crashing
    (AssessCaseView is AllowAny — request.user may have no profile at all).
(c) a run against an aryza_reference with no matching Application row skips
    tagging entirely and does not error.
"""

from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient

from debt_app.integrations.aryza import CaseData
from debt_app.models import Application, CouncilRule, Department, UserProfile
from debt_app.models import CreditorCriteria


def _build_case_data_obj(ref="DEPT-TAG-001"):
    case = CaseData()
    case.aryza_reference = ref
    case.client_name = "Dept Tag Test Client"
    case.dob = "1985-01-01"
    case.employment_status = "employed"
    case.disposable_income = 30000  # £300.00
    case.creditors = [
        {
            "name": "Test Loan Co",
            "type": "personal_loan",
            "balance": 500000,  # £5,000.00
            "ref": "LOAN-REF-1",
        },
    ]
    case.income = {
        "employment": 150000,
        "universal_credit": 0,
        "dla": 0,
        "pip": 0,
        "other_benefits": 0,
        "third_party_contribution": 0,
        "total": 150000,
    }
    case.expenditure = {
        "disability_expenses": 0,
        "total": 120000,
    }
    return case


class SourceDepartmentTaggingTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        CreditorCriteria.objects.create(
            creditor_name="Test Loan Co",
            representative="NONE",
            status="WILL_CONSIDER",
            is_active=True,
        )
        self.default_dept = Department.objects.create(name="Default", slug="default")
        self.lead_gen_dept = Department.objects.create(name="Lead Generation", slug="lead-generation")

    def _post_assess(self, aryza_reference):
        with patch(
            "debt_app.views.criteria.assess.fetch_case_by_reference",
            return_value=_build_case_data_obj(aryza_reference),
        ):
            return self.client.post(
                "/api/v1/criteria/assess/",
                data={"aryza_reference": aryza_reference},
                format="json",
            )

    def test_first_run_by_lead_gen_user_tags_and_is_never_overwritten(self):
        lead_gen_user = User.objects.create_user(username="leadgen1", password="pass")
        UserProfile.objects.create(user=lead_gen_user, department=self.lead_gen_dept)
        advisor_user = User.objects.create_user(username="advisor1", password="pass")
        UserProfile.objects.create(user=advisor_user, department=self.default_dept)

        app_obj = Application.objects.create(
            aryza_reference="DEPT-TAG-LEADGEN", client_name="Dept Tag Test Client"
        )
        self.assertIsNone(app_obj.source_department)

        self.client.force_authenticate(user=lead_gen_user)
        resp = self._post_assess("DEPT-TAG-LEADGEN")
        self.assertEqual(resp.status_code, 200, resp.content)
        app_obj.refresh_from_db()
        self.assertEqual(app_obj.source_department, "Lead Generation")

        # Second run by an Advisor (Default dept) must NOT overwrite the tag.
        self.client.force_authenticate(user=advisor_user)
        resp2 = self._post_assess("DEPT-TAG-LEADGEN")
        self.assertEqual(resp2.status_code, 200, resp2.content)
        app_obj.refresh_from_db()
        self.assertEqual(app_obj.source_department, "Lead Generation")

    def test_anonymous_request_tags_default_without_crashing(self):
        app_obj = Application.objects.create(
            aryza_reference="DEPT-TAG-ANON", client_name="Dept Tag Test Client"
        )
        self.assertIsNone(app_obj.source_department)

        resp = self._post_assess("DEPT-TAG-ANON")
        self.assertEqual(resp.status_code, 200, resp.content)
        app_obj.refresh_from_db()
        self.assertEqual(app_obj.source_department, "Default")

    def test_no_application_row_skips_tagging_cleanly(self):
        # No Application row created for this reference at all.
        resp = self._post_assess("DEPT-TAG-NOROW")
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertFalse(Application.objects.filter(aryza_reference="DEPT-TAG-NOROW").exists())
