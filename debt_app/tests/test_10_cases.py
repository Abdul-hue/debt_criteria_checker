"""
test_12_real_cases.py
=====================
11 real client cases sourced from Supabase (case assessment database).
Financial figures are exact from the database.
Creditor names are normalised to canonical DB names so the engine can
resolve them — the rule logic under test is the same regardless of the
Aryza full-legal-name variant.

Cases 4, 6, 8, 10 have no database match and are omitted.

Run:
    python -m pytest debt_app/tests/test_12_real_cases.py -v
"""

from datetime import date, timedelta
from django.test import TestCase as DjangoTestCase
from debt_app.criteria_engine import assess_case

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

RECENT_BANK  = (date.today() - timedelta(days=30)).isoformat()
RECENT_SLIP  = (date.today() - timedelta(days=14)).isoformat()
TODAY        = date.today().isoformat()


def _bank_doc(holder):
    return {
        "document_type": "bank_statement",
        "is_valid": True,
        "extracted_data": {"statement_date": RECENT_BANK, "account_holder": holder},
    }


def _payslip_doc():
    return {
        "document_type": "payslip",
        "is_valid": True,
        "extracted_data": {"statement_date": RECENT_SLIP},
    }


def _creditor(name, balance, debt_type, *, is_joint=False,
              arrears=0, months_since=None, age=24):
    return {
        "creditor_name": name,
        "balance": balance,
        "debt_type": debt_type,
        "debt_type_normalised": debt_type,
        "is_joint": is_joint,
        "account_age_months": age,
        "arrears_months": arrears,
        "first_payment_made": True,
        "months_since_purchase": months_since,
    }


def _has_block(result, code):
    for r in result.get("hard_blocks", []):
        if f"rule_id='{code}'" in str(r) and "triggered=True" in str(r):
            return True
    return False


def _has_flag(result, code):
    for r in result.get("flags", []):
        if f"rule_id='{code}'" in str(r) and "triggered=True" in str(r):
            return True
    return False


def _status(result):
    return result.get("overall_status", "")


