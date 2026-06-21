"""
TIG-17 council majority + income/benefit deductions tests.

Excel TIG_Criteria.md: "Council Majority — MUST NOT have a deduction from
income or benefits (will reject). Case by case — check council list."

The correct condition is: fire only when BOTH council_is_majority AND
income_deductions_active.  The old code fired on council_is_majority alone,
and the message misleadingly said "Confirm whether... deductions are being
taken" when no such check was performed.
"""

from django.test import TestCase

from debt_app.criteria_engine import _tig_17


def _case(**over):
    base = {"council_is_majority": False, "income_deductions_active": False}
    base.update(over)
    return base


class Tig17CouncilMajorityTests(TestCase):
    def test_not_majority_passes(self):
        r = _tig_17(_case(council_is_majority=False, income_deductions_active=True))
        self.assertFalse(r.triggered)

    def test_majority_no_deductions_passes(self):
        # Council is majority but no income/benefit deductions active → no flag.
        # Old code incorrectly flagged this case.
        r = _tig_17(_case(council_is_majority=True, income_deductions_active=False))
        self.assertFalse(r.triggered)

    def test_majority_with_deductions_flags(self):
        # Council majority AND income deductions active → flag.
        r = _tig_17(_case(council_is_majority=True, income_deductions_active=True))
        self.assertTrue(r.triggered)
        self.assertEqual(r.severity, "flag")
        # Message must NOT say "Confirm whether" (deductions are confirmed active)
        self.assertNotIn("Confirm whether", r.message)
        self.assertIn("deduction", r.message.lower())

    def test_not_majority_with_deductions_passes(self):
        r = _tig_17(_case(council_is_majority=False, income_deductions_active=True))
        self.assertFalse(r.triggered)
