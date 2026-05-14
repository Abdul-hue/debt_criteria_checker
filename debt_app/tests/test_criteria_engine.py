"""
Tests for criteria_engine.py

Comprehensive unit tests for the IVA criteria assessment engine.
All tests use pytest and mock data to ensure full testability.
"""

import copy
import pytest
from datetime import datetime, timedelta
from debt_app.criteria_engine import (
    assess_case,
    _matches_creditor,
    _detect_watch_creditor,
    _find_majority_creditor,
    _calculate_estimated_dividend,
    _rule_watch_equity_exceeds_debt,
)


# ============================================================================
# TEST FACTORIES
# ============================================================================

def make_case(**overrides):
    """Factory for minimal valid case data."""
    base = {
        "reference": "TIG-TEST-001",
        "client_name": "Test Client",
        "client_age": 45,
        "employment_status": "employed",
        "income": {
            "employed_monthly":         210000,
            "self_employed_monthly":    0,
            "universal_credit":         0,
            "dla":                      0,
            "pip":                      0,
            "esa":                      0,
            "other_benefits":           0,
            "third_party_contribution": 0,
            "total":                    210000,
        },
        "expenditure": {
            "disability_expenses": 0,
            "total":               0,
        },
        "disposable_income":    210000,
        "total_unsecured_debt": 2500000,
        "creditors": [
            {
                "name":                 "Barclaycard",
                "balance":              1500000,
                "monthly_payment":      10000,
                "account_open_date":    "2020-01-01",
                "last_transaction_date":"2020-01-01",
                "debt_type":            None,
                "is_hmrc":              False,
                "is_council":           False,
                "is_watch":             True,
                "is_tix":               False,
            },
            {
                "name":                 "Capital One",
                "balance":              1000000,
                "monthly_payment":      5000,
                "account_open_date":    "2020-01-01",
                "last_transaction_date":"2020-01-01",
                "debt_type":            None,
                "is_hmrc":              False,
                "is_council":           False,
                "is_watch":             False,
                "is_tix":               True,
            },
        ],
        "property": {
            "owns_property":    False,
            "property_value":   0,
            "mortgage_balance": 0,
            "equity":           0,
        },
        "vehicle": {
            "has_vehicle":            False,
            "vehicle_value":          0,
            "hp_monthly_payment":     0,
            "car_finance_start_date": None,
        },
        "flags": {
            "previous_iva":               False,
            "previous_iva_failed_reason": None,
            "antecedent_transactions":    False,
            "vulnerability_claimed":      False,
            "gambling_main_cause":        False,
            "unexplained_transactions":   False,
        },
        "gambling": {
            "monthly_total": 0,
            "has_gambling":  False,
        },
        "bank_statements": [
            {
                "account_name":   "Main Account",
                "statement_date": None,
                "months_held":    0,
            }
        ],
        "dependants": [],
        "previous_arrangements": [],
    }
    # Deep merge overrides so nested dicts don't replace entire sub-dicts
    merged = copy.deepcopy(base)
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key].update(value)
        else:
            merged[key] = value
    return merged


def make_clean_case(**overrides) -> tuple:
    """
    Returns a case where every rule passes out of the box.
    Use this for recommendation logic tests only.

    All documents are present and dated today.
    All creditors have proof of debt.
    Bank statements are dated today.
    Disposable income and debt are sized so no WATCH rule fires.

    Overrides specific fields to test recommendation logic only.
    """
    from datetime import date
    today = date.today().isoformat()

    base = make_case(
        # High debt, reasonable DI — debt/DI > 72 months so WATCH-01 won't fire
        total_unsecured_debt=2500000,   # £25,000
        disposable_income=50000,        # £500/month → 50 months < 72, but let's see
        creditors=[
            {
                "name":                  "Barclaycard",
                "balance":               1500000,
                "monthly_payment":       10000,
                "account_open_date":     "2020-01-01",
                "last_transaction_date": "2020-01-01",
                "debt_type":             None,
                "is_hmrc":               False,
                "is_council":            False,
                "is_watch":              True,
                "is_tix":                False,
            },
            {
                "name":                  "Capital One",
                "balance":               1000000,
                "monthly_payment":       5000,
                "account_open_date":     "2020-01-01",
                "last_transaction_date": "2020-01-01",
                "debt_type":             None,
                "is_hmrc":               False,
                "is_council":            False,
                "is_watch":              False,
                "is_tix":                True,
            },
        ],
        bank_statements=[
            {
                "account_name":   "Main Account",
                "statement_date": today,   # dated today — passes 90-day check
                "months_held":    3,
            }
        ],
        income={
            "employed_monthly":         20000,
            "self_employed_monthly":    0,
            "universal_credit":         0,
            "dla":                      0,
            "pip":                      0,
            "esa":                      0,
            "other_benefits":           0,
            "third_party_contribution": 0,
            "total":                    20000,
        },
        expenditure={"disability_expenses": 0, "total": 0},
        employment_status="employed",
        gambling={"monthly_total": 0, "has_gambling": False},
    )

    # Clean docs — everything present, all proofs provided
    docs = make_docs(
        wage_slips=[{"date": today}],      # recent wage slip
        benefit_letter=False,              # no benefits so not needed
        proof_of_debt={
            "barclaycard": True,
            "capital one":  True,
        },
        termination_report=False,          # no previous IVA
    )

    # Apply caller overrides to case
    result = copy.deepcopy(base)
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key].update(value)
        else:
            result[key] = value

    return result, docs


def make_rules(**overrides):
    """Factory for minimal valid rules config."""
    rules = {
        "min_debt": {
            "rule_key": "min_debt",
            "rule_name": "Minimum Debt Threshold",
            "criteria_set": "TIG",
            "severity": "hard_block",
            "is_active": True,
            "threshold_value": 600000,  # £6,000
        },
        "min_di": {
            "rule_key": "min_di",
            "rule_name": "Minimum Disposable Income",
            "criteria_set": "TIG",
            "severity": "hard_block",
            "is_active": True,
            "threshold_value": 10000,  # £100
        },
        "dla_pip_offset": {
            "rule_key": "dla_pip_offset",
            "rule_name": "DLA/PIP Offset",
            "criteria_set": "TIG",
            "severity": "hard_block",
            "is_active": True,
            "threshold_value": 0,
        },
        "wage_slip_check": {
            "rule_key": "wage_slip_check",
            "rule_name": "Wage Slip Check",
            "criteria_set": "TIG",
            "severity": "hard_block",
            "is_active": True,
            "threshold_value": 90,
        },
        "benefit_proof_check": {
            "rule_key": "benefit_proof_check",
            "rule_name": "Benefit Proof Check",
            "criteria_set": "TIG",
            "severity": "hard_block",
            "is_active": True,
            "threshold_value": 0,
        },
        "uc_journal_check": {
            "rule_key": "uc_journal_check",
            "rule_name": "UC Journal Check",
            "criteria_set": "TIG",
            "severity": "hard_block",
            "is_active": True,
            "threshold_value": 0,
        },
        "self_employed_proof": {
            "rule_key": "self_employed_proof",
            "rule_name": "Self-Employed Proof",
            "criteria_set": "TIG",
            "severity": "hard_block",
            "is_active": True,
            "threshold_value": 0,
        },
        "cis_proof": {
            "rule_key": "cis_proof",
            "rule_name": "CIS Proof",
            "criteria_set": "TIG",
            "severity": "hard_block",
            "is_active": True,
            "threshold_value": 0,
        },
        "bank_statement_check": {
            "rule_key": "bank_statement_check",
            "rule_name": "Bank Statement Check",
            "criteria_set": "TIG",
            "severity": "hard_block",
            "is_active": True,
            "threshold_value": 90,
        },
        "gambling_hard_block": {
            "rule_key": "gambling_hard_block",
            "rule_name": "Gambling Hard Block",
            "criteria_set": "TIG",
            "severity": "hard_block",
            "is_active": True,
            "threshold_value": 50000,  # £500
        },
        "gambling_flag": {
            "rule_key": "gambling_flag",
            "rule_name": "Gambling Flag",
            "criteria_set": "TIG",
            "severity": "flag",
            "is_active": True,
            "threshold_value": 10000,  # £100
        },
        "proof_of_debt": {
            "rule_key": "proof_of_debt",
            "rule_name": "Proof of Debt",
            "criteria_set": "TIG",
            "severity": "hard_block",
            "is_active": True,
            "threshold_value": 100000,  # £1,000
        },
        "third_party_letter": {
            "rule_key": "third_party_letter",
            "rule_name": "Third Party Letter",
            "criteria_set": "TIG",
            "severity": "hard_block",
            "is_active": True,
            "threshold_value": 0,
        },
        "previous_iva_check": {
            "rule_key": "previous_iva_check",
            "rule_name": "Previous IVA Check",
            "criteria_set": "TIG",
            "severity": "hard_block",
            "is_active": True,
            "threshold_value": 0,
        },
        "shop_direct_rules": {
            "rule_key": "shop_direct_rules",
            "rule_name": "Shop Direct Rules",
            "criteria_set": "TIG",
            "severity": "hard_block",
            "is_active": True,
            "threshold_value": 0,
        },
        "creation_rules": {
            "rule_key": "creation_rules",
            "rule_name": "Creation Rules",
            "criteria_set": "TIG",
            "severity": "hard_block",
            "is_active": True,
            "threshold_value": 0,
        },
        "link_financial_rules": {
            "rule_key": "link_financial_rules",
            "rule_name": "Link Financial Rules",
            "criteria_set": "TIG",
            "severity": "hard_block",
            "is_active": True,
            "threshold_value": 1200000,  # £12,000
        },
        "hmrc_rules": {
            "rule_key": "hmrc_rules",
            "rule_name": "HMRC Rules",
            "criteria_set": "TIG",
            "severity": "hard_block",
            "is_active": True,
            "threshold_value": 0,
        },
        "equity_flag": {
            "rule_key": "equity_flag",
            "rule_name": "Equity Flag",
            "criteria_set": "TIG",
            "severity": "flag",
            "is_active": True,
            "threshold_value": 0,
        },
        "unexplained_transactions": {
            "rule_key": "unexplained_transactions",
            "rule_name": "Unexplained Transactions",
            "criteria_set": "TIG",
            "severity": "flag",
            "is_active": True,
            "threshold_value": 0,
        },
        "recent_spending": {
            "rule_key": "recent_spending",
            "rule_name": "Recent Spending",
            "criteria_set": "TIG",
            "severity": "flag",
            "is_active": True,
            "threshold_value": 0,
        },
        # WATCH rules
        "watch_debt_repayable_under_6_years": {
            "rule_key": "watch_debt_repayable_under_6_years",
            "rule_name": "Debt Repayable Under 6 Years",
            "criteria_set": "WATCH",
            "severity": "hard_block",
            "is_active": True,
            "threshold_value": 0,
        },
        "watch_bankruptcy_higher": {
            "rule_key": "watch_bankruptcy_higher",
            "rule_name": "Bankruptcy Higher Return",
            "criteria_set": "WATCH",
            "severity": "hard_block",
            "is_active": True,
            "threshold_value": 0,
        },
        "watch_equity_exceeds_debt": {
            "rule_key": "watch_equity_exceeds_debt",
            "rule_name": "Equity Exceeds Debt",
            "criteria_set": "WATCH",
            "severity": "hard_block",
            "is_active": True,
            "threshold_value": 0,
        },
        "watch_single_creditor": {
            "rule_key": "watch_single_creditor",
            "rule_name": "Single Creditor",
            "criteria_set": "WATCH",
            "severity": "hard_block",
            "is_active": True,
            "threshold_value": 50000,  # £500
        },
        "watch_recent_spending": {
            "rule_key": "watch_recent_spending",
            "rule_name": "Recent Spending",
            "criteria_set": "WATCH",
            "severity": "hard_block",
            "is_active": True,
            "threshold_value": 90,
        },
        "watch_antecedent_transactions": {
            "rule_key": "watch_antecedent_transactions",
            "rule_name": "Antecedent Transactions",
            "criteria_set": "WATCH",
            "severity": "hard_block",
            "is_active": True,
            "threshold_value": 0,
        },
        "watch_recent_car_finance": {
            "rule_key": "watch_recent_car_finance",
            "rule_name": "Recent Car Finance",
            "criteria_set": "WATCH",
            "severity": "hard_block",
            "is_active": True,
            "threshold_value": 90,
        },
        "watch_vulnerability_no_evidence": {
            "rule_key": "watch_vulnerability_no_evidence",
            "rule_name": "Vulnerability No Evidence",
            "criteria_set": "WATCH",
            "severity": "flag",
            "is_active": True,
            "threshold_value": 0,
        },
        "watch_children_over_13": {
            "rule_key": "watch_children_over_13",
            "rule_name": "Children Over 13",
            "criteria_set": "WATCH",
            "severity": "flag",
            "is_active": True,
            "threshold_value": 0,
        },
        "watch_client_age_80": {
            "rule_key": "watch_client_age_80",
            "rule_name": "Client Age 80",
            "criteria_set": "WATCH",
            "severity": "info",
            "is_active": True,
            "threshold_value": 0,
        },
        "watch_vehicle_over_9000": {
            "rule_key": "watch_vehicle_over_9000",
            "rule_name": "Vehicle Over £9,000",
            "criteria_set": "WATCH",
            "severity": "flag",
            "is_active": True,
            "threshold_value": 900000,  # £9,000
        },
        "watch_hp_over_400": {
            "rule_key": "watch_hp_over_400",
            "rule_name": "HP Over £400",
            "criteria_set": "WATCH",
            "severity": "flag",
            "is_active": True,
            "threshold_value": 40000,  # £400
        },
        "watch_gambling_no_clean_statements": {
            "rule_key": "watch_gambling_no_clean_statements",
            "rule_name": "Gambling No Clean Statements",
            "criteria_set": "WATCH",
            "severity": "flag",
            "is_active": True,
            "threshold_value": 0,
        },
        "watch_previous_proposal": {
            "rule_key": "watch_previous_proposal",
            "rule_name": "Previous Proposal",
            "criteria_set": "WATCH",
            "severity": "flag",
            "is_active": True,
            "threshold_value": 0,
        },
    }
    merged = copy.deepcopy(rules)
    for rule_key, rule_overrides in overrides.items():
        if rule_key in merged:
            merged[rule_key].update(rule_overrides)
    return merged


