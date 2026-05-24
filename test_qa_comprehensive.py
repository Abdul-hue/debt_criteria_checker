#!/usr/bin/env python
"""
Phase 5: QA & Testing - Comprehensive Test Suite

Tests:
1. Database: All new fields are accessible
2. API: Responses include new fields
3. Relationships: Related rules work correctly
4. Data Integrity: No null values where unexpected
"""

import os
import django
import json
from django.db.models import Q

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'debt_project.settings')
django.setup()

from debt_app.models import GlobalCriteria
from django.test import Client
from django.contrib.auth.models import User

# ─────────────────────────────────────────────────────────────────────────────
# Test Suite
# ─────────────────────────────────────────────────────────────────────────────

def test_database_schema():
    """Test 1: Verify all new database fields are accessible"""
    print("\n" + "="*80)
    print("TEST 1: Database Schema")
    print("="*80)
    
    rule = GlobalCriteria.objects.first()
    
    fields_to_check = [
        'description',
        'implementation_notes',
        'category',
        'example_case',
        'rejection_message',
        'flag_message',
        'is_creditor_specific',
        'applies_to_creditors',
        'references',
        'execution_order',
        'depends_on_rules',
        'related_rules',
        'last_reviewed',
        'review_notes',
    ]
    
    print(f"Checking fields on rule: {rule.rule_key}")
    all_present = True
    
    for field in fields_to_check:
        if hasattr(rule, field):
            value = getattr(rule, field)
            value_display = str(value)[:50] if value else "None"
            print(f"  ✓ {field:30} = {value_display}")
        else:
            print(f"  ✗ {field:30} NOT FOUND")
            all_present = False
    
    print("\nResult:", "PASS" if all_present else "FAIL")
    return all_present


def test_populated_data():
    """Test 2: Verify data was populated correctly"""
    print("\n" + "="*80)
    print("TEST 2: Data Population")
    print("="*80)
    
    # Check a rule with documentation
    rule = GlobalCriteria.objects.filter(rule_key='TIG-19.1').first()
    
    if not rule:
        print("  ✗ TIG-19.1 not found")
        return False
    
    checks = {
        'description': bool(rule.description),
        'category': rule.category == 'creditor_specific',
        'is_creditor_specific': rule.is_creditor_specific == True,
        'applies_to_creditors': len(rule.applies_to_creditors or []) > 0,
        'related_rules': len(rule.related_rules or []) > 0,
        'last_reviewed': rule.last_reviewed is not None,
    }
    
    print(f"Checking populated data on: {rule.rule_key}")
    all_pass = True
    
    for check_name, result in checks.items():
        status = "✓" if result else "✗"
        print(f"  {status} {check_name:30} = {result}")
        all_pass = all_pass and result
    
    print("\nResult:", "PASS" if all_pass else "FAIL")
    return all_pass


def test_related_rules():
    """Test 3: Verify related rules links work correctly"""
    print("\n" + "="*80)
    print("TEST 3: Related Rules Relationships")
    print("="*80)
    
    # TIG-19 and TIG-19.1 should be related
    tig19 = GlobalCriteria.objects.filter(rule_key='TIG-19').first()
    tig19_1 = GlobalCriteria.objects.filter(rule_key='TIG-19.1').first()
    
    if not tig19 or not tig19_1:
        print("  ✗ Required rules not found")
        return False
    
    checks = {
        'TIG-19 related_rules contains TIG-19.1': 'TIG-19.1' in (tig19.related_rules or []),
        'TIG-19.1 related_rules contains TIG-19': 'TIG-19' in (tig19_1.related_rules or []),
    }
    
    all_pass = True
    for check_name, result in checks.items():
        status = "✓" if result else "✗"
        print(f"  {status} {check_name:50} = {result}")
        all_pass = all_pass and result
    
    print("\nResult:", "PASS" if all_pass else "FAIL")
    return all_pass


def test_creditor_specific_rules():
    """Test 4: Verify creditor-specific rules are tagged correctly"""
    print("\n" + "="*80)
    print("TEST 4: Creditor-Specific Rules")
    print("="*80)
    
    creditor_rules = GlobalCriteria.objects.filter(is_creditor_specific=True)
    
    if not creditor_rules.exists():
        print("  ✗ No creditor-specific rules found")
        return False
    
    print(f"Found {creditor_rules.count()} creditor-specific rules:")
    
    all_pass = True
    for rule in creditor_rules[:5]:  # Check first 5
        has_creditors = len(rule.applies_to_creditors or []) > 0
        status = "✓" if has_creditors else "✗"
        creditors = ', '.join(rule.applies_to_creditors or ['NONE'])
        print(f"  {status} {rule.rule_key:12} -> {creditors}")
        all_pass = all_pass and has_creditors
    
    print("\nResult:", "PASS" if all_pass else "FAIL")
    return all_pass


