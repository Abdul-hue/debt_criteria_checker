"""
EXAMPLES: Real-world usage of the criteria models

This file demonstrates common operations with CreditorCriteria, GlobalCriteria,
and CriteriaDecision models.
"""

# ============================================================================
# CREDITOR CRITERIA EXAMPLES
# ============================================================================

from debt_app.models import CreditorCriteria, GlobalCriteria, CriteriaDecision
from django.contrib.auth.models import User
from decimal import Decimal


def example_create_creditor():
    """Create a new creditor with all fields populated."""
    creditor = CreditorCriteria.objects.create(
        name='Shop Direct Group',
        trading_names=['Very', 'Littlewoods', 'Littlewoods.com'],
        representative='WATCH',
        min_dividend_pence=30,
        contact_email='creditor@shopdirect.com',
        contact_phone='+44 151 555 0000',
        is_active=True,
        is_watch=True,
        is_tix=False,
        is_evolve=False,
        parent_group=None,
        updated_by=User.objects.first()
    )
    print(f"Created: {creditor}")
    return creditor


def example_find_creditor_by_trading_name():
    """Find a creditor using their trading name."""
    # Direct lookup
    try:
        creditor = CreditorCriteria.objects.get(
            trading_names__contains=['Littlewoods'],
            is_active=True
        )
        print(f"Found: {creditor}")
    except Exception as e:
        print(f"Not found: {e}")


def example_update_creditor_with_audit():
    """Update a creditor and track who made the change."""
    user = User.objects.get(username='admin')
    creditor = CreditorCriteria.objects.get(name='Lloyds Bank')
    creditor.min_dividend_pence = 35
    creditor.updated_by = user
    creditor.save()
    print(f"Updated: {creditor}, by {creditor.updated_by.username} at {creditor.last_updated}")


def example_filter_watch_list_creditors():
    """Get all creditors on the watch list."""
    watch_creditors = CreditorCriteria.objects.filter(
        is_watch=True,
        is_active=True
    ).order_by('name')
    print(f"Found {watch_creditors.count()} watch-listed creditors")
    for creditor in watch_creditors:
        print(f"  - {creditor.name} (min: {creditor.min_dividend_pence}p)")


def example_find_parent_group_members():
    """Identify all creditors in the same banking group."""
    lloyds_group = CreditorCriteria.objects.filter(
        parent_group='Lloyds Banking Group',
        is_active=True
    )
    print(f"Lloyds Banking Group creditors: {list(lloyds_group.values_list('name', flat=True))}")
    # Output: ['Lloyds', 'MBNA', 'Scottish Widows']


def example_check_banking_conflict(client_bank, creditor_names):
    """
    Check if client's banking relationship conflicts with any creditors.
    E.g., Has Lloyds current account + owes money to MBNA (same group).
    """
    account_bank = CreditorCriteria.objects.filter(
        name=client_bank,
        is_active=True
    ).first()
    
    if not account_bank or not account_bank.parent_group:
        return False
    
    # Check for conflict
    conflict = CreditorCriteria.objects.filter(
        name__in=creditor_names,
        parent_group=account_bank.parent_group,
        is_active=True
    ).exists()
    
    return conflict


# ============================================================================
# GLOBAL CRITERIA EXAMPLES
# ============================================================================

def example_get_majority_threshold():
    """Retrieve the configurable majority creditor threshold."""
    from debt_app.helpers import get_majority_threshold
    threshold = get_majority_threshold()
    print(f"Majority creditor threshold: {threshold}% of total debt")
    # Output: 75.00


def example_update_threshold():
    """Update a threshold without touching code (key feature)."""
    rule = GlobalCriteria.objects.get(rule_key='majority_threshold')
    old_value = rule.threshold_value
    rule.threshold_value = Decimal('80.00')  # Changed from 75% to 80%
    rule.updated_by = User.objects.get(username='compliance_manager')
    rule.save()
    print(f"Updated: {old_value} → {rule.threshold_value}")