def make_docs(**overrides):
    """Factory for uploaded documents."""
    base = {
        "wage_slips":                      [],
        "benefit_letter":                  False,
        "uc_journal":                      None,
        "tax_return":                      False,
        "business_bank_statement_months":  0,
        "cis_invoice":                     None,
        "proof_of_debt":                   {},
        "third_party_letter":              False,
        "termination_report":              False,
        "hmrc_submission_confirmed":       False,
        "car_finance_evidence":            False,
        "vehicle_hp_evidence":             False,
        "vulnerability_evidence":          False,
        "sustainability_paragraph":        False,
        "gamstop_proof":                   False,
        "clean_bank_statement_months":     0,
        "ie_changed_without_explanation":  False,
    }
    merged = copy.deepcopy(base)
    merged.update(overrides)
    return merged


def make_creditor_list(**overrides):
    """Factory for creditor list."""
    creditors = [
        {
            "name": "Barclaycard",
            "trading_names": ["Barclaycard"],
            "representative": "WATCH",
            "min_dividend": 0,
            "is_watch": True,
            "is_tix": False,
            "parent_group": None,
        },
        {
            "name": "Capital One",
            "trading_names": ["Capital One"],
            "representative": "",
            "min_dividend": 0,
            "is_watch": False,
            "is_tix": False,
            "parent_group": None,
        },
        {
            "name": "Very",
            "trading_names": ["Very", "Shop Direct", "Littlewoods"],
            "representative": "",
            "min_dividend": 0,
            "is_watch": False,
            "is_tix": False,
            "parent_group": "Shop Direct",
        },
        {
            "name": "Shop Direct",
            "trading_names": ["Shop Direct", "Very", "Littlewoods"],
            "representative": "",
            "min_dividend": 0,
            "is_watch": False,
            "is_tix": False,
            "parent_group": None,
        },
        {
            "name": "Creation",
            "trading_names": ["Creation", "Sygma", "Laser", "Creation Consumer Finance"],
            "representative": "",
            "min_dividend": 0,
            "is_watch": False,
            "is_tix": False,
            "parent_group": None,
        },
        {
            "name": "Link Financial",
            "trading_names": ["Link Financial", "Link Financial Outsourcing"],
            "representative": "",
            "min_dividend": 0,
            "is_watch": False,
            "is_tix": False,
            "parent_group": None,
        },
        {
            "name": "HMRC",
            "trading_names": [
                "HMRC",
                "HM Revenue and Customs",
                "HM Revenue & Customs",
                "HM Revenue and Customs (VAT)",
                "HM Revenue and Customs (PAYE)",
                "HM Revenue and Customs (Self Assessment)",
            ],
            "representative": "",
            "min_dividend": 0,
            "is_watch": False,
            "is_tix": False,
            "parent_group": None,
        },
    ]
    creditors.extend(overrides.get("additional", []))
    return creditors


# ============================================================================
# TIG RULE TESTS
# ============================================================================

class TestMinDebt:
    def test_min_debt_fires(self):
        case = make_case(
            total_unsecured_debt=300000,  # £3,000 < £6,000
            employment_status="unemployed",  # Avoid wage slip checks
            income={
                "employed_monthly": 0,
                "self_employed_monthly": 0,
                "universal_credit": 0,
                "dla": 0,
                "pip": 0,
                "esa": 0,
                "other_benefits": 0,
                "third_party_contribution": 0,
                "total": 0,
            },
            creditors=[],  # No creditors to avoid proof of debt checks
            bank_statements=[],  # No bank statements to avoid bank statement checks
        )
        rules = make_rules()
        docs = make_docs()
        creditors = make_creditor_list()

        result = assess_case(case, rules, docs, creditors)

        assert len(result["hard_blocks"]) == 1
        assert result["hard_blocks"][0]["rule_key"] == "min_debt"
        assert "below the minimum" in result["hard_blocks"][0]["message"]

    def test_min_debt_does_not_fire(self):
        case = make_case(
            total_unsecured_debt=1000000,  # £10,000 > £6,000
            employment_status="unemployed",  # Avoid wage slip checks
            income={
                "employed_monthly": 0,
                "self_employed_monthly": 0,
                "universal_credit": 0,
                "dla": 0,
                "pip": 0,
                "esa": 0,
                "other_benefits": 0,
                "third_party_contribution": 0,
                "total": 0,
            },
            creditors=[],  # No creditors to avoid proof of debt checks
            bank_statements=[],  # No bank statements to avoid bank statement checks
        )
        rules = make_rules()
        docs = make_docs()
        creditors = make_creditor_list()

        result = assess_case(case, rules, docs, creditors)

        # Should only have min_debt rule checked, and it should not fire
        min_debt_blocks = [hb for hb in result["hard_blocks"] if hb["rule_key"] == "min_debt"]
        assert len(min_debt_blocks) == 0

    def test_min_debt_skipped_when_inactive(self):
        case = make_case(total_unsecured_debt=300000)
        rules = make_rules(min_debt={"is_active": False})
        docs = make_docs()
        creditors = make_creditor_list()

        result = assess_case(case, rules, docs, creditors)

        # Assert that min_debt rule did not fire (is not in hard_blocks)
        assert not any(block['rule_key'] == 'min_debt' for block in result["hard_blocks"])


class TestMinDi:
    def test_min_di_fires(self):
        case = make_case(disposable_income=5000)  # £50 < £100
        rules = make_rules()
        docs = make_docs()
        creditors = make_creditor_list()

        result = assess_case(case, rules, docs, creditors)

        # Assert that min_di rule fired
        assert any(block['rule_key'] == 'min_di' for block in result["hard_blocks"])

    def test_min_di_does_not_fire(self):
        case = make_case(disposable_income=20000)  # £200 > £100
        rules = make_rules()
        docs = make_docs()
        creditors = make_creditor_list()

        result = assess_case(case, rules, docs, creditors)

        # Assert that min_di rule did not fire
        assert not any(block['rule_key'] == 'min_di' for block in result["hard_blocks"])

    def test_min_di_skipped_when_inactive(self):
        case = make_case(disposable_income=5000)
        rules = make_rules(min_di={"is_active": False})
        docs = make_docs()
        creditors = make_creditor_list()

        result = assess_case(case, rules, docs, creditors)

        # Assert that min_di rule did not fire
        assert not any(block['rule_key'] == 'min_di' for block in result["hard_blocks"])


class TestDlaPipOffset:
    def test_dla_pip_offset_fires(self):
        case = make_case(
            income={
                "employed_monthly": 0,
                "self_employed_monthly": 0,
                "universal_credit": 0,
                "dla": 50000,  # £500
                "pip": 30000,  # £300
                "esa": 0,
                "other_benefits": 0,
                "third_party_contribution": 0,
                "total": 80000,
            },
            expenditure={
                "disability_expenses": 0,  # No disability expenses
                "total": 30000,
            }
        )
        rules = make_rules()
        docs = make_docs()
        creditors = make_creditor_list()

        result = assess_case(case, rules, docs, creditors)

        # Assert that dla_pip_offset rule fired
        assert any(block['rule_key'] == 'dla_pip_offset' for block in result["hard_blocks"])

    def test_dla_pip_offset_does_not_fire(self):
        case = make_case(
            income={
                "employed_monthly": 0,
                "self_employed_monthly": 0,
                "universal_credit": 0,
                "dla": 50000,
                "pip": 30000,
                "esa": 0,
                "other_benefits": 0,
                "third_party_contribution": 0,
                "total": 80000,
            },
            expenditure={
                "disability_expenses": 40000,  # Has disability expenses
                "total": 70000,
            }
        )
        rules = make_rules()
        docs = make_docs()
        creditors = make_creditor_list()

        result = assess_case(case, rules, docs, creditors)

        # Assert that dla_pip_offset rule did not fire
        assert not any(block['rule_key'] == 'dla_pip_offset' for block in result["hard_blocks"])

    def test_dla_pip_offset_skipped_when_inactive(self):
        case = make_case(
            income={
                "employed_monthly": 0,
                "self_employed_monthly": 0,
                "universal_credit": 0,
                "dla": 50000,
                "pip": 30000,
                "esa": 0,
                "other_benefits": 0,
                "third_party_contribution": 0,
                "total": 80000,
            },
            expenditure={
                "disability_expenses": 0,
                "total": 30000,
            }
        )
        rules = make_rules(dla_pip_offset={"is_active": False})
        docs = make_docs()
        creditors = make_creditor_list()

        result = assess_case(case, rules, docs, creditors)

        # Assert that dla_pip_offset rule did not fire
        assert not any(block['rule_key'] == 'dla_pip_offset' for block in result["hard_blocks"])


class TestWageSlipCheck:
    def test_wage_slip_check_fires(self):
        case = make_case(employment_status="employed")
        rules = make_rules()
        docs = make_docs(wage_slips=[])  # No wage slips
        creditors = make_creditor_list()

        result = assess_case(case, rules, docs, creditors)

        # Assert that wage_slip_check rule fired
        assert any(block['rule_key'] == 'wage_slip_check' for block in result["hard_blocks"])

    def test_wage_slip_check_does_not_fire(self):
        case = make_case(employment_status="employed")
        rules = make_rules()
        recent_date = (datetime.now() - timedelta(days=30)).date().isoformat()
        docs = make_docs(wage_slips=[{"date": recent_date}])  # Recent wage slip
        creditors = make_creditor_list()

        result = assess_case(case, rules, docs, creditors)

        # Assert that wage_slip_check rule did not fire
        assert not any(block['rule_key'] == 'wage_slip_check' for block in result["hard_blocks"])

    def test_wage_slip_check_skipped_when_inactive(self):
        case = make_case(employment_status="employed")
        rules = make_rules(wage_slip_check={"is_active": False})
        docs = make_docs(wage_slips=[])
        creditors = make_creditor_list()

        result = assess_case(case, rules, docs, creditors)

        # Assert that wage_slip_check rule did not fire
        assert not any(block['rule_key'] == 'wage_slip_check' for block in result["hard_blocks"])


