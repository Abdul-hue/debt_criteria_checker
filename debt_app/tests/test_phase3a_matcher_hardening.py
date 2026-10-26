"""
Phase 3A matcher hardening (2026-10-21). No intended outcome change.

1. Alias collision guard. CREDITOR_ALIAS_MAP is built by normalising every
   _RAW_CREDITOR_ALIAS_MAP key, so two raw keys that normalise alike keep only
   the LATER target, silently. Three such dead entries were removed
   ('creation consumer finance', 'pra group', 'perch capital'); these tests
   fail if a new pair with different targets appears.

2. Characterization of the 43 Aryza names whose winning matcher step finds
   several CreditorCriteria rows with DIFFERENT stances. The resolver takes the
   lowest id, so EXPECTED records today's winner - not necessarily the right
   one (e.g. 'South Manchester Credit Union Limited' -> 'Manchester Credit
   Union'). A matcher change that moves any of them must edit EXPECTED, which
   makes the outcome change explicit in review.

   ROWS are every candidate row for those names, from the scratch Criteria DB
   (789 active rows, 2026-10-21), created in their real id order. trading_names
   keep only the entries that matched. A subset of the real rows reproduces the
   real result: each step only asks "does any row match", so dropping rows can
   only remove matches, and every candidate at the winning step is kept.
"""

import ast
import inspect

from django.test import SimpleTestCase, TestCase

from debt_app import helpers
from debt_app.engine.criteria import _check_creditor_individual, _parse_case
from debt_app.helpers import CREDITOR_ALIAS_MAP, _RAW_CREDITOR_ALIAS_MAP, normalise_creditor_name
from debt_app.models import CreditorCriteria


def _raw_alias_pairs():
    """(key, target) for every entry as written in helpers.py. Read from the
    source because a dict literal keeps only the last of two identical keys."""
    for node in ast.parse(inspect.getsource(helpers)).body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == "_RAW_CREDITOR_ALIAS_MAP" for t in node.targets):
            return [(k.value, v.value) for k, v in zip(node.value.keys, node.value.values)]
    raise AssertionError("_RAW_CREDITOR_ALIAS_MAP not found in helpers.py")


class AliasCollisionTests(SimpleTestCase):

    def test_source_parse_matches_the_runtime_map(self):
        self.assertEqual(dict(_raw_alias_pairs()), _RAW_CREDITOR_ALIAS_MAP)

    def test_no_two_raw_keys_normalise_alike_with_different_targets(self):
        by_key = {}
        for key, target in _raw_alias_pairs():
            by_key.setdefault(normalise_creditor_name(key), {}).setdefault(target.strip().lower(), []).append(key)
        conflicts = {nk: targets for nk, targets in by_key.items() if len(targets) > 1}
        self.assertEqual(conflicts, {}, "these raw alias keys share a normalised key but name different "
                                        "targets - only the last one would ever be used")

    def test_removed_dead_aliases_leave_the_surviving_targets(self):
        self.assertEqual(CREDITOR_ALIAS_MAP["creation consumer finance"], "Creation Consumer Finance")
        self.assertEqual(CREDITOR_ALIAS_MAP["pra group"], "PRA Group")
        self.assertEqual(CREDITOR_ALIAS_MAP["perch capital"], "Perch Capital Limited")


def _position(name):
    case = _parse_case({"creditors": [{"creditor_name": name, "balance": 800}]})
    case.update({"aryza_reference": "T", "client_name": "T"})
    return _check_creditor_individual(case)[0]


