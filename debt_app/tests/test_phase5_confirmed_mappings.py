"""
Phase 5 confirmed creditor mappings (owner decisions 2026-10-21; workbook
"TIP CRITERIA & VOTING HISTORY", "Which Representative" (WATCH) WPM column
unless stated).

1. Shop Direct Finance -> 'Shop Direct Finance Company - IVA or TD' (WATCH,
   row 281). Same company number / UUID as Shop Direct Finance Company Ltd
   (04660974), whose names already reached that row. Not the TIX 'Shop Direct'.
2. BIP CREDIT (NewDay) -> 'BIP' (WATCH, row 203). The whole-word step found
   both 'NewDay' (TIX) and 'BIP'; NewDay won on the lower row id.
3. Birmingham Midshires Mortgage Shortfall -> 'HBOS - Birmingham Midshires
   Mortgage Shortfall - IVA' (WATCH, row 115). Not ordinary 'Birmingham
   Midshires' (NONE).
4. Ikano Finance stays on its own General Creditor row (sheet row 179), never
   merged with the Ikano Bank row - no change was needed, pinned here.
5. PRA-Barclays is NOT changed: the workbook has no PRA-Barclays treatment
   (its WATCH PRA row covers named portfolios only), so the target is an owner
   decision. Its current result is characterised so a change is explicit.

For representative-body creditors the vote is the body's outcome, never the
row's stored status (ACCEPT is a DB default) - see EffectiveOutcomeTests.

ROWS mirror the scratch Criteria DB (789 active rows, 2026-10-21) in real id
order, with only the trading names that matter.
"""

import copy

from django.test import TestCase

from debt_app.engine.criteria import _resolve_creditor_criteria, assess_case
from debt_app.models import CreditorCriteria

IKANO = "Ikano Bank AB - IVA or TD or BKY or DAS or SEQ or DRO"
IKANO_FINANCE_NOTES = (
    "REJECT - if under a year old/12 payments not being made. Do not put forward if majority and not a year "
    "old with 12 payments made, updated 24/03/2021 (tig10560 mentioned on reason for rejection)"
)

