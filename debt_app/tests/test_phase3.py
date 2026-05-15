"""
Phase 3 data-layer tests: helpers, _parse_case backward compatibility, Voter property.
"""

from datetime import date, timedelta

from django.test import SimpleTestCase, TestCase

from debt_app.criteria_engine import _parse_case
from debt_app.helpers import (
    DEBT_TYPE_CATALOGUE,
    DEBT_TYPE_COUNCIL_TAX,
    DEBT_TYPE_CREDIT_CARD,
    DEBT_TYPE_HP,
    DEBT_TYPE_HOUSING_BENEFIT,
    DEBT_TYPE_MOBILE,
    DEBT_TYPE_MORTGAGE,
    DEBT_TYPE_OVERDRAFT,
    DEBT_TYPE_PCN,
    DEBT_TYPE_PERSONAL_LOAN,
    DEBT_TYPE_RENT,
    DEBT_TYPE_STORE_CARD,
    DEBT_TYPE_UNKNOWN,
    DEBT_TYPE_UTILITY,
    is_vw_finance,
    normalise_debt_type,
)
from debt_app.models import Voter


def _minimal_old_payload():
    """CASE_ASSESSMENT_PAYLOAD.md minimal valid payload (no Phase 3 keys)."""
    return {
        "application_id": "TEST-001",
        "case_type": "IVA",
        "proposed_dividend_pence": 30,
        "financial_summary": {
            "net_balance": 200.00,
            "total_income": 2500.00,
            "total_expenses": 2300.00,
            "income_source": "salary",
        },
        "crm_data": {
            "total_unsecured_debt": 18000.00,
            "gambling_main_cause": False,
        },
        "creditors": [
            {
                "creditor_name": "Lloyds Bank",
                "balance": 10000.00,
                "creditor_type": "loan",
                "linked_creditor": "EVID-001",
                "covers_months": 3,
                "has_ccj": False,
            },
            {
                "creditor_name": "Barclays",
                "balance": 8000.00,
                "creditor_type": "credit_card",
                "linked_creditor": "EVID-002",
                "covers_months": 3,
                "has_ccj": False,
            },
        ],
        "evidence_ledger": [
            {"ref": "EVID-001", "doc_type": "creditor_statement"},
            {"ref": "EVID-002", "doc_type": "creditor_statement"},
        ],
        "documents": [],
        "gold_transactions": [],
        "mortgage_details": [],
    }


def _full_phase3_payload():
    payload = _minimal_old_payload()
    payload["clientInfo"] = {
        "dateOfBirth": "1980-01-01",
        "is_currently_in_dmp": True,
        "is_royal_mail_employee": True,
        "is_police_officer": False,
        "previous_iva_failed": True,
    }
    payload["creditors"] = [
        {
            "creditor_name": "Moneybarn",
            "balance": 8500.00,
            "creditor_type": "hire purchase",
            "is_joint": True,
            "last_payment_date": "2024-08-01",
            "first_payment_made": True,
            "vehicle_arrears_months": 2,
            "ie_matches_loan_application": False,
            "arrangement_confirmed_before_proposing": True,
            "client_still_has_asset_in_possession": True,
            "is_grant_overpayment": True,
            "guarantee_called_up": True,
            "linked_creditor": "EVID-001",
            "covers_months": 3,
            "has_ccj": False,
        },
    ]
    return payload


class TestNormaliseDebtType(SimpleTestCase):
    def test_canonical_mappings(self):
        cases = [
            ("Council Tax Arrears", DEBT_TYPE_COUNCIL_TAX),
            ("CTAX bill", DEBT_TYPE_COUNCIL_TAX),
            ("Hire Purchase", DEBT_TYPE_HP),
            ("vehicle finance", DEBT_TYPE_HP),
            ("Personal Loan", DEBT_TYPE_PERSONAL_LOAN),
            ("unsecured loan", DEBT_TYPE_PERSONAL_LOAN),
            ("Gas utility", DEBT_TYPE_UTILITY),
            ("Store Card", DEBT_TYPE_STORE_CARD),
            ("credit card", DEBT_TYPE_CREDIT_CARD),
            ("PCN fine", DEBT_TYPE_PCN),
            ("housing benefit overpayment", DEBT_TYPE_HOUSING_BENEFIT),
            ("overdraft", DEBT_TYPE_OVERDRAFT),
            ("catalogue debt", DEBT_TYPE_CATALOGUE),
            ("mortgage", DEBT_TYPE_MORTGAGE),
            ("rent arrears", DEBT_TYPE_RENT),
            ("mobile phone", DEBT_TYPE_MOBILE),
        ]
        for raw, expected in cases:
            with self.subTest(raw=raw):
                self.assertEqual(normalise_debt_type(raw), expected)

    def test_unknown(self):
        self.assertEqual(normalise_debt_type("crypto asset"), DEBT_TYPE_UNKNOWN)
        self.assertEqual(normalise_debt_type(""), DEBT_TYPE_UNKNOWN)