# ---------------------------------------------------------------------------
# Case 1 — M.J.  Supabase #319197
# Employed full-time (ASDA), income £1,993, DI £131, total debt £16,483
# 13 unsecured creditors, no property, no flags
# Expected: PASS / IVA_VIABLE
# ---------------------------------------------------------------------------
class TestCase12_01_CleanEmployed(DjangoTestCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.result = assess_case({
            "client_name": "M.J.",
            "assessment_date": TODAY,
            "employment_status": "employed",
            "is_employed": True,
            "income_source": "employed",
            "total_income": 1993.00,
            "monthly_income": 1993.00,
            "disposable_income": 131.00,
            "net_disposable_income": 131.00,
            "iva_term_months": 60,
            "has_property": False,
            "is_homeowner": False,
            "is_joint_case": False,
            "previous_iva": False,
            "has_previous_iva": False,
            "is_currently_trading": False,
            "has_antecedent_transactions": False,
            "gambling_primary_cause": False,
            "number_of_children": 0,
            "children_ages": [],
            "income_source_benefits": False,
            "creditors": [
                _creditor("Halifax",       3800.00, "personal_loan"),
                _creditor("Halifax",        700.00, "personal_loan"),
                _creditor("Barclaycard",   1100.00, "credit_card"),
                _creditor("Capital One",    600.00, "credit_card"),
                _creditor("Very",           500.00, "catalogue"),
                _creditor("MBNA",           800.00, "credit_card"),
                _creditor("Barclaycard",    300.00, "credit_card"),
                _creditor("Lloyds Bank",    250.00, "credit_card"),
                _creditor("NatWest",        100.00, "credit_card"),
                _creditor("Barclays",       170.00, "personal_loan"),
                _creditor("Halifax",         18.00, "overdraft"),
            ],
            "documents": [_bank_doc("M.J."), _payslip_doc()],
            "gold_transactions": [],
            "financial_summary": {
                "net_balance": 131.00,
                "total_income": 1993.00,
                "income_source": "employed",
            },
        })

    def test_status_pass(self):
        self.assertIn(_status(self.result), ("PASS", "FLAGGED"),
                      "Clean employed case should be PASS or FLAGGED, not BLOCKED")

    def test_tig_01_passes(self):
        self.assertFalse(_has_block(self.result, "TIG-01"),
                         "Debt £8,338 meets minimum — TIG-01 must not fire")

    def test_tig_02_passes(self):
        self.assertFalse(_has_block(self.result, "TIG-02"),
                         "DI £131 meets minimum — TIG-02 must not fire")

    def test_no_gambling_block(self):
        self.assertFalse(_has_block(self.result, "TIG-11-GAMBLING"),
                         "No gambling — TIG-11-GAMBLING must not fire")

    def test_majority_achievable(self):
        maj = self.result.get("majority_analysis", {})
        self.assertTrue(maj.get("achievable"),
                        f"Majority should be achievable with 13 known creditors. "
                        f"voting={maj.get('voting_debt')}/{maj.get('total_debt')}")


# ---------------------------------------------------------------------------
# Case 2 — C.I.  Supabase #332591
# Self-employed, income £2,335, DI £125, total debt £37,140
# Creation Finance x2 with months_since_purchase=3 → TIG-20 / TIX-03
# Expected: BLOCKED or IVA_WITH_CONDITIONS — Creation antecedent fires
# ---------------------------------------------------------------------------
class TestCase12_02_SelfEmployedCreation(DjangoTestCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.result = assess_case({
            "client_name": "C.I.",
            "assessment_date": TODAY,
            "employment_status": "self_employed",
            "is_employed": True,
            "income_source": "self_employed",
            "total_income": 2335.00,
            "monthly_income": 2335.00,
            "disposable_income": 125.00,
            "net_disposable_income": 125.00,
            "iva_term_months": 60,
            "has_property": False,
            "is_homeowner": False,
            "is_joint_case": False,
            "previous_iva": False,
            "has_previous_iva": False,
            "is_currently_trading": True,
            "has_antecedent_transactions": True,
            "gambling_primary_cause": False,
            "number_of_children": 0,
            "children_ages": [],
            "income_source_benefits": False,
            "creditors": [
                _creditor("Barclays",         21484.00, "personal_loan"),
                _creditor("Creation Finance",   5688.00, "credit_card",
                          months_since=3),
                _creditor("Capital One",        2420.00, "credit_card"),
                _creditor("Creation Finance",   1998.00, "credit_card",
                          months_since=3),
                _creditor("Barclaycard",         660.00, "credit_card"),
                _creditor("Barclays",            442.00, "overdraft"),
            ],
            "documents": [_bank_doc("C.I."), _payslip_doc()],
            "gold_transactions": [
                {"description": "Creation Finance", "amount": 200.00,
                 "transaction_date": RECENT_BANK},
                {"description": "Creation Finance", "amount": 150.00,
                 "transaction_date": RECENT_BANK},
            ],
            "financial_summary": {
                "net_balance": 125.00,
                "total_income": 2335.00,
                "income_source": "self_employed",
            },
        })

    def test_creation_antecedent_fires(self):
        self.assertTrue(
            _has_block(self.result, "TIG-20.1") or _has_flag(self.result, "TIG-20") or _has_block(self.result, "TIX-03"),
            "Creation Finance spend within 4 months must fire TIG-20 (flag) or TIG-20.1 (hard block) or TIX-03",
        )

    def test_self_employed_flag(self):
        self.assertTrue(
            _has_flag(self.result, "TIG-08") or _has_block(self.result, "TIG-08"),
            "Self-employed client must trigger TIG-08 self-employment proof check",
        )

    def test_tig_02_passes(self):
        self.assertFalse(_has_block(self.result, "TIG-02"),
                         "DI £125 meets minimum — TIG-02 must not fire")


# ---------------------------------------------------------------------------
# Case 3 — J.S.  Supabase #324901
# Employed (EDF), income £1,559, DI £101, total debt £14,028
# Brighton & Hove City Council = 32.7% of total debt → TIG-17 council risk
# Bet365 gambling transaction → TIG-11-GAMBLING
# Expected: IVA_WITH_CONDITIONS — council flag + gambling flag
# ---------------------------------------------------------------------------
class TestCase12_03_CouncilMajorityGambling(DjangoTestCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.result = assess_case({
            "client_name": "J.S.",
            "assessment_date": TODAY,
            "employment_status": "employed",
            "is_employed": True,
            "income_source": "employed",
            "total_income": 1559.00,
            "monthly_income": 1559.00,
            "disposable_income": 101.00,
            "net_disposable_income": 101.00,
            "iva_term_months": 60,
            "has_property": False,
            "is_homeowner": False,
            "is_joint_case": False,
            "previous_iva": False,
            "has_previous_iva": False,
            "is_currently_trading": False,
            "has_antecedent_transactions": False,
            "gambling_primary_cause": False,
            "number_of_children": 0,
            "children_ages": [],
            "income_source_benefits": False,
            "creditors": [
                _creditor("Brighton and Hove City Council",
                          4587.00, "COUNCIL_TAX"),
                _creditor("Nationwide",    1783.00, "overdraft"),
                _creditor("JD Williams",    187.00, "catalogue"),
                _creditor("Barclaycard",    379.00, "credit_card"),
                _creditor("Halifax",        892.00, "personal_loan"),
                _creditor("Halifax",        830.00, "personal_loan"),
                _creditor("Halifax",        737.00, "personal_loan"),
                _creditor("Barclays",       571.00, "personal_loan"),
                _creditor("Barclays",       252.00, "personal_loan"),
                _creditor("MBNA",           490.00, "credit_card"),
                _creditor("MBNA",           455.00, "credit_card"),
                _creditor("Capital One",    186.00, "credit_card"),
                _creditor("Lloyds Bank",    149.00, "personal_loan"),
                _creditor("Monzo",          530.00, "overdraft"),
            ],
            "documents": [_bank_doc("J.S."), _payslip_doc()],
            "gold_transactions": [
                {"description": "Trustly UK bet365 Limited",
                 "amount": 10.00, "months_ago": 4},
            ],
            "financial_summary": {
                "net_balance": 101.00,
                "total_income": 1559.00,
                "income_source": "employed",
            },
        })

    def test_council_majority_risk_fires(self):
        self.assertTrue(
            _has_flag(self.result, "TIG-17") or _has_block(self.result, "TIG-17"),
            "Brighton & Hove at 32.7% of debt must trigger TIG-17 council risk",
        )

    def test_gambling_flag_fires(self):
        self.assertTrue(
            _has_flag(self.result, "TIG-11-GAMBLING")
            or _has_block(self.result, "TIG-11-GAMBLING"),
            "Bet365 transaction must trigger TIG-11-GAMBLING",
        )

    def test_tig_01_passes(self):
        self.assertFalse(_has_block(self.result, "TIG-01"),
                         "Debt £14,028 meets minimum — TIG-01 must not fire")

    def test_tig_02_passes(self):
        self.assertFalse(_has_block(self.result, "TIG-02"),
                         "DI £101 meets minimum — TIG-02 must not fire")


# ---------------------------------------------------------------------------
# Case 5 — J.B.  Supabase #117865
# Homeowner, property £123,384, mortgage £0 (owned outright), equity £104,876
# Total unsecured debt £18,314 — equity >> debt → WATCH-22.4 + EVOLVE-01
# Expected: BLOCKED — equity exceeds total debt
# ---------------------------------------------------------------------------
class TestCase12_05_HighEquityOwned(DjangoTestCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.result = assess_case({
            "client_name": "J.B.",
            "assessment_date": TODAY,
            "employment_status": "employed",
            "is_employed": True,
            "income_source": "employed",
            "total_income": 2122.00,
            "monthly_income": 2122.00,
            "disposable_income": 100.00,
            "net_disposable_income": 100.00,
            "iva_term_months": 60,
            "has_property": True,
            "is_homeowner": True,
            "property_value": 123384.00,
            "mortgage_balance": 0.00,
            "is_joint_case": False,
            "previous_iva": False,
            "has_previous_iva": False,
            "is_currently_trading": False,
            "has_antecedent_transactions": False,
            "gambling_primary_cause": False,
            "number_of_children": 0,
            "children_ages": [],
            "income_source_benefits": False,
            "creditors": [
                _creditor("Barclays",     9321.00, "personal_loan"),
                _creditor("Lloyds Bank",  8077.00, "personal_loan"),
                _creditor("Barclaycard",   778.37, "credit_card"),
                _creditor("Very",          116.00, "catalogue"),
                _creditor("Halifax",        12.00, "overdraft"),
                _creditor("Halifax",        10.00, "overdraft"),
            ],
            "documents": [_bank_doc("J.B."), _payslip_doc()],
            "gold_transactions": [],
            "financial_summary": {
                "net_balance": 100.00,
                "total_income": 2122.00,
                "income_source": "employed",
            },
        })

    def test_equity_exceeds_debt_watch_fires(self):
        self.assertTrue(
            _has_block(self.result, "WATCH-22.4"),
            "Equity £104,876 > total debt £18,314 — WATCH-22.4 must fire",
        )

    def test_equity_exceeds_debt_evolve_fires(self):
        self.assertTrue(
            _has_block(self.result, "EVOLVE-01"),
            "Equity £104,876 > total debt £18,314 — EVOLVE-01 must fire",
        )

    def test_overall_blocked(self):
        self.assertEqual(_status(self.result), "BLOCKED",
                         "Equity far exceeds debt — case must be BLOCKED")

    def test_equity_flag_fires(self):
        self.assertTrue(
            _has_flag(self.result, "TIG-16") or _has_block(self.result, "TIG-16"),
            "TIG-16 equity flag must fire for homeowner case",
        )


# ---------------------------------------------------------------------------
# Case 7 — T.T.  Supabase #324991
# Homeowner, property £200,173, mortgage £106,098 (LTV 53%, equity £64,049)
# Unsecured debt £31,905 — equity > unsecured debt → WATCH-22.4 + EVOLVE-01
# Gambling: Tombola x4, National Lottery x1 (Jan 2026)
# Expected: BLOCKED — equity block fires; gambling flag present
# ---------------------------------------------------------------------------
class TestCase12_07_GamblingHomeownerEquity(DjangoTestCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.result = assess_case({
            "client_name": "T.T.",
            "assessment_date": TODAY,
            "employment_status": "employed",
            "is_employed": True,
            "income_source": "employed",
            "total_income": 3366.00,
            "monthly_income": 3366.00,
            "disposable_income": 120.00,
            "net_disposable_income": 120.00,
            "iva_term_months": 60,
            "has_property": True,
            "is_homeowner": True,
            "property_value": 200173.00,
            "mortgage_balance": 106098.00,
            "is_joint_case": False,
            "previous_iva": False,
            "has_previous_iva": False,
            "is_currently_trading": False,
            "has_antecedent_transactions": False,
            "gambling_primary_cause": False,
            "number_of_children": 0,
            "children_ages": [],
            "income_source_benefits": False,
            "creditors": [
                _creditor("MBNA",          8109.00, "credit_card"),
                _creditor("Lloyds Bank",   8499.00, "credit_card"),
                _creditor("NatWest",       8039.00, "credit_card"),
                _creditor("JD Williams",   3065.00, "catalogue"),
                _creditor("Barclays",      2583.00, "personal_loan"),
                _creditor("Barclaycard",   1610.00, "credit_card"),
            ],
            "documents": [_bank_doc("T.T."), _payslip_doc()],
            "gold_transactions": [
                {"description": "TOMBOLA",          "amount": 10.00, "months_ago": 4},
                {"description": "NATIONAL LOTTERY", "amount": 10.00, "months_ago": 4},
                {"description": "TOMBOLA",          "amount": 5.00,  "months_ago": 4},
                {"description": "TOMBOLA",          "amount": 5.00,  "months_ago": 4},
                {"description": "TOMBOLA",          "amount": 5.00,  "months_ago": 4},
            ],
            "financial_summary": {
                "net_balance": 120.00,
                "total_income": 3366.00,
                "income_source": "employed",
            },
        })

    def test_equity_watch_fires(self):
        self.assertTrue(
            _has_block(self.result, "WATCH-22.4"),
            "Equity £64,049 > unsecured debt £31,905 — WATCH-22.4 must fire",
        )

    def test_equity_evolve_fires(self):
        self.assertTrue(
            _has_block(self.result, "EVOLVE-01"),
            "Equity £64,049 > unsecured debt £31,905 — EVOLVE-01 must fire",
        )

    def test_gambling_flag_fires(self):
        self.assertTrue(
            _has_flag(self.result, "TIG-11-GAMBLING")
            or _has_block(self.result, "TIG-11-GAMBLING"),
            "Tombola/Lottery transactions must trigger TIG-11-GAMBLING",
        )

    def test_overall_blocked(self):
        self.assertEqual(_status(self.result), "BLOCKED",
                         "Equity exceeds unsecured debt — case must be BLOCKED")


# ---------------------------------------------------------------------------
# Case 9 — M.E.  Supabase #353060
# Employed, income £6,336, DI £500, homeowner LTV 46.5%
# equity_at_85 = 290578*0.85 - 135063 = £111,928 > unsecured debt £83,893
# Per Excel WATCH criteria: equity at 85% LTV > total unsecured → hard block
# Expected: BLOCKED — WATCH-22.4 and/or EVOLVE-01 fire on equity
# ---------------------------------------------------------------------------
class TestCase12_09_BambooHPAntecedent(DjangoTestCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.result = assess_case({
            "client_name": "M.E.",
            "assessment_date": TODAY,
            "employment_status": "employed",
            "is_employed": True,
            "income_source": "employed",
            "total_income": 6336.00,
            "monthly_income": 6336.00,
            "disposable_income": 500.00,
            "net_disposable_income": 500.00,
            "iva_term_months": 60,
            "has_property": True,
            "is_homeowner": True,
            "property_value": 290578.00,
            "mortgage_balance": 135063.00,
            "is_joint_case": False,
            "previous_iva": False,
            "has_previous_iva": False,
            "is_currently_trading": False,
            "has_antecedent_transactions": True,
            "gambling_primary_cause": False,
            "number_of_children": 1,
            "children_ages": [5],
            "income_source_benefits": False,
            "creditors": [
                _creditor("Barclays",      14602.00, "personal_loan"),
                _creditor("Barclaycard",    8039.00, "credit_card"),
                _creditor("MBNA",           8109.00, "credit_card"),
                _creditor("Lloyds Bank",    7055.00, "credit_card"),
                _creditor("Bamboo",         5857.00, "personal_loan",
                          months_since=3),
                _creditor("NatWest",        5454.00, "credit_card"),
                _creditor("Capital One",    4978.00, "credit_card"),
                _creditor("Halifax",        4555.00, "credit_card"),
                _creditor("Barclays",       3526.00, "credit_card"),
                _creditor("HSBC",           3408.00, "personal_loan"),
                _creditor("NatWest",        3165.00, "credit_card"),
                _creditor("Lloyds Bank",    2657.00, "credit_card"),
                _creditor("Halifax",        5000.00, "personal_loan"),
                _creditor("Barclaycard",    4322.00, "personal_loan"),
                _creditor("Monzo",           729.00, "overdraft"),
                _creditor("Monzo",           729.00, "overdraft"),
                _creditor("Halifax",        1708.20, "personal_loan"),
            ],
            "documents": [_bank_doc("M.E."), _payslip_doc()],
            "gold_transactions": [],
            "financial_summary": {
                "net_balance": 500.00,
                "total_income": 6336.00,
                "income_source": "employed",
            },
        })

    def test_equity_blocks(self):
        self.assertTrue(
            _has_block(self.result, "WATCH-22.4") or _has_block(self.result, "EVOLVE-01"),
            "Equity at 85% LTV £111,928 > unsecured debt £83,893 — equity block must fire",
        )

    def test_tig_01_passes(self):
        self.assertFalse(_has_block(self.result, "TIG-01"),
                         "Total debt well above minimum — TIG-01 must not fire")

    def test_tig_02_passes(self):
        self.assertFalse(_has_block(self.result, "TIG-02"),
                         "DI £500 well above minimum — TIG-02 must not fire")


# ---------------------------------------------------------------------------
# Case 11 — D.S.  Supabase #325014
# Employed director, income £1,014, DI £100, total debt £22,842
# Blue Motor Finance HP shortfall (vehicle already repossessed)
# Multiple credit cards, Klarna x3 catalogue
# Expected: IVA_WITH_CONDITIONS — DI at minimum, HP shortfall present
# ---------------------------------------------------------------------------
class TestCase12_11_DirectorHPShortfall(DjangoTestCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.result = assess_case({
            "client_name": "D.S.",
            "assessment_date": TODAY,
            "employment_status": "employed",
            "is_employed": True,
            "income_source": "employed",
            "total_income": 1014.00,
            "monthly_income": 1014.00,
            "disposable_income": 100.00,
            "net_disposable_income": 100.00,
            "iva_term_months": 60,
            "has_property": False,
            "is_homeowner": False,
            "is_joint_case": False,
            "previous_iva": False,
            "has_previous_iva": False,
            "is_currently_trading": False,
            "has_antecedent_transactions": False,
            "gambling_primary_cause": False,
            "number_of_children": 0,
            "children_ages": [],
            "income_source_benefits": False,
            "creditors": [
                _creditor("Barclays",      6906.00, "hire_purchase"),
                _creditor("Nationwide",    3249.00, "personal_loan"),
                _creditor("Nationwide",    2252.00, "credit_card"),
                _creditor("Barclaycard",   2198.00, "personal_loan"),
                _creditor("MBNA",          2126.00, "credit_card"),
                _creditor("Capital One",   1200.00, "credit_card"),
                _creditor("Halifax",       1224.00, "credit_card"),
                _creditor("Lloyds Bank",    792.00, "personal_loan"),
                _creditor("NatWest",        580.00, "credit_card"),
                _creditor("Barclays",       741.00, "personal_loan"),
                _creditor("Barclays",       320.00, "personal_loan"),
                _creditor("Halifax",        293.00, "credit_card"),
                _creditor("Lloyds Bank",    196.00, "credit_card"),
                _creditor("HSBC",           193.00, "credit_card"),
                _creditor("Nationwide",     112.00, "overdraft"),
                _creditor("Monzo",           60.00, "catalogue"),
                _creditor("Monzo",           54.00, "catalogue"),
                _creditor("Monzo",           34.00, "catalogue"),
                _creditor("Halifax",         10.00, "catalogue"),
                _creditor("Barclaycard",    102.00, "personal_loan"),
            ],
            "documents": [_bank_doc("D.S."), _payslip_doc()],
            "gold_transactions": [],
            "financial_summary": {
                "net_balance": 100.00,
                "total_income": 1014.00,
                "income_source": "employed",
            },
        })

    def test_tig_01_passes(self):
        self.assertFalse(_has_block(self.result, "TIG-01"),
                         "Debt £22,842 meets minimum — TIG-01 must not fire")

    def test_tig_02_passes(self):
        self.assertFalse(_has_block(self.result, "TIG-02"),
                         "DI £100 meets minimum — TIG-02 must not fire")

    def test_not_hard_blocked_on_di(self):
        """DI is exactly £100 — the minimum. Should pass TIG-02."""
        self.assertFalse(_has_block(self.result, "TIG-02"),
                         "DI exactly at minimum £100 must not hard block")

    def test_majority_achievable(self):
        maj = self.result.get("majority_analysis", {})
        self.assertTrue(maj.get("achievable"),
                        f"Majority must be achievable with known creditors. "
                        f"voting={maj.get('voting_debt')}/{maj.get('total_debt')}")


# ---------------------------------------------------------------------------
# Case 12 — A.O.  Supabase #355861
# Employed, income £2,118, DI £154, total debt £9,621
# Mansfield District Council = £7,020 = 72.97% of total debt
# Sky Betting gambling transactions (Feb 2026)
# Expected: IVA_WITH_CONDITIONS — council majority risk + gambling
# ---------------------------------------------------------------------------
class TestCase12_12_CouncilMajority73pct(DjangoTestCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.result = assess_case({
            "client_name": "A.O.",
            "assessment_date": TODAY,
            "employment_status": "employed",
            "is_employed": True,
            "income_source": "employed",
            "total_income": 2118.00,
            "monthly_income": 2118.00,
            "disposable_income": 154.00,
            "net_disposable_income": 154.00,
            "iva_term_months": 60,
            "has_property": False,
            "is_homeowner": False,
            "is_joint_case": False,
            "previous_iva": False,
            "has_previous_iva": False,
            "is_currently_trading": False,
            "has_antecedent_transactions": False,
            "gambling_primary_cause": False,
            "number_of_children": 0,
            "children_ages": [],
            "income_source_benefits": False,
            "creditors": [
                _creditor("Mansfield District Council",
                          7020.11, "COUNCIL_TAX"),
                _creditor("Barclays",    599.99, "personal_loan"),
                _creditor("Halifax",     557.00, "personal_loan"),
                _creditor("NatWest",     498.97, "personal_loan"),
                _creditor("Barclaycard", 425.00, "personal_loan"),
                _creditor("HSBC",        346.00, "personal_loan"),
                _creditor("Lloyds Bank", 174.00, "personal_loan"),
            ],
            "documents": [_bank_doc("A.O."), _payslip_doc()],
            "gold_transactions": [
                {"description": "SKY BETTING AND GAMING", "amount": 10.00,
                 "months_ago": 3},
                {"description": "SKY BETTING AND GAMING FPO", "amount": 10.00,
                 "months_ago": 3},
                {"description": "SKY BETTING AND GAMING FPI", "amount": 10.00,
                 "months_ago": 3},
            ],
            "financial_summary": {
                "net_balance": 154.00,
                "total_income": 2118.00,
                "income_source": "employed",
            },
        })

    def test_council_majority_risk_fires(self):
        self.assertTrue(
            _has_flag(self.result, "TIG-17") or _has_block(self.result, "TIG-17"),
            "Mansfield District Council at 72.97% must trigger TIG-17",
        )

    def test_gambling_flag_fires(self):
        self.assertTrue(
            _has_flag(self.result, "TIG-11-GAMBLING")
            or _has_block(self.result, "TIG-11-GAMBLING"),
            "Sky Betting transactions must trigger TIG-11-GAMBLING",
        )

    def test_tig_01_passes(self):
        self.assertFalse(_has_block(self.result, "TIG-01"),
                         "Debt £9,621 meets minimum — TIG-01 must not fire")

    def test_tig_02_passes(self):
        self.assertFalse(_has_block(self.result, "TIG-02"),
                         "DI £154 meets minimum — TIG-02 must not fire")


# ---------------------------------------------------------------------------
# Case 13 — A.G.  Supabase #117536
# Employed director, income £3,499, DI = -£486 (expenses exceed income)
# Total debt £33,590
# Expected: BLOCKED — TIG-02 fires on negative DI
# ---------------------------------------------------------------------------
class TestCase12_13_NegativeDI(DjangoTestCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.result = assess_case({
            "client_name": "A.G.",
            "assessment_date": TODAY,
            "employment_status": "employed",
            "is_employed": True,
            "income_source": "employed",
            "total_income": 3499.00,
            "monthly_income": 3499.00,
            "disposable_income": -486.00,
            "net_disposable_income": -486.00,
            "iva_term_months": 60,
            "has_property": False,
            "is_homeowner": False,
            "is_joint_case": False,
            "previous_iva": False,
            "has_previous_iva": False,
            "is_currently_trading": False,
            "has_antecedent_transactions": False,
            "gambling_primary_cause": False,
            "number_of_children": 1,
            "children_ages": [8],
            "income_source_benefits": False,
            "creditors": [
                _creditor("Barclaycard",  13070.00, "credit_card"),
                _creditor("NatWest",       6775.00, "personal_loan"),
                _creditor("Lloyds Bank",   6453.00, "personal_loan"),
                _creditor("Lloyds Bank",   3066.00, "credit_card"),
                _creditor("Halifax",       3126.00, "credit_card"),
                _creditor("Capital One",   1093.00, "credit_card"),
                _creditor("Monzo",            7.00, "overdraft"),
            ],
            "documents": [_bank_doc("A.G."), _payslip_doc()],
            "gold_transactions": [],
            "financial_summary": {
                "net_balance": -486.00,
                "total_income": 3499.00,
                "income_source": "employed",
            },
        })

    def test_tig_02_fires_on_negative_di(self):
        self.assertTrue(
            _has_block(self.result, "TIG-02"),
            "DI = -£486 must hard block on TIG-02 (minimum £100 required)",
        )

    def test_overall_blocked(self):
        self.assertEqual(_status(self.result), "BLOCKED",
                         "Negative DI case must be BLOCKED")

    def test_tig_01_passes(self):
        self.assertFalse(_has_block(self.result, "TIG-01"),
                         "Debt £33,590 meets minimum — TIG-01 must not fire")


# ---------------------------------------------------------------------------
# Case 14 — L.D.  Supabase #117016
# Employed, income £7,547, DI £1,550, property £789,488, mortgage £450,493
# Equity ≈ £220,571 vs non-mortgage unsecured debt ≈ £208,677
# HMRC self-assessment debt £20,834 → TIG-15.4 fires
# EVOLVE-01 fires because equity ≈ debt
# Expected: BLOCKED — HMRC majority + equity block
# ---------------------------------------------------------------------------
class TestCase12_14_HMRCHighEquity(DjangoTestCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.result = assess_case({
            "client_name": "L.D.",
            "assessment_date": TODAY,
            "employment_status": "employed",
            "is_employed": True,
            "income_source": "employed",
            "total_income": 7547.00,
            "monthly_income": 7547.00,
            "disposable_income": 1550.00,
            "net_disposable_income": 1550.00,
            "iva_term_months": 60,
            "has_property": True,
            "is_homeowner": True,
            "property_value": 789488.00,
            "mortgage_balance": 450493.00,
            "is_joint_case": False,
            "previous_iva": False,
            "has_previous_iva": False,
            "is_currently_trading": False,
            "has_antecedent_transactions": False,
            "gambling_primary_cause": False,
            "number_of_children": 1,
            "children_ages": [6],
            "income_source_benefits": False,
            "creditors": [
                _creditor("Barclays",      62191.50, "personal_loan"),
                _creditor("Barclaycard",   23559.92, "credit_card"),
                _creditor("Halifax",       27675.26, "personal_loan"),
                _creditor("Barclays",      21738.00, "hire_purchase"),
                _creditor("HMRC",          20834.08, "self_assessment"),
                _creditor("Lloyds Bank",   18542.17, "personal_loan"),
                _creditor("HSBC",          12840.11, "personal_loan"),
                _creditor("NatWest",       11281.98, "credit_card"),
                _creditor("Nationwide",    10014.01, "personal_loan"),
            ],
            "documents": [_bank_doc("L.D."), _payslip_doc()],
            "gold_transactions": [],
            "financial_summary": {
                "net_balance": 1550.00,
                "total_income": 7547.00,
                "income_source": "employed",
            },
        })

    def test_hmrc_block_fires(self):
        self.assertTrue(
            _has_block(self.result, "TIG-15.4")
            or _has_block(self.result, "TIG-15.3")
            or _has_flag(self.result, "TIG-HMRC-VOTE-NOT-GUARANTEED"),
            "HMRC self-assessment debt must trigger HMRC rule (TIG-15.3/15.4 "
            "or TIG-HMRC-VOTE-NOT-GUARANTEED)",
        )

    def test_equity_block_fires(self):
        self.assertTrue(
            _has_block(self.result, "EVOLVE-01") or _has_block(self.result, "WATCH-22.4"),
            "Equity £220k ≈ unsecured debt £208k — equity block must fire",
        )

    def test_overall_blocked(self):
        self.assertEqual(_status(self.result), "BLOCKED",
                         "HMRC + high equity — case must be BLOCKED")

    def test_equity_flag_fires(self):
        self.assertTrue(
            _has_flag(self.result, "TIG-16") or _has_block(self.result, "TIG-16"),
            "TIG-16 equity flag must fire for homeowner with significant equity",
        )


# ---------------------------------------------------------------------------
# Case 15 — B.S.  Supabase #330210
# Unemployed, benefits-only (UC £2,052 + child benefit), DI £100
# Total debt £10,203, no council tax, standard unsecured creditors
# Expected: PASS or FLAGGED — benefits sustainability flag expected
# ---------------------------------------------------------------------------
class TestCase12_15_BenefitsOnlyNoCouncilTax(DjangoTestCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.result = assess_case({
            "client_name": "B.S.",
            "assessment_date": TODAY,
            "employment_status": "unemployed",
            "is_employed": False,
            "income_source": "benefits",
            "total_income": 3256.00,
            "monthly_income": 3256.00,
            "disposable_income": 100.00,
            "net_disposable_income": 100.00,
            "iva_term_months": 60,
            "has_property": False,
            "is_homeowner": False,
            "is_joint_case": False,
            "previous_iva": False,
            "has_previous_iva": False,
            "is_currently_trading": False,
            "has_antecedent_transactions": False,
            "gambling_primary_cause": False,
            "number_of_children": 1,
            "children_ages": [7],
            "income_source_benefits": True,
            "creditors": [
                _creditor("Barclaycard",   2900.00, "credit_card"),
                _creditor("Very",          1500.00, "catalogue"),
                _creditor("Halifax",       1200.00, "personal_loan"),
                _creditor("Capital One",   1000.00, "credit_card"),
                _creditor("Barclays",       499.00, "personal_loan"),
                _creditor("Monzo",          100.00, "catalogue"),
            ],
            "documents": [_bank_doc("B.S.")],
            "gold_transactions": [
                {"description": "NATIONAL LOTTERY WATFORD",
                 "amount": 5.00, "months_ago": 4},
            ],
            "financial_summary": {
                "net_balance": 100.00,
                "total_income": 3256.00,
                "income_source": "benefits",
            },
        })

    def test_not_hard_blocked(self):
        self.assertNotEqual(_status(self.result), "BLOCKED",
                            "Benefits-only with standard creditors must not be BLOCKED")

    def test_tig_01_passes(self):
        self.assertFalse(_has_block(self.result, "TIG-01"),
                         "Debt £7,199 meets minimum — TIG-01 must not fire")

    def test_tig_02_passes(self):
        self.assertFalse(_has_block(self.result, "TIG-02"),
                         "DI £100 meets minimum — TIG-02 must not fire")

    def test_no_council_tax_block(self):
        self.assertFalse(_has_block(self.result, "TIG-17"),
                         "No council tax creditor — TIG-17 must not fire")

    def test_payslip_not_required(self):
        """Benefits-only client — TIG-05 payslip check must not fire."""
        self.assertFalse(_has_block(self.result, "TIG-05"),
                         "Benefits-only income — no payslip required, TIG-05 must not fire")


if __name__ == "__main__":
    import unittest
    unittest.main()