class TestBenefitProofCheck:
    def test_benefit_proof_check_fires(self):
        case = make_case(
            income={
                "employed_monthly": 0,
                "self_employed_monthly": 0,
                "universal_credit": 100000,  # £1,000 benefits
                "dla": 0,
                "pip": 0,
                "esa": 0,
                "other_benefits": 0,
                "third_party_contribution": 0,
                "total": 100000,
            }
        )
        rules = make_rules()
        docs = make_docs(benefit_letter=False)  # No benefit letter
        creditors = make_creditor_list()

        result = assess_case(case, rules, docs, creditors)

        # Assert that benefit_proof_check rule fired
        assert any(block['rule_key'] == 'benefit_proof_check' for block in result["hard_blocks"])

    def test_benefit_proof_check_does_not_fire(self):
        case = make_case(
            income={
                "employed_monthly": 0,
                "self_employed_monthly": 0,
                "universal_credit": 100000,
                "dla": 0,
                "pip": 0,
                "esa": 0,
                "other_benefits": 0,
                "third_party_contribution": 0,
                "total": 100000,
            }
        )
        rules = make_rules()
        docs = make_docs(benefit_letter=True)  # Has benefit letter
        creditors = make_creditor_list()

        result = assess_case(case, rules, docs, creditors)

        # Assert that benefit_proof_check rule did not fire
        assert not any(block['rule_key'] == 'benefit_proof_check' for block in result["hard_blocks"])

    def test_benefit_proof_check_skipped_when_inactive(self):
        case = make_case(
            income={
                "employed_monthly": 0,
                "self_employed_monthly": 0,
                "universal_credit": 100000,
                "dla": 0,
                "pip": 0,
                "esa": 0,
                "other_benefits": 0,
                "third_party_contribution": 0,
                "total": 100000,
            }
        )
        rules = make_rules(benefit_proof_check={"is_active": False})
        docs = make_docs(benefit_letter=False)
        creditors = make_creditor_list()

        result = assess_case(case, rules, docs, creditors)

        # Assert that benefit_proof_check rule did not fire
        assert not any(block['rule_key'] == 'benefit_proof_check' for block in result["hard_blocks"])


class TestUcJournalCheck:
    def test_uc_journal_check_fires(self):
        case = make_case(
            income={
                "employed_monthly": 0,
                "self_employed_monthly": 0,
                "universal_credit": 100000,
                "dla": 0,
                "pip": 0,
                "esa": 0,
                "other_benefits": 0,
                "third_party_contribution": 0,
                "total": 100000,
            }
        )
        rules = make_rules()
        docs = make_docs(uc_journal=[])  # No UC journal
        creditors = make_creditor_list()

        result = assess_case(case, rules, docs, creditors)

        # Assert that uc_journal_check rule fired
        assert any(block['rule_key'] == 'uc_journal_check' for block in result["hard_blocks"])

    def test_uc_journal_check_does_not_fire(self):
        case = make_case(
            income={
                "employed_monthly": 0,
                "self_employed_monthly": 0,
                "universal_credit": 100000,
                "dla": 0,
                "pip": 0,
                "esa": 0,
                "other_benefits": 0,
                "third_party_contribution": 0,
                "total": 100000,
            }
        )
        rules = make_rules()
        recent_date = (datetime.now() - timedelta(days=30)).date().isoformat()
        docs = make_docs(uc_journal=[{"date": recent_date}])  # Recent UC journal
        creditors = make_creditor_list()

        result = assess_case(case, rules, docs, creditors)

        # Assert that uc_journal_check rule did not fire
        assert not any(block['rule_key'] == 'uc_journal_check' for block in result["hard_blocks"])

    def test_uc_journal_check_skipped_when_inactive(self):
        case = make_case(
            income={
                "employed_monthly": 0,
                "self_employed_monthly": 0,
                "universal_credit": 100000,
                "dla": 0,
                "pip": 0,
                "esa": 0,
                "other_benefits": 0,
                "third_party_contribution": 0,
                "total": 100000,
            }
        )
        rules = make_rules(uc_journal_check={"is_active": False})
        docs = make_docs(uc_journal=[])
        creditors = make_creditor_list()

        result = assess_case(case, rules, docs, creditors)

        # Assert that uc_journal_check rule did not fire
        assert not any(block['rule_key'] == 'uc_journal_check' for block in result["hard_blocks"])


class TestSelfEmployedProof:
    def test_self_employed_proof_fires(self):
        case = make_case(employment_status="self_employed")
        rules = make_rules()
        docs = make_docs(tax_return=False, business_bank_statement_months=2)  # Neither requirement met
        creditors = make_creditor_list()

        result = assess_case(case, rules, docs, creditors)

        # Assert that self_employed_proof rule fired
        assert any(block['rule_key'] == 'self_employed_proof' for block in result["hard_blocks"])

    def test_self_employed_proof_does_not_fire(self):
        case = make_case(employment_status="self_employed")
        rules = make_rules()
        docs = make_docs(tax_return=True, business_bank_statement_months=2)  # Tax return present
        creditors = make_creditor_list()

        result = assess_case(case, rules, docs, creditors)

        # Assert that self_employed_proof rule did not fire
        assert not any(block['rule_key'] == 'self_employed_proof' for block in result["hard_blocks"])

    def test_self_employed_proof_skipped_when_inactive(self):
        case = make_case(employment_status="self_employed")
        rules = make_rules(self_employed_proof={"is_active": False})
        docs = make_docs(tax_return=False, business_bank_statement_months=2)
        creditors = make_creditor_list()

        result = assess_case(case, rules, docs, creditors)

        # Assert that self_employed_proof rule did not fire
        assert not any(block['rule_key'] == 'self_employed_proof' for block in result["hard_blocks"])


class TestCisProof:
    def test_cis_proof_fires(self):
        case = make_case(employment_status="cis")
        rules = make_rules()
        docs = make_docs(cis_invoice={"shows_deduction": False})  # No deduction shown
        creditors = make_creditor_list()

        result = assess_case(case, rules, docs, creditors)

        # Assert that cis_proof rule fired
        assert any(block['rule_key'] == 'cis_proof' for block in result["hard_blocks"])

    def test_cis_proof_does_not_fire(self):
        case = make_case(employment_status="cis")
        rules = make_rules()
        docs = make_docs(cis_invoice={"shows_deduction": True})  # Deduction shown
        creditors = make_creditor_list()

        result = assess_case(case, rules, docs, creditors)

        # Assert that cis_proof rule did not fire
        assert not any(block['rule_key'] == 'cis_proof' for block in result["hard_blocks"])

    def test_cis_proof_skipped_when_inactive(self):
        case = make_case(employment_status="cis")
        rules = make_rules(cis_proof={"is_active": False})
        docs = make_docs(cis_invoice={"shows_deduction": False})
        creditors = make_creditor_list()

        result = assess_case(case, rules, docs, creditors)

        # Assert that cis_proof rule did not fire
        assert not any(block['rule_key'] == 'cis_proof' for block in result["hard_blocks"])


class TestBankStatementCheck:
    def test_bank_statement_check_fires(self):
        case = make_case(
            bank_statements=[
                {
                    "account_name": "Main Account",
                    "statement_date": None,  # No statement
                    "months_held": 0,
                }
            ]
        )
        rules = make_rules()
        docs = make_docs()
        creditors = make_creditor_list()

        result = assess_case(case, rules, docs, creditors)

        # Assert that bank_statement_check rule fired
        assert any(block['rule_key'] == 'bank_statement_check' for block in result["hard_blocks"])

    def test_bank_statement_check_does_not_fire(self):
        case = make_case(
            bank_statements=[
                {
                    "account_name": "Main Account",
                    "statement_date": (datetime.now() - timedelta(days=30)).date().isoformat(),  # Recent statement
                    "months_held": 12,
                }
            ]
        )
        rules = make_rules()
        docs = make_docs()
        creditors = make_creditor_list()

        result = assess_case(case, rules, docs, creditors)

        # Assert that bank_statement_check rule did not fire
        assert not any(block['rule_key'] == 'bank_statement_check' for block in result["hard_blocks"])

    def test_bank_statement_check_skipped_when_inactive(self):
        case = make_case(
            bank_statements=[
                {
                    "account_name": "Main Account",
                    "statement_date": None,
                    "months_held": 0,
                }
            ]
        )
        rules = make_rules(bank_statement_check={"is_active": False})
        docs = make_docs()
        creditors = make_creditor_list()

        result = assess_case(case, rules, docs, creditors)

        # Assert that bank_statement_check rule did not fire
        assert not any(block['rule_key'] == 'bank_statement_check' for block in result["hard_blocks"])


class TestGamblingHardBlock:
    def test_gambling_hard_block_fires(self):
        case = make_case(
            gambling={
                "monthly_total": 100000,  # £1,000 > £500 threshold
                "has_gambling": True,
            }
        )
        rules = make_rules()
        docs = make_docs()
        creditors = make_creditor_list()

        result = assess_case(case, rules, docs, creditors)

        # Assert that gambling_hard_block rule fired
        assert any(block['rule_key'] == 'gambling_hard_block' for block in result["hard_blocks"])

    def test_gambling_hard_block_does_not_fire(self):
        case = make_case(
            gambling={
                "monthly_total": 20000,  # £200 < £500 threshold
                "has_gambling": True,
            }
        )
        rules = make_rules()
        docs = make_docs()
        creditors = make_creditor_list()

        result = assess_case(case, rules, docs, creditors)

        # Assert that gambling_hard_block rule did not fire
        assert not any(block['rule_key'] == 'gambling_hard_block' for block in result["hard_blocks"])

    def test_gambling_hard_block_skipped_when_inactive(self):
        case = make_case(
            gambling={
                "monthly_total": 100000,
                "has_gambling": True,
            }
        )
        rules = make_rules(gambling_hard_block={"is_active": False})
        docs = make_docs()
        creditors = make_creditor_list()

        result = assess_case(case, rules, docs, creditors)

        # Assert that gambling_hard_block rule did not fire
        assert not any(block['rule_key'] == 'gambling_hard_block' for block in result["hard_blocks"])


class TestGamblingFlag:
    def test_gambling_flag_fires(self):
        case = make_case(
            gambling={
                "monthly_total": 20000,  # £200 > £100 threshold
                "has_gambling": True,
            }
        )
        rules = make_rules()
        docs = make_docs(gamstop_proof=False)  # No GAMSTOP proof
        creditors = make_creditor_list()

        result = assess_case(case, rules, docs, creditors)

        assert len(result["flags"]) >= 1
        flag_keys = [f["rule_key"] for f in result["flags"]]
        assert "gambling_flag" in flag_keys

    def test_gambling_flag_does_not_fire(self):
        case = make_case(
            gambling={
                "monthly_total": 5000,  # £50 < £100 threshold
                "has_gambling": True,
            }
        )
        rules = make_rules()
        docs = make_docs(gamstop_proof=False)
        creditors = make_creditor_list()

        result = assess_case(case, rules, docs, creditors)

        flag_keys = [f["rule_key"] for f in result["flags"]]
        assert "gambling_flag" not in flag_keys

    def test_gambling_flag_skipped_when_inactive(self):
        case = make_case(
            gambling={
                "monthly_total": 20000,
                "has_gambling": True,
            }
        )
        rules = make_rules(gambling_flag={"is_active": False})
        docs = make_docs(gamstop_proof=False)
        creditors = make_creditor_list()

        result = assess_case(case, rules, docs, creditors)

        flag_keys = [f["rule_key"] for f in result["flags"]]
        assert "gambling_flag" not in flag_keys


