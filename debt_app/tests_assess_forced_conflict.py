"""
Run Assessment: previous-year HMRC VAT + Lead Gen low-income DRO conflict.

_derive_recommended_solution returns REVIEW_REQUIRED when the forced-DMP
(VAT) and forced-DRO (Lead Gen income below £399) overrides both fire.
get_recommendation() used to have no branch for it, so the final response
fell back to the ordinary hard-block/flag recommendation (IVA, DMP or
Breathing Space). These tests drive the real /api/v1/criteria/assess/
endpoint and check the final response and the saved decision.
"""

from unittest.mock import patch

from django.test import SimpleTestCase, TestCase
from rest_framework.test import APIClient

from debt_app.models import Application, CreditorCriteria, CriteriaDecision
from debt_app.recommendation_engine import get_recommendation
from debt_app.tests_cat_assessment_golden import _case, _creditor, _FixedDate

URL = "/api/v1/criteria/assess/"
FETCH = "debt_app.views.criteria_views.fetch_case_by_reference"
VAT = {"hmrc_debt_has_vat": True, "hmrc_previous_year_vat": True}
LOW_INCOME = {"income_pence": 30_000, "expenditure_pence": 10_000}


class _AssessFixture(TestCase):
    def setUp(self):
        self.client = APIClient()
        patcher = patch("debt_app.engine.criteria.date", _FixedDate)
        patcher.start()
        self.addCleanup(patcher.stop)
        for name in ("Alpha Bank", "Beta Loans"):
            CreditorCriteria.objects.create(creditor_name=name, representative="NONE", status="ACCEPT", is_active=True)

    def _assess(self, ref, lead_gen=False, dmp_checklist=None, **case_kw):
        if lead_gen:
            Application.objects.create(aryza_reference=ref, client_name="X", source_department="Lead Generation")
        case = _case(ref, [_creditor("Alpha Bank", 600_000), _creditor("Beta Loans", 450_000)], **case_kw)
        data = {"aryza_reference": ref}
        if dmp_checklist:
            data["dmp_checklist"] = dmp_checklist
        with patch(FETCH, return_value=case):
            resp = self.client.post(URL, data=data, format="json")
        self.assertEqual(resp.status_code, 200, resp.content)
        return resp.json()

    def _saved(self, ref):
        return CriteriaDecision.objects.get(application_id=ref).recommended_solution


class RunAssessmentForcedConflictTests(_AssessFixture):

    def test_vat_and_low_income_dro_together_require_review(self):
        body = self._assess("RA-CONFLICT", lead_gen=True, dmp_checklist=VAT, **LOW_INCOME)
        solution = body["recommended_solution"]
        self.assertEqual(solution["code"], "REVIEW_REQUIRED")
        self.assertEqual(solution["label"], "Caseworker Review Required")
        self.assertIn("decide between a DRO and a DMP", solution["rationale"])
        self.assertEqual(body["alternative_solutions"], [])
        self.assertEqual(self._saved("RA-CONFLICT"), "REVIEW_REQUIRED")

    def test_vat_alone_still_forces_dmp(self):
        body = self._assess("RA-VAT", lead_gen=True, dmp_checklist=VAT)
        self.assertEqual(body["recommended_solution"]["code"], "DMP")
        self.assertIn("previous-year HMRC VAT", body["recommended_solution"]["rationale"])
        self.assertEqual(self._saved("RA-VAT"), "DMP")

    def test_vat_alone_outside_lead_gen_still_forces_dmp_with_low_income(self):
        body = self._assess("RA-VAT-CAT", dmp_checklist=VAT, **LOW_INCOME)
        self.assertEqual(body["recommended_solution"]["code"], "DMP")
        self.assertIn("previous-year HMRC VAT", body["recommended_solution"]["rationale"])

    def test_low_income_dro_alone_still_forces_dro(self):
        body = self._assess("RA-DRO", lead_gen=True, **LOW_INCOME)
        self.assertEqual(body["recommended_solution"]["code"], "DRO")
        self.assertEqual(self._saved("RA-DRO"), "DRO")

    def test_has_vat_without_previous_year_and_low_income_still_forces_dro(self):
        body = self._assess("RA-DRO-VAT", lead_gen=True, dmp_checklist={"hmrc_debt_has_vat": True}, **LOW_INCOME)
        self.assertEqual(body["recommended_solution"]["code"], "DRO")

    def test_ordinary_assessment_is_unchanged(self):
        body = self._assess("RA-PLAIN")
        self.assertIn(body["recommended_solution"]["code"], ("IVA", "DMP", "BREATHING_SPACE"))
        self.assertNotEqual(body["recommended_solution"]["code"], "REVIEW_REQUIRED")
        self.assertNotIn("VAT", body["recommended_solution"]["rationale"])

    def test_ordinary_lead_gen_case_is_unchanged(self):
        body = self._assess("RA-LG-PLAIN", lead_gen=True)
        self.assertNotIn(body["recommended_solution"]["code"], ("REVIEW_REQUIRED", "DRO"))


class GetRecommendationConflictTests(SimpleTestCase):

    def test_conflict_is_checked_before_everything_else(self):
        rec = get_recommendation("ELIGIBLE", {}, {}, forced_conflict=True)
        self.assertEqual(rec["recommended_solution"]["code"], "REVIEW_REQUIRED")
        self.assertEqual(rec["alternative_solutions"], [])

    def test_without_conflict_the_ordinary_branches_are_unchanged(self):
        self.assertEqual(get_recommendation("ELIGIBLE", {}, {})["recommended_solution"]["code"], "IVA")
        self.assertEqual(get_recommendation("REFERRED", {}, {})["recommended_solution"]["code"], "IVA")
        self.assertEqual(get_recommendation("ELIGIBLE", {}, {}, vat_forced=True)["recommended_solution"]["code"], "DMP")
        self.assertEqual(get_recommendation("ELIGIBLE", {}, {}, dro_forced=True)["recommended_solution"]["code"], "DRO")
