"""
Lead Gen disposable income formula + £399 auto-DRO rule.

PART 1 — lead_gen_disposable_income (assess_case level):
  Total Household Income minus rent-or-mortgage monthly payment, gated on
  source_department == "Lead Generation". Falls back to Total Household
  Income alone when no rent/mortgage monthly payment was extracted (there is
  no structured rent figure anywhere in the system — only a credit-report
  mortgage monthly_payment, wired via _cross_check_property_from_credit_report).
  Must NEVER apply to Default/Advisor cases — disposable_income (the existing
  field TIG-02 etc. read) stays untouched either way.

PART 2 — £399 auto-DRO rule (_derive_recommended_solution):
  Lead Gen + lead_gen_disposable_income < £399 -> "FORCED_DRO_LG", at the same
  precedence tier as the existing VAT->FORCED_DMP_VAT override. Since the spec
  does not say which wins if both fire on the same case, that combination is
  treated as a genuine data conflict -> "REVIEW_REQUIRED", not a silent pick.

PART 3 — Integration test through the real /api/v1/criteria/assess/ endpoint
  (not just the isolated function), per the exact gap that hid the VAT-forced-
  DMP bug the first time: assess_case() can compute the right internal signal
  while get_recommendation() silently discards it before it reaches the
  frontend response.
"""

from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import SimpleTestCase, TestCase
from rest_framework.test import APIClient

from debt_app.aryza_client import CaseData
from debt_app.criteria_engine import (
    assess_case,
    detect_representatives,
    _derive_recommended_solution,
)
from debt_app.helpers import CreditorCriteria
from debt_app.models import Application, CreditReport, Department, UserProfile
from debt_app.views.criteria_views import AssessCaseView


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _mortgage_account(current_balance_pence, monthly_payment_pence):
    return {
        "raw_name": "Lloyds Bank Mortgages Ltd",
        "type_code": "MG",
        "normalised_name": "lloyds bank mortgages ltd",
        "matched_creditor": "Lloyds Bank Mortgages Ltd",
        "account_status": "up to date",
        "current_balance": current_balance_pence,
        "missed_payments_last_3_months": 0,
        "monthly_payment": monthly_payment_pence,
        "account_age_months": 60,
        "payment_history_months": 60,
        "recent_spending": False,
        "credit_limit": None,
        "utilisation_pct": None,
    }


def _build_case_data_obj(ref, total_income_pence):
    case = CaseData()
    case.aryza_reference = ref
    case.client_name = "Lead Gen Test Client"
    case.dob = "1985-01-01"
    case.employment_status = "employed"
    case.disposable_income = 30000  # £300.00 — the ordinary field, untouched throughout
    case.creditors = [
        {
            "name": "Test Loan Co",
            "type": "personal_loan",
            "balance": 500000,  # £5,000.00
            "ref": "LOAN-REF-1",
        },
    ]
    case.income = {
        "employment": total_income_pence,
        "universal_credit": 0,
        "dla": 0,
        "pip": 0,
        "other_benefits": 0,
        "third_party_contribution": 0,
        "total": total_income_pence,
    }
    case.expenditure = {
        "disability_expenses": 0,
        "total": 0,
    }
    return case


def _run_assess_case(case_data_obj, source_department=None):
    """Mirrors AssessCaseView.post()'s wiring, without the HTTP layer."""
    view = AssessCaseView()
    payload, prepared_creditors, _cr_unmatched = view._prepare_engine_payload(case_data_obj)
    payload["source_department"] = source_department
    detected_reps = detect_representatives(payload.get("creditors") or [])
    return assess_case(payload, detected_reps)


# ---------------------------------------------------------------------------
# PART 1 — lead_gen_disposable_income formula (assess_case level)
# ---------------------------------------------------------------------------