class TestProofOfDebt:
    def test_proof_of_debt_fires_hard_block(self):
        case = make_case(
            creditors=[
                {
                    "name": "Big Bank",
                    "balance": 200000,  # £2,000 > £1,000 threshold
                    "monthly_payment": 20000,
                    "account_open_date": "2020-01-01",
                    "last_transaction_date": "2023-01-01",
                    "debt_type": None,
                    "is_hmrc": False,
                    "is_council": False,
                    "is_watch": False,
                    "is_tix": False,
                }
            ]
        )
        rules = make_rules()
        docs = make_docs(proof_of_debt={"big bank": False})  # No proof
        creditors = make_creditor_list()

        result = assess_case(case, rules, docs, creditors)

        # Assert that proof_of_debt rule fired
        assert any(block['rule_key'] == 'proof_of_debt' for block in result["hard_blocks"])

    def test_proof_of_debt_fires_flag(self):
        case = make_case(
            creditors=[
                {
                    "name": "Small Bank",
                    "balance": 50000,  # £500 < £1,000 threshold
                    "monthly_payment": 5000,
                    "account_open_date": "2020-01-01",
                    "last_transaction_date": "2023-01-01",
                    "debt_type": None,
                    "is_hmrc": False,
                    "is_council": False,
                    "is_watch": False,
                    "is_tix": False,
                }
            ]
        )
        rules = make_rules()
        docs = make_docs(proof_of_debt={"small bank": False})  # No proof
        creditors = make_creditor_list()

        result = assess_case(case, rules, docs, creditors)

        assert len(result["flags"]) >= 1
        flag_keys = [f["rule_key"] for f in result["flags"]]
        assert "proof_of_debt" in flag_keys

    def test_proof_of_debt_does_not_fire(self):
        case = make_case(
            creditors=[
                {
                    "name": "Big Bank",
                    "balance": 200000,
                    "monthly_payment": 20000,
                    "account_open_date": "2020-01-01",
                    "last_transaction_date": "2023-01-01",
                    "debt_type": None,
                    "is_hmrc": False,
                    "is_council": False,
                    "is_watch": False,
                    "is_tix": False,
                }
            ]
        )
        rules = make_rules()
        docs = make_docs(proof_of_debt={"big bank": True})  # Has proof
        creditors = make_creditor_list()

        result = assess_case(case, rules, docs, creditors)

        hard_block_keys = [hb["rule_key"] for hb in result["hard_blocks"]]
        flag_keys = [f["rule_key"] for f in result["flags"]]
        assert "proof_of_debt" not in hard_block_keys
        assert "proof_of_debt" not in flag_keys

    def test_proof_of_debt_skipped_when_inactive(self):
        case = make_case(
            creditors=[
                {
                    "name": "Big Bank",
                    "balance": 200000,
                    "monthly_payment": 20000,
                    "account_open_date": "2020-01-01",
                    "last_transaction_date": "2023-01-01",
                    "debt_type": None,
                    "is_hmrc": False,
                    "is_council": False,
                    "is_watch": False,
                    "is_tix": False,
                }
            ]
        )
        rules = make_rules(proof_of_debt={"is_active": False})
        docs = make_docs(proof_of_debt={"Big Bank": False})
        creditors = make_creditor_list()

        result = assess_case(case, rules, docs, creditors)

        hard_block_keys = [hb["rule_key"] for hb in result["hard_blocks"]]
        flag_keys = [f["rule_key"] for f in result["flags"]]
        assert "proof_of_debt" not in hard_block_keys
        assert "proof_of_debt" not in flag_keys


class TestThirdPartyLetter:
    def test_third_party_letter_fires(self):
        case = make_case(
            income={
                "employed_monthly": 250000,
                "self_employed_monthly": 0,
                "universal_credit": 0,
                "dla": 0,
                "pip": 0,
                "esa": 0,
                "other_benefits": 0,
                "third_party_contribution": 50000,  # £500 third party
                "total": 300000,
            }
        )
        rules = make_rules()
        docs = make_docs(third_party_letter=False)  # No letter
        creditors = make_creditor_list()

        result = assess_case(case, rules, docs, creditors)

        # Assert that third_party_letter rule fired
        assert any(block['rule_key'] == 'third_party_letter' for block in result["hard_blocks"])

    def test_third_party_letter_does_not_fire(self):
        case = make_case(
            income={
                "employed_monthly": 250000,
                "self_employed_monthly": 0,
                "universal_credit": 0,
                "dla": 0,
                "pip": 0,
                "esa": 0,
                "other_benefits": 0,
                "third_party_contribution": 0,  # No third party
                "total": 250000,
            }
        )
        rules = make_rules()
        docs = make_docs(third_party_letter=False)
        creditors = make_creditor_list()

        result = assess_case(case, rules, docs, creditors)

        # Assert that third_party_letter rule did not fire
        assert not any(block['rule_key'] == 'third_party_letter' for block in result["hard_blocks"])

    def test_third_party_letter_skipped_when_inactive(self):
        case = make_case(
            income={
                "employed_monthly": 250000,
                "self_employed_monthly": 0,
                "universal_credit": 0,
                "dla": 0,
                "pip": 0,
                "esa": 0,
                "other_benefits": 0,
                "third_party_contribution": 50000,
                "total": 300000,
            }
        )
        rules = make_rules(third_party_letter={"is_active": False})
        docs = make_docs(third_party_letter=False)
        creditors = make_creditor_list()

        result = assess_case(case, rules, docs, creditors)

        # Assert that third_party_letter rule did not fire
        assert not any(block['rule_key'] == 'third_party_letter' for block in result["hard_blocks"])


class TestPreviousIvaCheck:
    def test_previous_iva_check_fires(self):
        case = make_case(
            flags={
                "previous_iva": True,  # Has previous IVA
                "previous_iva_failed_reason": None,
                "antecedent_transactions": False,
                "vulnerability_claimed": False,
                "gambling_main_cause": False,
                "unexplained_transactions": False,
            }
        )
        rules = make_rules()
        docs = make_docs(termination_report=False)  # No termination report
        creditors = make_creditor_list()

        result = assess_case(case, rules, docs, creditors)

        # Assert that previous_iva_check rule fired
        assert any(block['rule_key'] == 'previous_iva_check' for block in result["hard_blocks"])

    def test_previous_iva_check_does_not_fire(self):
        case = make_case(
            flags={
                "previous_iva": False,  # No previous IVA
                "previous_iva_failed_reason": None,
                "antecedent_transactions": False,
                "vulnerability_claimed": False,
                "gambling_main_cause": False,
                "unexplained_transactions": False,
            }
        )
        rules = make_rules()
        docs = make_docs(termination_report=False)
        creditors = make_creditor_list()

        result = assess_case(case, rules, docs, creditors)

        # Assert that previous_iva_check rule did not fire
        assert not any(block['rule_key'] == 'previous_iva_check' for block in result["hard_blocks"])

    def test_previous_iva_check_skipped_when_inactive(self):
        case = make_case(
            flags={
                "previous_iva": True,
                "previous_iva_failed_reason": None,
                "antecedent_transactions": False,
                "vulnerability_claimed": False,
                "gambling_main_cause": False,
                "unexplained_transactions": False,
            }
        )
        rules = make_rules(previous_iva_check={"is_active": False})
        docs = make_docs(termination_report=False)
        creditors = make_creditor_list()

        result = assess_case(case, rules, docs, creditors)

        # Assert that previous_iva_check rule did not fire
        assert not any(block['rule_key'] == 'previous_iva_check' for block in result["hard_blocks"])


class TestShopDirectRules:
    def test_shop_direct_rules_fires_account_open(self):
        case = make_case(
            creditors=[
                {
                    "name": "Very",
                    "balance": 500000,
                    "monthly_payment": 10000,
                    "account_open_date": (datetime.now() - timedelta(days=30)).date().isoformat(),  # Within 6 months
                    "last_transaction_date": "2024-01-01",
                    "debt_type": None,
                    "is_hmrc": False,
                    "is_council": False,
                    "is_watch": False,
                    "is_tix": False,
                }
            ]
        )
        rules = make_rules()
        docs = make_docs()
        creditors = make_creditor_list()  # Includes Very in trading names

        result = assess_case(case, rules, docs, creditors)

        # Assert that shop_direct_rules rule fired
        assert any(block['rule_key'] == 'shop_direct_rules' for block in result["hard_blocks"])

    def test_shop_direct_rules_fires_recent_purchase(self):
        case = make_case(
            creditors=[
                {
                    "name": "Very",
                    "balance": 500000,
                    "monthly_payment": 10000,
                    "account_open_date": "2020-01-01",  # Old account
                    "last_transaction_date": (datetime.now() - timedelta(days=30)).date().isoformat(),
                    "debt_type": None,
                    "is_hmrc": False,
                    "is_council": False,
                    "is_watch": False,
                    "is_tix": False,
                }
            ]
        )
        rules = make_rules()
        docs = make_docs()
        creditors = make_creditor_list()

        result = assess_case(case, rules, docs, creditors)

        flag_keys = [f["rule_key"] for f in result["flags"]]
        assert "shop_direct_rules" in flag_keys

    def test_shop_direct_rules_does_not_fire(self):
        case = make_case(
            creditors=[
                {
                    "name": "Very",
                    "balance": 500000,
                    "monthly_payment": 10000,
                    "account_open_date": "2020-01-01",  # Old account
                    "last_transaction_date": "2020-01-01",  # Old transaction
                    "debt_type": None,
                    "is_hmrc": False,
                    "is_council": False,
                    "is_watch": False,
                    "is_tix": False,
                }
            ]
        )
        rules = make_rules()
        docs = make_docs()
        creditors = make_creditor_list()

        result = assess_case(case, rules, docs, creditors)

        hard_block_keys = [hb["rule_key"] for hb in result["hard_blocks"]]
        flag_keys = [f["rule_key"] for f in result["flags"]]
        assert "shop_direct_rules" not in hard_block_keys
        assert "shop_direct_rules" not in flag_keys

    def test_shop_direct_rules_skipped_when_inactive(self):
        case = make_case(
            creditors=[
                {
                    "name": "Very",
                    "balance": 500000,
                    "monthly_payment": 10000,
                    "account_open_date": "2024-01-01",
                    "last_transaction_date": "2024-01-01",
                    "debt_type": None,
                    "is_hmrc": False,
                    "is_council": False,
                    "is_watch": False,
                    "is_tix": False,
                }
            ]
        )
        rules = make_rules(shop_direct_rules={"is_active": False})
        docs = make_docs()
        creditors = make_creditor_list()

        result = assess_case(case, rules, docs, creditors)

        hard_block_keys = [hb["rule_key"] for hb in result["hard_blocks"]]
        flag_keys = [f["rule_key"] for f in result["flags"]]
        assert "shop_direct_rules" not in hard_block_keys
        assert "shop_direct_rules" not in flag_keys


class TestCreationRules:
    def test_creation_rules_fires(self):
        case = make_case(
            creditors=[
                {
                    "name": "Creation",
                    "balance": 500000,
                    "monthly_payment": 10000,
                    "account_open_date": "2020-01-01",
                    "last_transaction_date": (datetime.now() - timedelta(days=30)).date().isoformat(),
                    "debt_type": None,
                    "is_hmrc": False,
                    "is_council": False,
                    "is_watch": False,
                    "is_tix": False,
                }
            ]
        )
        rules = make_rules()
        docs = make_docs()
        creditors = make_creditor_list()

        result = assess_case(case, rules, docs, creditors)

        assert any(block["rule_key"] == "creation_rules" for block in result["hard_blocks"])

    def test_creation_rules_does_not_fire(self):
        case = make_case(
            creditors=[
                {
                    "name": "Creation",
                    "balance": 500000,
                    "monthly_payment": 10000,
                    "account_open_date": "2020-01-01",
                    "last_transaction_date": "2020-01-01",  # Old transaction
                    "debt_type": None,
                    "is_hmrc": False,
                    "is_council": False,
                    "is_watch": False,
                    "is_tix": False,
                }
            ]
        )
        rules = make_rules()
        docs = make_docs()
        creditors = make_creditor_list()

        result = assess_case(case, rules, docs, creditors)

        assert not any(block["rule_key"] == "creation_rules" for block in result["hard_blocks"])

    def test_creation_rules_skipped_when_inactive(self):
        case = make_case(
            creditors=[
                {
                    "name": "Creation",
                    "balance": 500000,
                    "monthly_payment": 10000,
                    "account_open_date": "2020-01-01",
                    "last_transaction_date": "2024-01-01",
                    "debt_type": None,
                    "is_hmrc": False,
                    "is_council": False,
                    "is_watch": False,
                    "is_tix": False,
                }
            ]
        )
        rules = make_rules(creation_rules={"is_active": False})
        docs = make_docs()
        creditors = make_creditor_list()

        result = assess_case(case, rules, docs, creditors)

        assert not any(block["rule_key"] == "creation_rules" for block in result["hard_blocks"])


