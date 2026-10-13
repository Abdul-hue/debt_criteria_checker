"""
Multi-solution eligibility (IVA / DMP / DRO / Bankruptcy).

Source: "Debt Solution Criteria" document (2026-10-12). A customer can be
eligible for more than one solution. Criteria Aryza holds no data for
(assets/savings, England & Wales connection, current insolvency, previous
DRO) come from advisor answers in solution_checklist; unanswered means
NEEDS_REVIEW, never a silent pass or a block.
"""

from django.test import TestCase

from debt_app.engine.criteria import (
    SOLUTION_ELIGIBLE,
    SOLUTION_NEEDS_REVIEW,
    SOLUTION_NOT_ELIGIBLE,
    _evaluate_bankruptcy_solution,
    _evaluate_dmp_solution,
    _evaluate_dro_solution,
    _evaluate_iva_solution,
    _sanitize_solution_checklist,
    assess_case,
)

ALL_CONFIRMED = {
    "assets_over_2000": False,
    "england_wales_connection": True,
    "currently_insolvent": False,
    "dro_in_last_6_years": False,
}


def _case(**overrides):
    c = {
        "total_debt": 20000.0,
        "disposable_income": 50.0,
        "total_income": 1500.0,
        "has_property": False,
        "has_vehicle": False,
        "vehicle_value": None,
        "creditors": [],
        "solution_checklist": dict(ALL_CONFIRMED),
    }
    c.update(overrides)
    return c


DMP_PASSED = {"status": "DMP_ELIGIBLE", "reasons": [], "notes": []}


class SanitizeSolutionChecklistTests(TestCase):
    def test_missing_and_non_bool_values_are_unanswered(self):
        cleaned = _sanitize_solution_checklist({"assets_over_2000": "yes", "unknown": True})
        self.assertEqual(cleaned, {
            "assets_over_2000": None,
            "england_wales_connection": None,
            "currently_insolvent": None,
            "dro_in_last_6_years": None,
        })

    def test_bools_kept(self):
        self.assertEqual(_sanitize_solution_checklist(ALL_CONFIRMED), ALL_CONFIRMED)


class DroSolutionTests(TestCase):
    def test_all_criteria_met_is_eligible(self):
        self.assertEqual(_evaluate_dro_solution(_case())["status"], SOLUTION_ELIGIBLE)

    def test_debt_at_50000_not_eligible(self):
        result = _evaluate_dro_solution(_case(total_debt=50000.0))
        self.assertEqual(result["status"], SOLUTION_NOT_ELIGIBLE)

    def test_debt_just_under_50000_eligible(self):
        self.assertEqual(_evaluate_dro_solution(_case(total_debt=49999.99))["status"], SOLUTION_ELIGIBLE)

    def test_surplus_75_not_eligible(self):
        self.assertEqual(_evaluate_dro_solution(_case(disposable_income=75.0))["status"], SOLUTION_NOT_ELIGIBLE)

    def test_surplus_under_75_eligible(self):
        self.assertEqual(_evaluate_dro_solution(_case(disposable_income=74.99))["status"], SOLUTION_ELIGIBLE)

    def test_income_not_recorded_needs_review(self):
        result = _evaluate_dro_solution(_case(total_income=0, disposable_income=0))
        self.assertEqual(result["status"], SOLUTION_NEEDS_REVIEW)

    def test_property_owner_not_eligible(self):
        self.assertEqual(_evaluate_dro_solution(_case(has_property=True))["status"], SOLUTION_NOT_ELIGIBLE)

    def test_vehicle_4000_not_eligible(self):
        self.assertEqual(_evaluate_dro_solution(_case(vehicle_value=4000.0))["status"], SOLUTION_NOT_ELIGIBLE)

    def test_vehicle_on_hp_uses_net_value(self):
        hp = {"name": "Black Horse", "balance": 3000.0,
              "debt_type_normalised": "hire_purchase", "creditor_type": "car_hp"}
        c = _case(vehicle_value=6000.0, creditors=[hp])  # net £3,000
        self.assertEqual(_evaluate_dro_solution(c)["status"], SOLUTION_ELIGIBLE)

    def test_vehicle_value_missing_needs_review(self):
        result = _evaluate_dro_solution(_case(has_vehicle=True))
        self.assertEqual(result["status"], SOLUTION_NEEDS_REVIEW)

    def test_unanswered_questions_need_review_not_block(self):
        result = _evaluate_dro_solution(_case(solution_checklist={}))
        self.assertEqual(result["status"], SOLUTION_NEEDS_REVIEW)
        self.assertEqual(len(result["to_confirm"]), 4)
        self.assertEqual(result["reasons"], [])

    def test_each_failed_answer_blocks(self):
        for field, value in (
            ("assets_over_2000", True),
            ("england_wales_connection", False),
            ("currently_insolvent", True),
            ("dro_in_last_6_years", True),
        ):
            with self.subTest(field=field):
                answers = dict(ALL_CONFIRMED, **{field: value})
                result = _evaluate_dro_solution(_case(solution_checklist=answers))
                self.assertEqual(result["status"], SOLUTION_NOT_ELIGIBLE)

    def test_credit_report_insolvency_marker_mentioned_when_unanswered(self):
        answers = dict(ALL_CONFIRMED, currently_insolvent=None)
        result = _evaluate_dro_solution(_case(solution_checklist=answers, credit_report_iva_or_bankruptcy=True))
        self.assertIn("credit report shows", result["to_confirm"][0])


