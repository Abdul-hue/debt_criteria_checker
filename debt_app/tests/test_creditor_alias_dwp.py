"""The Department for Work and Pensions resolves to its "DWP" identity.

CAT's ledger (`common/creditor_identity.py`) and this service must agree on
creditor identity -- CAT mirrors `integrations/credit_report.py ::
CREDITOR_ALIAS_MAP`. Case 415929: Aryza held "Department of Work and Pensions
(DWP)" and the call sheet said "DWP"; without the map entries the two were two
creditors on each side.
"""
from django.test import SimpleTestCase

from debt_app.integrations.credit_report import CREDITOR_ALIAS_MAP, match_creditor


class DwpAliasTests(SimpleTestCase):

    def test_dwp_resolves_to_itself(self):
        self.assertEqual("DWP", match_creditor("DWP"))
        self.assertEqual("DWP", match_creditor("  dwp "))

    def test_department_for_work_and_pensions_is_dwp(self):
        self.assertEqual("DWP", match_creditor("Department for Work and Pensions"))
        self.assertEqual("DWP", match_creditor("DEPARTMENT FOR WORK AND PENSIONS"))

    def test_department_of_work_and_pensions_is_dwp(self):
        """Aryza's own spelling of the same department."""
        self.assertEqual("DWP", match_creditor("Department of Work and Pensions"))

    def test_unrelated_names_are_unaffected(self):
        for name, expected in (("Lowell Portfolio I Ltd", "Lowell"),
                               ("Southern Water", "Southern Water"),
                               ("Department for Education", "Department for Education"),
                               ("HM Revenue & Customs", "HM Revenue & Customs"),
                               ("Zopa", "Zopa")):
            with self.subTest(name=name):
                self.assertEqual(expected, match_creditor(name))

    def test_keys_stay_lowercase(self):
        """`match_creditor` lowercases the name, not the key."""
        self.assertEqual([], [k for k in CREDITOR_ALIAS_MAP if k != k.lower()])