class TestLinkFinancialRules:
    def test_link_financial_rules_fires_min_debt(self):
        case = make_case(
            total_unsecured_debt=600000,  # £6,000 < £12,000
            creditors=[
                {
                    "name": "Link Financial",
                    "balance": 600000,
                    "monthly_payment": 10000,
                    "account_open_date": "2020-01-01",
                    "last_transaction_date": "2020-01-01",
                    "debt_type": None,
                    "is_hmrc": False,
                    "is_council": False,
                    "is_watch": False,
                    "is_tix": False,
                }
            ]
        )
        rules = make_rules()
        docs = make_docs()
        creditors = make_creditor_list()

        result = assess_case(case, rules, docs, creditors)

        assert any(block["rule_key"] == "link_financial_rules" for block in result["hard_blocks"])
        assert any(
            "minimum £12,000 total debt required" in block["message"]
            for block in result["hard_blocks"]
            if block["rule_key"] == "link_financial_rules"
        )

    def test_link_financial_rules_does_not_fire(self):
        case = make_case(
            total_unsecured_debt=1500000,  # £15,000 > £12,000
            creditors=[
                {
                    "name": "Link Financial",
                    "balance": 1500000,
                    "monthly_payment": 10000,
                    "account_open_date": "2020-01-01",
                    "last_transaction_date": "2020-01-01",
                    "debt_type": None,
                    "is_hmrc": False,
                    "is_council": False,
                    "is_watch": False,
                    "is_tix": False,
                }
            ]
        )
        rules = make_rules()
        docs = make_docs()
        creditors = make_creditor_list()

        result = assess_case(case, rules, docs, creditors)

        hard_block_keys = [hb["rule_key"] for hb in result["hard_blocks"]]
        assert "link_financial_rules" not in hard_block_keys

    def test_link_financial_rules_skipped_when_inactive(self):
        case = make_case(
            total_unsecured_debt=600000,
            creditors=[
                {
                    "name": "Link Financial",
                    "balance": 600000,
                    "monthly_payment": 10000,
                    "account_open_date": "2020-01-01",
                    "last_transaction_date": "2020-01-01",
                    "debt_type": None,
                    "is_hmrc": False,
                    "is_council": False,
                    "is_watch": False,
                    "is_tix": False,
                }
            ]
        )
        rules = make_rules(link_financial_rules={"is_active": False})
        docs = make_docs()
        creditors = make_creditor_list()

        result = assess_case(case, rules, docs, creditors)

        hard_block_keys = [hb["rule_key"] for hb in result["hard_blocks"]]
        assert "link_financial_rules" not in hard_block_keys


class TestHmrcRules:
    def test_hmrc_rules_fires_seiss_fraud(self):
        case = make_case(
            creditors=[
                {
                    "name": "HMRC",
                    "balance": 1000000,
                    "monthly_payment": 20000,
                    "account_open_date": "2020-01-01",
                    "last_transaction_date": "2020-01-01",
                    "debt_type": "seiss_fraud",
                    "is_hmrc": True,
                    "is_council": False,
                    "is_watch": False,
                    "is_tix": False,
                }
            ]
        )
        rules = make_rules()
        docs = make_docs()
        creditors = make_creditor_list()

        result = assess_case(case, rules, docs, creditors)

        assert any(block["rule_key"] == "hmrc_rules" for block in result["hard_blocks"])
        assert any(
            "SEISS fraud debt cannot be included" in block["message"]
            for block in result["hard_blocks"]
            if block["rule_key"] == "hmrc_rules"
        )

    def test_hmrc_rules_does_not_fire(self):
        case = make_case(
            creditors=[
                {
                    "name": "HMRC",
                    "balance": 1000000,
                    "monthly_payment": 20000,
                    "account_open_date": "2020-01-01",
                    "last_transaction_date": "2020-01-01",
                    "debt_type": "tax",
                    "is_hmrc": True,
                    "is_council": False,
                    "is_watch": False,
                    "is_tix": False,
                }
            ]
        )
        rules = make_rules()
        docs = make_docs()
        creditors = make_creditor_list()

        result = assess_case(case, rules, docs, creditors)

        hard_block_keys = [hb["rule_key"] for hb in result["hard_blocks"]]
        assert "hmrc_rules" not in hard_block_keys

    def test_hmrc_rules_skipped_when_inactive(self):
        case = make_case(
            creditors=[
                {
                    "name": "HMRC",
                    "balance": 1000000,
                    "monthly_payment": 20000,
                    "account_open_date": "2020-01-01",
                    "last_transaction_date": "2020-01-01",
                    "debt_type": "seiss_fraud",
                    "is_hmrc": True,
                    "is_council": False,
                    "is_watch": False,
                    "is_tix": False,
                }
            ]
        )
        rules = make_rules(hmrc_rules={"is_active": False})
        docs = make_docs()
        creditors = make_creditor_list()

        result = assess_case(case, rules, docs, creditors)

        hard_block_keys = [hb["rule_key"] for hb in result["hard_blocks"]]
        assert "hmrc_rules" not in hard_block_keys


class TestEquityFlag:
    def test_equity_flag_fires(self):
        case = make_case(
            total_unsecured_debt=2000000,  # £20,000
            property={
                "owns_property": True,
                "property_value": 3000000,  # £30,000
                "mortgage_balance": 500000,  # £5,000
                "equity": 2500000,  # £25,000 > £20,000 debt
            }
        )
        rules = make_rules()
        docs = make_docs()
        creditors = make_creditor_list()

        result = assess_case(case, rules, docs, creditors)

        assert len(result["flags"]) >= 1
        flag_keys = [f["rule_key"] for f in result["flags"]]
        assert "equity_flag" in flag_keys

    def test_equity_flag_does_not_fire(self):
        case = make_case(
            total_unsecured_debt=2000000,  # £20,000
            property={
                "owns_property": True,
                "property_value": 2200000,  # £22,000
                "mortgage_balance": 1000000,  # £10,000
                "equity": 1200000,  # £12,000 < £20,000 debt
            }
        )
        rules = make_rules()
        docs = make_docs()
        creditors = make_creditor_list()

        result = assess_case(case, rules, docs, creditors)

        flag_keys = [f["rule_key"] for f in result["flags"]]
        assert "equity_flag" not in flag_keys

    def test_equity_flag_skipped_when_inactive(self):
        case = make_case(
            total_unsecured_debt=2000000,
            property={
                "owns_property": True,
                "property_value": 3000000,
                "mortgage_balance": 500000,
                "equity": 2500000,
            }
        )
        rules = make_rules(equity_flag={"is_active": False})
        docs = make_docs()
        creditors = make_creditor_list()

        result = assess_case(case, rules, docs, creditors)

        flag_keys = [f["rule_key"] for f in result["flags"]]
        assert "equity_flag" not in flag_keys


class TestUnexplainedTransactions:
    def test_unexplained_transactions_fires(self):
        case = make_case(
            flags={
                "previous_iva": False,
                "previous_iva_failed_reason": None,
                "antecedent_transactions": False,
                "vulnerability_claimed": False,
                "gambling_main_cause": False,
                "unexplained_transactions": True,  # Has unexplained transactions
            }
        )
        rules = make_rules()
        docs = make_docs()
        creditors = make_creditor_list()

        result = assess_case(case, rules, docs, creditors)

        assert len(result["flags"]) >= 1
        flag_keys = [f["rule_key"] for f in result["flags"]]
        assert "unexplained_transactions" in flag_keys

    def test_unexplained_transactions_does_not_fire(self):
        case = make_case(
            flags={
                "previous_iva": False,
                "previous_iva_failed_reason": None,
                "antecedent_transactions": False,
                "vulnerability_claimed": False,
                "gambling_main_cause": False,
                "unexplained_transactions": False,  # No unexplained transactions
            }
        )
        rules = make_rules()
        docs = make_docs()
        creditors = make_creditor_list()

        result = assess_case(case, rules, docs, creditors)

        flag_keys = [f["rule_key"] for f in result["flags"]]
        assert "unexplained_transactions" not in flag_keys

    def test_unexplained_transactions_skipped_when_inactive(self):
        case = make_case(
            flags={
                "previous_iva": False,
                "previous_iva_failed_reason": None,
                "antecedent_transactions": False,
                "vulnerability_claimed": False,
                "gambling_main_cause": False,
                "unexplained_transactions": True,
            }
        )
        rules = make_rules(unexplained_transactions={"is_active": False})
        docs = make_docs()
        creditors = make_creditor_list()

        result = assess_case(case, rules, docs, creditors)

        flag_keys = [f["rule_key"] for f in result["flags"]]
        assert "unexplained_transactions" not in flag_keys


class TestRecentSpending:
    def test_recent_spending_fires(self):
        case = make_case(
            flags={
                "previous_iva": False,
                "previous_iva_failed_reason": None,
                "antecedent_transactions": True,  # Antecedent transactions present
                "vulnerability_claimed": False,
                "gambling_main_cause": False,
                "unexplained_transactions": False,
            }
        )
        rules = make_rules()
        docs = make_docs()
        creditors = make_creditor_list()

        result = assess_case(case, rules, docs, creditors)

        assert len(result["flags"]) >= 1
        flag_keys = [f["rule_key"] for f in result["flags"]]
        assert "recent_spending" in flag_keys

    def test_recent_spending_does_not_fire(self):
        case = make_case(
            flags={
                "previous_iva": False,
                "previous_iva_failed_reason": None,
                "antecedent_transactions": False,  # No antecedent transactions
                "vulnerability_claimed": False,
                "gambling_main_cause": False,
                "unexplained_transactions": False,
            }
        )
        rules = make_rules()
        docs = make_docs()
        creditors = make_creditor_list()

        result = assess_case(case, rules, docs, creditors)

        flag_keys = [f["rule_key"] for f in result["flags"]]
        assert "recent_spending" not in flag_keys

    def test_recent_spending_skipped_when_inactive(self):
        case = make_case(
            flags={
                "previous_iva": False,
                "previous_iva_failed_reason": None,
                "antecedent_transactions": True,
                "vulnerability_claimed": False,
                "gambling_main_cause": False,
                "unexplained_transactions": False,
            }
        )
        rules = make_rules(recent_spending={"is_active": False})
        docs = make_docs()
        creditors = make_creditor_list()

        result = assess_case(case, rules, docs, creditors)

        flag_keys = [f["rule_key"] for f in result["flags"]]
        assert "recent_spending" not in flag_keys


# ============================================================================
# WATCH RULE TESTS
# ============================================================================

class TestWatchRulesSkippedWhenNoWatchCreditor:
    def test_watch_rules_skipped_when_no_watch_creditor(self):
        case = make_case(
            creditors=[
                {
                    "name": "NonWatch Bank",
                    "balance": 1000000,
                    "monthly_payment": 20000,
                    "account_open_date": "2020-01-01",
                    "last_transaction_date": "2024-01-01",  # Would trigger watch rules
                    "debt_type": None,
                    "is_hmrc": False,
                    "is_council": False,
                    "is_watch": False,  # Not WATCH
                    "is_tix": False,
                }
            ]
        )
        rules = make_rules()
        docs = make_docs()
        creditors = make_creditor_list()  # No WATCH creditors

        result = assess_case(case, rules, docs, creditors)

        assert result["watch_creditor_present"] == False
        # WATCH rules should not have fired
        hard_block_keys = [hb["rule_key"] for hb in result["hard_blocks"]]
        watch_rules = ["watch_debt_repayable_under_6_years", "watch_bankruptcy_higher", 
                      "watch_equity_exceeds_debt", "watch_single_creditor", 
                      "watch_recent_spending", "watch_antecedent_transactions",
                      "watch_recent_car_finance", "watch_vulnerability_no_evidence",
                      "watch_children_over_13", "watch_client_age_80",
                      "watch_vehicle_over_9000", "watch_hp_over_400",
                      "watch_gambling_no_clean_statements", "watch_previous_proposal"]
        for rule in watch_rules:
            assert rule not in hard_block_keys


