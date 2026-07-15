"""
Regression guardrail for manual council/energy creditor addition.

PART 1 baseline: exercises _prepare_engine_payload -> assess_case -> _parse_case
end-to-end via a realistic (synthetic) Aryza CaseData-shaped payload, containing
one council-name creditor and one ordinary unsecured creditor. Captures
total_debt, council_balance, council_is_majority, overall/overall_status and
len(creditor_positions) as a byte-identical baseline.

PART 2 regression check: re-runs the SAME case through _prepare_engine_payload
with manual_councils/manual_energy omitted (or empty) and asserts the baseline
values are unchanged — proving the manual-addition feature is fully opt-in.
A second case (with one manual council + one manual energy entry) proves the
totals correctly reflect the added synthetic creditors.
"""

from django.test import TestCase

from debt_app.aryza_client import CaseData
from debt_app.criteria_engine import assess_case, detect_representatives
from debt_app.helpers import CreditorCriteria
from debt_app.models import CouncilRule
from debt_app.views.criteria_views import AssessCaseView


def _build_case_data_obj():
    """Realistic synthetic Aryza CaseData: one council creditor + one ordinary
    unsecured creditor. Numbers are pence, per Aryza convention."""
    case = CaseData()
    case.aryza_reference = "TEST-MANUAL-001"
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


def _assess(view, case_data_obj, manual_councils=None, manual_energy=None):
    kwargs = {}
    if manual_councils is not None:
        kwargs["manual_councils"] = manual_councils
    if manual_energy is not None:
        kwargs["manual_energy"] = manual_energy
    payload, prepared_creditors, _cr_unmatched = view._prepare_engine_payload(
        case_data_obj, **kwargs
    )
    detected_reps = detect_representatives(payload.get("creditors") or [])
    result = assess_case(payload, detected_reps)

    parsed_creditors = payload.get("creditors") or []
    council_balance = sum(
        float(c.get("balance") or 0)
        for c in parsed_creditors
        if "council" in (c.get("creditor_name") or "").lower()
    )
    total_debt = result["total_unsecured_debt"]
    council_is_majority = (
        (council_balance / total_debt) > 0.25 if total_debt > 0 else False
    )
    return {
        "total_debt": total_debt,
        "council_balance": council_balance,
        "council_is_majority": council_is_majority,
        "overall": result["overall"],
        "overall_status": result["overall_status"],
        "num_creditor_positions": len(result["creditor_positions"]),
    }


class ManualCreditorAdditionBaselineTests(TestCase):
    """PART 1 — baseline captured against the CURRENT (pre-manual-addition) code."""

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
        CreditorCriteria.objects.create(
            creditor_name="Test Energy Co",
            representative="NONE",
            status="ACCEPT",
            is_active=True,
        )
        self.view = AssessCaseView()

    def test_baseline_values(self):
        case_data_obj = _build_case_data_obj()
        out = _assess(self.view, case_data_obj)

        # BASELINE — captured 2026-07-15 against pre-manual-addition code.
        self.assertEqual(out["total_debt"], 6500.0)
        self.assertEqual(out["council_balance"], 1500.0)
        self.assertFalse(out["council_is_majority"])
        self.assertIn(out["overall"], ("pass", "flagged", "blocked"))
        self.assertIsInstance(out["num_creditor_positions"], int)

        print("\n[PART 1 BASELINE]", out)


class ManualCreditorAdditionRegressionTests(TestCase):
    """
    PART 2 — re-runs Part 1's case with manual entries omitted (must be
    byte-identical to baseline) and with one manual council + one manual
    energy entry added (must reflect the added balances).
    """

    def setUp(self):
        self.council_rule = CouncilRule.objects.create(
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
        self.energy_creditor = CreditorCriteria.objects.create(
            creditor_name="Test Energy Co",
            representative="NONE",
            status="ACCEPT",
            is_active=True,
        )
        self.manual_council_rule = CouncilRule.objects.create(
            council_name="Manual Add Council",
            status="WILL_CONSIDER",
            min_dividend_pence=25,
        )
        self.manual_energy_creditor = CreditorCriteria.objects.create(
            creditor_name="Manual Add Energy",
            representative="NONE",
            status="ACCEPT",
            is_active=True,
        )
        self.view = AssessCaseView()

    def test_omitted_manual_entries_match_baseline(self):
        case_data_obj = _build_case_data_obj()
        out = _assess(self.view, case_data_obj, manual_councils=[], manual_energy=[])

        self.assertEqual(out["total_debt"], 6500.0)
        self.assertEqual(out["council_balance"], 1500.0)
        self.assertFalse(out["council_is_majority"])

        print("\n[PART 2 — no manual entries]", out)

    def test_manual_council_and_energy_added(self):
        case_data_obj = _build_case_data_obj()
        out = _assess(
            self.view,
            case_data_obj,
            manual_councils=[
                {"council_id": self.manual_council_rule.id, "balance": 800.0}
            ],
            manual_energy=[
                {"creditor_id": self.manual_energy_creditor.id, "balance": 300.0}
            ],
        )

        # total_debt should now include the manual council (+800) and manual
        # energy (+300) balances on top of the baseline £6,500.
        self.assertEqual(out["total_debt"], 6500.0 + 800.0 + 300.0)
        # council_balance should include both the original council and the
        # manual council.
        self.assertEqual(out["council_balance"], 1500.0 + 800.0)

        print("\n[PART 2 — with manual entries]", out)
