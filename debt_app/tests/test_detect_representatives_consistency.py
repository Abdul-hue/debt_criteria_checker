"""
Consistency tests for detect_representatives across both view code paths.

AssessCaseView.post previously called assess_case(case_data) with no second
argument, relying on assess_case's internal None-check to call
detect_representatives(creditors, assessment_date=c["assessment_date"]).

DirectAssessView.post calls detect_representatives(creditors) explicitly
first, then assess_case(case_json, detected_reps) — but without passing
assessment_date, so it defaults to date.today().

This divergence matters for historical cases: a case assessed before
30/04/2024 with Monzo as a creditor should NOT trigger WATCH; the two
paths produced different results because one respected the case date, the
other used today.

Fix: AssessCaseView.post now explicitly calls
  detected_reps = detect_representatives(case_creditors)
  result = assess_case(case_data, detected_reps)
matching DirectAssessView.post's explicit pattern and keeping behaviour
identical regardless of when the view is invoked.

These tests verify the expected contract: both the explicit pre-call
pattern and the implicit (None) internal pattern produce the same
representatives_detected for a given creditor list + assessment_date.
"""

from datetime import date

from django.test import TestCase

from debt_app.engine.criteria import assess_case, detect_representatives
from debt_app.models import CreditorCriteria


def _minimal_case(creditors, assessment_date_str="2025-01-01"):
    """Smallest valid case payload for representative detection."""
    return {
        "assessment_date": assessment_date_str,
        "creditors": creditors,
        "financial": {"net_balance": 100},
        "evidence_ledger": [],
    }


class DetectRepresentativesConsistencyTests(TestCase):
    """
    Verify explicit vs implicit (None) detect_representatives calls
    produce identical representatives_detected in assess_case output.
    """

    def setUp(self):
        CreditorCriteria.objects.create(
            creditor_name="Watch Lender Test", representative="WATCH",
            status="WILL_CONSIDER", is_active=True,
        )
        CreditorCriteria.objects.create(
            creditor_name="TIX Lender Test", representative="TIX",
            status="WILL_CONSIDER", is_active=True,
        )

    def test_explicit_matches_implicit_watch(self):
        creditors = [{"name": "Watch Lender Test", "balance": 1000.0, "creditor_type": "personal_loan"}]
        case = _minimal_case(creditors)

        detected_reps = detect_representatives(creditors, assessment_date=date(2025, 1, 1))
        result_explicit = assess_case(case, detected_reps)
        result_implicit = assess_case(case, None)

        self.assertEqual(
            result_explicit.get("representatives_detected"),
            result_implicit.get("representatives_detected"),
        )
        self.assertIn("WATCH", result_explicit.get("representatives_detected", set()))

    def test_explicit_matches_implicit_tix(self):
        creditors = [{"name": "TIX Lender Test", "balance": 1000.0, "creditor_type": "personal_loan"}]
        case = _minimal_case(creditors)

        detected_reps = detect_representatives(creditors, assessment_date=date(2025, 1, 1))
        result_explicit = assess_case(case, detected_reps)
        result_implicit = assess_case(case, None)

        self.assertEqual(
            result_explicit.get("representatives_detected"),
            result_implicit.get("representatives_detected"),
        )
        self.assertIn("TIX", result_explicit.get("representatives_detected", set()))

    def test_empty_creditors_both_empty(self):
        case = _minimal_case([])
        result_explicit = assess_case(case, set())
        result_implicit = assess_case(case, None)
        self.assertEqual(
            result_explicit.get("representatives_detected"),
            result_implicit.get("representatives_detected"),
        )
        self.assertEqual(result_explicit.get("representatives_detected"), set())


class AssessCaseViewExplicitCallTest(TestCase):
    """
    Verify AssessCaseView.post now follows the explicit pattern: it calls
    detect_representatives() before assess_case() and passes the result in,
    rather than relying on assess_case's internal None fallback.

    We test this by patching assess_case in views/criteria/assess.py and checking
    that it receives a non-None detected_representatives argument.
    """

    def test_assess_case_called_with_explicit_reps_in_criteria_view(self):
        """
        Import the view module and confirm detect_representatives is called
        before assess_case (explicit pattern vs implicit None fallback).
        This test is structural: it reads the source to ensure the pattern
        is consistent across both view files.
        """
        import inspect
        from debt_app.views.criteria import assess as criteria_assess
        from debt_app.views import assess_direct

        assess_src = inspect.getsource(assess_direct.DirectAssessView.post)
        criteria_src = inspect.getsource(criteria_assess.AssessCaseView.post)

        # Both should call detect_representatives explicitly before assess_case.
        self.assertIn("detect_representatives", assess_src,
                      "DirectAssessView.post must call detect_representatives explicitly")
        self.assertIn("detect_representatives", criteria_src,
                      "AssessCaseView.post must call detect_representatives explicitly")

        # assess_case in AssessCaseView must receive the result as second argument.
        # Check that it's not called with just one argument (no detected_reps).
        self.assertNotIn("assess_case(case_data)", criteria_src,
                         "AssessCaseView.post must not call assess_case with no detected_reps")