class TestWatchDebtRepayableUnder6Years:
    def test_watch_debt_repayable_under_6_years_fires(self):
        case = make_case(
            total_unsecured_debt=300000,  # £3,000
            disposable_income=10000,  # £100/month - repayable in 30 months (< 72)
        )
        rules = make_rules()
        docs = make_docs()
        creditors = make_creditor_list()  # Has WATCH creditor

        result = assess_case(case, rules, docs, creditors)

        assert result["watch_creditor_present"] == True
        assert len(result["hard_blocks"]) >= 1
        hard_block_keys = [hb["rule_key"] for hb in result["hard_blocks"]]
        assert "watch_debt_repayable_under_6_years" in hard_block_keys

    def test_watch_debt_repayable_under_6_years_does_not_fire(self):
        case = make_case(
            total_unsecured_debt=5000000,  # £50,000
            disposable_income=10000,  # £100/month - repayable in 500 months (> 72)
        )
        rules = make_rules()
        docs = make_docs()
        creditors = make_creditor_list()

        result = assess_case(case, rules, docs, creditors)

        hard_block_keys = [hb["rule_key"] for hb in result["hard_blocks"]]
        assert "watch_debt_repayable_under_6_years" not in hard_block_keys

    def test_watch_debt_repayable_under_6_years_skipped_when_inactive(self):
        case = make_case(
            total_unsecured_debt=300000,
            disposable_income=10000,
        )
        rules = make_rules(watch_debt_repayable_under_6_years={"is_active": False})
        docs = make_docs()
        creditors = make_creditor_list()

        result = assess_case(case, rules, docs, creditors)

        hard_block_keys = [hb["rule_key"] for hb in result["hard_blocks"]]
        assert "watch_debt_repayable_under_6_years" not in hard_block_keys


class TestWatchBankruptcyHigher:
    def test_watch_bankruptcy_higher_fires(self):
        case = make_case(
            total_unsecured_debt=1000000,  # £10,000
            disposable_income=20000,  # £200/month
        )
        rules = make_rules()
        docs = make_docs()
        creditors = make_creditor_list()

        result = assess_case(case, rules, docs, creditors)

        assert result["watch_creditor_present"] == True
        # IVA return: 200 * 60 = 12,000 * 0.75 = 9,000
        # Bankruptcy return: 10,000
        # So bankruptcy is higher - should fire
        hard_block_keys = [hb["rule_key"] for hb in result["hard_blocks"]]
        assert "watch_bankruptcy_higher" in hard_block_keys

    def test_watch_bankruptcy_higher_does_not_fire(self):
        case = make_case(
            total_unsecured_debt=1000000,  # £10,000
            disposable_income=200000,  # £2,000/month
        )
        rules = make_rules()
        docs = make_docs()
        creditors = make_creditor_list()

        result = assess_case(case, rules, docs, creditors)

        # IVA return: 2000 * 60 = 120,000 * 0.75 = 90,000
        # Bankruptcy return: 10,000
        # So IVA is higher - should not fire
        hard_block_keys = [hb["rule_key"] for hb in result["hard_blocks"]]
        assert "watch_bankruptcy_higher" not in hard_block_keys

    def test_watch_bankruptcy_higher_skipped_when_inactive(self):
        case = make_case(
            total_unsecured_debt=1000000,
            disposable_income=50000,
        )
        rules = make_rules(watch_bankruptcy_higher={"is_active": False})
        docs = make_docs()
        creditors = make_creditor_list()

        result = assess_case(case, rules, docs, creditors)

        hard_block_keys = [hb["rule_key"] for hb in result["hard_blocks"]]
        assert "watch_bankruptcy_higher" not in hard_block_keys


class TestWatchEquityExceedsDebt:
    def test_watch_equity_exceeds_debt_fires(self):
        case = make_case(
            total_unsecured_debt=2000000,  # £20,000
            property={
                "owns_property": True,
                "property_value": 3000000,  # £30,000
                "mortgage_balance": 500000,  # £5,000
                "equity": 2500000,  # £25,000 > £20,000 debt
            }
        )
        rules = make_rules()
        docs = make_docs()
        creditors = make_creditor_list()

        result = assess_case(case, rules, docs, creditors)

        assert result["watch_creditor_present"] == True
        hard_block_keys = [hb["rule_key"] for hb in result["hard_blocks"]]
        assert "watch_equity_exceeds_debt" in hard_block_keys

    def test_watch_equity_exceeds_debt_does_not_fire(self):
        case_data = make_case(equity=500000, total_unsecured_debt=1000000)
        rules = make_rules()
        result = {}
        _rule_watch_equity_exceeds_debt(case_data, rules, result)
        hard_block_keys = [b["rule_key"] for b in result.get("hard_blocks", [])]
        assert "watch_equity_exceeds_debt" not in hard_block_keys

    def test_watch_equity_exceeds_debt_handles_none(self):
        # Regression test for TypeError when equity or total_debt is None
        case_data = {
            "property": {"equity": None},
            "total_unsecured_debt": None
        }
        rules = {
            "watch_equity_exceeds_debt": {
                "rule_key": "watch_equity_exceeds_debt",
                "rule_name": "Equity Exceeds Debt",
                "is_active": True
            }
        }
        result = {"hard_blocks": []}
        # Should not raise TypeError
        _rule_watch_equity_exceeds_debt(case_data, rules, result)
        assert len(result["hard_blocks"]) == 0

    def test_watch_equity_exceeds_debt_skipped_when_inactive(self):
        case = make_case(
            total_unsecured_debt=2000000,
            property={
                "owns_property": True,
                "property_value": 3000000,
                "mortgage_balance": 500000,
                "equity": 2500000,
            }
        )
        rules = make_rules(watch_equity_exceeds_debt={"is_active": False})
        docs = make_docs()
        creditors = make_creditor_list()

        result = assess_case(case, rules, docs, creditors)

        hard_block_keys = [hb["rule_key"] for hb in result["hard_blocks"]]
        assert "watch_equity_exceeds_debt" not in hard_block_keys


class TestWatchSingleCreditor:
    def test_watch_single_creditor_fires(self):
        case = make_case(
            creditors=[
                {
                    "name": "Barclaycard",
                    "balance": 100000,  # £1,000 > £500 threshold
                    "monthly_payment": 20000,
                    "account_open_date": "2020-01-01",
                    "last_transaction_date": "2023-01-01",
                    "debt_type": None,
                    "is_hmrc": False,
                    "is_council": False,
                    "is_watch": True,
                    "is_tix": False,
                }
            ]
        )
        rules = make_rules()
        docs = make_docs()
        creditors = make_creditor_list()

        result = assess_case(case, rules, docs, creditors)

        assert result["watch_creditor_present"] == True
        hard_block_keys = [hb["rule_key"] for hb in result["hard_blocks"]]
        assert "watch_single_creditor" in hard_block_keys

    def test_watch_single_creditor_does_not_fire(self):
        case = make_case(
            creditors=[
                {
                    "name": "Barclaycard",
                    "balance": 1000000,  # £10,000 > £500 threshold
                    "monthly_payment": 20000,
                    "account_open_date": "2020-01-01",
                    "last_transaction_date": "2023-01-01",
                    "debt_type": None,
                    "is_hmrc": False,
                    "is_council": False,
                    "is_watch": True,
                    "is_tix": False,
                },
                {
                    "name": "Another Bank",
                    "balance": 600000,  # £6,000 > £500 threshold
                    "monthly_payment": 10000,
                    "account_open_date": "2020-01-01",
                    "last_transaction_date": "2023-01-01",
                    "debt_type": None,
                    "is_hmrc": False,
                    "is_council": False,
                    "is_watch": False,
                    "is_tix": False,
                }
            ]
        )
        rules = make_rules()
        docs = make_docs()
        creditors = make_creditor_list()

        result = assess_case(case, rules, docs, creditors)

        assert result["watch_creditor_present"] == True
        hard_block_keys = [hb["rule_key"] for hb in result["hard_blocks"]]
        assert "watch_single_creditor" not in hard_block_keys

    def test_watch_single_creditor_skipped_when_inactive(self):
        case = make_case(
            creditors=[
                {
                    "name": "Big WATCH Bank",
                    "balance": 100000,
                    "monthly_payment": 20000,
                    "account_open_date": "2020-01-01",
                    "last_transaction_date": "2023-01-01",
                    "debt_type": None,
                    "is_hmrc": False,
                    "is_council": False,
                    "is_watch": True,
                    "is_tix": False,
                }
            ]
        )
        rules = make_rules(watch_single_creditor={"is_active": False})
        docs = make_docs()
        creditors = make_creditor_list()

        result = assess_case(case, rules, docs, creditors)

        hard_block_keys = [hb["rule_key"] for hb in result["hard_blocks"]]
        assert "watch_single_creditor" not in hard_block_keys


class TestWatchRecentSpending:
    def test_watch_recent_spending_fires(self):
        case = make_case(
            creditors=[
                {
                    "name": "Barclaycard",
                    "balance": 1500000,
                    "monthly_payment": 30000,
                    "account_open_date": "2020-01-01",
                    "last_transaction_date": (datetime.now() - timedelta(days=30)).date().isoformat(),  # Within 90 days
                    "debt_type": None,
                    "is_hmrc": False,
                    "is_council": False,
                    "is_watch": True,
                    "is_tix": False,
                }
            ]
        )
        rules = make_rules()
        docs = make_docs()
        creditors = make_creditor_list()

        result = assess_case(case, rules, docs, creditors)

        assert result["watch_creditor_present"] == True
        hard_block_keys = [hb["rule_key"] for hb in result["hard_blocks"]]
        assert "watch_recent_spending" in hard_block_keys

    def test_watch_recent_spending_does_not_fire(self):
        case = make_case(
            creditors=[
                {
                    "name": "Barclaycard",
                    "balance": 1500000,
                    "monthly_payment": 30000,
                    "account_open_date": "2020-01-01",
                    "last_transaction_date": "2020-01-01",  # Old transaction
                    "debt_type": None,
                    "is_hmrc": False,
                    "is_council": False,
                    "is_watch": True,
                    "is_tix": False,
                }
            ]
        )
        rules = make_rules()
        docs = make_docs()
        creditors = make_creditor_list()

        result = assess_case(case, rules, docs, creditors)

        hard_block_keys = [hb["rule_key"] for hb in result["hard_blocks"]]
        assert "watch_recent_spending" not in hard_block_keys

    def test_watch_recent_spending_skipped_when_inactive(self):
        case = make_case(
            creditors=[
                {
                    "name": "Barclaycard",
                    "balance": 1500000,
                    "monthly_payment": 30000,
                    "account_open_date": "2020-01-01",
                    "last_transaction_date": "2024-01-01",
                    "debt_type": None,
                    "is_hmrc": False,
                    "is_council": False,
                    "is_watch": True,
                    "is_tix": False,
                }
            ]
        )
        rules = make_rules(watch_recent_spending={"is_active": False})
        docs = make_docs()
        creditors = make_creditor_list()

        result = assess_case(case, rules, docs, creditors)

        hard_block_keys = [hb["rule_key"] for hb in result["hard_blocks"]]
        assert "watch_recent_spending" not in hard_block_keys


