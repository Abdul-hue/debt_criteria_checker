"""
Phase 7 tests: ResultAggregator fields, majority/dividend analysis, view serialization.
"""

import json
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from debt_app.criteria_engine import (
    _compute_dividend_analysis,
    _compute_majority_analysis,
    _derive_recommended_solution,
    _parse_case,
    assess_case,
)
from debt_app.models import CreditorCriteria
from debt_app.tests.test_phase3 import _minimal_old_payload
from debt_app.tests.test_phase4 import _phase4_base_payload
from debt_app.views.criteria_views import build_phase7_response_fields

PHASE7_RESPONSE_KEYS = (
    "overall_status",
    "passes_all_hard_blocks",
    "recommended_solution",
    "creditor_positions",
    "council_positions",
    "majority_analysis",
    "dividend_analysis",
)


def _phase7_payload(**overrides):
    payload = _phase4_base_payload()
    payload.setdefault("clientInfo", {})
    payload["clientInfo"]["is_employed"] = False
    payload.update(overrides)
    return payload


def _phase7_clean_payload(**overrides):
    """Minimal payload that clears core evidence (TIG-05 wage slip + TIG-11 bank statement)."""
    payload = _minimal_old_payload()
    stmt_date = (date.today() - timedelta(days=7)).isoformat()
    payload["documents"] = [
        {
            "document_type": "payslip",
            "is_valid": True,
            "extracted_data": {"statement_date": stmt_date},
        },
        {
            "document_type": "bank_statement",
            "is_valid": True,
            "extracted_data": {
                "statement_date": stmt_date,
                "account_holder": "Test Client",
            },
        },
    ]
    payload.update(overrides)
    return payload


class TestOverallStatus(TestCase):
    def test_overall_status_uppercase(self):
        result = assess_case(_phase7_payload(), detected_representatives=set())
        self.assertEqual(result["overall_status"], result["overall"].upper())


class TestPassesAllHardBlocks(TestCase):
    def test_true_when_no_hard_blocks(self):
        result = assess_case(_phase7_clean_payload(), detected_representatives=set())
        self.assertTrue(result["passes_all_hard_blocks"])

    def test_false_when_hard_block(self):
        payload = _phase7_payload(
            creditors=[
                {
                    "creditor_name": "Volkswagen Financial Services",
                    "balance": 10000.0,
                    "creditor_type": "hire purchase",
                },
                {
                    "creditor_name": "Barclays",
                    "balance": 8000.0,
                    "creditor_type": "loan",
                },
            ],
        )
        result = assess_case(payload, detected_representatives=set())
        self.assertFalse(result["passes_all_hard_blocks"])


class TestRecommendedSolution(TestCase):
    def test_iva_not_viable_when_hard_blocks(self):
        payload = _phase7_payload(
            creditors=[
                {
                    "creditor_name": "Volkswagen Financial Services",
                    "balance": 10000.0,
                    "creditor_type": "hire purchase",
                },
                {
                    "creditor_name": "Barclays",
                    "balance": 8000.0,
                    "creditor_type": "loan",
                },
            ],
        )
        result = assess_case(payload, detected_representatives=set())
        self.assertEqual(result["recommended_solution"], "IVA_NOT_VIABLE")

    def test_iva_viable_when_no_blocks_or_flags(self):
        solution = _derive_recommended_solution([], [], [])
        self.assertEqual(solution, "IVA_VIABLE")

    def test_iva_with_conditions_when_flags_only(self):
        # £300 gambling spend → TIG-11-GAMBLING flag (>£200, <£1,000 hard-block threshold)
        payload = _phase7_clean_payload()
        payload["gold_transactions"] = [
            {"description": "bet365 deposit", "amount": 300, "transaction_type": "money_out"},
        ]
        result = assess_case(payload, detected_representatives=set())
        self.assertGreater(len(result["flags"]), 0)
        self.assertEqual(len(result["hard_blocks"]), 0)
        self.assertEqual(result["recommended_solution"], "IVA_WITH_CONDITIONS")

    def test_review_required_when_do_not_vote_creditor(self):
        solution = _derive_recommended_solution(
            [],
            [],
            [{"effective_status": "DO_NOT_VOTE"}],
        )
        self.assertEqual(solution, "REVIEW_REQUIRED")