class LeadGenDisposableIncomeFormulaTests(TestCase):

    def setUp(self):
        CreditorCriteria.objects.create(
            creditor_name="Test Loan Co",
            representative="NONE",
            status="WILL_CONSIDER",
            is_active=True,
        )

    def test_lead_gen_with_mortgage_payment_subtracts_it(self):
        ref = "LG-DI-001"
        CreditReport.objects.create(
            aryza_reference=ref,
            uploaded_file="fake.pdf",
            extraction_status="extracted",
            extracted_data={
                "accounts": [],
                "mortgage_accounts": [_mortgage_account(10_000_00, 85_000)],  # £100k bal, £850/mo
            },
        )
        result = _run_assess_case(
            _build_case_data_obj(ref, total_income_pence=200_000),  # £2,000.00
            source_department="Lead Generation",
        )
        # £2,000.00 - £850.00 = £1,150.00 -> above £399, not forced DRO
        self.assertAlmostEqual(result["lead_gen_disposable_income"], 1150.0, places=2)
        self.assertNotEqual(result["recommended_solution"], "FORCED_DRO_LG")
        # The ordinary field is completely unaffected by the Lead Gen formula:
        # income>0/expenditure=0 always yields 0.0 via the existing DI fallback
        # branch in _prepare_engine_payload, regardless of source_department.
        self.assertEqual(result["disposable_income"], 0.0)

    def test_lead_gen_below_threshold_is_forced_to_dro(self):
        ref = "LG-DI-002"
        CreditReport.objects.create(
            aryza_reference=ref,
            uploaded_file="fake.pdf",
            extraction_status="extracted",
            extracted_data={
                "accounts": [],
                "mortgage_accounts": [_mortgage_account(10_000_00, 175_000)],  # £1,750/mo
            },
        )
        result = _run_assess_case(
            _build_case_data_obj(ref, total_income_pence=200_000),  # £2,000.00
            source_department="Lead Generation",
        )
        # £2,000.00 - £1,750.00 = £250.00 -> below £399
        self.assertAlmostEqual(result["lead_gen_disposable_income"], 250.0, places=2)
        self.assertEqual(result["recommended_solution"], "FORCED_DRO_LG")

    def test_lead_gen_with_no_mortgage_data_falls_back_to_total_income(self):
        """Azzam's stated fallback — not a gap. No credit report at all."""
        ref = "LG-DI-003"
        result = _run_assess_case(
            _build_case_data_obj(ref, total_income_pence=100_000),  # £1,000.00
            source_department="Lead Generation",
        )
        self.assertAlmostEqual(result["lead_gen_disposable_income"], 1000.0, places=2)

    def test_default_department_is_completely_unaffected(self):
        """Advisor/Default case: lead_gen_disposable_income must be None, and
        disposable_income-based logic (recommended_solution, etc.) must be
        byte-identical to the same payload run with no source_department at all."""
        ref = "LG-DI-004"
        CreditReport.objects.create(
            aryza_reference=ref,
            uploaded_file="fake.pdf",
            extraction_status="extracted",
            extracted_data={
                "accounts": [],
                "mortgage_accounts": [_mortgage_account(10_000_00, 175_000)],
            },
        )
        case_obj_a = _build_case_data_obj(ref, total_income_pence=100_000)
        result_default = _run_assess_case(case_obj_a, source_department="Default")

        case_obj_b = _build_case_data_obj(ref, total_income_pence=100_000)
        result_none = _run_assess_case(case_obj_b, source_department=None)

        self.assertIsNone(result_default["lead_gen_disposable_income"])
        self.assertIsNone(result_none["lead_gen_disposable_income"])
        self.assertNotEqual(result_default["recommended_solution"], "FORCED_DRO_LG")

        # Every other key is unaffected by source_department, proving the Lead
        # Gen formula is fully gated and doesn't leak into the Default path.
        for key in ("recommended_solution", "disposable_income", "overall", "overall_status"):
            self.assertEqual(result_default[key], result_none[key])


# ---------------------------------------------------------------------------
# PART 2 — precedence: VAT-forced-DMP vs DRO-forced conflict
# ---------------------------------------------------------------------------

class LeadGenDroPrecedenceTests(SimpleTestCase):

    def _case(self, source_department=None, lg_di=None, vat=False):
        return {
            "source_department": source_department,
            "lead_gen_disposable_income": lg_di,
            "dmp_checklist": {"hmrc_previous_year_vat": vat},
        }

    def test_lead_gen_below_threshold_alone_forces_dro(self):
        result = _derive_recommended_solution(
            [], [], [], self._case(source_department="Lead Generation", lg_di=100.0, vat=False)
        )
        self.assertEqual(result, "FORCED_DRO_LG")

    def test_lead_gen_above_threshold_does_not_force_dro(self):
        result = _derive_recommended_solution(
            [], [], [], self._case(source_department="Lead Generation", lg_di=500.0, vat=False)
        )
        self.assertEqual(result, "IVA_VIABLE")

    def test_non_lead_gen_below_399_does_not_force_dro(self):
        # lead_gen_disposable_income should never even be populated for a
        # non-Lead-Gen case, but the guard must hold even if it somehow were.
        result = _derive_recommended_solution(
            [], [], [], self._case(source_department="Default", lg_di=100.0, vat=False)
        )
        self.assertEqual(result, "IVA_VIABLE")

    def test_vat_and_dro_both_firing_is_a_conflict_not_a_silent_pick(self):
        result = _derive_recommended_solution(
            [], [], [], self._case(source_department="Lead Generation", lg_di=100.0, vat=True)
        )
        self.assertEqual(result, "REVIEW_REQUIRED")

    def test_vat_alone_unaffected_by_new_dro_branch(self):
        result = _derive_recommended_solution(
            [], [], [], self._case(source_department="Default", lg_di=None, vat=True)
        )
        self.assertEqual(result, "FORCED_DMP_VAT")


# ---------------------------------------------------------------------------
# PART 3 — integration test through the real endpoint
# ---------------------------------------------------------------------------