class TestWatchAntecedentTransactions:
    def test_watch_antecedent_transactions_fires(self):
        case = make_case(
            flags={
                "previous_iva": False,
                "previous_iva_failed_reason": None,
                "antecedent_transactions": True,  # Has antecedent transactions
                "vulnerability_claimed": False,
                "gambling_main_cause": False,
                "unexplained_transactions": False,
            }
        )
        rules = make_rules()
        docs = make_docs()
        creditors = make_creditor_list()

        result = assess_case(case, rules, docs, creditors)

        assert result["watch_creditor_present"] == True
        hard_block_keys = [hb["rule_key"] for hb in result["hard_blocks"]]
        assert "watch_antecedent_transactions" in hard_block_keys

    def test_watch_antecedent_transactions_does_not_fire(self):
        case = make_case(
            flags={
                "previous_iva": False,
                "previous_iva_failed_reason": None,
                "antecedent_transactions": False,  # No antecedent transactions
                "vulnerability_claimed": False,
                "gambling_main_cause": False,
                "unexplained_transactions": False,
            }
        )
        rules = make_rules()
        docs = make_docs()
        creditors = make_creditor_list()

        result = assess_case(case, rules, docs, creditors)

        hard_block_keys = [hb["rule_key"] for hb in result["hard_blocks"]]
        assert "watch_antecedent_transactions" not in hard_block_keys

    def test_watch_antecedent_transactions_skipped_when_inactive(self):
        case = make_case(
            flags={
                "previous_iva": False,
                "previous_iva_failed_reason": None,
                "antecedent_transactions": True,
                "vulnerability_claimed": False,
                "gambling_main_cause": False,
                "unexplained_transactions": False,
            }
        )
        rules = make_rules(watch_antecedent_transactions={"is_active": False})
        docs = make_docs()
        creditors = make_creditor_list()

        result = assess_case(case, rules, docs, creditors)

        hard_block_keys = [hb["rule_key"] for hb in result["hard_blocks"]]
        assert "watch_antecedent_transactions" not in hard_block_keys


class TestWatchRecentCarFinance:
    def test_watch_recent_car_finance_fires(self):
        case = make_case(
            vehicle={
                "has_vehicle": True,
                "vehicle_value": 1000000,
                "hp_monthly_payment": 20000,
                "car_finance_start_date": (datetime.now() - timedelta(days=30)).date().isoformat(),  # Within 90 days
            }
        )
        rules = make_rules()
        docs = make_docs(car_finance_evidence=False)  # No evidence
        creditors = make_creditor_list()

        result = assess_case(case, rules, docs, creditors)

        assert result["watch_creditor_present"] == True
        hard_block_keys = [hb["rule_key"] for hb in result["hard_blocks"]]
        assert "watch_recent_car_finance" in hard_block_keys

    def test_watch_recent_car_finance_does_not_fire(self):
        case = make_case(
            vehicle={
                "has_vehicle": True,
                "vehicle_value": 1000000,
                "hp_monthly_payment": 20000,
                "car_finance_start_date": "2020-01-01",  # Old finance
            }
        )
        rules = make_rules()
        docs = make_docs(car_finance_evidence=False)
        creditors = make_creditor_list()

        result = assess_case(case, rules, docs, creditors)

        hard_block_keys = [hb["rule_key"] for hb in result["hard_blocks"]]
        assert "watch_recent_car_finance" not in hard_block_keys

    def test_watch_recent_car_finance_skipped_when_inactive(self):
        case = make_case(
            vehicle={
                "has_vehicle": True,
                "vehicle_value": 1000000,
                "hp_monthly_payment": 20000,
                "car_finance_start_date": "2024-01-01",
            }
        )
        rules = make_rules(watch_recent_car_finance={"is_active": False})
        docs = make_docs(car_finance_evidence=False)
        creditors = make_creditor_list()

        result = assess_case(case, rules, docs, creditors)

        hard_block_keys = [hb["rule_key"] for hb in result["hard_blocks"]]
        assert "watch_recent_car_finance" not in hard_block_keys


class TestWatchVulnerabilityNoEvidence:
    def test_watch_vulnerability_no_evidence_fires(self):
        case = make_case(
            flags={
                "previous_iva": False,
                "previous_iva_failed_reason": None,
                "antecedent_transactions": False,
                "vulnerability_claimed": True,  # Vulnerability claimed
                "gambling_main_cause": False,
                "unexplained_transactions": False,
            }
        )
        rules = make_rules()
        docs = make_docs(vulnerability_evidence=False)  # No evidence
        creditors = make_creditor_list()

        result = assess_case(case, rules, docs, creditors)

        assert result["watch_creditor_present"] == True
        flag_keys = [f["rule_key"] for f in result["flags"]]
        assert "watch_vulnerability_no_evidence" in flag_keys

    def test_watch_vulnerability_no_evidence_does_not_fire(self):
        case = make_case(
            flags={
                "previous_iva": False,
                "previous_iva_failed_reason": None,
                "antecedent_transactions": False,
                "vulnerability_claimed": False,  # No vulnerability claimed
                "gambling_main_cause": False,
                "unexplained_transactions": False,
            }
        )
        rules = make_rules()
        docs = make_docs(vulnerability_evidence=False)
        creditors = make_creditor_list()

        result = assess_case(case, rules, docs, creditors)

        flag_keys = [f["rule_key"] for f in result["flags"]]
        assert "watch_vulnerability_no_evidence" not in flag_keys

    def test_watch_vulnerability_no_evidence_skipped_when_inactive(self):
        case = make_case(
            flags={
                "previous_iva": False,
                "previous_iva_failed_reason": None,
                "antecedent_transactions": False,
                "vulnerability_claimed": True,
                "gambling_main_cause": False,
                "unexplained_transactions": False,
            }
        )
        rules = make_rules(watch_vulnerability_no_evidence={"is_active": False})
        docs = make_docs(vulnerability_evidence=False)
        creditors = make_creditor_list()

        result = assess_case(case, rules, docs, creditors)

        flag_keys = [f["rule_key"] for f in result["flags"]]
        assert "watch_vulnerability_no_evidence" not in flag_keys


class TestWatchChildrenOver13:
    def test_watch_children_over_13_fires(self):
        case = make_case(
            dependants=[
                {"age": 15},  # Over 13
            ]
        )
        rules = make_rules()
        docs = make_docs(sustainability_paragraph=False)  # No paragraph
        creditors = make_creditor_list()

        result = assess_case(case, rules, docs, creditors)

        assert result["watch_creditor_present"] == True
        flag_keys = [f["rule_key"] for f in result["flags"]]
        assert "watch_children_over_13" in flag_keys

    def test_watch_children_over_13_does_not_fire(self):
        case = make_case(
            dependants=[
                {"age": 10},  # Under 13
            ]
        )
        rules = make_rules()
        docs = make_docs(sustainability_paragraph=False)
        creditors = make_creditor_list()

        result = assess_case(case, rules, docs, creditors)

        flag_keys = [f["rule_key"] for f in result["flags"]]
        assert "watch_children_over_13" not in flag_keys

    def test_watch_children_over_13_skipped_when_inactive(self):
        case = make_case(
            dependants=[
                {"age": 15},
            ]
        )
        rules = make_rules(watch_children_over_13={"is_active": False})
        docs = make_docs(sustainability_paragraph=False)
        creditors = make_creditor_list()

        result = assess_case(case, rules, docs, creditors)

        flag_keys = [f["rule_key"] for f in result["flags"]]
        assert "watch_children_over_13" not in flag_keys


class TestWatchClientAge80:
    def test_watch_client_age_80_fires(self):
        case = make_case(client_age=85)  # Over 80
        rules = make_rules()
        docs = make_docs()
        creditors = make_creditor_list()

        result = assess_case(case, rules, docs, creditors)

        assert result["watch_creditor_present"] == True
        info_keys = [i["rule_key"] for i in result["info"]]
        assert "watch_client_age_80" in info_keys

    def test_watch_client_age_80_does_not_fire(self):
        case = make_case(client_age=75)  # Under 80
        rules = make_rules()
        docs = make_docs()
        creditors = make_creditor_list()

        result = assess_case(case, rules, docs, creditors)

        info_keys = [i["rule_key"] for i in result["info"]]
        assert "watch_client_age_80" not in info_keys

    def test_watch_client_age_80_skipped_when_inactive(self):
        case = make_case(client_age=85)
        rules = make_rules(watch_client_age_80={"is_active": False})
        docs = make_docs()
        creditors = make_creditor_list()

        result = assess_case(case, rules, docs, creditors)

        info_keys = [i["rule_key"] for i in result["info"]]
        assert "watch_client_age_80" not in info_keys


class TestWatchVehicleOver9000:
    def test_watch_vehicle_over_9000_fires(self):
        case = make_case(
            vehicle={
                "has_vehicle": True,
                "vehicle_value": 1000000,  # £10,000 > £9,000
                "hp_monthly_payment": 20000,
                "car_finance_start_date": None,
            }
        )
        rules = make_rules()
        docs = make_docs()
        creditors = make_creditor_list()

        result = assess_case(case, rules, docs, creditors)

        assert result["watch_creditor_present"] == True
        flag_keys = [f["rule_key"] for f in result["flags"]]
        assert "watch_vehicle_over_9000" in flag_keys

    def test_watch_vehicle_over_9000_does_not_fire(self):
        case = make_case(
            vehicle={
                "has_vehicle": True,
                "vehicle_value": 800000,  # £8,000 < £9,000
                "hp_monthly_payment": 20000,
                "car_finance_start_date": None,
            }
        )
        rules = make_rules()
        docs = make_docs()
        creditors = make_creditor_list()

        result = assess_case(case, rules, docs, creditors)

        flag_keys = [f["rule_key"] for f in result["flags"]]
        assert "watch_vehicle_over_9000" not in flag_keys

    def test_watch_vehicle_over_9000_skipped_when_inactive(self):
        case = make_case(
            vehicle={
                "has_vehicle": True,
                "vehicle_value": 1000000,
                "hp_monthly_payment": 20000,
                "car_finance_start_date": None,
            }
        )
        rules = make_rules(watch_vehicle_over_9000={"is_active": False})
        docs = make_docs()
        creditors = make_creditor_list()

        result = assess_case(case, rules, docs, creditors)

        flag_keys = [f["rule_key"] for f in result["flags"]]
        assert "watch_vehicle_over_9000" not in flag_keys


class TestWatchHpOver400:
    def test_watch_hp_over_400_fires(self):
        case = make_case(
            vehicle={
                "has_vehicle": True,
                "vehicle_value": 1000000,
                "hp_monthly_payment": 50000,  # £500 > £400
                "car_finance_start_date": None,
            }
        )
        rules = make_rules()
        docs = make_docs(vehicle_hp_evidence=False)  # No evidence
        creditors = make_creditor_list()

        result = assess_case(case, rules, docs, creditors)

        assert result["watch_creditor_present"] == True
        flag_keys = [f["rule_key"] for f in result["flags"]]
        assert "watch_hp_over_400" in flag_keys

    def test_watch_hp_over_400_does_not_fire(self):
        case = make_case(
            vehicle={
                "has_vehicle": True,
                "vehicle_value": 1000000,
                "hp_monthly_payment": 30000,  # £300 < £400
                "car_finance_start_date": None,
            }
        )
        rules = make_rules()
        docs = make_docs(vehicle_hp_evidence=False)
        creditors = make_creditor_list()

        result = assess_case(case, rules, docs, creditors)

        flag_keys = [f["rule_key"] for f in result["flags"]]
        assert "watch_hp_over_400" not in flag_keys

    def test_watch_hp_over_400_skipped_when_inactive(self):
        case = make_case(
            vehicle={
                "has_vehicle": True,
                "vehicle_value": 1000000,
                "hp_monthly_payment": 50000,
                "car_finance_start_date": None,
            }
        )
        rules = make_rules(watch_hp_over_400={"is_active": False})
        docs = make_docs(vehicle_hp_evidence=False)
        creditors = make_creditor_list()

        result = assess_case(case, rules, docs, creditors)

        flag_keys = [f["rule_key"] for f in result["flags"]]
        assert "watch_hp_over_400" not in flag_keys