class BankruptcySolutionTests(TestCase):
    def test_eligible_with_no_debt_or_surplus_limit(self):
        result = _evaluate_bankruptcy_solution(_case(total_debt=90000.0, disposable_income=400.0))
        self.assertEqual(result["status"], SOLUTION_ELIGIBLE)
        self.assertTrue(any("income payments" in n for n in result["notes"]))

    def test_no_england_wales_connection_not_eligible(self):
        answers = dict(ALL_CONFIRMED, england_wales_connection=False)
        result = _evaluate_bankruptcy_solution(_case(solution_checklist=answers))
        self.assertEqual(result["status"], SOLUTION_NOT_ELIGIBLE)

    def test_connection_unanswered_needs_review(self):
        result = _evaluate_bankruptcy_solution(_case(solution_checklist={}))
        self.assertEqual(result["status"], SOLUTION_NEEDS_REVIEW)

    def test_savings_over_2000_needs_review(self):
        answers = dict(ALL_CONFIRMED, assets_over_2000=True)
        result = _evaluate_bankruptcy_solution(_case(solution_checklist=answers))
        self.assertEqual(result["status"], SOLUTION_NEEDS_REVIEW)

    def test_property_owner_still_eligible_with_note(self):
        result = _evaluate_bankruptcy_solution(_case(has_property=True))
        self.assertEqual(result["status"], SOLUTION_ELIGIBLE)
        self.assertTrue(any("home or equity" in n for n in result["notes"]))


class DmpSolutionTests(TestCase):
    def test_positive_surplus_eligible_with_term_note(self):
        result = _evaluate_dmp_solution(_case(total_debt=12000.0, disposable_income=200.0), DMP_PASSED)
        self.assertEqual(result["status"], SOLUTION_ELIGIBLE)
        self.assertTrue(any("60 months" in n for n in result["notes"]))

    def test_zero_surplus_not_eligible(self):
        result = _evaluate_dmp_solution(_case(disposable_income=0.0), DMP_PASSED)
        self.assertEqual(result["status"], SOLUTION_NOT_ELIGIBLE)

    def test_income_not_recorded_needs_review(self):
        result = _evaluate_dmp_solution(_case(total_income=0, disposable_income=0), DMP_PASSED)
        self.assertEqual(result["status"], SOLUTION_NEEDS_REVIEW)

    def test_checklist_rejection_carried_over(self):
        rejected = {"status": "DMP_REJECTED", "reasons": ["Council tax reason"], "notes": []}
        result = _evaluate_dmp_solution(_case(), rejected)
        self.assertEqual(result["status"], SOLUTION_NOT_ELIGIBLE)
        self.assertIn("Council tax reason", result["reasons"])

    def test_checklist_not_completed_needs_review(self):
        not_evaluated = {"status": "DMP_NOT_EVALUATED", "reasons": [], "notes": []}
        result = _evaluate_dmp_solution(_case(), not_evaluated)
        self.assertEqual(result["status"], SOLUTION_NEEDS_REVIEW)


class IvaSolutionTests(TestCase):
    def test_no_blocks_or_flags_eligible(self):
        self.assertEqual(_evaluate_iva_solution([], [], [])["status"], SOLUTION_ELIGIBLE)

    def test_hard_block_not_eligible(self):
        self.assertEqual(_evaluate_iva_solution([object()], [], [])["status"], SOLUTION_NOT_ELIGIBLE)

    def test_flag_needs_review(self):
        self.assertEqual(_evaluate_iva_solution([], [object()], [])["status"], SOLUTION_NEEDS_REVIEW)


class AssessCaseSolutionEligibilityTests(TestCase):
    def test_more_than_one_solution_can_be_eligible(self):
        # £5,000 debt (below the IVA £6,000 minimum), £50 surplus, no assets.
        case = {
            "creditors": [{"name": "Some Bank", "balance": 5000.0, "creditor_type": "credit_card"}],
            "financial_summary": {"net_balance": 50, "total_income": 1200},
            "evidence_ledger": [],
            "dmp_checklist": {"current_gas_bill": False},
            "solution_checklist": ALL_CONFIRMED,
        }
        result = assess_case(case, set())
        statuses = {s["code"]: s["status"] for s in result["solution_eligibility"]}
        self.assertEqual(list(statuses), ["IVA", "DMP", "DRO", "BANKRUPTCY"])
        self.assertEqual(statuses["IVA"], SOLUTION_NOT_ELIGIBLE)
        self.assertEqual(statuses["DMP"], SOLUTION_ELIGIBLE)
        self.assertEqual(statuses["DRO"], SOLUTION_ELIGIBLE)
        self.assertEqual(statuses["BANKRUPTCY"], SOLUTION_ELIGIBLE)

    def test_recommended_solution_unchanged_by_new_output(self):
        case = {
            "creditors": [{"name": "Some Bank", "balance": 5000.0, "creditor_type": "credit_card"}],
            "financial_summary": {"net_balance": 50, "total_income": 1200},
            "evidence_ledger": [],
        }
        result = assess_case(case, set())
        self.assertEqual(result["recommended_solution"], "IVA_NOT_VIABLE")