class TestIsVwFinance(SimpleTestCase):
    def test_positive(self):
        self.assertTrue(is_vw_finance("Volkswagen Financial Services"))
        self.assertTrue(is_vw_finance("my VWFS account"))

    def test_negative(self):
        self.assertFalse(is_vw_finance("Barclays Bank"))
        self.assertFalse(is_vw_finance(""))
        self.assertFalse(is_vw_finance(None))


class TestParseCasePhase3(SimpleTestCase):
    def test_old_payload_safe_defaults(self):
        c = _parse_case(_minimal_old_payload())
        self.assertFalse(c["has_partner_on_case"])
        self.assertFalse(c["is_currently_in_dmp"])
        self.assertFalse(c["is_royal_mail_employee"])
        self.assertFalse(c["is_police_officer"])
        self.assertFalse(c["previous_iva_failed"])

        for creditor in c["creditors"]:
            self.assertFalse(creditor["is_joint"])
            self.assertIsNone(creditor["last_payment_date"])
            self.assertFalse(creditor["first_payment_made"])
            self.assertIsNone(creditor["vehicle_arrears_months"])
            self.assertIsNone(creditor["ie_matches_loan_application"])
            self.assertFalse(creditor["arrangement_confirmed_before_proposing"])
            self.assertFalse(creditor["client_still_has_asset_in_possession"])
            self.assertFalse(creditor["is_grant_overpayment"])
            self.assertIsNone(creditor["guarantee_called_up"])
            self.assertIsNone(creditor["months_since_last_payment"])
            self.assertIn("debt_type_normalised", creditor)

    def test_has_partner_on_case_from_client_block(self):
        payload = _minimal_old_payload()
        payload["client"] = {"has_partner_on_case": True}
        c = _parse_case(payload)
        self.assertTrue(c["has_partner_on_case"])

    def test_new_payload_reads_fields(self):
        c = _parse_case(_full_phase3_payload())
        self.assertFalse(c["has_partner_on_case"])
        self.assertTrue(c["is_currently_in_dmp"])
        self.assertTrue(c["is_royal_mail_employee"])
        self.assertFalse(c["is_police_officer"])
        self.assertTrue(c["previous_iva_failed"])

        debtor = c["creditors"][0]
        self.assertTrue(debtor["is_joint"])
        self.assertEqual(debtor["last_payment_date"], "2024-08-01")
        self.assertTrue(debtor["first_payment_made"])
        self.assertEqual(debtor["vehicle_arrears_months"], 2)
        self.assertFalse(debtor["ie_matches_loan_application"])
        self.assertTrue(debtor["arrangement_confirmed_before_proposing"])
        self.assertTrue(debtor["client_still_has_asset_in_possession"])
        self.assertTrue(debtor["is_grant_overpayment"])
        self.assertTrue(debtor["guarantee_called_up"])
        self.assertEqual(debtor["debt_type_normalised"], DEBT_TYPE_HP)
        self.assertIsNotNone(debtor["months_since_last_payment"])


class TestMonthsSinceLastPayment(TestCase):
    def test_with_date(self):
        three_months_ago = date.today().replace(day=1) - timedelta(days=95)
        voter = Voter(
            name="Test",
            last_payment_date=three_months_ago,
        )
        self.assertIsNotNone(voter.months_since_last_payment)
        self.assertGreaterEqual(voter.months_since_last_payment, 2)

    def test_without_date(self):
        voter = Voter(name="Test")
        self.assertIsNone(voter.months_since_last_payment)

    def test_future_date(self):
        future = date.today() + timedelta(days=30)
        voter = Voter(name="Test", last_payment_date=future)
        self.assertIsNone(voter.months_since_last_payment)
