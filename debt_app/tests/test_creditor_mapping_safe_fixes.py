"""
Confirmed creditor-mapping fixes (owner decisions 2026-10-21).

1. 118 118 Money: every variant resolves to '118 Money' (TIX), never to the
   '118 118 Money' row (NONE).
2. Asset Link Capital: the numbered SPVs and the c/o TIX name resolve to
   'Asset Link Capital' (WATCH), no longer to 'Asset Link' (NONE); plain
   'Asset Link' keeps its row.
3. Tesco: Tesco Personal Finance Plc (Tesco Bank's company) -> Tesco Bank;
   plain 'Tesco' keeps the Intrum row; Tesco Mobile stays separate.
4. Trading-name step: the name must equal a whole trading-name entry. The old
   icontains match ran over the JSON text, so short or generic names hit
   fragments of unrelated entries (owner-confirmed non-equivalences below).
   Two names are pinned by alias so the stricter step does not move them:
   Birmingham Midshires Mortgage Shortfall (not 'Birmingham Midshires') and
   Shop Direct Finance. Phase 5 retargeted both pins to their own WATCH rows
   (see test_phase5_confirmed_mappings).

ROWS are scratch Criteria DB rows (789 active, 2026-10-21) in real id order;
trading_names keep only the entries that matched (a subset reproduces the
real result: each step only asks "does any row match").
"""

from django.test import TestCase

from debt_app.engine.criteria import _resolve_creditor_criteria
from debt_app.models import CreditorCriteria

# (creditor_name, representative, status, trading_names) - ascending real id
ROWS = (
    ("NatWest", "EVOLVE", "ACCEPT", ["NatWest Bank", "NatWest Personal Loan", "Natwest"]),  # #2
    ("Co-operative Bank", "NONE", "ACCEPT", []),  # #12
    ("The Co-operative Bank", "NONE", "ACCEPT", []),  # #13
    ("Birmingham Midshires", "NONE", "ACCEPT", []),  # #22
    ("118 Money", "TIX", "ACCEPT", []),  # #54
    ("Barclaycard (including cards below) - IVA", "WATCH", "ACCEPT",
     ["Argos Mastercard - IVA", "Morgan Stanley - IVA", "Orange - CREDIT CARD ONLY - IVA", "Sky Card - IVA"]),  # #104
    ("Barclaycard (including cards below) - TD", "WATCH", "ACCEPT",
     ["Barclaycard Amazon - IVA", "Barclaycard Amazon - TD",
      "Barclays Partner Finance (also known as Clydesdale Financial Services) - TD"]),  # #105
    ("Ikano Bank AB - IVA or TD or BKY or DAS or SEQ or DRO", "WATCH", "ACCEPT",
     ["incl. New Look Card", "DFS Loan", "Vision Express"]),  # #118
    ("Intrum UK Ltd (previously 1st Credit) - IVA or BKY", "WATCH", "ACCEPT",
     ["Tesco C/O WPM (Intrum)", "Tesco C/O WPM Intrum", "Tesco Bank"]),  # #119
    ("Lloyds Banking Group (Including the Companies/Brands below) - IVA", "WATCH", "ACCEPT",
     ["Lloyds - LTSB American Express Private Banking Card - IVA",
      "HBOS - Birmingham Midshires Mortgage Shortfall - IVA",
      "Blackhorse - International Motors (IM) Finance - IVA"]),  # #132
    ("New Day / PRA - IVA or BKY", "WATCH", "ACCEPT",
     ["Amazon - IVA, AO - IVA, Aqua - IVA, Arcadia - IVA, Argos - IVA, BIP,"]),  # #144
    ("The Very Group - IVA or TD", "WATCH", "ACCEPT",
     ["Shop Direct Financial Services, Littlewoods (SDG), Very (SDG), Very,", "Shop Direct Finance Company, Abound"]),  # #159
    ("Tesco Bank", "WATCH", "ACCEPT", ["Tesco Personal Finance", "Tesco Credit Card", "Tesco Bank PLC"]),  # #165
    ("Asset Link", "NONE", "ACCEPT", ["Asset Link Capital"]),  # #185
    ("Shop Direct", "TIX", "ACCEPT", ["Shop Direct Finance", "Shop Direct Group", "Shop Direct Home Shopping"]),  # #223
    ("Virgin Money", "WATCH", "ACCEPT", ["Virgin Money Credit Card", "Virgin Money Personal Loan", "Virgin Money UK"]),  # #231
    ("118 118 Money", "NONE", "ACCEPT", []),  # #259
    ("Amazon - IVA", "WATCH", "ACCEPT", []),  # #284
    ("Asset Link Capital", "WATCH", "ACCEPT", []),  # #301
    ("Co-op Credit Union", "NONE", "REJECT", []),  # #392
    ("HBOS - Birmingham Midshires Mortgage Shortfall - IVA", "WATCH", "ACCEPT", []),  # #474
    ("Shop Direct Finance Company - IVA or TD", "WATCH", "ACCEPT", []),  # #707
    ("Sky Card - IVA", "WATCH", "ACCEPT", []),  # #710
    ("Tesco Mobile", "NONE", "DO_NOT_VOTE", []),  # #740
)