# (creditor_name, representative, status, trading_names, extra) - ascending real id
ROWS = (
    ("Barclays", "WATCH", "ACCEPT", ["Barclays Bank", "Barclays PLC", "Barclays Personal Loan", "Barclays Bank PLC"],
     {"parent_group": "Barclays Group"}),  # #6
    ("Barclays Bank", "TIX", "ACCEPT", [], {"parent_group": "Barclays Group"}),  # #7
    ("Birmingham Midshires", "NONE", "ACCEPT", [], {"parent_group": "Lloyds Group"}),  # #22
    (IKANO, "WATCH", "ACCEPT", ["incl. New Look Card", "DFS Loan"], {}),  # #118
    ("Lloyds Banking Group (Including the Companies/Brands below) - IVA", "WATCH", "ACCEPT",
     ["HBOS - Birmingham Midshires Mortgage Shortfall - IVA"], {}),  # #132
    ("The Very Group - IVA or TD", "WATCH", "ACCEPT", ["Shop Direct Finance Company, Abound"], {}),  # #159
    ("Tesco Bank", "WATCH", "ACCEPT", ["Tesco Personal Finance"], {}),  # #165
    ("Fluid", "WATCH", "ACCEPT", [], {}),  # #204
    ("NewDay", "TIX", "ACCEPT", ["NewDay Ltd", "NewDay Cards"], {}),  # #217
    ("Shop Direct", "TIX", "ACCEPT", ["Shop Direct Finance", "Shop Direct Group"], {"parent_group": "Shop Direct Group"}),  # #223
    ("JD Williams", "TIX", "ACCEPT", [], {"parent_group": "Shop Direct Group"}),  # #236
    ("EE FLEX PAY", "NONE", "ACCEPT", [], {}),  # #257
    ("BIP", "WATCH", "ACCEPT", [], {}),  # #309
    ("HBOS - Birmingham Midshires Mortgage Shortfall - IVA", "WATCH", "ACCEPT", [], {"parent_group": "Lloyds Group"}),  # #474
    ("Ikano Finance", "NONE", "WILL_CONSIDER", [], {"criteria_notes": IKANO_FINANCE_NOTES}),  # #538
    ("PRA Group", "NONE", "WILL_CONSIDER", [], {}),  # #651
    ("Shop Direct Finance Company - IVA or TD", "WATCH", "ACCEPT", [], {"parent_group": "Shop Direct Group"}),  # #707
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


class ShopDirectFinanceTests(_Rows):

    def test_shop_direct_finance_company_names_are_the_watch_row(self):
        self.assertResolves("Shop Direct Finance Company - IVA or TD", [
            "Shop Direct Finance", "Shop Direct Finance Company Limited", "Shop Direct Finance Company LTD",
            "SHOP DIRECT FINANCE COMPANY LTD (I)",
        ])

    def test_other_shop_direct_and_very_names_are_unchanged(self):
        self.assertResolves("Shop Direct", ["Shop Direct", "Shop Direct Group"])
        self.assertResolves("The Very Group - IVA or TD", ["The Very Group - IVA or TD"])


class BipTests(_Rows):

    def test_bip_credit_is_the_watch_bip_row(self):
        self.assertResolves("BIP", ["BIP CREDIT (NewDay)", "BIP Credit", "BIP"])

    def test_newday_names_are_unchanged(self):
        self.assertResolves("NewDay", ["NewDay Limited", "NewDay (Argos, HRG, Sainsburys)", "Newday"])
        self.assertResolves("Fluid", ["Fluid Credit (NewDay Limited)"])


class BirminghamMidshiresTests(_Rows):

    def test_mortgage_shortfall_is_its_own_watch_row(self):
        self.assertResolves("HBOS - Birmingham Midshires Mortgage Shortfall - IVA",
                            ["Birmingham Midshires Mortgage Shortfall"])

    def test_ordinary_birmingham_midshires_is_unchanged(self):
        self.assertResolves("Birmingham Midshires",
                            ["Birmingham Midshires", "Birmingham Midshires Mortgage Services Limited"])


class IkanoFinanceTests(_Rows):

    def test_ikano_finance_is_its_own_rule(self):
        self.assertResolves("Ikano Finance", ["Ikano Finance", "Ikano Finance Limited"])
        row = CreditorCriteria.objects.get(creditor_name="Ikano Finance")
        self.assertEqual(("NONE", "WILL_CONSIDER", IKANO_FINANCE_NOTES),
                         (row.representative, row.status, row.criteria_notes))

    def test_ikano_bank_and_new_look_are_unchanged(self):
        self.assertResolves(IKANO, ["Ikano Bank", "New Look"])


class PraTests(_Rows):

    def test_pra_barclays_is_characterised_pending_an_owner_decision(self):
        # NOT the owner's intended treatment - the workbook gives none. Edit
        # this when the PRA-Barclays decision is made.
        self.assertResolves("Barclays", ["PRA-Barclays Bank BV23071IVB", "PRA-Barclays Bank BY22071IVB"])

    def test_pra_tesco_bank_keeps_the_tesco_treatment(self):
        self.assertResolves("Tesco Bank", ["PRA-Tesco Bank TB21012TDF", "PRA-Tesco Bank-TB21071IVF"])

    def test_ordinary_barclays_and_other_pra_names_are_unchanged(self):
        self.assertResolves("Barclays Bank", ["Barclays Bank Plc", "Barclays"])
        self.assertResolves("PRA Group", ["PRA Group (UK) Limited (TIX)", "PRA Group (UK) Limited 01/10"])
        self.assertResolves("JD Williams", ["PRA-JD Williams JD24061IVB"])
        self.assertResolves(None, ["PRA-BNP Paribas BN18121IVB"])


BASE = {
    "assessment_date": "2026-10-15",
    "client": {"date_of_birth": "1985-01-01"},
    "financial_summary": {"net_balance": 450.0, "total_income": 2400.0, "income_source": "employed"},
    "documents": [
        {"document_type": "payslip", "is_valid": True, "document_date": "2026-10-01"},
        {"document_type": "bank_statement", "is_valid": True, "document_date": "2026-10-01",
         "extracted_data": {"statement_date": "2026-10-01", "account_holder": "Test Case"}},
    ],
    "gold_transactions": [],
}


class EffectiveOutcomeTests(_Rows):
    """The vote of a WATCH creditor is the WATCH body outcome; a NONE creditor
    keeps its row status."""

    def _position(self, name):
        case = copy.deepcopy(BASE)
        case["creditors"] = [{"name": name, "balance": 15000, "creditor_type": "credit_card"},
                             {"name": "EE FLEX PAY", "balance": 15000, "creditor_type": "credit_card"}]
        result = assess_case(case)
        return result["creditor_positions"][0], result["representative_outcomes"]

    def test_watch_mappings_vote_with_the_watch_body(self):
        for name in ("Shop Direct Finance", "BIP CREDIT (NewDay)", "Birmingham Midshires Mortgage Shortfall"):
            with self.subTest(name=name):
                pos, outcomes = self._position(name)
                self.assertEqual("WATCH", pos["representative"])
                self.assertEqual(outcomes["WATCH"]["status"], pos["effective_status"])

    def test_ikano_finance_votes_its_own_status(self):
        pos, _ = self._position("Ikano Finance")
        self.assertEqual(("NONE", "WILL_CONSIDER"), (pos["representative"], pos["effective_status"]))
        self.assertIn("CREDITOR-MANUAL-CHECK-REQUIRED", [f["code"] for f in pos["findings"]])
