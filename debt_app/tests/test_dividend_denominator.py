"""
Item #13 — dividend denominator: secured debt types must be excluded.

_compute_dividend_analysis previously summed ALL creditor crm_balance
values into the denominator, including mortgages and HP.  This inflates
the denominator and underestimates the dividend pence-per-pound.

The engine's _parse_case already excludes secured types from total_debt
using helpers._SECURED_TYPES = {"hire_purchase", "mortgage"}.
_compute_dividend_analysis must use the same filter.

DISCREPANCY FLAG (raised per spec):
  _parse_case uses helpers._SECURED_TYPES = {"hire_purchase", "mortgage"}
  _prepare_engine_payload uses a wider raw set:
      {"mortgage", "hire_purchase", "hp", "secured_loan", "secured",
       "charge", "second_charge", "secured loan"}
  _compute_dividend_analysis receives creditors that have already been
  through _parse_case (debt_type_normalised is already normalised, so
  "hp" becomes "hire_purchase"). The canonical post-normalisation set
  to use here is helpers._SECURED_TYPES (2 types), NOT the raw-string
  set in _prepare_engine_payload.
"""

from decimal import Decimal

from django.test import TestCase

from debt_app.engine.criteria import _compute_dividend_analysis


def _creditor(name, balance, debt_type_normalised="personal_loan"):
    return {
        "name": name,
        "creditor_name": name,
        "original_name": name,
        "crm_balance": Decimal(str(balance)),
        "balance": balance,
        "debt_type_normalised": debt_type_normalised,
    }


def _case(creditors, monthly_di=200.0, iva_term_months=60):
    return {
        "creditors": creditors,
        "monthly_di": monthly_di,
        "iva_term_months": iva_term_months,
    }


class DividendDenominatorSecuredExclusionTests(TestCase):
    """
    The dividend denominator must exclude secured (mortgage, HP) creditors.
    Without the fix the mortgage balance inflates the denominator and the
    estimated pence-per-pound is too low.
    """

    def test_mortgage_excluded_from_denominator(self):
        # Unsecured total = £10,000; mortgage = £150,000 (must be excluded).
        # monthly_di=200, term=60 months → fund = £12,000.
        # Correct: 12000 / 10000 * 100 = 120p
        # Bug (pre-fix): 12000 / 160000 * 100 = 7p
        creditors = [
            _creditor("Unsecured Lender", 10000.0, "personal_loan"),
            _creditor("Nationwide", 150000.0, "mortgage"),
        ]
        result = _compute_dividend_analysis(_case(creditors, monthly_di=200.0), [])
        self.assertGreaterEqual(
            result["estimated_pence"], 100,
            "Mortgage must not inflate the denominator — dividend should be >=100p here",
        )

    def test_hire_purchase_excluded_from_denominator(self):
        # Unsecured total = £5,000; HP = £20,000 (must be excluded).
        # monthly_di=100, term=60 → fund = £6,000.
        # Correct: 6000 / 5000 * 100 = 120p
        # Bug: 6000 / 25000 * 100 = 24p
        creditors = [
            _creditor("Unsecured Lender", 5000.0, "personal_loan"),
            _creditor("Black Horse", 20000.0, "hire_purchase"),
        ]
        result = _compute_dividend_analysis(_case(creditors, monthly_di=100.0), [])
        self.assertGreaterEqual(
            result["estimated_pence"], 100,
            "HP must not inflate the denominator — dividend should be >=100p here",
        )

    def test_unsecured_only_denominator_unchanged(self):
        # No secured debt — denominator = sum of all unsecured.
        # monthly_di=100, term=60, unsecured=12000 → 6000/12000*100 = 50p
        creditors = [
            _creditor("Lender A", 7000.0, "personal_loan"),
            _creditor("Lender B", 5000.0, "credit_card"),
        ]
        result = _compute_dividend_analysis(_case(creditors, monthly_di=100.0), [])
        self.assertEqual(result["estimated_pence"], 50)

    def test_no_secured_debt_passes_unchanged(self):
        creditors = [_creditor("Only Lender", 10000.0, "personal_loan")]
        result = _compute_dividend_analysis(_case(creditors, monthly_di=100.0), [])
        self.assertEqual(result["estimated_pence"], 60)

    def test_all_secured_no_div_by_zero(self):
        # Edge: only secured debt — total_unsecured=0 → estimated_pence=0 (no division).
        creditors = [
            _creditor("Bank Mortgage", 200000.0, "mortgage"),
        ]
        result = _compute_dividend_analysis(_case(creditors, monthly_di=200.0), [])
        self.assertEqual(result["estimated_pence"], 0)