class TestMajorityAnalysis(TestCase):
    def test_achievable_when_voting_debt_at_least_75_percent(self):
        case = {
            "creditors": [
                {"name": "Voter A", "crm_balance": Decimal("8000")},
                {"name": "Voter B", "crm_balance": Decimal("8000")},
            ],
        }
        positions = [
            {"creditor_name": "Voter A", "effective_status": "ACCEPT"},
            {"creditor_name": "Voter B", "effective_status": "ACCEPT"},
        ]
        analysis = _compute_majority_analysis(case, positions)
        self.assertTrue(analysis["achievable"])
        self.assertEqual(analysis["shortfall"], Decimal("0"))

    def test_not_achievable_when_voting_debt_below_75_percent(self):
        case = {
            "creditors": [
                {"name": "Voter A", "crm_balance": Decimal("5000")},
                {"name": "Blocker", "crm_balance": Decimal("5000")},
            ],
        }
        positions = [
            {"creditor_name": "Voter A", "effective_status": "ACCEPT"},
            {"creditor_name": "Blocker", "effective_status": "REJECT"},
        ]
        analysis = _compute_majority_analysis(case, positions)
        self.assertFalse(analysis["achievable"])
        self.assertEqual(analysis["shortfall"], Decimal("2500"))


class TestDividendAnalysis(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.fce = CreditorCriteria.objects.filter(
            creditor_name__icontains="FCE",
            min_dividend_pence__isnull=False,
        ).first()

    def test_estimated_pence_calculation(self):
        case = {
            "monthly_di": Decimal("100"),
            "iva_term_months": 60,
            "creditors": [{"name": "Barclays", "crm_balance": Decimal("10000")}],
        }
        analysis = _compute_dividend_analysis(case, [])
        self.assertEqual(analysis["estimated_pence"], 60)

    def test_below_min_populated_when_creditor_min_not_met(self):
        self.assertIsNotNone(self.fce)
        case = {
            "monthly_di": Decimal("100"),
            "iva_term_months": 60,
            "creditors": [
                {"name": self.fce.creditor_name, "crm_balance": Decimal("10000")},
            ],
        }
        analysis = _compute_dividend_analysis(case, [])
        self.assertGreater(len(analysis["below_min"]), 0)
        self.assertGreater(analysis["min_required_pence"], analysis["estimated_pence"])

    def test_below_min_empty_when_all_mins_met(self):
        self.assertIsNotNone(self.fce)
        case = {
            "monthly_di": Decimal("200"),
            "iva_term_months": 60,
            "creditors": [
                {"name": self.fce.creditor_name, "crm_balance": Decimal("10000")},
            ],
        }
        analysis = _compute_dividend_analysis(case, [])
        self.assertEqual(analysis["below_min"], [])


class TestIvaTermMonths(TestCase):
    def test_defaults_to_60_when_not_in_payload(self):
        parsed = _parse_case(_phase4_base_payload())
        self.assertEqual(parsed["iva_term_months"], 60)


class TestCreditorPositionShape(TestCase):
    def test_normalized_position_keys(self):
        payload = _phase7_payload(
            creditors=[
                {
                    "creditor_name": "Barclays",
                    "balance": 8000.0,
                    "creditor_type": "loan",
                    "first_payment_made": True,
                },
                {
                    "creditor_name": "Lloyds Bank",
                    "balance": 10000.0,
                    "creditor_type": "loan",
                    "first_payment_made": True,
                },
            ],
        )
        result = assess_case(payload, detected_representatives=set())
        for pos in result["creditor_positions"]:
            for key in ("creditor_name", "effective_status", "reason", "rule_ids", "balance"):
                self.assertIn(key, pos)
            self.assertIsInstance(pos["rule_ids"], list)
            self.assertIsInstance(pos["balance"], Decimal)


class TestAssessCasePhase7Keys(TestCase):
    def test_return_dict_includes_phase7_keys(self):
        result = assess_case(_minimal_old_payload(), detected_representatives=set())
        for key in PHASE7_RESPONSE_KEYS:
            self.assertIn(key, result)


class TestPhase7ViewSerialization(TestCase):
    @patch("debt_app.views.criteria_views.fetch_case_by_reference")
    def test_view_includes_phase7_keys_and_serializes_decimals(self, mock_fetch):
        mock_case = MagicMock()
        mock_case.to_dict.return_value = _phase7_clean_payload()
        mock_case.client_name = "Test Client"
        mock_case.aryza_reference = "REF-PHASE7"
        mock_case.dob = "1980-01-01"
        mock_case.creditors = []
        mock_case.income = {"total": 0}
        mock_case.expenditure = {}
        mock_case.property = {}
        mock_case.vehicle = {}
        mock_case.flags = {}
        mock_case.dependants = 0
        mock_case.employment_status = "employed"
        mock_case.disposable_income = 10000
        
        mock_fetch.return_value = mock_case
        user = get_user_model().objects.create_user(
            username="phase7user",
            email="phase7@example.com",
            password="testpass123",
        )
        client = APIClient()
        client.force_authenticate(user=user)
        response = client.post(
            "/api/v1/criteria/assess/",
            {"aryza_reference": "REF-PHASE7"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        data = response.data
        for key in PHASE7_RESPONSE_KEYS:
            self.assertIn(key, data)
        serializable = build_phase7_response_fields(
            assess_case(_phase7_clean_payload(), detected_representatives=set())
        )
        json.dumps(serializable)
