"""
Ikano and Orange mappings (owner decisions 2026-10-21).

1. The Aryza "Ikano Bank", "Ikano Bank Direct" and "New Look" records carry
   Ikano's company number (FC031187) and Aryza UUID, but none reached the
   Ikano row: "Ikano Bank AB - IVA or ..." is not contained in "Ikano Bank",
   and the existing alias key is only "ikano". Exact aliases now send them to
   it. Workbook, Which Representative (WATCH column): "Ikano Bank AB - IVA or
   TD or BKY or DAS or SEQ or DRO", with "incl. New Look Card" under it.
2. "Orange Lettings" (company 12262029) and "Orange Installations c/o Harwood
   & Co Limited" (10758849) reached 'Orange - CREDIT CARD ONLY' only through
   its bare "Orange" segment. They are listed in helpers._NO_CRITERIA_MATCH
   and resolve to nothing. Other Orange names are untouched.

ROWS mirror the scratch Criteria DB (789 active rows, 2026-10-21) in real id
order, with only the trading names that matter.
"""

from django.test import TestCase

from debt_app.engine.criteria import _resolve_creditor_criteria
from debt_app.models import CreditorCriteria

IKANO = "Ikano Bank AB - IVA or TD or BKY or DAS or SEQ or DRO"

# (creditor_name, representative, status, trading_names) - ascending real id
ROWS = (
    (IKANO, "WATCH", "ACCEPT", ["incl. New Look Card", "DFS Loan", "Ikano D2C Loan"]),  # #118
    ("Ikano D2C Loan", "WATCH", "ACCEPT", []),  # #537
    ("Ikano Finance", "NONE", "WILL_CONSIDER", []),  # #538 (General Creditor sheet)
    ("Orange - CREDIT CARD ONLY - IVA", "WATCH", "ACCEPT", []),  # #646
    ("Orange - CREDIT CARD ONLY - TD", "WATCH", "ACCEPT", []),  # #647
    ("incl. New Look Card", "WATCH", "ACCEPT", []),  # #790
)


def _row(name):
    try:
        return _resolve_creditor_criteria(name).creditor_name
    except CreditorCriteria.DoesNotExist:
        return None


class _Rows(TestCase):

    @classmethod
    def setUpTestData(cls):
        CreditorCriteria.objects.all().delete()
        for name, rep, status, trading in ROWS:
            CreditorCriteria.objects.create(creditor_name=name, representative=rep, status=status,
                                            trading_names=trading, is_active=True)

    def assertResolves(self, expected, names):
        for name in names:
            with self.subTest(name=name):
                self.assertEqual(expected, _row(name))


class IkanoTests(_Rows):

    def test_ikano_bank_records_reach_the_ikano_row(self):
        self.assertResolves(IKANO, ["Ikano Bank", "IKANO BANK", "Ikano Bank Direct", "Ikano"])

    def test_new_look_reaches_the_ikano_row(self):
        self.assertResolves(IKANO, ["New Look", "New Look (Ikano Bank)"])

    def test_ikano_finance_keeps_its_general_creditor_row(self):
        self.assertResolves("Ikano Finance", ["Ikano Finance"])

    def test_dfs_stays_unresolved(self):
        self.assertResolves(None, ["DFS"])


class OrangeTests(_Rows):

    def test_unrelated_orange_companies_resolve_to_nothing(self):
        self.assertResolves(None, ["Orange Lettings", "ORANGE LETTINGS",
                                   "Orange Installations c/o Harwood & Co Limited"])

    def test_other_orange_names_are_untouched(self):
        # ORANGE / Orange Personal Communications moved to the EE row in
        # Phase 6A - see test_phase6_orange_pra.
        self.assertResolves("Orange - CREDIT CARD ONLY - IVA", ["Orange - CREDIT CARD ONLY - IVA"])