def example_get_all_hard_block_rules():
    """Get all rules that should block loan approval."""
    hard_rules = GlobalCriteria.objects.filter(
        severity='hard_block',
        is_active=True
    ).order_by('criteria_set')
    
    for rule in hard_rules:
        print(f"{rule.rule_key}: {rule.rule_name}")
        if rule.threshold_value:
            print(f"  Threshold: {rule.threshold_value}")


def example_check_eligibility_for_criteria_set(criteria_set_name):
    """
    Get rules for a specific solution (e.g., check if client eligible for TIX).
    Returns all active rules for that solution type.
    """
    rules = GlobalCriteria.objects.filter(
        criteria_set=criteria_set_name,
        is_active=True
    ).order_by('severity')
    
    print(f"\nRules for {criteria_set_name}:")
    for rule in rules:
        print(f"  [{rule.severity}] {rule.rule_name}")
    
    return rules


def example_deactivate_rule():
    """Disable a rule without deleting it (maintains history)."""
    rule = GlobalCriteria.objects.get(rule_key='watch_single_creditor')
    rule.is_active = False
    rule.updated_by = User.objects.get(username='admin')
    rule.save()
    print(f"Deactivated rule: {rule.rule_key}")


# ============================================================================
# CRITERIA DECISION EXAMPLES
# ============================================================================

def example_log_assessment_decision():
    """Record a full criteria assessment decision."""
    user = User.objects.get(username='assessor_jenny')
    
    decision = CriteriaDecision.objects.create(
        application_id='ARY-2026-45821',
        client_name='John Smith',
        input_snapshot={
            'total_debt': 15000,
            'monthly_income': 2000,
            'creditors': ['Lloyds', 'Capital One', 'Very'],
            'creditor_breakdown': {
                'Lloyds': 11000,
                'Capital One': 3000,
                'Very': 1000
            }
        },
        decision_output={
            'recommendation': 'IVA',
            'hard_blocks_passed': True,
            'flags': [],
            'majority_threshold_check': 'PASS (73.3% < 75%)',
            'watch_list_check': 'PASS (no watch creditors)',
        },
        recommended_solution='IVA',
        passes_all_hard_blocks=True,
        triggered_by=user,
        source='CASE_ASSESSMENT'
    )
    print(f"Decision logged: {decision.id}")
    return decision


def example_retrieve_decision_history():
    """Get all decisions for a single application."""
    from debt_app.helpers import get_criteria_decisions_for_application
    
    decisions = get_criteria_decisions_for_application('ARY-2026-45821')
    print(f"Found {decisions.count()} decisions")
    
    for decision in decisions:
        print(f"  {decision.triggered_at}: {decision.recommended_solution}")
        print(f"    By: {decision.triggered_by.username}")


def example_audit_trail_for_case():
    """Build a complete audit trail for compliance review."""
    from django.utils import timezone
    from datetime import timedelta
    
    # Get decisions from last 7 days
    recent_decisions = CriteriaDecision.objects.filter(
        triggered_at__gte=timezone.now() - timedelta(days=7)
    ).order_by('-triggered_at')
    
    for decision in recent_decisions:
        print(f"\n{decision.application_id}: {decision.client_name}")
        print(f"  Time: {decision.triggered_at}")
        print(f"  Assessor: {decision.triggered_by.get_full_name() if decision.triggered_by else 'System'}")
        print(f"  Solution: {decision.recommended_solution}")
        print(f"  Passed hard blocks: {decision.passes_all_hard_blocks}")
        print(f"  Source: {decision.source}")


def example_search_decisions_by_recommendation():
    """Find all IVA recommendations from this month."""
    from django.utils import timezone
    from dateutil.relativedelta import relativedelta
    
    month_start = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    
    iva_decisions = CriteriaDecision.objects.filter(
        recommended_solution='IVA',
        triggered_at__gte=month_start
    )
    
    print(f"IVA recommendations this month: {iva_decisions.count()}")


