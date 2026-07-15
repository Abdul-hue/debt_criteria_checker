"""
Regression guardrail for the DMP Eligibility Checklist fields (Phase A —
plumbing only, no rule logic reads these yet).

PART 1: proves AssessCaseView's default-filling logic (mirrors post()) fills
every missing key with False, and never requires the frontend to send all
11 keys.

PART 2: proves assess_case()'s output is IDENTICAL whether or not
case_data["dmp_checklist"] is present — since nothing reads it yet, this
should be trivially true, but we prove it rather than assume it. Reuses the
same synthetic case shape as tests_manual_creditor_addition.py.
"""

from django.test import TestCase

from debt_app.aryza_client import CaseData
from debt_app.criteria_engine import (
    assess_case,
    detect_representatives,
    _evaluate_dmp_eligibility,
)
from debt_app.helpers import CreditorCriteria
from debt_app.models import CouncilRule
from debt_app.views.criteria_views import AssessCaseView, DMP_CHECKLIST_FIELDS


def _build_case_data_obj():
    case = CaseData()
    case.aryza_reference = "TEST-DMP-001"
    case.client_name = "Test Client"
    case.dob = "1985-01-01"
    case.employment_status = "employed"
    case.disposable_income = 30000  # £300.00
    case.creditors = [
        {
            "name": "Test City Council",
            "type": "council_tax",
            "balance": 150000,  # £1,500.00
            "ref": "COUNCIL-REF-1",
        },
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


def _run(view, case_data_obj, dmp_checklist=None):
    payload, prepared_creditors, _cr_unmatched = view._prepare_engine_payload(case_data_obj)
    if dmp_checklist is not None:
        payload["dmp_checklist"] = dmp_checklist
    detected_reps = detect_representatives(payload.get("creditors") or [])
    result = assess_case(payload, detected_reps)

    parsed_creditors = payload.get("creditors") or []
    council_balance = sum(
        float(c.get("balance") or 0)
        for c in parsed_creditors
        if "council" in (c.get("creditor_name") or "").lower()
    )
    total_debt = result["total_unsecured_debt"]
    return {
        "total_debt": total_debt,
        "council_balance": council_balance,
        "overall": result["overall"],
        "overall_status": result["overall_status"],
        "num_creditor_positions": len(result["creditor_positions"]),
    }


class DmpChecklistDefaultFillingTests(TestCase):
    """PART 1 — default-filling logic (mirrors AssessCaseView.post())."""

    def _fill(self, raw):
        return {
            field: bool(raw.get(field, False))
            for field in DMP_CHECKLIST_FIELDS
        }

    def test_empty_dict_defaults_all_false(self):
        filled = self._fill({})
        self.assertEqual(len(filled), 11)
        self.assertTrue(all(v is False for v in filled.values()))

    def test_partial_dict_defaults_missing_keys(self):
        raw = {"current_gas_bill": True, "current_year_council_tax": True}
        filled = self._fill(raw)
        self.assertTrue(filled["current_gas_bill"])
        self.assertTrue(filled["current_year_council_tax"])
        # every other key defaults to False
        for field in DMP_CHECKLIST_FIELDS:
            if field not in raw:
                self.assertFalse(filled[field])

    def test_all_11_fields_present(self):
        expected = {
            "current_year_council_tax", "previous_year_council_tax",
            "lost_right_to_pay_instalments", "current_gas_bill",
            "current_electric_bill", "previous_gas_provider_debt",
            "previous_electric_provider_debt", "current_water_bill",
            "government_parking_hmrc_debt", "private_parking_debt",
            "current_phone_contract",
        }
        self.assertEqual(set(DMP_CHECKLIST_FIELDS), expected)


class DmpChecklistRegressionTests(TestCase):
    """PART 2 — assess_case output is unaffected by dmp_checklist presence."""

    def setUp(self):
        CouncilRule.objects.create(
            council_name="Test City Council",
            status="WILL_CONSIDER",
            min_dividend_pence=25,
        )
        CreditorCriteria.objects.create(
            creditor_name="Test Loan Co",
            representative="NONE",
            status="WILL_CONSIDER",
            is_active=True,
        )
        self.view = AssessCaseView()

    def test_output_identical_with_and_without_dmp_checklist(self):
        case_data_obj = _build_case_data_obj()

        baseline = _run(self.view, case_data_obj, dmp_checklist=None)

        all_false = {field: False for field in DMP_CHECKLIST_FIELDS}
        with_all_false = _run(self.view, case_data_obj, dmp_checklist=all_false)

        all_true = {field: True for field in DMP_CHECKLIST_FIELDS}
        with_all_true = _run(self.view, case_data_obj, dmp_checklist=all_true)

        self.assertEqual(baseline, with_all_false)
        self.assertEqual(baseline, with_all_true)

        print("\n[DMP CHECKLIST REGRESSION] baseline:", baseline)
        print("[DMP CHECKLIST REGRESSION] with_all_true:", with_all_true)

    def test_hard_blocks_flags_passed_info_recommended_solution_untouched(self):
        """Same case run with a DMP-rejecting checklist must not change any of
        hard_blocks/flags/passed/info/recommended_solution — only the new
        sibling dmp_eligibility key should differ."""
        case_data_obj = _build_case_data_obj()
        payload, _prepared, _unmatched = self.view._prepare_engine_payload(case_data_obj)
        detected_reps = detect_representatives(payload.get("creditors") or [])

        baseline_result = assess_case(dict(payload), detected_reps)

        payload_with_checklist = dict(payload)
        payload_with_checklist["dmp_checklist"] = {
            "current_year_council_tax": True,
            "previous_year_council_tax": True,
            "lost_right_to_pay_instalments": True,
        }
        result_with_checklist = assess_case(payload_with_checklist, detected_reps)

        for key in ("hard_blocks", "flags", "passed", "info", "recommended_solution"):
            self.assertEqual(
                [r.rule_id if hasattr(r, "rule_id") else r for r in baseline_result[key]]
                if isinstance(baseline_result[key], list) else baseline_result[key],
                [r.rule_id if hasattr(r, "rule_id") else r for r in result_with_checklist[key]]
                if isinstance(result_with_checklist[key], list) else result_with_checklist[key],
                f"{key} must be unaffected by dmp_checklist",
            )

        self.assertEqual(baseline_result["dmp_eligibility"]["status"], "DMP_NOT_EVALUATED")
        self.assertEqual(result_with_checklist["dmp_eligibility"]["status"], "DMP_REJECTED")


def _make_c(total_debt, checklist=None):
    return {"total_debt": total_debt, "dmp_checklist": checklist}


class DmpEligibilityUnitTests(TestCase):
    """PART 4 — direct unit tests of _evaluate_dmp_eligibility."""

    def test_no_checklist_is_not_evaluated(self):
        result = _evaluate_dmp_eligibility(_make_c(6500, None))
        self.assertEqual(result["status"], "DMP_NOT_EVALUATED")
        self.assertEqual(result["reasons"], [])

    def test_empty_checklist_dict_is_not_evaluated(self):
        result = _evaluate_dmp_eligibility(_make_c(6500, {}))
        self.assertEqual(result["status"], "DMP_NOT_EVALUATED")

    def test_above_minimum_all_false_is_eligible(self):
        checklist = {field: False for field in DMP_CHECKLIST_FIELDS}
        result = _evaluate_dmp_eligibility(_make_c(3500, checklist))
        self.assertEqual(result["status"], "DMP_ELIGIBLE")
        self.assertEqual(result["reasons"], [])

    def test_lost_right_to_pay_with_both_years_council_tax_rejected(self):
        checklist = {field: False for field in DMP_CHECKLIST_FIELDS}
        checklist.update({
            "current_year_council_tax": True,
            "previous_year_council_tax": True,
            "lost_right_to_pay_instalments": True,
        })
        result = _evaluate_dmp_eligibility(_make_c(3500, checklist))
        self.assertEqual(result["status"], "DMP_REJECTED")
        self.assertIn(
            "Lost right to pay instalments with both current and previous "
            "year council tax outstanding",
            result["reasons"],
        )

    def test_below_minimum_debt_rejected_regardless_of_other_fields(self):
        checklist = {field: False for field in DMP_CHECKLIST_FIELDS}
        result = _evaluate_dmp_eligibility(_make_c(2000, checklist))
        self.assertEqual(result["status"], "DMP_REJECTED")
        self.assertIn("Total debt below £3,000 minimum", result["reasons"])

    def test_current_gas_bill_alone_does_not_reject_but_notes_exclusion(self):
        """Confirmed with user 2026-07-15: Musa's rule excludes that specific
        debt from the DMP arrangement — it does not reject the whole case.
        This differs from the original task spec's assumption of a hard reject."""
        checklist = {field: False for field in DMP_CHECKLIST_FIELDS}
        checklist["current_gas_bill"] = True
        result = _evaluate_dmp_eligibility(_make_c(3500, checklist))
        self.assertEqual(result["status"], "DMP_ELIGIBLE")
        self.assertEqual(result["reasons"], [])
        self.assertTrue(any("current gas bill" in note for note in result["notes"]))

    def test_government_parking_hmrc_debt_alone_rejected(self):
        checklist = {field: False for field in DMP_CHECKLIST_FIELDS}
        checklist["government_parking_hmrc_debt"] = True
        result = _evaluate_dmp_eligibility(_make_c(3500, checklist))
        self.assertEqual(result["status"], "DMP_REJECTED")

    def test_government_parking_offset_by_private_parking_not_rejected(self):
        checklist = {field: False for field in DMP_CHECKLIST_FIELDS}
        checklist["government_parking_hmrc_debt"] = True
        checklist["private_parking_debt"] = True
        result = _evaluate_dmp_eligibility(_make_c(3500, checklist))
        self.assertEqual(result["status"], "DMP_ELIGIBLE")

    def test_below_minimum_debt_takes_priority_message_present_even_with_other_true_fields(self):
        checklist = {field: True for field in DMP_CHECKLIST_FIELDS}
        result = _evaluate_dmp_eligibility(_make_c(2000, checklist))
        self.assertEqual(result["status"], "DMP_REJECTED")
        self.assertIn("Total debt below £3,000 minimum", result["reasons"])

    def test_previous_gas_provider_debt_alone_is_eligible_with_note(self):
        checklist = {field: False for field in DMP_CHECKLIST_FIELDS}
        checklist["previous_gas_provider_debt"] = True
        result = _evaluate_dmp_eligibility(_make_c(3500, checklist))
        self.assertEqual(result["status"], "DMP_ELIGIBLE")
        self.assertEqual(result["reasons"], [])
        self.assertEqual(
            result["notes"], ["Previous gas provider debt — included in DMP total."]
        )

    def test_previous_electric_provider_debt_alone_is_eligible_with_note(self):
        checklist = {field: False for field in DMP_CHECKLIST_FIELDS}
        checklist["previous_electric_provider_debt"] = True
        result = _evaluate_dmp_eligibility(_make_c(3500, checklist))
        self.assertEqual(result["status"], "DMP_ELIGIBLE")
        self.assertEqual(result["reasons"], [])
        self.assertEqual(
            result["notes"], ["Previous electricity provider debt — included in DMP total."]
        )

    def test_current_water_bill_alone_is_eligible_with_note(self):
        checklist = {field: False for field in DMP_CHECKLIST_FIELDS}
        checklist["current_water_bill"] = True
        result = _evaluate_dmp_eligibility(_make_c(3500, checklist))
        self.assertEqual(result["status"], "DMP_ELIGIBLE")
        self.assertEqual(result["reasons"], [])
        self.assertEqual(
            result["notes"], ["Current water bill — included in DMP total."]
        )