class LeadGenDroIntegrationTests(TestCase):
    """Exercises /api/v1/criteria/assess/ end-to-end — the layer where the VAT
    override was previously silently discarded by get_recommendation(). Proves
    the same wiring holds for the £399 auto-DRO rule."""

    def setUp(self):
        self.client = APIClient()
        CreditorCriteria.objects.create(
            creditor_name="Test Loan Co",
            representative="NONE",
            status="WILL_CONSIDER",
            is_active=True,
        )
        self.lead_gen_dept = Department.objects.create(name="Lead Generation", slug="lead-generation")

    @patch("debt_app.views.criteria_views.fetch_case_by_reference")
    def test_lead_gen_below_399_forces_dro_through_real_endpoint(self, mock_fetch):
        ref = "LG-DRO-INT-001"
        Application.objects.create(aryza_reference=ref, client_name="Lead Gen Test Client")
        CreditReport.objects.create(
            aryza_reference=ref,
            uploaded_file="fake.pdf",
            extraction_status="extracted",
            extracted_data={
                "accounts": [],
                "mortgage_accounts": [_mortgage_account(10_000_00, 175_000)],  # £1,750/mo
            },
        )
        mock_fetch.return_value = _build_case_data_obj(ref, total_income_pence=200_000)  # £2,000.00

        lead_gen_user = User.objects.create_user(username="leadgen-int", password="pass")
        UserProfile.objects.create(user=lead_gen_user, department=self.lead_gen_dept)
        self.client.force_authenticate(user=lead_gen_user)

        resp = self.client.post(
            "/api/v1/criteria/assess/",
            data={"aryza_reference": ref},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        body = resp.json()

        solution = body.get("recommended_solution")
        self.assertIsInstance(solution, dict)
        self.assertEqual(solution.get("code"), "DRO")
        self.assertIn("Lead Generation", solution.get("rationale", ""))
        self.assertIn("399", solution.get("rationale", ""))

        from debt_app.models import CriteriaDecision
        decision = CriteriaDecision.objects.get(application_id=ref)
        self.assertEqual(decision.recommended_solution, "DRO")

    @patch("debt_app.views.criteria_views.fetch_case_by_reference")
    def test_lead_gen_above_399_is_not_forced_through_real_endpoint(self, mock_fetch):
        ref = "LG-DRO-INT-002"
        Application.objects.create(aryza_reference=ref, client_name="Lead Gen Test Client")
        CreditReport.objects.create(
            aryza_reference=ref,
            uploaded_file="fake.pdf",
            extraction_status="extracted",
            extracted_data={
                "accounts": [],
                "mortgage_accounts": [_mortgage_account(10_000_00, 85_000)],  # £850/mo
            },
        )
        mock_fetch.return_value = _build_case_data_obj(ref, total_income_pence=200_000)  # £2,000.00

        lead_gen_user = User.objects.create_user(username="leadgen-int-2", password="pass")
        UserProfile.objects.create(user=lead_gen_user, department=self.lead_gen_dept)
        self.client.force_authenticate(user=lead_gen_user)

        resp = self.client.post(
            "/api/v1/criteria/assess/",
            data={"aryza_reference": ref},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        body = resp.json()

        solution = body.get("recommended_solution")
        self.assertIsInstance(solution, dict)
        self.assertNotEqual(solution.get("code"), "DRO")

        from debt_app.models import CriteriaDecision
        decision = CriteriaDecision.objects.get(application_id=ref)
        self.assertNotEqual(decision.recommended_solution, "DRO")

    @patch("debt_app.views.criteria_views.fetch_case_by_reference")
    def test_default_department_case_unaffected_through_real_endpoint(self, mock_fetch):
        """Same low-DI/high-mortgage-payment shape as the forced-DRO case above,
        but the requesting user is NOT Lead Generation — must behave exactly as
        it did before this feature existed (never forced to DRO)."""
        ref = "LG-DRO-INT-003"
        Application.objects.create(aryza_reference=ref, client_name="Advisor Test Client")
        CreditReport.objects.create(
            aryza_reference=ref,
            uploaded_file="fake.pdf",
            extraction_status="extracted",
            extracted_data={
                "accounts": [],
                "mortgage_accounts": [_mortgage_account(10_000_00, 175_000)],  # £1,750/mo
            },
        )
        mock_fetch.return_value = _build_case_data_obj(ref, total_income_pence=200_000)

        resp = self.client.post(
            "/api/v1/criteria/assess/",
            data={"aryza_reference": ref},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        body = resp.json()
        solution = body.get("recommended_solution")
        self.assertNotEqual((solution or {}).get("code") if isinstance(solution, dict) else solution, "DRO")

        from debt_app.models import CriteriaDecision
        decision = CriteriaDecision.objects.get(application_id=ref)
        self.assertNotEqual(decision.recommended_solution, "DRO")
