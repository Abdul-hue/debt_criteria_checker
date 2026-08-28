from decimal import Decimal
from django.test import TestCase
from debt_app.criteria_engine import _check_creditor_individual, assess_case
from debt_app.models import CreditorCriteria

class DividendCheckVisibilityTests(TestCase):
    """
    Tests for adding dividend check result visibility for every creditor that has min_dividend_pence set.
    """

    def setUp(self):
        # Clean up any existing criteria to avoid database contamination
        CreditorCriteria.objects.all().delete()
        
        # Create test CreditorCriteria
        self.creditor_pass = CreditorCriteria.objects.create(
            creditor_name="Pass Lender",
            is_active=True,
            min_dividend_pence=10,
        )
        self.creditor_fail = CreditorCriteria.objects.create(
            creditor_name="Fail Lender",
            is_active=True,
            min_dividend_pence=30,
        )
        self.creditor_none = CreditorCriteria.objects.create(
            creditor_name="No Min Lender",
            is_active=True,
            min_dividend_pence=None,
        )
        self.creditor_zero = CreditorCriteria.objects.create(
            creditor_name="Zero Min Lender",
            is_active=True,
            min_dividend_pence=0,
        )

    def test_dividend_check_pass_fail_injection(self):
        # Case setup: total debt £10,000, monthly di £41.67, term 60 months
        # estimated_pence = 12
        case = {
            "creditors": [
                {
                    "name": "Pass Lender",
                    "original_name": "Pass Lender",
                    "debt_type_normalised": "personal_loan",
                    "crm_balance": Decimal("5000.0"),
                    "balance": 5000.0,
                },
                {
                    "name": "Fail Lender",
                    "original_name": "Fail Lender",
                    "debt_type_normalised": "personal_loan",
                    "crm_balance": Decimal("5000.0"),
                    "balance": 5000.0,
                },
                {
                    "name": "No Min Lender",
                    "original_name": "No Min Lender",
                    "debt_type_normalised": "personal_loan",
                    "crm_balance": Decimal("5000.0"),
                    "balance": 5000.0,
                },
                {
                    "name": "Zero Min Lender",
                    "original_name": "Zero Min Lender",
                    "debt_type_normalised": "personal_loan",
                    "crm_balance": Decimal("5000.0"),
                    "balance": 5000.0,
                }
            ],
            "monthly_di": Decimal("41.67"),
            "iva_term_months": 60,
            "total_debt": Decimal("20000.0"),
            "aryza_reference": "TEST-123",
            "client_name": "Test Client",
            "has_property": False,
            "previous_iva": False,
        }

        # Call _check_creditor_individual directly
        positions = _check_creditor_individual(case)
        
        pos_pass = next(p for p in positions if p["creditor_name"] == "Pass Lender")
        pos_fail = next(p for p in positions if p["creditor_name"] == "Fail Lender")
        pos_none = next(p for p in positions if p["creditor_name"] == "No Min Lender")
        pos_zero = next(p for p in positions if p["creditor_name"] == "Zero Min Lender")

        # 1. Pass Lender: estimated_pence (12) >= min_dividend_pence (10) -> Pass
        # fund = 41.67 * 60 = 2500.2
        # 2500.2 / 20000 = 0.12501 -> estimated_pence = 12
        # Min dividend met: 12p/£ >= 10p/£
        pass_findings = [f for f in pos_pass["findings"] if f["code"] == "DIVIDEND-CHECK-PASS"]
        self.assertEqual(len(pass_findings), 1)
        self.assertEqual(pass_findings[0]["severity"], "pass")
        self.assertEqual(pass_findings[0]["reason"], "Minimum dividend met: 12p/£ ≥ 10p/£")

        # 2. Fail Lender: estimated_pence (12) < min_dividend_pence (30) -> Fail
        # Minimum dividend NOT met: 12p/£ < 30p/£
        fail_findings = [f for f in pos_fail["findings"] if f["code"] == "DIVIDEND-CHECK-FAIL"]
        self.assertEqual(len(fail_findings), 1)
        self.assertEqual(fail_findings[0]["severity"], "flag")
        self.assertEqual(fail_findings[0]["reason"], "Minimum dividend NOT met: 12p/£ < 30p/£")

        # 3. No Min Lender: has no min_dividend_pence (None) -> No finding injected
        none_pass_findings = [f for f in pos_none["findings"] if f["code"] in ("DIVIDEND-CHECK-PASS", "DIVIDEND-CHECK-FAIL")]
        self.assertEqual(len(none_pass_findings), 0)

        # 4. Zero Min Lender: has min_dividend_pence = 0 -> No finding injected
        zero_pass_findings = [f for f in pos_zero["findings"] if f["code"] in ("DIVIDEND-CHECK-PASS", "DIVIDEND-CHECK-FAIL")]
        self.assertEqual(len(zero_pass_findings), 0)
