"""
Phase 1 tests: unsecured debt classification, core evidence, Link matching, WATCH-22.12.
"""

from datetime import date

from django.test import SimpleTestCase, TestCase

from debt_app.criteria_engine import (
    NON_OVERRIDABLE_RULE_IDS,
    WATCH_HP_MONTHLY_CAP,
    _parse_case,
    _tig_05,
    _tig_09,
    _watch_22_10,
    _watch_22_12,
    assess_case,
    is_core_evidence_complete,
)
from debt_app.helpers import (
    get_secured_debt_total,
    get_unsecured_debt_total,
    is_asset_link_capital,
    is_link_financial,
)
from debt_app.tests.test_phase3 import _minimal_old_payload
from debt_app.tests.test_phase7 import _phase7_clean_payload


class TestDebtClassification(SimpleTestCase):
    def test_unsecured_excludes_hp_and_mortgage(self):
        creditors = [
            {"balance": 10000, "creditor_type": "credit_card"},
            {"balance": 50000, "creditor_type": "hire purchase"},
            {"balance": 200000, "creditor_type": "mortgage"},
            {"balance": 5000, "creditor_type": "loan"},
        ]
        self.assertEqual(get_unsecured_debt_total(creditors), 15000.0)
        self.assertEqual(get_secured_debt_total(creditors), 250000.0)

    def test_parse_case_prefers_computed_unsecured_over_inflated_crm(self):
        payload = _minimal_old_payload()
        payload["crm_data"]["total_unsecured_debt"] = 999999.0
        payload["creditors"] = [
            {"creditor_name": "Barclays", "balance": 8000.0, "creditor_type": "credit_card"},
            {
                "creditor_name": "Lloyds HP",
                "balance": 100000.0,
                "creditor_type": "mortgage",
            },
        ]
        c = _parse_case(payload)
        self.assertEqual(c["total_debt"], 8000.0)
        self.assertEqual(c["total_secured_debt"], 100000.0)


class TestLinkFinancialMatch(SimpleTestCase):
    def test_substring_match(self):
        self.assertTrue(is_link_financial("Link Financial Outsourcing Limited"))
        self.assertTrue(is_link_financial("LINK FINANCIAL"))
        self.assertTrue(is_link_financial("LINK"))
        self.assertTrue(is_link_financial("Link Financial - IVA"))
        self.assertFalse(is_link_financial("Barclays Bank"))

    def test_asset_link_capital_excluded(self):
        self.assertTrue(is_asset_link_capital("Asset Link Capital"))
        self.assertFalse(is_link_financial("Asset Link Capital"))


class TestWatchHpThreshold(SimpleTestCase):
    def test_watch_cap_matches_excel_400(self):
        self.assertEqual(WATCH_HP_MONTHLY_CAP, 400)

    def test_watch_22_10_flags_above_400_only(self):
        c = {"vehicle_hp_monthly": 401.0}
        r = _watch_22_10(c)
        self.assertTrue(r.triggered)
        self.assertEqual(r.threshold, 400.0)

        c_ok = {"vehicle_hp_monthly": 400.0}
        self.assertFalse(_watch_22_10(c_ok).triggered)


class TestCisVsWageSlip(SimpleTestCase):
    def test_cis_does_not_require_wage_slip(self):
        c = _parse_case({
            "application_id": "CIS-1",
            "financial_summary": {
                "net_balance": 200.0,
                "total_income": 2000.0,
                "income_source": "cis",
            },
            "crm_data": {"total_unsecured_debt": 10000.0},
            "creditors": [{"creditor_name": "X", "balance": 10000.0, "creditor_type": "loan"}],
            "documents": [],
        })
        self.assertEqual(_tig_05(c).rule_id, "TIG-05")
        self.assertFalse(_tig_05(c).triggered)
        self.assertEqual(_tig_09(c).rule_id, "TIG-09")
        self.assertTrue(_tig_09(c).triggered)


class TestCoreEvidence(TestCase):
    def test_salary_employed_requires_wage_slip(self):
        payload = _phase7_clean_payload(
            financial_summary={
                "net_balance": 200.0,
                "total_income": 2000.0,
                "total_expenses": 1800.0,
                "income_source": "salary",
            },
            clientInfo={"employment_status": "employed"},
            documents=[
                {
                    "document_type": "bank_statement",
                    "is_valid": True,
                    "extracted_data": {
                        "statement_date": date.today().isoformat(),
                        "account_holder": "Test Client",
                    },
                },
            ],
        )
        result = assess_case(payload, detected_representatives=set())
        rule_ids = [r.rule_id for r in result["hard_blocks"]]
        self.assertIn("TIG-05", rule_ids)
        self.assertFalse(result["tig_eligible"])

    def test_watch_22_12_without_watch_rep(self):
        payload = _phase7_clean_payload(previous_iva=True)
        c = _parse_case(payload)
        r = _watch_22_12(c)
        self.assertEqual(r.rule_id, "WATCH-22.12")
        self.assertTrue(r.triggered)

        result = assess_case(payload, detected_representatives=set())
        flag_ids = [f.rule_id for f in result["flags"]]
        self.assertIn("WATCH-22.12", flag_ids)

    def test_core_evidence_non_overridable(self):
        self.assertIn("TIG-05", NON_OVERRIDABLE_RULE_IDS)
        self.assertIn("TIG-11", NON_OVERRIDABLE_RULE_IDS)
        self.assertIn("TIG-13", NON_OVERRIDABLE_RULE_IDS)

    def test_override_cannot_clear_tig_11(self):
        payload = _phase7_clean_payload(
            override_code="MANAGER_REVIEW",
            override_reason="test",
            override_by="manager1",
            documents=[],
        )
        payload["financial_summary"]["income_source"] = "benefits"
        result = assess_case(payload, detected_representatives=set())
        self.assertTrue(any(r.rule_id == "TIG-11" for r in result["hard_blocks"]))

    def test_multi_account_bank_statements(self):
        today = date.today().isoformat()
        payload = _phase7_clean_payload(
            financial_summary={
                "net_balance": 200.0,
                "total_income": 2000.0,
                "total_expenses": 1800.0,
                "income_source": "benefits",
                "bank_accounts": [
                    {"account_name": "Current"},
                    {"account_name": "Savings"},
                ],
            },
            documents=[
                {
                    "document_type": "bank_statement",
                    "is_valid": True,
                    "extracted_data": {
                        "statement_date": today,
                        "account_holder": "Test",
                        "account_name": "Current",
                    },
                },
            ],
        )
        c = _parse_case(payload)
        self.assertFalse(is_core_evidence_complete(c))