def example_export_to_json():
    """Export decision data for reporting."""
    import json
    from django.forms.models import model_to_dict
    
    decision = CriteriaDecision.objects.get(id='uuid-here')
    
    export_data = {
        'id': str(decision.id),
        'application_id': decision.application_id,
        'client_name': decision.client_name,
        'recommendation': decision.recommended_solution,
        'assessment_date': decision.triggered_at.isoformat(),
        'assessment_by': decision.triggered_by.username,
        'input': decision.input_snapshot,
        'output': decision.decision_output,
    }
    
    json_string = json.dumps(export_data, indent=2)
    print(json_string)


# ============================================================================
# COMPLEX WORKFLOWS
# ============================================================================

def example_full_assessment_workflow(application_id, client_name, debt_data):
    """
    Complete workflow: check all criteria, make decision, log it.
    """
    from debt_app.helpers import (
        get_majority_threshold,
        check_parent_group_conflict,
        get_creditor_by_trading_name,
    )
    
    print(f"\nAssessing: {client_name}")
    print("=" * 50)
    
    # Step 1: Validate creditors exist
    creditor_names = debt_data['creditors']
    invalid_creditors = []
    for name in creditor_names:
        try:
            get_creditor_by_trading_name(name)
        except CreditorCriteria.DoesNotExist:
            invalid_creditors.append(name)
    
    if invalid_creditors:
        print(f"WARNING: Unknown creditors: {invalid_creditors}")
    
    # Step 2: Check majority threshold
    majority_threshold = get_majority_threshold()
    total_debt = sum(debt_data['amounts'].values())
    largest_debt = max(debt_data['amounts'].values())
    percentage = (largest_debt / total_debt * 100) if total_debt > 0 else 0
    
    passes_majority = percentage <= majority_threshold
    print(f"Majority check: {percentage:.1f}% vs {majority_threshold}% → {'PASS' if passes_majority else 'FAIL'}")
    
    # Step 3: Check parent group conflicts
    banking_conflicts = check_parent_group_conflict(
        debt_data.get('bank_account'),
        creditor_names
    )
    print(f"Banking conflict: {'YES' if banking_conflicts else 'NO'}")
    
    # Step 4: Check watch list
    watch_creditors = CreditorCriteria.objects.filter(
        name__in=creditor_names,
        is_watch=True
    )
    
    print(f"Watch-listed: {watch_creditors.count()} creditors")
    
    # Step 5: Determine recommendation
    if not passes_majority or banking_conflicts:
        recommendation = 'UNCLEAR'
        passes_hard_blocks = False
    elif watch_creditors.exists():
        recommendation = 'DMP'
        passes_hard_blocks = True
    else:
        recommendation = 'IVA'
        passes_hard_blocks = True
    
    print(f"Recommendation: {recommendation}")
    
    # Step 6: Log decision
    user = User.objects.get(username='auto_assessor')
    decision = CriteriaDecision.objects.create(
        application_id=application_id,
        client_name=client_name,
        input_snapshot=debt_data,
        decision_output={
            'majority_check': f"{percentage:.1f}%",
            'banking_conflict': banking_conflicts,
            'watch_creditors': list(watch_creditors.values_list('name', flat=True)),
        },
        recommended_solution=recommendation,
        passes_all_hard_blocks=passes_hard_blocks,
        triggered_by=user,
        source='STANDALONE'
    )
    
    print(f"Decision logged: {decision.id}")
    print("=" * 50)
    
    return decision


# ============================================================================
# RUNNING EXAMPLES
# ============================================================================

if __name__ == '__main__':
    # Uncomment to run examples (requires Django setup)
    
    # example_create_creditor()
    # example_filter_watch_list_creditors()
    # example_get_majority_threshold()
    # example_log_assessment_decision()
    # example_retrieve_decision_history()
    
    # Full workflow example
    # example_full_assessment_workflow(
    #     application_id='ARY-2026-12345',
    #     client_name='Test Client',
    #     debt_data={
    #         'creditors': ['Lloyds', 'Very', 'Capital One'],
    #         'amounts': {'Lloyds': 8000, 'Very': 1500, 'Capital One': 1000},
    #         'bank_account': 'Lloyds'
    #     }
    # )
