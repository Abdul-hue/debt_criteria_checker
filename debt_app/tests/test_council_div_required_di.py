"""
COUNCIL-DIV-REQUIRED-DI: where council debt is the majority and a DIV is known,
Required DI = ((Debt Level x DIV) + £4,250) / term, and the case DI must meet it.
Seeded switched off (migration 0095) with the fee in threshold_value.
"""
from decimal import Decimal

from django.test import SimpleTestCase, TestCase

from debt_app.engine.criteria import (
    COUNCIL_DIV_RULE_ID,
    _council_div_fee,
    _council_div_required_di,
    _parse_case,
    assess_case,
)
from debt_app.models import CouncilRule, GlobalCriteria


def _case(creditors, monthly_di=150, **extra):
    case = {"assessment_date": "2026-10-28", "creditors": creditors, "monthly_di": monthly_di}
    case.update(extra)
    return _parse_case(case)


def _council_case(council_balance=15000, other_balance=5000, **extra):
    return _case([
        {"creditor_name": "Testshire Council", "balance": council_balance, "creditor_type": "council tax"},
        {"creditor_name": "Lendable", "balance": other_balance, "creditor_type": "personal loan"},
    ], **extra)


def _positions(min_dividend_pence=25, idx=0):
    return [{"_creditor_idx": idx, "effective_status": "WILL_CONSIDER", "findings": [],
             "min_dividend_pence": min_dividend_pence}]


class RequiredDiTest(SimpleTestCase):

    def test_business_example_returns_the_case(self):
        # £20,000 x 0.25 = £5,000; + £4,250 = £9,250; / 60 = £154.17 against £150.00.
        r = _council_div_required_di(_council_case(), _positions())
        self.assertEqual(r.severity, "hard_block")
        self.assertTrue(r.triggered)
        self.assertEqual(r.threshold, 154.17)
        self.assertEqual(r.actual_value, 150.0)
        self.assertIn("Required DI: £154.17", r.message)
        self.assertIn("Actual DI: £150.00", r.message)
        self.assertIn("Shortfall: £4.17", r.message)
        self.assertEqual(r.required_before, "drafting")

    def test_di_equal_to_requirement_passes(self):
        r = _council_div_required_di(_council_case(monthly_di=154.17), _positions())
        self.assertFalse(r.triggered)
        self.assertEqual(r.threshold, 154.17)

    def test_mortgage_uses_72_months(self):
        c = _council_case(has_property=True, mortgage_balance=90000)
        r = _council_div_required_di(c, _positions())
        # £9,250 / 72 = £128.47, which £150 covers.
        self.assertFalse(r.triggered)
        self.assertEqual(r.threshold, 128.47)

    def test_iva_term_months_sent_by_cat_is_ignored(self):
        r = _council_div_required_di(_council_case(iva_term_months=72), _positions())
        self.assertEqual(r.threshold, 154.17)

    def test_council_debt_not_the_majority_is_not_checked(self):
        c = _council_case(council_balance=10000, other_balance=10000)  # exactly half
        r = _council_div_required_di(c, _positions())
        self.assertFalse(r.triggered)
        self.assertIsNone(r.threshold)

    def test_no_div_is_not_checked(self):
        r = _council_div_required_di(_council_case(), _positions(min_dividend_pence=None))
        self.assertFalse(r.triggered)
        self.assertIsNone(r.threshold)

    def test_div_returned_on_the_case_beats_the_stored_one(self):
        c = _case([
            {"creditor_name": "Testshire Council", "balance": 15000, "creditor_type": "council tax",
             "div_returned": 0.10},
            {"creditor_name": "Lendable", "balance": 5000},
        ])
        r = _council_div_required_di(c, _positions(min_dividend_pence=25))
        # (£2,000 + £4,250) / 60 = £104.17
        self.assertEqual(r.threshold, 104.17)

    def test_highest_div_of_several_councils_applies(self):
        c = _case([
            {"creditor_name": "A Council", "balance": 8000, "creditor_type": "council tax"},
            {"creditor_name": "B Council", "balance": 8000, "creditor_type": "council tax"},
            {"creditor_name": "Lendable", "balance": 4000},
        ])
        positions = _positions(10, idx=0) + _positions(30, idx=1)
        r = _council_div_required_di(c, positions)
        # (£20,000 x 0.30 + £4,250) / 60 = £170.83
        self.assertEqual(r.threshold, 170.83)
        self.assertEqual(r.creditors, ["B Council"])

    def test_fee_is_a_parameter(self):
        r = _council_div_required_di(_council_case(), _positions(), Decimal("5000"))
        # (£5,000 + £5,000) / 60 = £166.67
        self.assertEqual(r.threshold, 166.67)


