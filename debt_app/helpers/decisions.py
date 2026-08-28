"""Reading and writing CriteriaDecision audit rows."""

from debt_app.models import CriteriaDecision, GlobalCriteria

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
