"""Helpers shared by more than one criteria view module.

Everything here is imported by at least two siblings; single-use helpers
stay in the module that uses them."""

from decimal import Decimal
from django.db.models import Q
from django.db.models import Count
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from debt_app.models import GlobalCriteria
from debt_app.models import CreditorOutcome
from debt_app.models import CreditorVoteSummary
from debt_app.services.crm_vote_sync import get_last_5_tally

def _rule_to_dict(r) -> dict:
    # Handle both object (from engine) and dict (after enrichment)
    if isinstance(r, dict):
        return {
            "rule_id": r.get("rule_id"),
            "severity": r.get("severity"),
            "triggered": r.get("triggered"),
            "message": r.get("message"),
            "threshold": r.get("threshold"),
            "actual_value": r.get("actual_value"),
            "creditors": r.get("creditors", []),
            "title": r.get("title"),
            "description": r.get("description"),
            "action": r.get("action"),
        }
    return {
        "rule_id": r.rule_id,
        "severity": r.severity,
        "triggered": r.triggered,
        "message": r.message,
        "threshold": r.threshold,
        "actual_value": r.actual_value,
    }


def _serialise_value(v):
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, set):
        return list(v)
    return v


def enrich_positions_with_tallies(creditor_positions):
    """
    Enriches creditor position objects with outcomes tally data
    and CRM vote summary statistics.
    The outcomes/summary lookups above are bulk queries (no N+1), but
    last_5_tally is fetched via get_last_5_tally() per creditor with a
    CreditorVoteSummary - see the performance note on that call below.
    """
    from django.db.models import Count, Q
    from debt_app.models import CreditorOutcome, CreditorVoteSummary

    criteria_ids = [pos.get("criteria_id") for pos in creditor_positions if pos.get("criteria_id")]

    tally_map = {}
    summary_map = {}
    summary_obj_map = {}
    if criteria_ids:
        # Outcomes from manual tracking
        outcomes = (
            CreditorOutcome.objects.filter(creditor_id__in=criteria_ids)
            .values('creditor_id')
            .annotate(
                approved_count=Count('id', filter=Q(outcome='approved')),
                disapproved_count=Count('id', filter=Q(outcome='disapproved')),
            )
        )
        for row in outcomes:
            cid = row['creditor_id']
            app = row['approved_count']
            dis = row['disapproved_count']
            tally_map[cid] = {
                "outcomes_approved": app,
                "outcomes_disapproved": dis,
                "outcomes_total": app + dis
            }

        # CRM vote summaries
        summaries = CreditorVoteSummary.objects.filter(creditor_criteria_id__in=criteria_ids)
        for s in summaries:
            summary_map[s.creditor_criteria_id] = {
                "crm_total_votes": s.total_votes or 0,
                "crm_accepted_count": s.accepted_count or 0,
                "crm_rejected_count": s.rejected_count or 0,
                "crm_modified_count": s.modified_count or 0,
                "crm_pod_count": s.pod_count or 0,
                "latest_vote_outcome": s.latest_vote_outcome,
                "latest_vote_date": s.latest_vote_date.isoformat() if s.latest_vote_date else None,
            }
            summary_obj_map[s.creditor_criteria_id] = s

    for pos in creditor_positions:
        cid = pos.get("criteria_id")
        
        # Populate Outcomes
        if cid and cid in tally_map:
            tally = tally_map[cid]
            pos["outcomes_approved"] = tally["outcomes_approved"]
            pos["outcomes_disapproved"] = tally["outcomes_disapproved"]
            pos["outcomes_total"] = tally["outcomes_total"]
        else:
            pos["outcomes_approved"] = 0
            pos["outcomes_disapproved"] = 0
            pos["outcomes_total"] = 0

        # Populate CRM vote summaries
        if cid and cid in summary_map:
            summary = summary_map[cid]
            pos["crm_total_votes"] = summary["crm_total_votes"]
            pos["crm_accepted_count"] = summary["crm_accepted_count"]
            pos["crm_rejected_count"] = summary["crm_rejected_count"]
            pos["crm_modified_count"] = summary["crm_modified_count"]
            pos["crm_pod_count"] = summary["crm_pod_count"]
            pos["latest_vote_outcome"] = summary["latest_vote_outcome"]
            pos["latest_vote_date"] = summary["latest_vote_date"]
            # get_last_5_tally() issues its own CreditorVoteChangeEvent query
            # per call (see performance note in Prompt 17) - one extra query
            # per creditor that has a CreditorVoteSummary, on top of the two
            # bulk queries above.
            pos["last_5_tally"] = get_last_5_tally(summary_obj_map[cid])
        else:
            pos["crm_total_votes"] = 0
            pos["crm_accepted_count"] = 0
            pos["crm_rejected_count"] = 0
            pos["crm_modified_count"] = 0
            pos["crm_pod_count"] = 0
            pos["latest_vote_outcome"] = None
            pos["latest_vote_date"] = None
            pos["last_5_tally"] = None


def error_response(message: str, code: str, status_code: int):
    return Response(
        {"success": False, "error": message, "code": code},
        status=status_code
    )


class AssessRateThrottle(UserRateThrottle):
    scope = 'assess'


def enrich_rules_with_meta(rule_list):
    """
    Takes a list of RuleResult objects or dicts and adds
    description and action from GlobalCriteria.
    Returns a list of dictionaries.
    """
    if not rule_list:
        return []
        
    # Build a lookup once - handle both objects and dicts
    rule_keys = []
    for r in rule_list:
        if hasattr(r, 'rule_id'):
            rule_keys.append(r.rule_id)
        elif isinstance(r, dict):
            rule_keys.append(r.get('rule_id'))
            
    criteria = GlobalCriteria.objects.filter(
        rule_key__in=rule_keys
    ).values('rule_key', 'rule_name', 'description', 'action')
    
    meta_map = {c['rule_key']: c for c in criteria}
    
    enriched = []
    for r in rule_list:
        # Get rule_id based on type
        rid = r.rule_id if hasattr(r, 'rule_id') else r.get('rule_id')
        meta = meta_map.get(rid, {})
        
        # Convert to dict if it's an object
        if hasattr(r, 'rule_id'):
            r_dict = {
                "rule_id": r.rule_id,
                "severity": r.severity,
                "triggered": r.triggered,
                "message": r.message,
                "threshold": r.threshold,
                "actual_value": r.actual_value,
                "creditors": r.creditors if hasattr(r, 'creditors') else [],
            }
        else:
            r_dict = {**r}

        # Add enrichment
        r_dict.update({
            'title': meta.get('rule_name') or rid,
            'rule_name': meta.get('rule_name') or rid,
            'description': meta.get('description') or None,
            'action': meta.get('action') or None,
        })
        enriched.append(r_dict)
        
    return enriched