class MultiCandidateCharacterizationTests(TestCase):
    # (creditor_name, representative, status, trading_names) - ascending scratch id
    ROWS = (
        ('Royal Bank of Scotland', 'EVOLVE', 'ACCEPT', []),  # #1
        ('NatWest', 'EVOLVE', 'ACCEPT', ['NatWest Bank', 'NatWest Personal Loan']),  # #2
        ('Barclays', 'WATCH', 'ACCEPT', ['Barclays Personal Loan']),  # #6
        ('Barclays Bank', 'TIX', 'ACCEPT', []),  # #7
        ('Barclaycard', 'EVOLVE', 'ACCEPT', ['Barclaycard Credit Card']),  # #9
        ('Co-operative Bank', 'NONE', 'ACCEPT', []),  # #12
        ('The Co-operative Bank', 'NONE', 'ACCEPT', []),  # #13
        ('Bank of Scotland', 'NONE', 'ACCEPT', []),  # #18
        ('Halifax', 'NONE', 'ACCEPT', ['Halifax Credit Card']),  # #19
        ('Santander', 'NONE', 'ACCEPT', ['Santander UK', 'Santander Personal Loan']),  # #35
        ('Clydesdale Bank', 'NONE', 'ACCEPT', []),  # #42
        ('Clydesdale Bank plc', 'NONE', 'ACCEPT', []),  # #43
        ('118 Money', 'TIX', 'ACCEPT', []),  # #54
        ('Capital One', 'WATCH', 'ACCEPT', ['Capital One Credit Card']),  # #58
        ('Grattan', 'TIX', 'ACCEPT', []),  # #65
        ('Moneybarn', 'TIX', 'ACCEPT', ['Moneybarn Limited']),  # #91
        ('Santander Consumer Finance', 'TIX', 'ACCEPT', ['Northridge Finance']),  # #92
        ('Barclaycard (including cards below) - IVA', 'WATCH', 'ACCEPT', ['Argos Mastercard - IVA']),  # #104
        ('Barclaycard (including cards below) - TD', 'WATCH', 'ACCEPT', ['Argos Mastercard - TD', 'Barclays Partner Finance (also known as Clydesdale Financial Services) - IVA']),  # #105
        ('The Co-operative Bank - IVA', 'WATCH', 'ACCEPT', []),  # #108
        ('The Co-operative Bank - TD', 'WATCH', 'ACCEPT', []),  # #109
        ('Ikano Bank AB - IVA or TD or BKY or DAS or SEQ or DRO', 'WATCH', 'ACCEPT', ['incl. New Look Card', 'Principles Card (loans taken out from 2006 onwards)', 'Vision Express']),  # #118
        ('Intrum UK Ltd (previously 1st Credit) - IVA or BKY', 'WATCH', 'ACCEPT', ['Tesco C/O WPM (Intrum)']),  # #119
        ('Intrum UK Ltd (previously 1st Credit) - TD or DAS or SEQ', 'WATCH', 'ACCEPT', ['Tesco C/O WPM (Intrum)']),  # #120
        ('La Redoute - IVA or TD or BKY or DAS or SEQ or DRO', 'WATCH', 'ACCEPT', ['incl. La Redoute']),  # #125
        ('Link Financial - IVA', 'WATCH', 'ACCEPT', ['Asset Link Capital', 'incl. Link Financial Outsourcing']),  # #130
        ('Link Financial - TD', 'WATCH', 'ACCEPT', ['Asset Link Capital', 'incl. Link Financial Outsourcing']),  # #131
        ('Lloyds Banking Group (Including the Companies/Brands below) - IVA', 'WATCH', 'ACCEPT', ['Lloyds - Create (Wealth Management) Card - IVA', 'Blackhorse - Suzuki Financial Services Ltd - IVA', 'Lloyds - LTSB American Express Private Banking Card - IVA']),  # #132
        ('Lloyds Banking Group (Including the Companies/Brands below) - TD', 'WATCH', 'ACCEPT', ['Lloyds - Create (Wealth Management) Card - TD', 'Blackhorse - Suzuki Financial Services Ltd - TD', 'Lloyds - LTSB American Express Private Banking Card - TD']),  # #133
        ('New Day / PRA - IVA or BKY', 'WATCH', 'ACCEPT', ['Burton Menswear - IVA, Debenhams - IVA, Dorothy Perkins - IVA, Evans - IVA,', 'Laura Ashley - IVA, Marbles - IVA, Miss Selfridge - IVA, NewPay - IVA,']),  # #144
        ('New Day / PRA - TD or SEQ', 'WATCH', 'ACCEPT', ['Burton Menswear - TD, Debenhams - TD, Dorothy Perkins - TD, Evans - TD,', 'Laura Ashley - TD, Marbles - TD, Miss Selfridge - TD, NewPay - TD,']),  # #145
        ('The Very Group - IVA or TD', 'WATCH', 'ACCEPT', ['Shop Direct Financial Services, Littlewoods (SDG), Very (SDG), Very,', 'Littlewoods, Empire (SDG), Marshall Ward, Kays, Great Universal, K&Co,', 'Shop Direct Finance Company, Abound']),  # #159
        ('Tesco Bank', 'WATCH', 'ACCEPT', ['Tesco Personal Finance']),  # #165
        ('TBI Financial Services', 'NONE', 'REJECT', ['TBI Financial Services Limited']),  # #170
        ('Bamboo', 'NONE', 'REJECT', ['Bamboo Loans Limited']),  # #171
        ('Volkswagen Financial Services', 'NONE', 'DO_NOT_VOTE', ['VW Financial Services']),  # #172
        ('Buddy Loans', 'NONE', 'DO_NOT_VOTE', ['Advancis Limited', 'Advancis Ltd']),  # #173
        ('Salary Finance', 'NONE', 'CONDITIONAL_VOTER', ['Salary Finance Limited']),  # #174
        ('Commsave Credit Union', 'NONE', 'WILL_CONSIDER', ['Commsave']),  # #175
        ('CAMBRIAN Credit Union', 'NONE', 'WILL_CONSIDER', ['Cambrian Credit Union']),  # #176
        ('Amigo Loans', 'NONE', 'DO_NOT_VOTE', ['Amigo Loans Limited']),  # #177
        ('No1 Copperpot Credit Union', 'NONE', 'REJECT', ['Copperpot']),  # #179
        ('Penny Post Credit Union', 'NONE', 'REJECT', ['Penny Post']),  # #180
        ('Aqua', 'WATCH', 'ACCEPT', ['Aqua Credit Card']),  # #183
        ('Asset Link', 'NONE', 'ACCEPT', ['Asset Link Capital']),  # #185
        ('Creation', 'TIX', 'ACCEPT', ['Creation Consumer Finance Ltd', 'Creation Financial Services']),  # #199
        ('Fluid', 'WATCH', 'ACCEPT', []),  # #204
        ('Hull and East Yorkshire CU', 'NONE', 'ACCEPT', ['Hull & East Yorkshire Credit Union']),  # #209
        ('Littlewoods', 'TIX', 'ACCEPT', ['Littlewoods Catalogue']),  # #211
        ('MBNA', 'WATCH', 'ACCEPT', ['MBNA Limited']),  # #213
        ('NewDay', 'TIX', 'ACCEPT', ['NewDay Ltd']),  # #217
        ('Shell Energy', 'EVOLVE', 'ACCEPT', ['Shell Energy Retail Limited']),  # #222
        ('Shop Direct', 'TIX', 'ACCEPT', ['Shop Direct Finance']),  # #223
        ('Transave Credit Union', 'NONE', 'ACCEPT', []),  # #229
        ('Virgin Money', 'WATCH', 'ACCEPT', ['Virgin Money Credit Card', 'Virgin Money Personal Loan']),  # #231
        ('JD Williams', 'TIX', 'ACCEPT', ['Simply Be']),  # #236
        ('Lowell', 'TIX', 'ACCEPT', ['Lowell Financial']),  # #237
        ('Lantern', 'WATCH', 'ACCEPT', ['Lantern Debt Recovery Services Ltd']),  # #238
        ('Perch Capital', 'NONE', 'ACCEPT', ['Perch Capital Limited']),  # #239
        ('Octopus Energy', 'EVOLVE', 'ACCEPT', ['Bulb Energy']),  # #240
        ('DWP', 'NONE', 'DO_NOT_VOTE', ['Department for Work and Pensions']),  # #242
        ('Boom Credit Union', 'NONE', 'REJECT', ['East Sussex Credit Union']),  # #245
        ('American Express', 'NONE', 'WILL_CONSIDER', ['Amex', 'American Express Service']),  # #247
        ('Mutual (Home Credit)', 'NONE', 'WILL_CONSIDER', ['Mutual Home Credit']),  # #249
        ('HMRC', 'NONE', 'DO_NOT_VOTE', ['HM Revenue & Customs']),  # #250
        ('Anderson Brookes', 'NONE', 'DO_NOT_VOTE', ['Anderson Brookes Solicitors']),  # #251
        ('Credit4', 'NONE', 'WILL_CONSIDER', ['Credit 4']),  # #254
        ('CCC Debt Management', 'NONE', 'DO_NOT_VOTE', ['Complete Credit Control']),  # #255
        ('The Money Platform', 'NONE', 'WILL_CONSIDER', ['Money Platform']),  # #256
        ('118 118 Money', 'NONE', 'ACCEPT', []),  # #259
        ('1st Class Credit Union', 'NONE', 'WILL_CONSIDER', []),  # #262
        ('Asset Link Capital', 'WATCH', 'ACCEPT', []),  # #301
        ('BIP', 'WATCH', 'ACCEPT', []),  # #309
        ('Curvissa', 'NONE', 'DO_NOT_VOTE', []),  # #398
        ('Future Finance', 'NONE', 'DO_NOT_VOTE', []),  # #453
        ('IDR Finance UK Ltd', 'WATCH', 'ACCEPT', []),  # #531
        ('LINK', 'NONE', 'WILL_CONSIDER', []),  # #554
        ('Manchester Credit Union', 'NONE', 'WILL_CONSIDER', []),  # #598
        ('Perch Capital Limited', 'NONE', 'WILL_CONSIDER', []),  # #660
        ('Platform', 'NONE', 'DO_NOT_VOTE', []),  # #668
        ('Shoosmiths LLP', 'NONE', 'WILL_CONSIDER', []),  # #706
        ('Shop Direct Finance Company - IVA or TD', 'WATCH', 'ACCEPT', []),  # #707
        ('South Manchester Credit Union', 'NONE', 'REJECT', []),  # #717
        ('Tesco Mobile', 'NONE', 'DO_NOT_VOTE', []),  # #740
        ('Wilkin Chapman', 'NONE', 'REJECT', []),  # #781
        ('Zilch', 'NONE', 'DO_NOT_VOTE', ['Zilch Technology Limited']),  # #786
    )

    # (Aryza name, today's winning row, its representative)
    EXPECTED = (
        ('118 118 Money - Credit Cards', '118 Money', 'TIX'),
        ('118 118 Money - Loans', '118 Money', 'TIX'),
        # Phase 9 (manager 2026-10-21, option b): the organisation after "c/o"
        # decides when it has an exact row - Wilkin Chapman, Shoosmiths LLP.
        ('1st Class Credit Union c/o Wilkin Chapman', 'Wilkin Chapman', 'NONE'),
        # Owner decision 2026-10-21: Asset Link Capital variants alias to the
        # 'Asset Link Capital' row (were 'Asset Link', NONE).
        ('Asset Link Capital (No 1)', 'Asset Link Capital', 'WATCH'),
        ('Asset Link Capital (No 5)', 'Asset Link Capital', 'WATCH'),
        ('Asset Link Capital (No 7)', 'Asset Link Capital', 'WATCH'),
        ('Asset Link Capital (No 9)', 'Asset Link Capital', 'WATCH'),
        ('Asset Link Capital (No 9) (Ex Future Finance Loan Corporation Limited)', 'Asset Link Capital', 'WATCH'),
        ('Asset Link Capital (No. 7) Limited', 'Asset Link Capital', 'WATCH'),
        ('Asset Link Capital c/o The Insolvency Exchange', 'Asset Link Capital', 'WATCH'),
        # Phase 5 (owner, 2026-10-21): exact alias to the WATCH 'BIP' row (was NewDay, TIX).
        ('BIP CREDIT (NewDay)', 'BIP', 'WATCH'),
        ('Clydesdale Bank PLC t/a Virgin Money Business', 'Clydesdale Bank', 'NONE'),
        ('Curvissa (Freemans Grattan Holdings Limited)', 'Grattan', 'TIX'),
        # Whole-entry trading-name match (2026-10-21): E / ERS / NCI / PERSONAL /
        # RIC / ss only ever matched a fragment of another row's trading name
        # ("NatWest", "Personal Loan", "fiNanCIal", "AmeRICan", "ExpreSS").
        # Now unresolved (UNKNOWN keeps the raw name).
        ('E', 'E', 'NONE'),
        ('ERS', 'ERS', 'NONE'),
        ('Gracombex Ltd t/a The Money Platform c/o Credit Resource Solutions', 'The Money Platform', 'NONE'),
        ('IDR Finance UK Ltd (Link)', 'IDR Finance UK Ltd', 'WATCH'),
        ('Lowell Portfolio c/o Wilkin Chapman Rollits LLP', 'Lowell', 'TIX'),
        ('Lowell tesco mobile', 'Lowell', 'TIX'),
        ('Madison CF UK Limited (T/A 118 118 Money)', '118 Money', 'TIX'),
        ('Madison Cf Uk LTD T/A 118 118 Money Credit Card', '118 Money', 'TIX'),
        ('NCI', 'NCI', 'NONE'),
        ('NEWDAY CARDS LTD (FLUID)', 'Fluid', 'WATCH'),
        ('Newday LTD Fluid Mastercard', 'Fluid', 'WATCH'),
        ('Perch Capital Limited (ACI) c/o Aryza Connect', 'Perch Capital', 'NONE'),
        ('Perch Capital Limited c/o My Money Options Limited (ACI) PRE SEPTEMBER 2025 MOC ONLY', 'Perch Capital', 'NONE'),
        ('Perch Capital Limited c/o My Money Options Limited (TMLS)', 'Perch Capital', 'NONE'),
        ('Perch Capital Limited c/o My Money Options Limited (Uncle Buck)', 'Perch Capital', 'NONE'),
        ('PERSONAL', 'PERSONAL', 'NONE'),
        ('PRA-Barclays Bank BV23071IVB', 'Barclays', 'WATCH'),
        ('PRA-Barclays Bank BY20111IVB', 'Barclays', 'WATCH'),
        ('PRA-Barclays Bank BY22071IVB', 'Barclays', 'WATCH'),
        ('RIC', 'RIC', 'NONE'),
        ('Royal Bank of Scotland (RBS) Business Banking', 'Royal Bank of Scotland', 'EVOLVE'),
        ('Royal Bank of Scotland (RBS) Mortgages', 'Royal Bank of Scotland', 'EVOLVE'),
        # Phase 5 (owner, 2026-10-21): same company as Shop Direct Finance Company Ltd.
        ('Shop Direct Finance', 'Shop Direct Finance Company - IVA or TD', 'WATCH'),
        # Phase 9 (manager 2026-10-21): South Manchester CU is its own lender (alias).
        ('South Manchester Credit Union Limited', 'South Manchester Credit Union', 'NONE'),
        ('ss', 'ss', 'NONE'),
        ('The Co-operative Bank t/a Platform Mortgages', 'Co-operative Bank', 'NONE'),
        # Phase 3C hyphen fix: these matched the bank via the "the co" segment
        # split out of "Co-operative"; now unresolved (UNKNOWN keeps the raw name).
        ('The Co-Operative Credit Union', 'The Co-Operative Credit Union', 'NONE'),
        ('The Co-Operative Credit Union c/o C&L Collections', 'The Co-Operative Credit Union c/o C&L Collections', 'NONE'),
        ('Transave Credit Union Limited c/o Wilkin Chapman LLP', 'Wilkin Chapman', 'NONE'),  # Phase 9 c/o
        ('Volkswagen Financial Services (UK) Limited c/o Shoosmiths LLP', 'Shoosmiths LLP', 'NONE'),  # Phase 9 c/o
    )

    @classmethod
    def setUpTestData(cls):
        CreditorCriteria.objects.all().delete()
        for name, rep, status, trading in cls.ROWS:
            CreditorCriteria.objects.create(creditor_name=name, representative=rep, status=status,
                                            trading_names=trading, is_active=True)

    def test_current_winner_is_locked(self):
        for raw, canonical, rep in self.EXPECTED:
            with self.subTest(raw=raw):
                pos = _position(raw)
                self.assertEqual((pos["resolved_canonical_name"], pos["representative"]), (canonical, rep))
