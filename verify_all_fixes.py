#!/usr/bin/env python3
import os
import sys
import django
from decimal import Decimal
from unittest.mock import MagicMock, patch
from datetime import date

# Set up Django environment
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "debt_project.settings")
django.setup()

from debt_app.criteria_engine import assess_case

def print_test_header(name):
    print(f"\n{'='*60}")
    print(f" {name}")
    print(f"{'='*60}")

def verify_result(rule_id, results, expected_triggered, expected_severity=None):
    """Helper to find a rule in the results and verify its status."""
    all_rules = results.get("hard_blocks", []) + results.get("flags", []) + \
                results.get("info", []) + results.get("passed", [])
    
    match = next((r for r in all_rules if r.rule_id == rule_id), None)
    
    if not match:
        print(f"FAIL: Rule {rule_id} not found in results")
        return False

    triggered = match.triggered
    severity = match.severity
    
    status = "PASS"
    if triggered != expected_triggered:
        status = "FAIL"
    if expected_severity and severity != expected_severity:
        # If expected is 'pass', triggered=False is enough
        if expected_severity == "pass" and not triggered:
            pass
        else:
            status = "FAIL"
        
    print(f"[{status}] {rule_id}: triggered={triggered}, severity={severity}")
    print(f"      Message: {match.message}")
    return status == "PASS"

def get_mock_criteria(name="Generic Creditor"):
    """Helper to create a mock CreditorCriteria with sensible defaults."""
    mock_criteria = MagicMock()
    mock_criteria.creditor_name = name
    mock_criteria.blocked_until_cleared = False
    mock_criteria.blocked_reason = None
    mock_criteria.reject_if_never_made_payment = False
    mock_criteria.vehicle_arrears_repossession_months = None
    mock_criteria.reject_if_client_still_has_asset = False
    mock_criteria.requires_arrangement_call_before_proposing = False
    mock_criteria.fees_cap_percentage = None
    mock_criteria.reject_if_majority_share_exceeds_pct = None
    mock_criteria.reject_if_second_iva = False
    mock_criteria.min_dividend_pence = None
    mock_criteria.reject_if_debt_repayable_within_months = None
    mock_criteria.requires_pg_called_up = False
    return mock_criteria

def test_1_property_parsing():
    print_test_header("TEST 1 — Property parsing fix (Issue 1)")
    # Input: payload with property nested under "property" key, owns_property=true, 
    # property_value=200000.0, mortgage_balance=100000.0, total_debt=30000.0 
    # Expected: TIG-16 fires as hard_block (equity at 85% LTV = 70000 > 30000)
    
    payload = {
        "property": {
            "owns_property": True,
            "property_value": 200000.0,
            "mortgage_balance": 100000.0
        },
        "creditors": [
            {"creditor_name": "Creditor 1", "balance": 30000.0, "debt_type": "personal_loan"}
        ]
    }
    
    mock_criteria = get_mock_criteria()
    with patch("debt_app.helpers.get_creditor_by_trading_name", return_value=mock_criteria):
        with patch("debt_app.models.CreditorCriteria.objects.filter") as mock_filter:
            mock_filter.return_value.all.return_value = []
            mock_filter.return_value.values_list.return_value = []
            with patch("debt_app.models.CouncilRule.objects.get") as mock_council:
                mock_council.side_effect = Exception("DoesNotExist")
                result = assess_case(payload, detected_representatives=set())
        
    verify_result("TIG-16", result, expected_triggered=True, expected_severity="hard_block")

def test_2_no_property_regression():
    print_test_header("TEST 2 — Property parsing with no property (Issue 1 regression)")
    # Input: payload with "property": {"owns_property": false, "property_value": null} 
    # Expected: TIG-16 passes with "No property" message
    
    payload = {
        "property": {
            "owns_property": False,
            "property_value": None
        },
        "creditors": [
            {"creditor_name": "Creditor 1", "balance": 10000.0, "debt_type": "personal_loan"}
        ]
    }
    
    mock_criteria = get_mock_criteria()
    with patch("debt_app.helpers.get_creditor_by_trading_name", return_value=mock_criteria):
        with patch("debt_app.models.CreditorCriteria.objects.filter") as mock_filter:
            mock_filter.return_value.all.return_value = []
            mock_filter.return_value.values_list.return_value = []
            with patch("debt_app.models.CouncilRule.objects.get") as mock_council:
                mock_council.side_effect = Exception("DoesNotExist")
                result = assess_case(payload, detected_representatives=set())
        
    verify_result("TIG-16", result, expected_triggered=False, expected_severity="pass")

