"""
Helper functions for criteria management
"""
from decimal import Decimal
from django.utils import timezone
from .models import GlobalCriteria, CriteriaDecision, CreditorCriteria


def get_rule_threshold(rule_key: str) -> Decimal:
    """Retrieve a rule's threshold value by key."""
    try:
        rule = GlobalCriteria.objects.get(rule_key=rule_key, is_active=True)
        return rule.threshold_value
    except GlobalCriteria.DoesNotExist:
        raise ValueError(f"Rule '{rule_key}' not found or is inactive")


def get_majority_threshold() -> Decimal:
    """Get the majority creditor threshold (75% by default)."""
    return get_rule_threshold('majority_threshold')


def log_criteria_decision(application_id: str, client_name: str, 
                         input_data: dict, output_data: dict,
                         recommendation: str, passes_hard_blocks: bool,
                         triggered_by=None, source: str = 'STANDALONE') -> CriteriaDecision:
    """Log a criteria assessment decision."""
    return CriteriaDecision.objects.create(
        application_id=application_id,
        client_name=client_name,
        input_snapshot=input_data,
        decision_output=output_data,
        recommended_solution=recommendation,
        passes_all_hard_blocks=passes_hard_blocks,
        triggered_by=triggered_by,
        source=source
    )


def get_creditor_by_trading_name(name: str) -> CreditorCriteria:
    """Find a creditor by name or trading name."""
    # First try exact match on name
    try:
        return CreditorCriteria.objects.get(name=name, is_active=True)
    except CreditorCriteria.DoesNotExist:
        pass
    
    # Then try partial match on trading_names
    creditors = CreditorCriteria.objects.filter(is_active=True)
    for creditor in creditors:
        if creditor.trading_names and name in creditor.trading_names:
            return creditor
    
    raise CreditorCriteria.DoesNotExist(f"No active creditor found for '{name}'")


def check_parent_group_conflict(client_bank_account: str, debtor_creditors: list) -> bool:
    """
    Check if client has a current account with same parent group as any debtor creditor.
    Returns True if conflict found.
    """
    account_bank = CreditorCriteria.objects.filter(
        name=client_bank_account,
        is_active=True
    ).first()
    
    if not account_bank or not account_bank.parent_group:
        return False
    
    # Check if any debtor creditor is in same parent group
    conflicting = CreditorCriteria.objects.filter(
        name__in=debtor_creditors,
        parent_group=account_bank.parent_group,
        is_active=True
    ).exists()
    
    return conflicting


def get_criteria_decisions_for_application(application_id: str):
    """Retrieve all decisions for an application."""
    return CriteriaDecision.objects.filter(
        application_id=application_id
    ).order_by('-triggered_at')


def get_rule_by_criteria_set(criteria_set: str):
    """Get all active rules for a criteria set."""
    return GlobalCriteria.objects.filter(
        criteria_set=criteria_set,
        is_active=True
    ).order_by('severity')
