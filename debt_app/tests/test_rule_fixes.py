"""
Regression tests for WATCH-22.2 (payoff-duration formula) and TIG-18 (2-month spend).

WATCH-22.2 fix: repayment_months = total_debt / (disposable_income * 0.83)
  Hard block if <= 72 months (repayable within 6 years).
  Pass       if >  72 months.
  Non-positive DI returns pass ("cannot calculate").

TIG-18 fix: trigger only when total_spend_2mo >= monthly_income * 2.0.
  Previous code compared 2-month spend against 1-month income — always fired.

TIG-06 fix: trigger when receives_any_benefits=True or benefit_income_amount>0
  regardless of whether income_source == "employed".

TIG-07 fix: trigger when has_uc_journal=True regardless of income_source.
"""

from datetime import date
from django.test import TestCase
from debt_app.engine.criteria import _watch_22_2, _tig_18, _tig_06, _tig_07


def _base_case(**overrides) -> dict:
    """Minimal case dict for rule evaluation."""
    base = {
        "disposable_income": 500.0,
        "total_debt": 15000.0,
        "total_income": 2000.0,
        "total_spend_2mo": 2500.0,
        "has_open_banking": True,
        "income_source": "employed",
        "receives_any_benefits": False,
        "benefit_income_amount": 0,
        "benefit_letter_docs": [],
        "bank_stmt_date": None,
        "assessment_date": date(2025, 6, 1),
        "has_uc_journal": False,
        "uc_journal_date": None,
    }
    base.update(overrides)
    return base


# -----------------------------------------------------------------------
# WATCH-22.2
# -----------------------------------------------------------------------
class Watch222Tests(TestCase):

    def test_hard_block_when_within_72_months(self):
        """total_debt / (DI * 0.83) <= 72 -> hard block."""
        # 15000 / (500 * 0.83) = 36.1 months -> block
        c = _base_case(disposable_income=500.0, total_debt=15000.0)
        r = _watch_22_2(c)
        self.assertTrue(r.triggered)
        self.assertEqual(r.severity, "hard_block")
        self.assertAlmostEqual(r.actual_value, 15000 / (500 * 0.83), places=1)

    def test_hard_block_at_exactly_72_months(self):
        """Boundary: exactly 72 months is still a block (<=)."""
        di = 30000 / (0.83 * 72)
        c = _base_case(disposable_income=di, total_debt=30000.0)
        r = _watch_22_2(c)
        self.assertTrue(r.triggered)
        self.assertEqual(r.severity, "hard_block")

    def test_pass_when_above_72_months(self):
        """total_debt / (DI * 0.83) > 72 -> pass."""
        # 100000 / (100 * 0.83) = 1204 months -> pass
        c = _base_case(disposable_income=100.0, total_debt=100000.0)
        r = _watch_22_2(c)
        self.assertFalse(r.triggered)
        self.assertEqual(r.severity, "pass")

    def test_zero_debt_not_applicable(self):
        c = _base_case(total_debt=0.0)
        r = _watch_22_2(c)
        self.assertFalse(r.triggered)

    def test_zero_di_not_applicable(self):
        c = _base_case(disposable_income=0.0)
        r = _watch_22_2(c)
        self.assertFalse(r.triggered)

    def test_negative_di_not_applicable(self):
        c = _base_case(disposable_income=-50.0)
        r = _watch_22_2(c)
        self.assertFalse(r.triggered)


# -----------------------------------------------------------------------
# TIG-18
# -----------------------------------------------------------------------
class Tig18Tests(TestCase):

    def test_no_flag_when_2mo_spend_below_2mo_income(self):
        """2-month spend well below 2x monthly income -> pass."""
        c = _base_case(total_spend_2mo=2000.0, total_income=2000.0)
        r = _tig_18(c)
        self.assertFalse(r.triggered)

    def test_flag_when_2mo_spend_equals_2mo_income(self):
        """Boundary: 2-month spend == 2x monthly income -> flag."""
        c = _base_case(total_spend_2mo=4000.0, total_income=2000.0)
        r = _tig_18(c)
        self.assertTrue(r.triggered)
        self.assertEqual(r.severity, "flag")
        self.assertAlmostEqual(r.threshold, 4000.0)

    def test_flag_when_2mo_spend_exceeds_2mo_income(self):
        c = _base_case(total_spend_2mo=5000.0, total_income=2000.0)
        r = _tig_18(c)
        self.assertTrue(r.triggered)

    def test_no_open_banking_still_flags_manual(self):
        """No open banking -> flag with manual-check message (existing behaviour preserved)."""
        c = _base_case(has_open_banking=False)
        r = _tig_18(c)
        self.assertTrue(r.triggered)
        self.assertEqual(r.severity, "flag")

    def test_old_false_positive_no_longer_fires(self):
        """Regression: spend=2500 vs income=2000 must NOT fire after fix (2500 < 4000)."""
        c = _base_case(total_spend_2mo=2500.0, total_income=2000.0)
        r = _tig_18(c)
        self.assertFalse(r.triggered)


# -----------------------------------------------------------------------
# TIG-06 dual-income
# -----------------------------------------------------------------------
class Tig06DualIncomeTests(TestCase):

    def test_employed_no_benefits_passes(self):
        c = _base_case(income_source="employed", receives_any_benefits=False, benefit_income_amount=0)
        r = _tig_06(c)
        self.assertFalse(r.triggered)

    def test_receives_any_benefits_triggers_even_if_employed(self):
        c = _base_case(
            income_source="employed",
            receives_any_benefits=True,
            benefit_income_amount=0,
            benefit_letter_docs=[],
            bank_stmt_date=None,
        )
        r = _tig_06(c)
        self.assertTrue(r.triggered)
        self.assertEqual(r.severity, "hard_block")

    def test_benefit_income_amount_triggers_even_if_employed(self):
        c = _base_case(
            income_source="employed",
            receives_any_benefits=False,
            benefit_income_amount=350.0,
            benefit_letter_docs=[],
            bank_stmt_date=None,
        )
        r = _tig_06(c)
        self.assertTrue(r.triggered)

    def test_benefit_letter_present_clears_tig06(self):
        c = _base_case(
            income_source="employed",
            receives_any_benefits=True,
            benefit_income_amount=200.0,
            benefit_letter_docs=[{"document_type": "benefit_letter", "is_valid": True}],
        )
        r = _tig_06(c)
        self.assertFalse(r.triggered)


# -----------------------------------------------------------------------
# TIG-07 dual-income
# -----------------------------------------------------------------------
class Tig07DualIncomeTests(TestCase):

    def test_no_uc_employed_passes(self):
        c = _base_case(income_source="employed", has_uc_journal=False)
        r = _tig_07(c)
        self.assertFalse(r.triggered)

    def test_has_uc_journal_triggers_check_regardless_of_income_source(self):
        """UC journal uploaded but no date -> flag regardless of income_source."""
        c = _base_case(
            income_source="employed",
            has_uc_journal=True,
            uc_journal_date=None,
        )
        r = _tig_07(c)
        self.assertTrue(r.triggered)
        self.assertEqual(r.severity, "flag")

    def test_valid_uc_journal_clears_tig07(self):
        c = _base_case(
            income_source="universal_credit",
            has_uc_journal=True,
            uc_journal_date=date(2025, 5, 1),
            assessment_date=date(2025, 6, 1),
        )
        r = _tig_07(c)
        self.assertFalse(r.triggered)