def _row(name):
    """The row the engine assesses `name` against, or None (UNKNOWN)."""
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


class OneOneEightMoneyTests(_Rows):

    def test_every_variant_is_the_tix_row(self):
        self.assertResolves("118 Money", [
            "118 118 Money", "118 118 Money - Loans", "118 118 Money - Credit Cards", "118118 MONEY (I)",
            "118 118 MONEY (MADISON CF UK LIMITED)", "118118 MONEY MADISON CF UK LTD", "118 118 Credit Card",
            "Madison CF UK Limited (T/A 118 118 Money)", "Madison Cf Uk LTD T/A 118 118 Money",
            "Madison Cf Uk LTD T/A 118 118 Money Credit Card",
        ])

    def test_unrelated_118_names_are_not_pulled_in(self):
        self.assertResolves(None, ["Capquest Arrow Mixed Mar 24 P11852", "Berneslai Homes 291184075"])


class AssetLinkCapitalTests(_Rows):

    def test_capital_variants_are_the_watch_row(self):
        self.assertResolves("Asset Link Capital", [
            "Asset Link Capital", "Asset Link Capital (No 1)", "Asset Link Capital (No 5)", "Asset Link Capital (No 7)",
            "Asset Link Capital (No 9)", "Asset Link Capital (No 9) (Ex Future Finance Loan Corporation Limited)",
            "Asset Link Capital (No. 7) Limited", "Asset Link Capital c/o The Insolvency Exchange",
        ])

    def test_plain_asset_link_keeps_its_row(self):
        self.assertResolves("Asset Link", ["Asset Link"])


class TescoTests(_Rows):

    def test_tesco_personal_finance_is_tesco_bank(self):
        self.assertResolves("Tesco Bank", ["Tesco Personal Finance Plc", "Tesco Bank", "Tesco Bank PLC"])

    def test_tesco_and_the_intrum_variant_keep_the_intrum_row(self):
        self.assertResolves("Intrum UK Ltd (previously 1st Credit) - IVA or BKY",
                            ["Tesco", "Tesco C/O WPM (Intrum)", "tesco c/o wpm (intrum)"])

    def test_tesco_mobile_stays_separate(self):
        self.assertResolves("Tesco Mobile", ["Tesco Mobile", "Tesco Mobile Limited"])


class WholeEntryTradingNameTests(_Rows):

    def test_short_names_no_longer_match_inside_other_entries(self):
        # E in "NatWest", ERS / PERSONAL in "Personal Loan", NCI in "fiNanCIal",
        # RIC in "AmeRICan", SS in "Vision ExpreSS", MOTORS in "International
        # Motors", Virgin in "Virgin Money ...", AO in New Day's brand list.
        self.assertResolves(None, ["E", "ERS", "NCI", "RIC", "ss", "PERSONAL", "MOTORS", "Virgin", "AO", "Sky"])

    def test_sky_card_and_amazon_are_not_barclaycard(self):
        self.assertEqual("Sky Card - IVA", _row("Sky Card"))  # its own existing row
        self.assertEqual("Amazon - IVA", _row("Amazon"))

    def test_a_whole_trading_name_still_matches_in_any_case(self):
        self.assertResolves("NatWest", ["NatWest Personal Loan", "natwest bank"])
        self.assertResolves("Ikano Bank AB - IVA or TD or BKY or DAS or SEQ or DRO", ["Vision Express"])

    def test_pinned_names_keep_their_rows(self):
        # Phase 5 (owner, 2026-10-21) moved both pins to their own WATCH rows.
        self.assertEqual("HBOS - Birmingham Midshires Mortgage Shortfall - IVA",
                         _row("Birmingham Midshires Mortgage Shortfall"))
        self.assertEqual("Birmingham Midshires", _row("Birmingham Midshires"))
        self.assertEqual("Shop Direct Finance Company - IVA or TD", _row("Shop Direct Finance"))


class CooperativeTests(_Rows):

    def test_credit_union_is_not_the_bank(self):
        for name in ("The Co-Operative Credit Union", "Co-operative Credit Union"):
            with self.subTest(name=name):
                self.assertNotIn(_row(name), ("Co-operative Bank", "The Co-operative Bank"))
        self.assertEqual("The Co-operative Bank", _row("The Co-operative Bank"))