def test_3_link_financial_alias():
    print_test_header("TEST 3 — Link Financial alias (Issue 2)")
    # Input: creditor with name "link financial outsourcing" (no "limited") 
    # Expected: creditor does NOT resolve as CREDITOR-UNKNOWN
    
    payload = {
        "creditors": [
            {"creditor_name": "link financial outsourcing", "balance": 1000.0, "debt_type": "personal_loan"}
        ]
    }
    
    # Mock the criteria object that should be returned for Link Financial
    mock_criteria = get_mock_criteria("Link Financial - IVA")

    with patch("debt_app.helpers.get_creditor_by_trading_name") as mock_get_cred:
        mock_get_cred.return_value = mock_criteria
        with patch("debt_app.models.CreditorCriteria.objects.filter") as mock_filter:
            # Module 4 rules use this
            mock_filter.return_value.all.return_value = []
            # _check_creditor_individual uses values_list
            mock_filter.return_value.values_list.return_value = ["Link Financial - IVA"]
            with patch("debt_app.models.CouncilRule.objects.get") as mock_council:
                mock_council.side_effect = Exception("DoesNotExist")
                result = assess_case(payload, detected_representatives=set())
    
    # Check creditor_positions for CREDITOR-UNKNOWN
    positions = result.get("creditor_positions", [])
    unknown = any(f.get("code") == "CREDITOR-UNKNOWN" for p in positions for f in p.get("findings", []))
    
    if not unknown and len(positions) > 0:
        print("[PASS] Link Financial resolved correctly (not UNKNOWN)")
    else:
        print("[FAIL] Link Financial failed to resolve or was UNKNOWN")
        for p in positions:
            print(f"      Creditor: {p['creditor_name']}, Status: {p['effective_status']}")

def test_4_tig05_fallback():
    print_test_header("TEST 4 — TIG-05 is_employed fallback (Issue 7)")
    # Input: is_employed=true, income_source="full_time", has_job=false, no documents 
    # Expected: TIG-05 fires as hard_block
    
    payload = {
        "is_employed": True,
        "income_source": "full_time",
        "has_job": False,
        "documents": [],
        "creditors": [
            {"creditor_name": "Creditor 1", "balance": 10000.0, "debt_type": "personal_loan"}
        ]
    }
    
    mock_criteria = get_mock_criteria()
    with patch("debt_app.helpers.get_creditor_by_trading_name", return_value=mock_criteria):
        with patch("debt_app.models.CreditorCriteria.objects.filter") as mock_filter:
            mock_filter.return_value.all.return_value = []
            mock_filter.return_value.values_list.return_value = []
            with patch("debt_app.models.CouncilRule.objects.get") as mock_council:
                mock_council.side_effect = Exception("DoesNotExist")
                result = assess_case(payload, detected_representatives=set())
        
    verify_result("TIG-05", result, expected_triggered=True, expected_severity="hard_block")

def test_5_watch_22_6_uncategorised():
    print_test_header("TEST 5 — WATCH-22.6 uncategorised transactions (Issue 10)")
    # Input: gold_transactions with money_out entries that have no category field, 
    # detected_representatives={"WATCH"} 
    # Expected: WATCH-22.6 does NOT fire as a flag (should be info or pass)
    
    payload = {
        "gold_transactions": [
            {
                "transaction_type": "money_out",
                "amount": 1000.0,
                "transaction_date": date.today().isoformat(),
                "description": "Unknown Spend"
                # category is missing
            }
        ],
        "financial_summary": {
            "total_income": 2000.0,
            "net_balance": 100.0
        },
        "creditors": [
            {"creditor_name": "Creditor 1", "balance": 10000.0, "debt_type": "personal_loan"}
        ]
    }
    
    mock_criteria = get_mock_criteria()
    with patch("debt_app.helpers.get_creditor_by_trading_name", return_value=mock_criteria):
        with patch("debt_app.models.CreditorCriteria.objects.filter") as mock_filter:
            mock_filter.return_value.all.return_value = []
            mock_filter.return_value.values_list.return_value = []
            with patch("debt_app.models.CouncilRule.objects.get") as mock_council:
                mock_council.side_effect = Exception("DoesNotExist")
                result = assess_case(payload, detected_representatives={"WATCH"})
        
    verify_result("WATCH-22.6", result, expected_triggered=False, expected_severity="info")

if __name__ == "__main__":
    try:
        test_1_property_parsing()
        test_2_no_property_regression()
        test_3_link_financial_alias()
        test_4_tig05_fallback()
        test_5_watch_22_6_uncategorised()
        print("\nAll verification tests completed.")
    except Exception as e:
        print(f"\nAn error occurred during verification: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
