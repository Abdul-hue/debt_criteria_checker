"""
Phase 7A - Sky (investigation 2026-10-21). Guards only: no Sky mapping is
approved yet.

The workbook's only Sky entries are credit cards: "Sky Card - IVA / - TD"
(WATCH; IVA Watch Creditors row 17, Which Representative rows 24 and 37) and
"BSKYB VISA (JLP)" (an HSBC card, TIX Creditors). It has no treatment for Sky's
subscription business. In Aryza that is "Sky Subscribers Services Ltd"
(company 02340150; 727 C1 debts, mostly communications-supply and fixed-term
accounts) plus "Sky UK" (25) and "Sky" (7), which carry no company number or
UUID to tie them to it. Until the owner decides the treatment, whether those
names share it, and whether a new Criteria row is needed, every Sky
subscription name stays UNKNOWN - never the Sky Card or Barclaycard rows.

ROWS mirror the scratch Criteria DB (789 active rows, 2026-10-21) in real id
order, with only the trading names that matter.
"""

import copy
import re

from django.test import SimpleTestCase, TestCase

from debt_app.engine.criteria import _resolve_creditor_criteria, assess_case
from debt_app.helpers import CREDITOR_ALIAS_MAP
from debt_app.models import CreditorCriteria

SKY_CARD_IVA, SKY_CARD_TD = "Sky Card - IVA", "Sky Card - TD"
BARCLAYCARD = ("Barclaycard (including cards below) - IVA", "Barclaycard (including cards below) - TD")

# (creditor_name, representative, status, trading_names) - ascending real id
ROWS = (
    (BARCLAYCARD[0], "WATCH", "ACCEPT", ["Argos Mastercard - IVA", SKY_CARD_IVA]),  # #104
    (BARCLAYCARD[1], "WATCH", "ACCEPT", ["Barclaycard Amazon - IVA", SKY_CARD_TD]),  # #105
    ("EE FLEX PAY", "NONE", "ACCEPT", []),  # #257
    ("Amazon - IVA", "WATCH", "ACCEPT", []),  # #284
    (SKY_CARD_IVA, "WATCH", "ACCEPT", []),  # #710
    (SKY_CARD_TD, "WATCH", "ACCEPT", []),  # #711
)

# Every Sky name in the Aryza creditor list except "Sky Card" (2026-10-21).
SKY_SUBSCRIPTION_NAMES = (
    "Sky Subscribers Services Ltd", "Sky UK", "SKY UK", "Sky", "Sky Mobile ", "SKY MOBILE (I)",
    "Sky Glass Large", "Sky Subscribers (TV) Ltd", "SKY TECH LTD", "Sky Credit Cards",
)


def _row(name):
    try:
        return _resolve_creditor_criteria(name).creditor_name
    except CreditorCriteria.DoesNotExist:
        return None


class NoUnapprovedSkyAliasTests(SimpleTestCase):

    def test_no_alias_maps_a_sky_name(self):
        # Adding one assigns Sky an outcome; it needs the owner's decision
        # (treatment, scope of names, new row?) - update this test with it.
        sky = {k: v for k, v in CREDITOR_ALIAS_MAP.items() if re.search(r"\bsky\b", k)}
        self.assertEqual({}, sky)


class _Rows(TestCase):

    @classmethod
    def setUpTestData(cls):
        CreditorCriteria.objects.all().delete()
        for name, rep, status, trading in ROWS:
            CreditorCriteria.objects.create(creditor_name=name, representative=rep, status=status,
                                            trading_names=trading, is_active=True)


class SkyResolutionTests(_Rows):

    def test_sky_subscription_names_stay_unresolved(self):
        for name in SKY_SUBSCRIPTION_NAMES:
            with self.subTest(name=name):
                self.assertIsNone(_row(name))

    def test_sky_card_keeps_its_own_watch_rows(self):
        self.assertEqual(SKY_CARD_IVA, _row("Sky Card"))
        self.assertEqual(SKY_CARD_IVA, _row(SKY_CARD_IVA))
        self.assertEqual(SKY_CARD_TD, _row(SKY_CARD_TD))

    def test_no_sky_name_reaches_barclaycard(self):
        for name in (*SKY_SUBSCRIPTION_NAMES, "Sky Card"):
            with self.subTest(name=name):
                self.assertNotIn(_row(name), BARCLAYCARD)

    def test_neighbouring_barclaycard_and_amazon_rows_are_unchanged(self):
        # Barclaycard is still reached by its genuine whole trading names.
        self.assertEqual(BARCLAYCARD[0], _row("Argos Mastercard - IVA"))
        self.assertEqual("Amazon - IVA", _row("Amazon"))


class SkyEffectiveOutcomeTests(_Rows):

    def _assess(self, name):
        case = {
            "assessment_date": "2026-10-15",
            "client": {"date_of_birth": "1985-01-01"},
            "financial_summary": {"net_balance": 450.0, "total_income": 2400.0, "income_source": "employed"},
            "documents": [], "gold_transactions": [],
            "creditors": [{"name": name, "balance": 15000, "creditor_type": "communications_supply_account"},
                          {"name": "EE FLEX PAY", "balance": 15000, "creditor_type": "credit_card"}],
        }
        result = assess_case(copy.deepcopy(case))
        return result["creditor_positions"][0], result

    def test_sky_subscribers_is_an_unidentified_creditor_with_no_representative(self):
        pos, result = self._assess("Sky Subscribers Services Ltd")
        self.assertEqual(("NONE", "UNKNOWN"), (pos["representative"], pos["effective_status"]))
        self.assertIn("CREDITOR-UNKNOWN", pos["rule_ids"])
        self.assertNotIn("WATCH", result["representatives_detected"])
        self.assertEqual(15000, float(result["majority_analysis"]["unknown_debt"]))

    def test_sky_card_votes_with_the_watch_body_not_its_stored_status(self):
        pos, result = self._assess("Sky Card")
        self.assertEqual("WATCH", pos["representative"])
        self.assertEqual(result["representative_outcomes"]["WATCH"]["status"], pos["effective_status"])