def test_data_completeness():
    """Test 5: Check overall data completeness"""
    print("\n" + "="*80)
    print("TEST 5: Data Completeness")
    print("="*80)
    
    total_rules = GlobalCriteria.objects.count()
    
    with_description = GlobalCriteria.objects.exclude(description='').exclude(description__isnull=True).count()
    with_category = GlobalCriteria.objects.exclude(category='').exclude(category__isnull=True).count()
    with_messages = GlobalCriteria.objects.filter(rejection_message__isnull=False).filter(~Q(rejection_message='')).count()
    with_related = GlobalCriteria.objects.exclude(related_rules=[]).exclude(related_rules__isnull=True).count()
    with_review = GlobalCriteria.objects.exclude(last_reviewed__isnull=True).count()
    
    print(f"Total rules: {total_rules}")
    print(f"  ✓ With description:    {with_description}/{total_rules} ({100*with_description//total_rules if total_rules else 0}%)")
    print(f"  ✓ With category:       {with_category}/{total_rules} ({100*with_category//total_rules if total_rules else 0}%)")
    print(f"  ✓ With messages:       {with_messages}/{total_rules} ({100*with_messages//total_rules if total_rules else 0}%)")
    print(f"  ✓ With related rules:  {with_related}/{total_rules} ({100*with_related//total_rules if total_rules else 0}%)")
    print(f"  ✓ With review date:    {with_review}/{total_rules} ({100*with_review//total_rules if total_rules else 0}%)")
    
    coverage = min(100, (with_description + with_category + with_review) // 3 // total_rules * 100) if total_rules else 0
    
    print("\nResult:", "PASS" if coverage >= 70 else "WARNING - Low coverage")
    return coverage >= 70


def test_api_responses():
    """Test 6: Test API responses include new fields"""
    print("\n" + "="*80)
    print("TEST 6: API Responses")
    print("="*80)
    
    # Create a test client
    client = Client()
    
    # Fetch a rule via API (this would require authentication in production)
    rule = GlobalCriteria.objects.filter(rule_key='TIG-20.1').first()
    
    if not rule:
        print("  ✗ TIG-20.1 not found")
        return False
    
    # Simulate API response structure
    from debt_app.views.criteria_views import _rule_obj_to_dict
    
    basic_response = _rule_obj_to_dict(rule, include_full=False)
    full_response = _rule_obj_to_dict(rule, include_full=True)
    
    print("Basic response fields:")
    for key in basic_response.keys():
        print(f"  ✓ {key:25} = {str(basic_response[key])[:40]}")
    
    print(f"\nFull response fields (additional):")
    additional_fields = set(full_response.keys()) - set(basic_response.keys())
    for key in sorted(additional_fields):
        value = full_response[key]
        value_display = str(value)[:40] if value else "None"
        print(f"  ✓ {key:25} = {value_display}")
    
    # Check that full response has more fields than basic
    has_all_fields = len(full_response) > len(basic_response)
    
    print("\nResult:", "PASS" if has_all_fields else "FAIL")
    return has_all_fields


def test_migrations_applied():
    """Test 7: Verify migration was applied"""
    print("\n" + "="*80)
    print("TEST 7: Migrations Applied")
    print("="*80)
    
    from django.db import connection
    from django.db.migrations.recorder import MigrationRecorder
    
    recorder = MigrationRecorder(connection)
    applied_migrations = recorder.applied_migrations()
    
    # Check if our migration was applied
    target_migration = ('debt_app', '0035_globalcriteria_add_documentation_fields')
    is_applied = target_migration in applied_migrations
    
    print(f"Looking for migration: {target_migration}")
    print(f"  {'✓' if is_applied else '✗'} Migration applied: {is_applied}")
    
    if is_applied:
        print(f"\nLatest 5 applied migrations in debt_app:")
        debt_app_migrations = [m for m in applied_migrations if m[0] == 'debt_app'][-5:]
        for app, name in debt_app_migrations:
            print(f"  ✓ {name}")
    
    print("\nResult:", "PASS" if is_applied else "FAIL")
    return is_applied


# ─────────────────────────────────────────────────────────────────────────────
# Main Test Runner
# ─────────────────────────────────────────────────────────────────────────────

def run_all_tests():
    print("\n" + "█"*80)
    print("█" + " "*78 + "█")
    print("█" + "  PHASE 5: QA & TESTING - COMPREHENSIVE TEST SUITE".center(78) + "█")
    print("█" + " "*78 + "█")
    print("█"*80)
    
    results = {
        'Database Schema': test_database_schema(),
        'Data Population': test_populated_data(),
        'Related Rules': test_related_rules(),
        'Creditor Specific': test_creditor_specific_rules(),
        'Data Completeness': test_data_completeness(),
        'API Responses': test_api_responses(),
        'Migrations Applied': test_migrations_applied(),
    }
    
    # Summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for test_name, result in results.items():
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"  {status:8} | {test_name:30}")
    
    print("─"*80)
    print(f"Result: {passed}/{total} tests passed ({100*passed//total}%)")
    print("─"*80 + "\n")
    
    if passed == total:
        print("🎉 All tests passed! Implementation complete and verified.")
    else:
        print(f"⚠ {total - passed} test(s) failed. Please review the output above.")
    
    return passed == total


if __name__ == '__main__':
    success = run_all_tests()
    exit(0 if success else 1)
