"""New Wave Capital resolves to its "Capital On Tap" identity.

CAT's ledger (`common/creditor_identity.py`) and this service must agree on
creditor identity -- CAT mirrors `integrations/credit_report.py ::
CREDITOR_ALIAS_MAP`. Case 429331: Aryza held "Capital On Tap"; Capital on Tap
is a trading name of New Wave Capital Ltd (workbook row "CAPITAL ON TAP (NEW
WAVE)"), and its letters may print either name.
"""
from django.test import SimpleTestCase

from debt_app.integrations.credit_report import match_creditor


class CapitalOnTapAliasTests(SimpleTestCase):

    def test_capital_on_tap_resolves_to_itself(self):
        for name in ("Capital On Tap", "capital on tap", "  CAPITAL ON TAP ",
                     "Capital on Tap Card"):
            with self.subTest(name=name):
                self.assertEqual("Capital On Tap", match_creditor(name))

    def test_the_legal_entity_is_capital_on_tap(self):
        for name in ("New Wave Capital", "NEW WAVE CAPITAL LTD",
                     "New Wave Capital Limited"):
            with self.subTest(name=name):
                self.assertEqual("Capital On Tap", match_creditor(name))

    def test_capital_one_is_a_different_lender(self):
        self.assertEqual("Capital One", match_creditor("Capital One"))

    def test_unrelated_names_are_unaffected(self):
        for name, expected in (("New Day", "New Day"),
                               ("Wave Energy", "Wave Energy"),
                               ("Zopa", "Zopa")):
            with self.subTest(name=name):
                self.assertEqual(expected, match_creditor(name))
