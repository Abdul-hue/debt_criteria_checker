"""
Phase 6A / 6B (owner decisions 2026-10-21).

6A. ORANGE and Orange Personal Communications Services Ltd (the network,
    company 02178917) are one creditor with the mobile treatment: 'EE
    Insolvency Team' (workbook GENERAL CREDITOR, DO NOT VOTE "Will only submit
    a POD"). The workbook has no Orange mobile row; its only Orange rows are
    'Orange - CREDIT CARD ONLY' (WATCH), which both names used to reach through
    the bare "Orange" segment. The EE row was chosen by the owner.

6B. PRA-Barclays is NOT Barclays, but the workbook gives no treatment for a
    PRA-Barclays portfolio (its WATCH PRA row covers named portfolios - previous
    MBNA, Activ Capital - only). Nothing is changed; the current result is
    characterised so the owner's eventual decision shows up as a test edit.
    PRA-Barclays and the other PRA portfolio names share PRA Group's company
    number (04267803) and reach the seller's row by the same whole-word match,
    so no matcher rule can separate them.

ROWS mirror the scratch Criteria DB (789 active rows, 2026-10-21) in real id
order, with only the trading names that matter.
"""

import copy

from django.test import TestCase

from debt_app.engine.criteria import _resolve_creditor_criteria, assess_case
from debt_app.models import CreditorCriteria

# (creditor_name, representative, status, trading_names, extra) - ascending real id
ROWS = (
    ("Barclays", "WATCH", "ACCEPT", ["Barclays Bank", "Barclays PLC", "Barclays Personal Loan", "Barclays Bank PLC"], {}),  # #6
    ("Barclays Bank", "TIX", "ACCEPT", [], {}),  # #7
    ("Grattan", "TIX", "ACCEPT", [], {}),  # #65
    ("Vanquis Bank", "TIX", "ACCEPT", [], {}),  # #86
    ("Barclaycard (including cards below) - IVA", "WATCH", "ACCEPT", ["Orange - CREDIT CARD ONLY - IVA"], {}),  # #104
    ("Tesco Bank", "WATCH", "ACCEPT", [], {}),  # #165
    ("JD Williams", "TIX", "ACCEPT", [], {}),  # #236
    ("EE FLEX PAY", "NONE", "ACCEPT", [], {}),  # #257
    ("EE Insolvency Team", "NONE", "DO_NOT_VOTE", [], {"criteria_notes": "Do not vote - Will only submit a POD"}),  # #415
    ("Orange - CREDIT CARD ONLY - IVA", "WATCH", "ACCEPT", [], {}),  # #646
    ("Orange - CREDIT CARD ONLY - TD", "WATCH", "ACCEPT", [], {}),  # #647
    ("PRA Group", "NONE", "WILL_CONSIDER", [], {}),  # #651
    ("T Mobile (EE)", "NONE", "DO_NOT_VOTE", [], {}),  # #730
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
        for name, rep, status, trading, extra in ROWS:
            CreditorCriteria.objects.create(creditor_name=name, representative=rep, status=status,
                                            trading_names=trading, is_active=True, **extra)

    def assertResolves(self, expected, names):
        for name in names:
            with self.subTest(name=name):
                self.assertEqual(expected, _row(name))


class OrangeTests(_Rows):

    def test_orange_network_names_reach_the_ee_row(self):
        self.assertResolves("EE Insolvency Team", [
            "ORANGE", "ORANGE PERSONAL COMMUNICATIONS SERVICES LIMITED", "Orange Personal Communications Services Ltd",
        ])

    def test_credit_card_only_rows_are_unchanged(self):
        self.assertResolves("Orange - CREDIT CARD ONLY - IVA", ["Orange - CREDIT CARD ONLY - IVA"])
        self.assertResolves("Orange - CREDIT CARD ONLY - TD", ["Orange - CREDIT CARD ONLY - TD"])

    def test_unrelated_orange_companies_stay_unresolved(self):
        self.assertResolves(None, ["Orange Lettings", "Orange Installations c/o Harwood & Co Limited"])

    def test_other_ee_names_are_unchanged(self):
        self.assertResolves("EE Insolvency Team", ["EE Insolvency Team"])
        self.assertResolves("T Mobile (EE)", ["T Mobile (EE)"])
        self.assertResolves("EE FLEX PAY", ["EE FLEX PAY"])


class PraTests(_Rows):

    def test_pra_barclays_is_characterised_pending_an_owner_decision(self):
        # NOT the owner's intended treatment (PRA-Barclays is not Barclays) -
        # the workbook gives none. Edit this when the decision is made.
        self.assertResolves("Barclays", ["PRA-Barclays Bank BV23071IVB", "PRA-Barclays Bank BY20111IVB",
                                         "PRA-Barclays Bank BY22071IVB"])

    def test_other_pra_portfolios_keep_their_seller_rows(self):
        self.assertResolves("Tesco Bank", ["PRA-Tesco Bank TB21012TDF", "PRA-Tesco Bank-TB21071IVF"])
        self.assertResolves("JD Williams", ["PRA-JD Williams JD24061IVB"])
        self.assertResolves("Vanquis Bank", ["PRA-Vanquis Bank VQ24041IVB"])
        self.assertResolves("Grattan", ["PRA-Freemans Grattan FG23061IVB"])

    def test_ordinary_barclays_is_unchanged(self):
        self.assertResolves("Barclays Bank", ["Barclays Bank Plc", "Barclays"])


class EffectiveOutcomeTests(_Rows):

    def _position(self, name):
        case = {
            "assessment_date": "2026-10-15",
            "client": {"date_of_birth": "1985-01-01"},
            "financial_summary": {"net_balance": 450.0, "total_income": 2400.0, "income_source": "employed"},
            "documents": [], "gold_transactions": [],
            "creditors": [{"name": name, "balance": 15000, "creditor_type": "mobile"},
                          {"name": "EE FLEX PAY", "balance": 15000, "creditor_type": "credit_card"}],
        }
        result = assess_case(copy.deepcopy(case))
        return result["creditor_positions"][0], result

    def test_orange_network_does_not_vote_and_brings_in_no_representative(self):
        pos, result = self._position("ORANGE PERSONAL COMMUNICATIONS SERVICES LIMITED")
        self.assertEqual(("EE Insolvency Team", "NONE", "DO_NOT_VOTE"),
                         (pos["creditor_name"], pos["representative"], pos["effective_status"]))
        self.assertNotIn("WATCH", result["representatives_detected"])

    def test_orange_credit_card_still_votes_with_watch(self):
        pos, result = self._position("Orange - CREDIT CARD ONLY - IVA")
        self.assertEqual("WATCH", pos["representative"])
        self.assertEqual(result["representative_outcomes"]["WATCH"]["status"], pos["effective_status"])