class CouncilDivAssessCaseTest(TestCase):
    """Through assess_case, with the GlobalCriteria row migration 0095 seeds."""

    CASE = {
        "application_id": "DIV-1",
        "assessment_date": "2026-10-28",
        "monthly_di": 150.0,
        "creditors": [
            {"name": "Testshire District Council", "balance": 15000.0, "creditor_type": "council_tax"},
            {"name": "Generic Lender", "balance": 5000.0, "creditor_type": "personal_loan"},
        ],
    }

    def setUp(self):
        CouncilRule.objects.create(council_name="Testshire District Council", status="WILL_CONSIDER",
                                   min_dividend_pence=25)

    @staticmethod
    def _ids(result, key):
        return [r.rule_id for r in result[key]]

    def test_migration_seeds_the_rule_switched_off_with_the_fee(self):
        row = GlobalCriteria.objects.get(rule_key=COUNCIL_DIV_RULE_ID)
        self.assertFalse(row.is_active)
        self.assertEqual(row.severity, "hard_block")
        self.assertEqual(row.threshold_value, Decimal("4250.00"))
        self.assertEqual(_council_div_fee(), Decimal("4250.00"))

    def test_switched_off_rule_does_not_run(self):
        result = assess_case(dict(self.CASE), set())
        all_ids = sum((self._ids(result, k) for k in ("hard_blocks", "flags", "info", "passed")), [])
        self.assertNotIn(COUNCIL_DIV_RULE_ID, all_ids)

    #: DI low enough for the OLD estimate to fail the council's 25p minimum:
    #: £50 x 60 / £20,000 = 15p in the pound.
    LOW_DI_CASE = {**CASE, "monthly_di": 50.0}

    def test_switched_off_rule_leaves_the_old_council_dividend_flag(self):
        """The rule's function still runs when it is off (its name does not map
        to its key) -- that must not silence the flag it replaces."""
        result = assess_case(dict(self.LOW_DI_CASE), set())
        self.assertTrue([r for r in result["flags"]
                         if r.rule_id == "DIVIDEND-BELOW-MIN" and "Testshire" in r.message])

    def test_switched_on_rule_returns_the_case(self):
        GlobalCriteria.objects.filter(rule_key=COUNCIL_DIV_RULE_ID).update(is_active=True)
        result = assess_case(dict(self.CASE), set())
        block = next(r for r in result["hard_blocks"] if r.rule_id == COUNCIL_DIV_RULE_ID)
        self.assertEqual(block.threshold, 154.17)
        self.assertEqual(block.actual_value, 150.0)

    def test_fee_change_takes_effect_without_a_release(self):
        GlobalCriteria.objects.filter(rule_key=COUNCIL_DIV_RULE_ID).update(
            is_active=True, threshold_value=Decimal("5000"))
        result = assess_case(dict(self.CASE), set())
        block = next(r for r in result["hard_blocks"] if r.rule_id == COUNCIL_DIV_RULE_ID)
        self.assertEqual(block.threshold, 166.67)

    def test_old_council_dividend_flag_is_dropped_once_the_rule_applies(self):
        GlobalCriteria.objects.filter(rule_key=COUNCIL_DIV_RULE_ID).update(is_active=True)
        result = assess_case(dict(self.LOW_DI_CASE), set())
        council_below_min = [r for r in result["flags"]
                             if r.rule_id == "DIVIDEND-BELOW-MIN" and "Testshire" in r.message]
        self.assertEqual(council_below_min, [])
        # ...and the new rule stands in its place.
        self.assertIn(COUNCIL_DIV_RULE_ID, [r.rule_id for r in result["hard_blocks"]])
