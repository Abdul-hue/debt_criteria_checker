"""The Driver and Vehicle Licensing Agency resolves to its "DVLA" identity.

CAT's ledger (`common/creditor_identity.py`) and this service must agree on
creditor identity -- CAT mirrors `integrations/credit_report.py ::
CREDITOR_ALIAS_MAP`. Case 146305: Aryza held "DVLA" £181.08 and the letter
said "Driver and Vehicle Licensing Agency" £181.08 -- one debt, two rows.
"""
from django.test import SimpleTestCase

from debt_app.integrations.credit_report import match_creditor


class DvlaAliasTests(SimpleTestCase):

    def test_dvla_resolves_to_itself(self):
        self.assertEqual("DVLA", match_creditor("DVLA"))
        self.assertEqual("DVLA", match_creditor("  dvla "))

    def test_the_full_name_is_dvla(self):
        for name in ("Driver and Vehicle Licensing Agency",
                     "DRIVER AND VEHICLE LICENSING AGENCY",
                     "Driver & Vehicle Licensing Agency"):
            with self.subTest(name=name):
                self.assertEqual("DVLA", match_creditor(name))

    def test_unrelated_names_are_unaffected(self):
        for name, expected in (("Driver Hire", "Driver Hire"),
                               ("DWP", "DWP"),
                               ("Zopa", "Zopa")):
            with self.subTest(name=name):
                self.assertEqual(expected, match_creditor(name))
