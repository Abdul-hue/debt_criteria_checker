"""
Hire purchase, mortgage and secured loan on a Valid8 report (2026-11-24).

Case 438519: three First Response Finance accounts the report prints as
"Account Type: Hire Purchase/Conditional Sale" reached CAT as "OT" (Other).
`_VALID8_CATEGORY_TO_TYPE` listed none of the three secured / vehicle
wordings, and Valid8 prints the HP one with NO spaces round the slash, which
the Experian map's "hire purchase / conditional sale" never matched.

Pinned here:
  * HP and MG wordings map exactly as on the Experian map;
  * MG goes to `mortgage_accounts`, never IVA debt; HP stays debt;
  * nothing near them moves: "Unsecured Loan ..." is never secured, and
    "Second Mortgage", "Mortgage Protection" stay "OT" on BOTH Experian
    routes (open business decision D1). "Balloon HP" is HP on both since
    2026-11-24 (user, case 432916 -- `test_balloon_hp.py`).
"""
from django.test import SimpleTestCase

from debt_app.integrations.credit_report import (
    DEBT_TYPE_CODES,
    _EXPERIAN_CATEGORY_TO_TYPE,
    _VALID8_CATEGORY_TO_TYPE,
    _parse_valid8_account,
)


def _valid8(account_type, status="Active", balance="Balance: £593.00"):
    return "\n".join([status, "Company: FIRST RESPONSE FINANCE LTD", f"Account Type: {account_type}",
                      balance, "Start Date: 31/01/2020"])


def _code(account_type, **kw):
    return _parse_valid8_account("1 High Street", _valid8(account_type, **kw))["type_code"]


class HirePurchaseTests(SimpleTestCase):

    def test_the_438519_wording_is_hire_purchase(self):
        self.assertEqual(_code("Hire Purchase/Conditional Sale"), "HP")

    def test_every_hire_purchase_wording(self):
        for wording in ("Hire Purchase/Conditional Sale", "Hire Purchase / Conditional Sale",
                        "HIRE PURCHASE/CONDITIONAL SALE", "Hire Purchase", "Conditional Sale"):
            self.assertEqual(_code(wording), "HP", wording)

    def test_hire_purchase_is_still_debt(self):
        parsed = _parse_valid8_account("1 High Street", _valid8("Hire Purchase/Conditional Sale"))
        self.assertIn("HP", DEBT_TYPE_CODES)
        self.assertFalse(parsed["reconciliation_only"])
        self.assertEqual(parsed["current_balance"], 59300)
        self.assertFalse(parsed["type_unmapped"])

    def test_a_settled_hire_purchase_is_hire_purchase_at_nil(self):
        parsed = _parse_valid8_account(
            "1 High Street", _valid8("Hire Purchase/Conditional Sale", status="Settled",
                                     balance="Balance: Settled"))
        self.assertEqual((parsed["type_code"], parsed["current_balance"]), ("HP", 0))


class MortgageAndSecuredLoanTests(SimpleTestCase):

    def test_mortgage_and_secured_loan_are_mg(self):
        for wording in ("Mortgage", "Mortgages", "Secured Loan", "Secured Loans"):
            self.assertEqual(_code(wording), "MG", wording)


class NothingNearbyMovesTests(SimpleTestCase):

    def test_unsecured_loans_are_never_secured(self):
        self.assertEqual(_code("Unsecured Loan (personal loans etc)"), "UL")
        for wording in ("Unsecured Loan", "Unsecured Loans", "Unsecured Loan (Personal Loan)"):
            self.assertNotEqual(_code(wording), "MG", wording)

    def test_the_d1_variants_stay_other_as_on_the_experian_map(self):
        for wording in ("Second Mortgage", "Residential Mortgage", "Buy To Let Mortgage",
                        "Flexible Mortgages", "Mortgage Protection", "Mortgage and Unsecured Loan",
                        "Credit Sale Fixed Term", "BNPL/Deferred Payment"):
            self.assertEqual(_code(wording), "OT", wording)
            self.assertNotIn(wording.lower(), _EXPERIAN_CATEGORY_TO_TYPE, wording)

    def test_the_valid8_codes_agree_with_the_experian_map(self):
        for wording in ("hire purchase / conditional sale", "hire purchase", "conditional sale",
                        "mortgage", "mortgages", "secured loan", "secured loans"):
            self.assertEqual(_VALID8_CATEGORY_TO_TYPE[wording], _EXPERIAN_CATEGORY_TO_TYPE[wording], wording)

    def test_car_insurance_is_still_reconciliation_only(self):
        parsed = _parse_valid8_account("1 High Street", _valid8("Car Insurance"))
        self.assertEqual(parsed["type_code"], "MI")
        self.assertTrue(parsed["reconciliation_only"])