class TestWatchGamblingNoCleanStatements:
    def test_watch_gambling_no_clean_statements_fires(self):
        case = make_case(
            flags={
                "previous_iva": False,
                "previous_iva_failed_reason": None,
                "antecedent_transactions": False,
                "vulnerability_claimed": False,
                "gambling_main_cause": True,  # Gambling is main cause
                "unexplained_transactions": False,
            }
        )
        rules = make_rules()
        docs = make_docs(clean_bank_statement_months=2)  # Less than 3 months
        creditors = make_creditor_list()

        result = assess_case(case, rules, docs, creditors)

        assert result["watch_creditor_present"] == True
        flag_keys = [f["rule_key"] for f in result["flags"]]
        assert "watch_gambling_no_clean_statements" in flag_keys

    def test_watch_gambling_no_clean_statements_does_not_fire(self):
        case = make_case(
            flags={
                "previous_iva": False,
                "previous_iva_failed_reason": None,
                "antecedent_transactions": False,
                "vulnerability_claimed": False,
                "gambling_main_cause": False,  # Gambling not main cause
                "unexplained_transactions": False,
            }
        )
        rules = make_rules()
        docs = make_docs(clean_bank_statement_months=2)
        creditors = make_creditor_list()

        result = assess_case(case, rules, docs, creditors)

        flag_keys = [f["rule_key"] for f in result["flags"]]
        assert "watch_gambling_no_clean_statements" not in flag_keys

    def test_watch_gambling_no_clean_statements_skipped_when_inactive(self):
        case = make_case(
            flags={
                "previous_iva": False,
                "previous_iva_failed_reason": None,
                "antecedent_transactions": False,
                "vulnerability_claimed": False,
                "gambling_main_cause": True,
                "unexplained_transactions": False,
            }
        )
        rules = make_rules(watch_gambling_no_clean_statements={"is_active": False})
        docs = make_docs(clean_bank_statement_months=2)
        creditors = make_creditor_list()

        result = assess_case(case, rules, docs, creditors)

        flag_keys = [f["rule_key"] for f in result["flags"]]
        assert "watch_gambling_no_clean_statements" not in flag_keys


class TestWatchPreviousProposal:
    def test_watch_previous_proposal_fires(self):
        case = make_case(
            flags={
                "previous_iva": True,  # Has previous IVA
                "previous_iva_failed_reason": None,
                "antecedent_transactions": False,
                "vulnerability_claimed": False,
                "gambling_main_cause": False,
                "unexplained_transactions": False,
            }
        )
        rules = make_rules()
        docs = make_docs(ie_changed_without_explanation=True)  # I&E changed without explanation
        creditors = make_creditor_list()

        result = assess_case(case, rules, docs, creditors)

        assert result["watch_creditor_present"] == True
        flag_keys = [f["rule_key"] for f in result["flags"]]
        assert "watch_previous_proposal" in flag_keys

    def test_watch_previous_proposal_does_not_fire(self):
        case = make_case(
            flags={
                "previous_iva": False,  # No previous IVA
                "previous_iva_failed_reason": None,
                "antecedent_transactions": False,
                "vulnerability_claimed": False,
                "gambling_main_cause": False,
                "unexplained_transactions": False,
            }
        )
        rules = make_rules()
        docs = make_docs(ie_changed_without_explanation=True)
        creditors = make_creditor_list()

        result = assess_case(case, rules, docs, creditors)

        flag_keys = [f["rule_key"] for f in result["flags"]]
        assert "watch_previous_proposal" not in flag_keys

    def test_watch_previous_proposal_skipped_when_inactive(self):
        case = make_case(
            flags={
                "previous_iva": True,
                "previous_iva_failed_reason": None,
                "antecedent_transactions": False,
                "vulnerability_claimed": False,
                "gambling_main_cause": False,
                "unexplained_transactions": False,
            }
        )
        rules = make_rules(watch_previous_proposal={"is_active": False})
        docs = make_docs(ie_changed_without_explanation=True)
        creditors = make_creditor_list()

        result = assess_case(case, rules, docs, creditors)

        flag_keys = [f["rule_key"] for f in result["flags"]]
        assert "watch_previous_proposal" not in flag_keys


# ============================================================================
# INTEGRATION TESTS
# ============================================================================

class TestMajorityCreditorDetected:
    def test_majority_creditor_detected(self):
        case = make_case(
            creditors=[
                {
                    "name": "Majority Bank",
                    "balance": 1800000,  # £18,000 (90% of £20,000)
                    "monthly_payment": 30000,
                    "account_open_date": "2020-01-01",
                    "last_transaction_date": "2023-01-01",
                    "debt_type": None,
                    "is_hmrc": False,
                    "is_council": False,
                    "is_watch": False,
                    "is_tix": False,
                },
                {
                    "name": "Small Bank",
                    "balance": 200000,  # £2,000
                    "monthly_payment": 10000,
                    "account_open_date": "2020-01-01",
                    "last_transaction_date": "2023-01-01",
                    "debt_type": None,
                    "is_hmrc": False,
                    "is_council": False,
                    "is_watch": False,
                    "is_tix": False,
                }
            ],
            total_unsecured_debt=2000000,  # £20,000
        )
        rules = make_rules()
        docs = make_docs()
        creditors = make_creditor_list()

        result = assess_case(case, rules, docs, creditors)

        assert result["majority_creditor"] is not None
        assert result["majority_creditor"]["name"] == "Majority Bank"
        assert result["majority_creditor"]["balance"] == 1800000
        assert result["majority_creditor"]["percentage"] == 90.0

    def test_no_majority_creditor(self):
        case = make_case(
            creditors=[
                {
                    "name": "Bank A",
                    "balance": 1000000,  # £10,000 (50% of £20,000)
                    "monthly_payment": 20000,
                    "account_open_date": "2020-01-01",
                    "last_transaction_date": "2023-01-01",
                    "debt_type": None,
                    "is_hmrc": False,
                    "is_council": False,
                    "is_watch": False,
                    "is_tix": False,
                },
                {
                    "name": "Bank B",
                    "balance": 1000000,  # £10,000 (50% of £20,000)
                    "monthly_payment": 20000,
                    "account_open_date": "2020-01-01",
                    "last_transaction_date": "2023-01-01",
                    "debt_type": None,
                    "is_hmrc": False,
                    "is_council": False,
                    "is_watch": False,
                    "is_tix": False,
                }
            ],
            total_unsecured_debt=2000000,  # £20,000
        )
        rules = make_rules()
        docs = make_docs()
        creditors = make_creditor_list()

        result = assess_case(case, rules, docs, creditors)

        assert result["majority_creditor"] is None


class TestRecommendationIva:
    def test_recommendation_iva(self):
        case, docs = make_clean_case()
        rules = make_rules(
            watch_debt_repayable_under_6_years={"is_active": False},
            watch_bankruptcy_higher={"is_active": False},
        )
        creditors = make_creditor_list()

        result = assess_case(case, rules, docs, creditors)

        assert result["recommended_solution"] == "IVA"
        assert result["tig_eligible"] == True
        assert result["passes_all_hard_blocks"] == True
        assert result["estimated_dividend_pence"] > 0

    def test_recommendation_dmp(self):
        # Below min_debt threshold so TIG-ineligible, but DI > 0
        case, docs = make_clean_case(
            total_unsecured_debt=300000,   # £3,000 — below £6,000 min
        )
        rules = make_rules(
            watch_debt_repayable_under_6_years={"is_active": False},
            watch_bankruptcy_higher={"is_active": False},
        )
        creditors = make_creditor_list()

        result = assess_case(case, rules, docs, creditors)

        assert result["recommended_solution"] == "DMP"

    def test_recommendation_free_sector(self):
        # DI is zero
        case, docs = make_clean_case(
            total_unsecured_debt=300000,   # below min_debt
            disposable_income=0,
        )
        rules = make_rules(
            watch_debt_repayable_under_6_years={"is_active": False},
            watch_bankruptcy_higher={"is_active": False},
        )
        creditors = make_creditor_list()

        result = assess_case(case, rules, docs, creditors)

        assert result["recommended_solution"] == "FREE_SECTOR"

    def test_recommendation_unclear(self):
        # Even with hard blocks, if DI >0, recommend DMP
        case, docs = make_clean_case()
        docs["wage_slips"] = []            # removes wage slip → hard block
        rules = make_rules(
            watch_debt_repayable_under_6_years={"is_active": False},
            watch_bankruptcy_higher={"is_active": False},
        )
        creditors = make_creditor_list()

        result = assess_case(case, rules, docs, creditors)

        assert result["recommended_solution"] == "UNCLEAR"
        assert result["passes_all_hard_blocks"] == False


class TestMoneyNeverFloats:
    def test_money_never_floats(self):
        case = make_case()
        rules = make_rules()
        docs = make_docs()
        creditors = make_creditor_list()

        result = assess_case(case, rules, docs, creditors)

        # Check all money values are integers
        assert isinstance(result["estimated_dividend_pence"], (int, type(None)))
        if result["majority_creditor"]:
            assert isinstance(result["majority_creditor"]["balance"], int)
            assert isinstance(result["majority_creditor"]["percentage"], float)  # Percentage can be float

        for creditor in result.get("creditors", []):
            assert isinstance(creditor["balance"], int)
            assert isinstance(creditor["monthly_payment"], int)


# ============================================================================
# HELPER FUNCTION TESTS
# ============================================================================

class TestMatchesCreditor:
    def test_matches_creditor_exact(self):
        creditor_entry = {"name": "Barclaycard", "trading_names": ["Barclays"]}
        assert _matches_creditor("Barclaycard", creditor_entry) == True

    def test_matches_creditor_trading_name(self):
        creditor_entry = {"name": "Barclaycard", "trading_names": ["Barclays"]}
        assert _matches_creditor("Barclays", creditor_entry) == True

    def test_matches_creditor_case_insensitive(self):
        creditor_entry = {"name": "Barclaycard", "trading_names": ["Barclays"]}
        assert _matches_creditor("barclaycard", creditor_entry) == True

    def test_matches_creditor_no_match(self):
        creditor_entry = {"name": "Barclaycard", "trading_names": ["Barclays"]}
        assert _matches_creditor("HSBC", creditor_entry) == False


class TestDetectWatchCreditor:
    def test_detect_watch_creditor_present(self):
        case_data = make_case()
        creditor_list = make_creditor_list()  # Has WATCH creditor
        assert _detect_watch_creditor(case_data, creditor_list) == True

    def test_detect_watch_creditor_not_present(self):
        case_data = make_case()
        creditor_list = [{"name": "NonWatch", "trading_names": [], "is_watch": False}]
        assert _detect_watch_creditor(case_data, creditor_list) == False

    def test_detect_watch_creditor_fuzzy_match(self):
        case_data = {
            "creditors": [{"name": "Halifax (HBOS)", "balance": 100000}]
        }
        creditor_list = [
            {"name": "Halifax", "trading_names": ["Halifax HBOS"], "is_watch": True}
        ]
        assert _detect_watch_creditor(case_data, creditor_list) == True


class TestFindMajorityCreditor:
    def test_find_majority_creditor_exists(self):
        creditors = [
            {"name": "Big Bank", "balance": 1800000},  # 90%
            {"name": "Small Bank", "balance": 200000},  # 10%
        ]
        result = _find_majority_creditor(creditors, 2000000)
        assert result is not None
        assert result["name"] == "Big Bank"
        assert result["percentage"] == 90.0

    def test_find_majority_creditor_none(self):
        creditors = [
            {"name": "Bank A", "balance": 1000000},  # 50%
            {"name": "Bank B", "balance": 1000000},  # 50%
        ]
        result = _find_majority_creditor(creditors, 2000000)
        assert result is None


class TestCalculateEstimatedDividend:
    def test_calculate_estimated_dividend(self):
        disposable_income = 10000  # �100
        total_debt = 1000000       # �10,000
        result = _calculate_estimated_dividend(disposable_income, total_debt)
        assert result == 45
        assert isinstance(result, int)
