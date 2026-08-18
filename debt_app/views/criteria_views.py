import logging
from datetime import timedelta
from decimal import Decimal
from django.contrib.auth.models import User
from django.db.models import Q, Count
from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework import status
from rest_framework.parsers import MultiPartParser, FormParser
from django.conf import settings as django_settings
from rest_framework.permissions import AllowAny, BasePermission, IsAuthenticated, IsAdminUser
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication

from debt_app.aryza_client import (
    fetch_case_by_reference,
    AryzaCaseNotFoundError,
    AryzaConnectionError,
    AryaTimeoutError,
    AryzaDataError,
)
from debt_app.criteria_engine import (
    assess_case,
    detect_representatives,
    _sanitize_dmp_checklist,
)
from debt_app.recommendation_engine import get_recommendation
from debt_app.helpers import (
    GlobalCriteria, CreditorCriteria, CriteriaDecision, CouncilRule,
    Application, EvidenceLedger, Voter,
    get_user_department, filter_by_department,
)
from debt_app.permissions import HasFeatureAccess, HasWritePermission, HasReadPermission
from debt_app.models import (
    GuidelineCategory, ExpenditureGuideline, CreditReport,
    DepartmentRuleVisibility, DepartmentCreditorVisibility, DepartmentCouncilVisibility,
    DepartmentSFSVisibility, CreditorOutcome, CriteriaAuditLog,
    CountyCouncil, CreditorVoteSummary, CrmSyncRun, CreditorVoteChangeEvent,
    CreditorMocAlert, CreditorNonAcceptMilestone,
)
from debt_app.credit_report_extractor import extract_credit_report, normalise_start_date_iso
from debt_app.services.crm_vote_sync import run_crm_vote_sync, get_recent_vote_tally, get_last_5_tally
import threading

logger = logging.getLogger(__name__)


def _lookup_creditor_name(raw_name: str) -> str:
    """
    Resolve a raw Aryza creditor name using ONLY the explicit alias map.
    
    This performs a single, deterministic lookup without fuzzy matching.
    The engine's CREDITOR_ALIAS_MAP is authoritative — no estimation or 
    fuzzy logic is applied here.
    
    Returns the mapped name from CREDITOR_ALIAS_MAP, or the raw name 
    if no mapping exists. The engine will attempt internal resolution.
    """
    from debt_app.helpers import CREDITOR_ALIAS_MAP
    
    normalized = raw_name.strip().lower()
    mapped = CREDITOR_ALIAS_MAP.get(normalized)
    
    if mapped:
        logger.warning(f"[RESOLVE ALIAS] '{raw_name}' → '{mapped}'")
        return mapped
    
    logger.warning(f"[RESOLVE UNMAPPED] '{raw_name}' — no alias, passing raw")
    return raw_name


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


def build_phase7_response_fields(result: dict) -> dict:
    """Serialize assess_case result into a JSON-safe dict suitable for API responses."""
    def _rules(lst):
        return [_rule_to_dict(r) for r in lst]

    def _serialise_dict(d):
        if d is None:
            return None
        return {k: _serialise_value(v) for k, v in d.items()}

    return {
        "overall": result.get("overall"),
        "overall_status": result.get("overall_status"),
        "passes_all_hard_blocks": result.get("passes_all_hard_blocks"),
        "recommended_solution": result.get("recommended_solution"),
        "alternative_solutions": result.get("alternative_solutions", []),
        "tig_eligible": result.get("tig_eligible"),
        "hard_blocks": _rules(result.get("hard_blocks", [])),
        "flags": _rules(result.get("flags", [])),
        "info": _rules(result.get("info", [])),
        "passed": _rules(result.get("passed", [])),
        "creditor_positions": [
            {
                **pos,
                "balance": float(pos["balance"]) if isinstance(pos["balance"], Decimal) else pos["balance"],
            }
            for pos in result.get("creditor_positions", [])
        ],
        "council_positions": result.get("council_positions", []),
        "majority_analysis": _serialise_dict(result.get("majority_analysis")),
        "dividend_analysis": result.get("dividend_analysis"),
        "representatives_detected": list(result.get("representatives_detected") or []),
        "dmp_eligibility": result.get("dmp_eligibility"),
        "hmrc_is_creditor": result.get("hmrc_is_creditor", False),
    }


def error_response(message: str, code: str, status_code: int):
    return Response(
        {"success": False, "error": message, "code": code},
        status=status_code
    )


class AssessRateThrottle(UserRateThrottle):
    scope = 'assess'


# DMP Eligibility Checklist fields. _evaluate_dmp_eligibility (criteria_engine.py)
# reads this full flat dict unchanged regardless of source — see build_dmp_checklist()
# below, which merges per-creditor-row dropdown selections with the remaining
# case-level checkboxes that have no reliable per-creditor signal.
DMP_CHECKLIST_FIELDS = [
    "current_year_council_tax",
    "previous_year_council_tax",
    "lost_right_to_pay_instalments",
    "current_gas_bill",
    "current_electric_bill",
    "previous_gas_provider_debt",
    "previous_electric_provider_debt",
    "current_water_bill",
    "council_parking_fine",
    "private_parking_debt",
    "current_phone_contract",
]

# Case-level checkboxes (Part 4 of the Aryza-only DMP redesign) — kept as a
# compact checklist since no reliable per-creditor signal exists for these:
# no gas/electric distinguishing signal in Aryza data, and
# lost_right_to_pay_instalments is a case-level fact, never per-row.
DMP_CASE_LEVEL_CHECKLIST_FIELDS = [
    "current_gas_bill",
    "current_electric_bill",
    "previous_gas_provider_debt",
    "previous_electric_provider_debt",
    "current_phone_contract",
    "lost_right_to_pay_instalments",
    # HMRC VAT (only offered when hmrc_is_creditor is true). hmrc_debt_has_vat is
    # the parent tick; hmrc_previous_year_vat is the only one that drives
    # behaviour — a confirmed previous-year VAT debt forces the case to DMP
    # (see _derive_recommended_solution). These flow through the flat checklist
    # dict but are read by _derive_recommended_solution, NOT by
    # _evaluate_dmp_eligibility (which only reads its own DMP_CHECKLIST_FIELDS).
    "hmrc_debt_has_vat",
    "hmrc_previous_year_vat",
]


def build_dmp_checklist(creditor_rows, case_level_raw):
    """
    Builds the flat DMP_CHECKLIST_FIELDS dict _evaluate_dmp_eligibility reads,
    combining (a) per-row dropdown selections from the Creditor Positions table
    and (b) the remaining DMP_CASE_LEVEL_CHECKLIST_FIELDS checkboxes.

    creditor_rows: list of {"debt_type_normalised": str, "value": str|None} —
      one entry per row where the caseworker made a dropdown selection.
      council_tax value: "current" | "previous"
      water value:       "current"
      pcn value:         "council" | "private"
      mobile value:      "current"
      A row left "Not set" (value None/absent) contributes nothing.
    case_level_raw: dict of the 6 DMP_CASE_LEVEL_CHECKLIST_FIELDS checkboxes.

    Multiple rows of the same type OR together (e.g. two council-tax rows,
    one "current" and one "previous", both set their respective flag True) —
    _evaluate_dmp_eligibility only reads case-wide booleans, not per-creditor
    identity, so this is the correct aggregation.
    """
    checklist = {field: False for field in DMP_CHECKLIST_FIELDS}
    for field in DMP_CASE_LEVEL_CHECKLIST_FIELDS:
        checklist[field] = bool((case_level_raw or {}).get(field, False))

    for row in creditor_rows or []:
        debt_type = row.get("debt_type_normalised") or row.get("type")
        value = row.get("value") or row.get("selection")
        if not value:
            continue
        if debt_type == "council_tax":
            if value == "current":
                checklist["current_year_council_tax"] = True
            elif value == "previous":
                checklist["previous_year_council_tax"] = True
        elif debt_type == "utility" and value == "current":
            # Water toggle is scoped to water-supplier names on the frontend
            # (DEBT_TYPE_UTILITY rows whose creditor_name matches a water
            # supplier) — see WATER_SUPPLIER_NAMES in the row-rendering logic.
            checklist["current_water_bill"] = True
        elif debt_type == "pcn":
            if value == "council":
                checklist["council_parking_fine"] = True
            elif value == "private":
                checklist["private_parking_debt"] = True
        elif debt_type == "mobile" and value == "current":
            checklist["current_phone_contract"] = True

    # Server-side guard: hmrc_previous_year_vat is only honoured when its parent
    # hmrc_debt_has_vat is also true. The frontend enforces this by only showing
    # the child tick once the parent is set, but a raw API call can submit the
    # child alone — and that tick is the highest-precedence forced-DMP override.
    # See _sanitize_dmp_checklist in criteria_engine.py.
    return _sanitize_dmp_checklist(checklist)


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


def build_creditor_list() -> list:
    """
    Load all active CreditorCriteria records and convert to
    the creditor_list format expected by assess_case().
    """
    creditors = []
    for c in CreditorCriteria.objects.filter(is_active=True):
        creditors.append({
            "creditor_name":  c.creditor_name,
            "trading_names":  c.trading_names or [],
            "representative": c.representative or "",
            "min_dividend":   c.min_dividend_pence or 0,
            "parent_group":   c.parent_group or None,
        })
    return creditors


def build_uploaded_docs(aryza_reference: str) -> dict:
    """
    Returns empty document defaults.

    TODO: When Zubair's CA integration is complete,
    query EvidenceLedger by aryza_reference and map
    verified documents to this structure.
    """
    return {
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


class AssessCaseView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [AssessRateThrottle]

    def _prepare_engine_payload(self, case_data_obj, credit_report_id=None):
        """
        Transforms Aryza CaseData object into the payload format expected by the criteria engine.

        Converts pence (int) to pounds (float).
        Excludes secured debt types (mortgage, hp, etc).
        Deduplicates on (creditor_name, debt_type, reference) — same name + type + reference = skip.
        Applies CREDITOR_ALIAS_MAP to resolve names BEFORE passing to engine.
        This ensures detect_representatives() matches correctly.

        credit_report_id: when given, pins credit-report enrichment to this EXACT
          CreditReport row (e.g. the id returned by upload-credit-report) instead of
          re-selecting among every historical extraction for this aryza_reference.

        Returns: (payload, prepared_creditors)
          payload: dict for assess_case()
          prepared_creditors: list of creditor dicts, used for ACCEPT creditor restoration
        """
        from rapidfuzz import fuzz, process as rfprocess
        from debt_app.helpers import CREDITOR_ALIAS_MAP, normalise_creditor_name, normalise_debt_type, _SECURED_TYPES
        from debt_app.models import CountyCouncilRouting

        # Secured/unsecured classification uses the SAME normalise_debt_type()
        # helper the engine uses everywhere else (helpers.py) — this used to be
        # a hand-rolled exact-match set here that missed real Aryza values like
        # "Car HP" (space-separated, not the literal string "hp"), which let a
        # £17,007 secured car-finance debt get counted into the unsecured total.
        # One classifier, one place it can go wrong, instead of three.

        # Convert pence to pounds for all financial fields.
        # Never produce a negative DI — income=0 means fact find is incomplete,
        # not that the client owes money every month.
        _income_total_pence = (case_data_obj.income or {}).get("total", 0) or 0
        _expenditure_total_pence = (case_data_obj.expenditure or {}).get("total", 0) or 0
        if _income_total_pence > 0 and _expenditure_total_pence > 0:
            di_pounds = max(0, _income_total_pence - _expenditure_total_pence) / 100.0
        elif _income_total_pence > 0:
            di_pounds = 0.0  # income present but no SFS expenses yet
        else:
            # No income rows in client_income — fall back to Aryza's pre-computed DI
            # (td_client.td_contribution), already clamped to >= 0 by _calculate_totals.
            di_pounds = max(0, case_data_obj.disposable_income) / 100.0
        
        # Deduplication on (name, type, reference) — same entry only counted once
        seen_keys = set()
        prepared_creditors = []
        unsecured_debt_pounds = 0

        raw_creditors = case_data_obj.creditors or []

        # DB name lists — queried once before the loop, never per-creditor
        council_names = list(CouncilRule.objects.values_list('council_name', flat=True))
        county_names = list(CountyCouncilRouting.objects.values_list('county_name', flat=True))
        creditor_db_names = list(CreditorCriteria.objects.filter(is_active=True).values_list('creditor_name', flat=True))

        for creditor in raw_creditors:
            raw_name = (creditor.get('name') or '').strip()
            if not raw_name:
                continue

            debt_type = (creditor.get('type') or creditor.get('creditor_type') or '').strip().lower()
            ref = (creditor.get('ref') or creditor.get('reference') or '').strip().lower()

            # STEP 4 — secured/unsecured classification. The creditor is still
            # KEPT in prepared_creditors (so it shows up in the Creditor
            # Positions table, e.g. as "Does Not Vote") — it's just excluded
            # from unsecured_debt_pounds below. This mirrors how the
            # case-assessment tool sends secured debts: visible, tagged,
            # excluded from the unsecured total — rather than silently
            # disappearing from the creditor list.
            is_secured = normalise_debt_type(debt_type) in _SECURED_TYPES
            if is_secured:
                logger.warning(
                    f"[SECURED — excluded from unsecured total] '{raw_name}' type='{debt_type}'"
                )

            # --- 5-check name resolution waterfall ---
            resolved_name = raw_name
            debt_type_override = None

            # CHECK 1 — CouncilRule match (exact + '&'/'and' + suffix-strip).
            # NB: the old fuzz.partial_ratio>=85 matched on the shared
            # 'City Council' substring and mis-mapped e.g.
            # 'Brighton & Hove City Council' -> 'Derby City Council'. Use the same
            # robust resolver the engine uses at assessment so both agree.
            from debt_app.criteria_engine import _match_council_rule
            _council_rule = _match_council_rule(raw_name)
            if _council_rule is not None:
                logger.info(
                    "[COUNCIL MATCH] '%s' → '%s' — reclassified from type='%s' to council",
                    raw_name, _council_rule.council_name, debt_type,
                )
                resolved_name = _council_rule.council_name
                debt_type_override = 'council_tax'
            else:
                # CHECK 2 — CountyCouncilRouting fuzzy match (partial_ratio ≥ 85)
                _cr = rfprocess.extractOne(
                    raw_name, county_names, scorer=fuzz.partial_ratio, score_cutoff=85
                )
                if _cr:
                    _matched, _score, _ = _cr
                    logger.info(
                        "[COUNTY COUNCIL MATCH] '%s' → '%s' score=%d — "
                        "reclassified from type='%s' to council",
                        raw_name, _matched, _score, debt_type,
                    )
                    resolved_name = _matched
                    debt_type_override = 'council_tax'
                else:
                    # CHECK 3 — CreditorCriteria DB fuzzy match (token_sort_ratio ≥ 85)
                    _cr = rfprocess.extractOne(
                        raw_name, creditor_db_names, scorer=fuzz.token_sort_ratio, score_cutoff=85
                    )
                    if _cr:
                        _matched, _score, _ = _cr
                        logger.info(
                            "[CREDITOR DB MATCH] '%s' → '%s' score=%d — resolved from DB",
                            raw_name, _matched, _score,
                        )
                        resolved_name = _matched
                    else:
                        # CHECK 4 — CREDITOR_ALIAS_MAP exact match (existing behaviour)
                        # Keys in CREDITOR_ALIAS_MAP are normalised (legal suffixes stripped),
                        # so we must normalise the raw name before lookup.
                        _alias = CREDITOR_ALIAS_MAP.get(normalise_creditor_name(raw_name))
                        if _alias:
                            resolved_name = _alias
                        else:
                            # CHECK 5 — Aryza type fallback
                            logger.info(
                                "[CREDITOR UNRESOLVED] '%s' type='%s' — "
                                "no DB match, passing raw name",
                                raw_name, debt_type,
                            )

            balance_pence = creditor.get('balance') or creditor.get('total') or 0
            balance_pounds = float(balance_pence) / 100.0

            # STEP 5 — Deduplication on (name, type, reference, balance)
            # Including balance ensures that separate debts with the same name/type (e.g. 2 loans)
            # are not incorrectly merged when they lack a reference number.
            dedup_key = (raw_name.lower(), debt_type, ref, balance_pence)
            if dedup_key in seen_keys:
                logger.warning(
                    f"[TRUE DUPLICATE] '{raw_name}' type='{debt_type}' "
                    f"ref='{ref}' balance={balance_pounds} — skipping exact duplicate"
                )
                continue
            seen_keys.add(dedup_key)

            # Only count unsecured debts toward total
            if not is_secured:
                unsecured_debt_pounds += balance_pounds

            effective_type = debt_type_override if debt_type_override else debt_type
            creditor_dict = {
                **creditor,
                'creditor_name': resolved_name,
                'original_name': raw_name,
                'crm_balance': balance_pounds,
                'balance': balance_pounds,
                # Set both fields so _parse_case reads our intended type at priority 1
                # regardless of which field name Aryza used in the original payload.
                'creditor_type': effective_type,
                'debt_type_normalised': effective_type,
                'is_secured': is_secured,
            }
            prepared_creditors.append(creditor_dict)

            logger.warning(
                f"[PASS TO ENGINE] '{raw_name}' → '{resolved_name}' "
                f"balance=£{balance_pounds:,.2f} type='{effective_type}'"
            )

        # Enrich creditors with type_code and raw_name from credit report
        # Match by matched_creditor (lower) + balance (pence) for accuracy
        # Enrich creditors with CR data — match by name+balance (closest), carry all fields
        _cr_unmatched = []  # accounts in CR not matched to any declared creditor
        try:
            from debt_app.models import CreditReport
            cr_obj = None
            if credit_report_id:
                # Caller (e.g. the frontend, right after upload-credit-report)
                # knows exactly which extraction to use — pin to that row
                # instead of re-deriving "best" from history. Scoped to this
                # aryza_reference so a stray/mistyped id can't pull another
                # case's report.
                cr_obj = CreditReport.objects.filter(
                    id=credit_report_id,
                    aryza_reference=case_data_obj.aryza_reference,
                ).first()
                if not cr_obj:
                    logger.warning(
                        "[CR ENRICH] credit_report_id=%s not found for reference=%s — "
                        "falling back to most-recent extraction",
                        credit_report_id, case_data_obj.aryza_reference,
                    )
            if cr_obj is None:
                # No explicit id given (or it didn't resolve) — fall back to the
                # most recent extraction for this reference. Previously this
                # picked the extraction with the MOST accounts across ALL
                # history, which can silently resurrect a stale report: case
                # 349223 had four old extractions with 29 accounts each, then a
                # fresh, correct re-upload with only 26 — "most accounts wins"
                # kept serving the six-day-old 29-account report instead of the
                # one just uploaded. Recency is the right default; passing
                # credit_report_id explicitly is the reliable fix.
                recent_reports = CreditReport.objects.filter(
                    aryza_reference=case_data_obj.aryza_reference,
                    extraction_status="extracted",
                ).order_by('-created_at')
                cr_obj = next(
                    (r for r in recent_reports if (r.extracted_data or {}).get('accounts')),
                    None,
                )
            if cr_obj is None:
                # Nothing to enrich from — every creditor's CR columns (cr_balance,
                # cr_account_status, cr_missed_payments_3m, Match) will be left blank.
                # This is not an exception, so without an explicit log line it looks
                # to a caseworker like the feature was never implemented.
                logger.warning(
                    "[CR ENRICH] no extracted CreditReport found for reference=%s "
                    "(credit_report_id=%s) — creditor CR columns will be blank",
                    case_data_obj.aryza_reference, credit_report_id,
                )
            if cr_obj and cr_obj.extracted_data:
                # Mortgages are extracted into a SEPARATE list from unsecured/HP
                # accounts (mortgage_accounts vs accounts) — folding both in here
                # means a case's mortgage debt (e.g. "HBOS LLOYDS MORTGAGE") can
                # still be cross-checked against the credit report instead of
                # always showing no CR match.
                cr_accounts = (
                    (cr_obj.extracted_data.get('accounts', []) or []) +
                    (cr_obj.extracted_data.get('mortgage_accounts', []) or [])
                )

                # Build list of (normalised_name, balance_pence, full_account)
                # Include zero-balance accounts (bal=0 or None)
                cr_list = []
                for acc in cr_accounts:
                    mc = (acc.get('matched_creditor') or acc.get('raw_name') or '').lower().strip()
                    bal = acc.get('current_balance')  # pence, may be None
                    cr_list.append((mc, bal, acc))

                used_indices = set()

                # Tolerance on how far apart an Aryza balance and a credit-report
                # balance can be and still count as "the same account". A flat
                # £50 cap rejected genuine matches on larger balances that had
                # simply moved between the credit-report pull date and the
                # Aryza factfind date (e.g. a £9,760 debt vs an £8,791 CR
                # balance — £969 apart, clearly the same loan). Scaling with
                # the balance (20%, floor £50) keeps the original protection —
                # a shared/generic resolved name (e.g. two distinct Aryza debts
                # both aliased to "Monzo") still can't grab a wildly different
                # same-named CR account, since a wrong account is typically off
                # by far more than 20% — while tolerating normal balance drift.
                def _cr_match_tolerance_pence(aryza_bal_pence):
                    return max(5000, round(aryza_bal_pence * 0.20))

                for cd in prepared_creditors:
                    # Match on BOTH the resolved/representative name AND the
                    # raw Aryza name — a case creditor is often resolved to a
                    # representative-body brand (e.g. "Admiral Loans", "HBOS -
                    # Halifax - IVA", "Zopa - IVA or BKY") that shares no
                    # substring with the credit report's actual legal-entity
                    # name ("ADMIRAL FINANCIAL SERVICES LTD", "HALIFAX CREDIT
                    # CARD", "ZOPA LIMITED"). The raw Aryza name is much closer
                    # to the credit-bureau name, so trying both recovers these.
                    key_name = (cd.get('creditor_name') or '').lower().strip()
                    orig_name = (cd.get('original_name') or '').lower().strip()
                    # Aryza balance is in pounds — convert to pence for comparison
                    aryza_bal_pence = int(round((cd.get('balance') or 0) * 100))
                    tolerance_pence = _cr_match_tolerance_pence(aryza_bal_pence)

                    best_idx = None
                    best_diff = None

                    for i, (mc, bal, acc) in enumerate(cr_list):
                        if i in used_indices:
                            continue
                        name_match = (
                            mc == key_name or mc == orig_name or
                            (len(mc) >= 5 and (
                                mc in key_name or key_name in mc or
                                mc in orig_name or orig_name in mc
                            ))
                        )
                        if not name_match:
                            continue
                        # Balance match — treat None CR balance as 0
                        cr_bal = bal if bal is not None else 0
                        diff = abs(cr_bal - aryza_bal_pence)
                        # Only cap when the CR balance is actually known — if
                        # it's None there's nothing to compare, so fall back to
                        # the pre-existing name-only behaviour for that case.
                        if bal is not None and diff > tolerance_pence:
                            continue
                        if best_diff is None or diff < best_diff:
                            best_diff = diff
                            best_idx = i

                    if best_idx is not None:
                        used_indices.add(best_idx)
                        acc = cr_list[best_idx][2]
                        cd['type_code']         = acc.get('type_code') or ''
                        cd['cr_raw_name']       = acc.get('raw_name') or ''
                        cd['cr_balance']        = acc.get('current_balance')  # pence
                        cd['cr_account_status']            = acc.get('account_status') or ''
                        cd['cr_account_status_subjective'] = acc.get('account_status_subjective') or ''
                        cd['cr_credit_limit']   = acc.get('credit_limit')
                        # ISO YYYY-MM-DD. Normalised on read as well as on
                        # extraction so credit reports stored before
                        # normalise_start_date_iso() existed (Experian
                        # DD-MM-YYYY, or no start_date at all) still render.
                        cd['cr_start_date']     = normalise_start_date_iso(acc.get('start_date'))
                        cd['cr_account_age_months'] = acc.get('account_age_months')
                        cd['cr_missed_payments_3m'] = acc.get('missed_payments_last_3_months')

                # Collect CR accounts that were NOT matched to any case creditor.
                # These will be backfilled into all_creditor_positions later so
                # caseworkers can see ALL accounts from the credit report regardless
                # of whether the client declared them in the case payload.
                _cr_unmatched = [
                    acc
                    for i, (_mc, _bal, acc) in enumerate(cr_list)
                    if i not in used_indices
                    and "application type" not in (acc.get('raw_name') or '').lower()
                ]

        except Exception as e:
            logger.warning(f"[CR ENRICH] failed: {e}")

        # Disambiguate duplicate creditor_name labels AFTER credit-report
        # matching (so the CR-enrich step above still matches against the
        # clean base name). Aryza's `creditor` table is one master record
        # per legal entity — a bank's current-account overdraft and its
        # separate credit card both join to the SAME creditorid, so
        # `creditor_name` is legitimately identical for two distinct debts
        # (confirmed: "Monzo Bank Limited" for both a Current Account and a
        # Credit Card debt in a live case). That's correct data, not a bug —
        # but showing two identically-labelled rows in the UI makes them
        # impossible to tell apart. Suffix the display name with its debt
        # type ONLY when it collides with another row in this same case.
        from collections import Counter
        _name_counts = Counter(cd.get('creditor_name') for cd in prepared_creditors)
        for cd in prepared_creditors:
            if _name_counts.get(cd.get('creditor_name'), 0) > 1:
                _type_label = (cd.get('debt_type_normalised') or cd.get('creditor_type') or '').replace('_', ' ').strip().title()
                if _type_label:
                    cd['creditor_name'] = f"{cd['creditor_name']} ({_type_label})"

        # Build the engine payload matching CASE_ASSESSMENT_PAYLOAD.md
        property_data = case_data_obj.property or {}
        vehicle_data = case_data_obj.vehicle or {}
        income_data = case_data_obj.income or {}
        expenditure_data = case_data_obj.expenditure or {}
        flags_data = case_data_obj.flags or {}
        payload = {
            "application_id": case_data_obj.aryza_reference,
            "client_name": case_data_obj.client_name,
            "clientInfo": {
                "dateOfBirth": case_data_obj.dob,
                "client_name": case_data_obj.client_name,
            },
            "employment_status": case_data_obj.employment_status,
            "disposable_income": di_pounds,
            "total_unsecured_debt": unsecured_debt_pounds,
            "financial_summary": {
                "net_balance": di_pounds,
                "total_income": (income_data.get("total") or 0) / 100.0,
                "income_source": case_data_obj.employment_status,
            },
            "crm_data": {
                "total_unsecured_debt": unsecured_debt_pounds,
            },
            "creditors": prepared_creditors,
            "income": {k: v/100.0 for k, v in income_data.items()},
            "expenditure": {k: v/100.0 for k, v in expenditure_data.items()},
            "third_party_contribution": (income_data.get("third_party_contribution", 0) or 0) / 100.0,
            "property": {
                "owns_property": property_data.get("owns_property", False),
                "property_value": (property_data.get("property_value") or 0) / 100.0 if property_data.get("property_value") is not None else 0.0,
                "mortgage_balance": (
                    (property_data.get("mortgage_balance") or 0) / 100.0
                    or sum(
                        float(cr.get("balance") or 0) / 100.0
                        for cr in (case_data_obj.creditors or [])
                        if (cr.get("type") or cr.get("creditor_type") or "").lower()
                        in {"mortgage", "secured", "secured_loan", "second_charge"}
                    )
                ),
                "equity": (property_data.get("equity") or 0) / 100.0 if property_data.get("equity") is not None else 0.0,
            },
            "vehicle": {
                "has_vehicle": vehicle_data.get("has_vehicle", False),
                "vehicle_value": (vehicle_data.get("vehicle_value") or 0) / 100.0 if vehicle_data.get("vehicle_value") else None,
                "hp_monthly_payment": (vehicle_data.get("hp_monthly_payment") or 0) / 100.0 if vehicle_data.get("hp_monthly_payment") else None,
            },
            "sfs_expenditure_breakdown": case_data_obj.sfs_expenditure_breakdown,
            "gold_transactions": case_data_obj.gold_transactions,
            "flags": flags_data,
            "previous_iva_failed_reason": flags_data.get("previous_iva_failed_reason"),
            "dependants": case_data_obj.dependants,
        }

        # Step 6 — Calculate aggregated benefit income for TIG-21.4
        # Rule TIG-21.4 requires the sum of all benefit components
        benefit_income_pence = (
            income_data.get("universal_credit", 0) or 0
        ) + (
            income_data.get("dla", 0) or 0
        ) + (
            income_data.get("pip", 0) or 0
        ) + (
            income_data.get("other_benefits", 0) or 0
        )

        benefit_income_pounds = benefit_income_pence / 100.0
        payload["benefit_income_amount"] = benefit_income_pounds if benefit_income_pounds > 0 else None
             
        return payload, prepared_creditors, _cr_unmatched


    def post(self, request):
        # Step 1 — Validate
        aryza_reference = (
            request.data.get("aryza_reference")
            or request.data.get("application_id")
        )
        if not aryza_reference:
            return error_response(
                "aryza_reference is required",
                "MISSING_REFERENCE",
                status.HTTP_422_UNPROCESSABLE_ENTITY
            )
        credit_report_id = request.data.get("credit_report_id")
        # DMP Eligibility Checklist — combines per-row dropdown selections
        # (council tax current/previous, water included, parking
        # government/private, mobile) with the remaining case-level
        # checkboxes that have no reliable per-creditor signal (Part 4/5 of
        # the Aryza-only DMP redesign). See build_dmp_checklist().
        _creditor_rows = request.data.get("creditor_rows") or []
        _dmp_checklist_raw = request.data.get("dmp_checklist") or {}
        dmp_checklist = build_dmp_checklist(_creditor_rows, _dmp_checklist_raw)
        logger.warning(f"[DMP DEBUG] received creditor_rows={_creditor_rows!r} "
                       f"dmp_checklist_raw={_dmp_checklist_raw!r} -> built={dmp_checklist!r}")

        # Step 2 — Fetch from Aryza
        try:
            case_data_obj = fetch_case_by_reference(aryza_reference)
            case_data, prepared_creditors, _cr_unmatched = self._prepare_engine_payload(
                case_data_obj, credit_report_id,
            )
            # Phase A: attach as a new top-level payload key only — not read
            # by _parse_case or any rule function yet (see DMP_CHECKLIST_FIELDS).
            case_data["dmp_checklist"] = dmp_checklist
        except AryzaCaseNotFoundError:
            return error_response(
                f"Case {aryza_reference} not found in Aryza",
                "CASE_NOT_FOUND",
                status.HTTP_404_NOT_FOUND
            )
        except AryaTimeoutError:
            return error_response(
                "Aryza database timed out. Please try again.",
                "ARYZA_TIMEOUT",
                status.HTTP_503_SERVICE_UNAVAILABLE
            )
        except AryzaConnectionError:
            return error_response(
                "Unable to connect to Aryza database.",
                "ARYZA_UNAVAILABLE",
                status.HTTP_503_SERVICE_UNAVAILABLE
            )
        except AryzaDataError as e:
            logger.error("Aryza data error for %s: %s", aryza_reference, e)
            return error_response(
                "Data error reading case. Contact support.",
                "ARYZA_DATA_ERROR",
                status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        # Step 3 — Run assessment engine
        # Fetch local evidence and flags to enrich the Aryza data
        try:
            from debt_app.models import Application, EvidenceLedger
            app_obj = Application.objects.filter(aryza_reference=aryza_reference).first()
            if app_obj:
                # First-assessment department tagging. Permanent snapshot of the
                # submitting user's department — set once, never overwritten by
                # later runs/users. This view allows anonymous access (AllowAny),
                # so we don't assume request.user is authenticated; if there's no
                # profile, get_user_department() falls back to "Default", which we
                # store as a real signal ("not Lead Gen") rather than leaving null.
                # We never create the Application row here — creation is admin-only
                # via ApplicationListView.post elsewhere.
                if not app_obj.source_department:
                    dept = get_user_department(request.user)
                    app_obj.source_department = dept.name if dept else None
                    app_obj.save(update_fields=['source_department'])

                # Feed into the engine payload so assess_case() can gate the
                # Lead Gen disposable-income formula / £399 auto-DRO rule on it.
                case_data["source_department"] = app_obj.source_department

                # Map EvidenceLedger to the format engine expects
                # Engine expects: [{"ref": "...", "is_verified": True, "category": "..."}]
                local_evidence = list(app_obj.evidence.all().values('entry_type', 'created_at'))
                # Since EvidenceLedger in models.py is minimal, we'll map entry_type to category
                # and assume created_at means it exists. We might need more fields in models.py later.
                case_data["evidence_ledger"] = [
                    {"category": e["entry_type"], "is_verified": True, "ref": e["entry_type"]} 
                    for e in local_evidence
                ]
                
                # Check for ClientFlags
                if hasattr(app_obj, 'client_flags'):
                    flags = app_obj.client_flags
                    case_data["is_currently_in_dmp"] = flags.is_currently_in_dmp
                    case_data["is_royal_mail_employee"] = flags.is_royal_mail_employee
                    case_data["is_police_officer"] = flags.is_police_officer
                    case_data["previous_iva_failed"] = flags.previous_iva_failed
        except Exception as e:
            logger.error(f"Failed to fetch local evidence/flags: {e}")

        # Normalise evidence_ledger — engine expects a list of 
        # {"category": str, "is_verified": bool, "ref": str} 
        # Guard against dict format from external callers 
        _ev = case_data.get("evidence_ledger", []) 
        if isinstance(_ev, dict): 
            case_data["evidence_ledger"] = [ 
                {"category": k, "is_verified": bool(v), "ref": k} 
                for k, v in _ev.items() 
            ] 
        elif not isinstance(_ev, list): 
            case_data["evidence_ledger"] = [] 

        case_creditors = case_data.get("creditors") or []
        detected_reps = detect_representatives(case_creditors)
        result = assess_case(case_data, detected_reps)

        # STEP 7 — Reconcile creditors the engine routed elsewhere (councils) or
        # could not assess. Uses the shared helper so the displayed status is always
        # the engine's CALCULATED value — councils reuse their real council_positions
        # status (e.g. Rother District Council = REJECT), and genuinely unidentified
        # creditors become UNKNOWN. NEVER a hardcoded ACCEPT.
        from debt_app.criteria_engine import reconcile_creditor_positions
        engine_positions = result.get("creditor_positions", [])
        all_creditor_positions = reconcile_creditor_positions(result, prepared_creditors)

        # STEP 7b — stamp CR fields onto engine position dicts, balance-aware dedup
        _pc_enriched = [
            pc for pc in prepared_creditors
            if pc.get('type_code') or pc.get('cr_raw_name')
        ]
        _used_pc = set()

        for pos in all_creditor_positions:
            pos_name = (pos.get('original_aryza_name') or pos.get('creditor_name') or '').lower().strip()
            pos_bal_pence = int(round((pos.get('balance') or 0) * 100))

            best_idx = None
            best_diff = None
            for i, pc in enumerate(_pc_enriched):
                if i in _used_pc:
                    continue
                pc_name = (pc.get('creditor_name') or '').lower().strip()
                pos_canonical = (pos.get('creditor_name') or '').lower().strip()
                name_match = (
                    pc_name == pos_name or
                    pc_name == pos_canonical or
                    (len(pc_name) >= 5 and (pc_name in pos_name or pos_name in pc_name)) or
                    (len(pc_name) >= 5 and (pc_name in pos_canonical or pos_canonical in pc_name))
                )
                if not name_match:
                    continue
                pc_bal_pence = int(round((pc.get('balance') or 0) * 100))
                diff = abs(pc_bal_pence - pos_bal_pence)
                if best_diff is None or diff < best_diff:
                    best_diff = diff
                    best_idx = i

            if best_idx is not None:
                _used_pc.add(best_idx)
                pc = _pc_enriched[best_idx]
                pos['type_code']             = pc.get('type_code') or ''
                pos['cr_raw_name']           = pc.get('cr_raw_name') or ''
                pos['cr_balance']            = pc.get('cr_balance')
                pos['cr_account_status']            = pc.get('cr_account_status') or ''
                pos['cr_account_status_subjective'] = pc.get('cr_account_status_subjective') or ''
                pos['cr_credit_limit']       = pc.get('cr_credit_limit')
                pos['cr_start_date']         = pc.get('cr_start_date')
                pos['cr_account_age_months'] = pc.get('cr_account_age_months')
                pos['cr_missed_payments_3m'] = pc.get('cr_missed_payments_3m')

        # Re-apply representative-body vote mapping over the combined list so any
        # backfilled (engine-missed) WATCH/TIX/EVOLVE creditor reflects its body's
        # outcome. Idempotent for engine positions already mapped in assess_case().
        from debt_app.criteria_engine import _apply_representative_outcomes
        _apply_representative_outcomes(
            all_creditor_positions,
            result.get("representative_outcomes") or {},
        )

        restored_count = len(all_creditor_positions) - len(engine_positions)
        logger.warning(
            f"[POSITIONS TOTAL] {len(engine_positions)} engine + "
            f"{restored_count} restored = "
            f"{len(all_creditor_positions)} total"
        )

        # STEP 7c — Backfill credit-report-only accounts.
        # Any CR account that was NOT matched to a case creditor is appended as
        # an informational "CREDITOR-CR-ONLY" row so caseworkers see the full
        # picture of the client's credit file, including undeclared accounts.
        if _cr_unmatched:
            # Build a set of cr_raw_names already stamped onto engine positions
            # (from Step 7b enrichment) so we never double-append.
            _already_stamped = {
                (pos.get('cr_raw_name') or '').lower().strip()
                for pos in all_creditor_positions
                if pos.get('cr_raw_name')
            }
            from debt_app.helpers import get_creditor_by_trading_name, normalise_creditor_name
            from debt_app.models import CreditorResolutionMiss

            for _acc in _cr_unmatched:
                _raw = ((_acc.get('raw_name') or '')).strip()
                if not _raw:
                    continue
                if _raw.lower() in _already_stamped:
                    continue
                _cr_bal_pence = _acc.get('current_balance')
                _cr_name = _acc.get('matched_creditor') or _raw

                # Resolve against the SAME CreditorCriteria table/alias map used
                # for declared creditors — a CR-only (undeclared) account is not
                # exempt from representative-body voting just because it never
                # reached _check_creditor_individual(). Previously this branch
                # hardcoded representative='NONE' unconditionally, which meant a
                # genuinely WATCH/TIX/EVOLVE creditor that only showed up as an
                # undeclared credit-report account silently lost its badge.
                try:
                    _cr_criteria = get_creditor_by_trading_name(_cr_name)
                    _cr_representative = _cr_criteria.representative
                except CreditorCriteria.DoesNotExist:
                    _cr_representative = 'NONE'
                    try:
                        CreditorResolutionMiss.objects.create(
                            raw_name=_raw,
                            normalised_name=normalise_creditor_name(_raw) or _raw,
                            case_reference=aryza_reference,
                            client_name=case_data.get('client_name', ''),
                            balance=(_cr_bal_pence or 0) / 100.0,
                        )
                    except Exception as e:
                        logger.error(f"Failed to log CreditorResolutionMiss for CR-only account {_raw!r}: {e}")

                _cr_only_pos = {
                    'criteria_id': None,
                    'creditor_name': _cr_name,
                    'display_name': None,
                    'original_aryza_name': _raw if _raw != _cr_name else None,
                    'resolved_canonical_name': _cr_name,
                    'representative': _cr_representative,
                    'effective_status': 'UNKNOWN',
                    'findings': [{
                        'code': 'CREDITOR-CR-ONLY',
                        'reason': (
                            'This account appears on the customer\'s credit report but '
                            'was not declared as a debt on this case. The caseworker '
                            'should confirm with the customer whether this debt exists '
                            'and should be added.'
                        ),
                        'severity': 'info',
                    }],
                    'reason': (
                        'This account appears on the customer\'s credit report but '
                        'was not declared as a debt on this case. The caseworker '
                        'should confirm with the customer whether this debt exists '
                        'and should be added.'
                    ),
                    'rule_ids': ['CREDITOR-CR-ONLY'],
                    'balance': 0.0,  # £0 — not declared in case
                    'criteria_notes': '',
                    'dividend_notes': '',
                    'is_secured': False,
                    'debt_type_normalised': None,
                    '_creditor_idx': None,
                    'cr_raw_name': _raw,
                    'type_code': _acc.get('type_code') or '',
                    'cr_balance': _cr_bal_pence,
                    'cr_account_status': _acc.get('account_status') or '',
                    'cr_account_status_subjective': _acc.get('account_status_subjective') or '',
                    'cr_credit_limit': _acc.get('credit_limit'),
                    'cr_start_date': normalise_start_date_iso(_acc.get('start_date')),
                    'cr_account_age_months': _acc.get('account_age_months'),
                    'cr_missed_payments_3m': _acc.get('missed_payments_last_3_months'),
                }
                all_creditor_positions.append(_cr_only_pos)
                logger.info(
                    f"[CR-ONLY] Backfilled undeclared account: {_raw!r} "
                    f"(CR balance: {_cr_bal_pence}p, status: {_acc.get('account_status')!r})"
                )

            # Re-apply the representative-body outcome mapping now that CR-only
            # accounts have been appended. The first call (above, before this
            # block) ran before these positions existed, so a CR-only account
            # correctly resolved to e.g. TIX would otherwise show the TIX badge
            # but stay stuck at effective_status='UNKNOWN' — the outcome was
            # never applied because the position didn't exist yet when that
            # call ran. Documented as idempotent, so re-running it over
            # everything (not just the new positions) is safe.
            _apply_representative_outcomes(
                all_creditor_positions,
                result.get("representative_outcomes") or {},
            )

        enrich_positions_with_tallies(all_creditor_positions)
        result["creditor_positions"] = all_creditor_positions
        
        # Enrich rules with metadata from GlobalCriteria
        result['hard_blocks'] = enrich_rules_with_meta(result.get('hard_blocks', []))
        result['flags'] = enrich_rules_with_meta(result.get('flags', []))
        result['passed'] = enrich_rules_with_meta(result.get('passed', []))
        result['info'] = enrich_rules_with_meta(result.get('info', []))

        # Determine decision and get recommendation
        hard_blocks = result.get("hard_blocks", [])
        flags = result.get("flags", [])
        
        if hard_blocks:
            decision = "INELIGIBLE"
        elif flags:
            decision = "REFERRED"
        else:
            decision = "ELIGIBLE"
            
        # Captured BEFORE the overwrite two lines down — assess_case's own
        # _derive_recommended_solution already computed "FORCED_DMP_VAT" as the
        # single source of truth for the VAT-override precedence; get_recommendation
        # must honour it rather than silently recompute a different decision from
        # hard_blocks/flags alone (that was the bug: this view used to discard it).
        vat_forced = result.get("recommended_solution") == "FORCED_DMP_VAT"
        # Same capture pattern as vat_forced, for the Lead Gen £399 auto-DRO rule.
        # Mutually exclusive with vat_forced by construction — assess_case routes
        # a case where both conditions fire to "REVIEW_REQUIRED" instead, so at
        # most one of vat_forced/dro_forced is ever True here.
        dro_forced = result.get("recommended_solution") == "FORCED_DRO_LG"
        recommendations = get_recommendation(
            decision, result, case_data, vat_forced=vat_forced, dro_forced=dro_forced,
        )
        result["recommended_solution"] = recommendations.get("recommended_solution")
        result["alternative_solutions"] = recommendations.get("alternative_solutions", [])

        serialized = build_phase7_response_fields(result)

        # Attach financial summary fields that are NOT produced by build_phase7_response_fields
        # but are required for correct display when the saved result is later reloaded.
        # Without this, reloading from history always shows disposable_income = 0.
        serialized["disposable_income"] = case_data.get("disposable_income")
        serialized["total_unsecured_debt"] = case_data.get("total_unsecured_debt")
        serialized["lead_gen_disposable_income"] = result.get("lead_gen_disposable_income")

        # Step 4 — Save to CriteriaDecision
        try:
            # Clear previous history for this reference to satisfy "no history" requirement
            CriteriaDecision.objects.filter(application_id=aryza_reference).delete()

            # recommended_solution field in DB expects a string (the code)
            db_recommended_solution = result["recommended_solution"].get("code", "UNCLEAR") if isinstance(result["recommended_solution"], dict) else (result["recommended_solution"] or "UNCLEAR")

            decision_obj = CriteriaDecision.objects.create(
                application_id=aryza_reference,
                client_name=case_data.get("client_name", "Unknown"),
                input_snapshot=case_data,
                decision_output=serialized,
                recommended_solution=db_recommended_solution,
                passes_all_hard_blocks=serialized.get("passes_all_hard_blocks", False),
                triggered_by=request.user if getattr(request.user, 'is_authenticated', False) else None,
                source="STANDALONE"
            )
            decision_id = str(decision_obj.id)
        except Exception as e:
            logger.error("Failed to save CriteriaDecision: %s", e)
            decision_id = None

        logger.info("Assessment completed for %s: %s", aryza_reference, serialized.get("recommended_solution"))
        return Response({
            "success": True,
            "decision_id": decision_id,
            "client_name": case_data_obj.client_name,
            "aryza_reference": aryza_reference,
            "evaluated_at": timezone.now().isoformat(),
            "disposable_income": case_data.get("disposable_income"),
            "total_unsecured_debt": case_data.get("total_unsecured_debt"),
            **serialized,
        }, status=status.HTTP_200_OK)


class AssessHistoryView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated, HasFeatureAccess]
    required_feature = 'decisions'

    def get(self, request):
        page = int(request.query_params.get('page', 1))
        page_size = min(int(request.query_params.get('page_size', 20)), 100)
        reference = request.query_params.get('reference', '')
        date_from = request.query_params.get('date_from')
        date_to = request.query_params.get('date_to')

        queryset = CriteriaDecision.objects.all().order_by('-triggered_at')

        if reference:
            queryset = queryset.filter(application_id__icontains=reference)

        if date_from:
            parsed_date = parse_date(date_from)
            if parsed_date:
                queryset = queryset.filter(triggered_at__date__gte=parsed_date)

        if date_to:
            parsed_date = parse_date(date_to)
            if parsed_date:
                queryset = queryset.filter(triggered_at__date__lte=parsed_date)

        from django.core.paginator import Paginator
        paginator = Paginator(queryset, page_size)
        page_obj = paginator.get_page(page)

        results = []
        for decision in page_obj:
            results.append({
                "id": str(decision.id),
                "aryza_reference": decision.application_id,
                "client_name": decision.client_name,
                "recommended_solution": decision.recommended_solution,
                "passes_all_hard_blocks": decision.passes_all_hard_blocks,
                "triggered_by": decision.triggered_by.username if decision.triggered_by else None,
                "created_at": decision.triggered_at.isoformat(),
                "result_json": decision.result_json,
                "decision_output": decision.decision_output,
            })

        return Response({
            "count": paginator.count,
            "next": f"{request.build_absolute_uri(request.path)}?page={page + 1}" if page_obj.has_next() else None,
            "previous": f"{request.build_absolute_uri(request.path)}?page={page - 1}" if page_obj.has_previous() else None,
            "results": results,
        }, status=status.HTTP_200_OK)


class AssessHistoryDetailView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAdminUser]

    def _get_object(self, id):
        try:
            return CriteriaDecision.objects.get(id=id)
        except CriteriaDecision.DoesNotExist:
            return None

    def get(self, request, id):
        decision = self._get_object(id)
        if decision is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        return Response({
            "id": str(decision.id),
            "application_id": decision.application_id,
            "client_name": decision.client_name,
            "input_snapshot": decision.input_snapshot,
            "decision_output": decision.decision_output,
            "result_json": decision.result_json,
            "recommended_solution": decision.recommended_solution,
            "passes_all_hard_blocks": decision.passes_all_hard_blocks,
            "triggered_by": decision.triggered_by.username if decision.triggered_by else None,
            "triggered_at": decision.triggered_at.isoformat(),
            "source": decision.source,
        }, status=status.HTTP_200_OK)

    def delete(self, request, id):
        decision = self._get_object(id)
        if decision is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        decision.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


def _creditor_to_dict(creditor):
    return {
        "id": creditor.id,
        "creditor_name": creditor.creditor_name,
        "trading_names": creditor.trading_names,
        "representative": creditor.representative,
        "status": creditor.status,
        "min_dividend_pence": creditor.min_dividend_pence,
        "dividend_notes": creditor.dividend_notes,
        "contact_name": creditor.contact_name,
        "contact_email": creditor.contact_email,
        "contact_phone": creditor.contact_phone,
        "criteria_notes": creditor.criteria_notes,
        "raw_updated_criteria": creditor.raw_updated_criteria,
        "source_sheet": creditor.source_sheet,
        "is_active": creditor.is_active,
        "blocked_until_cleared": creditor.blocked_until_cleared,
        "blocked_reason": creditor.blocked_reason,
        "parent_group": creditor.parent_group,
        "account_age_months": creditor.account_age_months,
        "reject_if_in_dmp": creditor.reject_if_in_dmp,
        "reject_if_never_made_payment": creditor.reject_if_never_made_payment,
        "reject_if_ie_doesnt_match_application": creditor.reject_if_ie_doesnt_match_application,
        "reject_if_debt_repayable_within_months": creditor.reject_if_debt_repayable_within_months,
        "reject_if_client_still_has_asset": creditor.reject_if_client_still_has_asset,
        "reject_if_majority_share_exceeds_pct": creditor.reject_if_majority_share_exceeds_pct,
        "reject_if_second_iva": creditor.reject_if_second_iva,
        "reject_if_police_employed": creditor.reject_if_police_employed,
        "reject_if_equity_exceeds_debt": creditor.reject_if_equity_exceeds_debt,
        "reject_if_ccj": creditor.reject_if_ccj,
        "reject_if_aoe": creditor.reject_if_aoe,
        "requires_pg_called_up": creditor.requires_pg_called_up,
        "requires_arrangement_call_before_proposing": creditor.requires_arrangement_call_before_proposing,
        "requires_grant_overpayment_only": creditor.requires_grant_overpayment_only,
        "vehicle_arrears_repossession_months": creditor.vehicle_arrears_repossession_months,
        "fees_cap_percentage": creditor.fees_cap_percentage,
        "min_di_for_fees_pence": creditor.min_di_for_fees_pence,
        "termination_risk_if_vehicle_on_finance": creditor.termination_risk_if_vehicle_on_finance,
        "conditional_voter": creditor.conditional_voter,
        "conditional_voter_min_dividend_pence": creditor.conditional_voter_min_dividend_pence,
        "open_banking_access": creditor.open_banking_access,
        "fraud_claim_risk": creditor.fraud_claim_risk,
        "last_reviewed": creditor.last_reviewed.isoformat() if creditor.last_reviewed else None,
        "last_updated": creditor.last_updated.isoformat(),
    }


_CREDITOR_WRITABLE_FIELDS = [
    'creditor_name', 'trading_names', 'representative', 'status',
    'min_dividend_pence', 'dividend_notes', 'contact_name', 'contact_email', 'contact_phone',
    'criteria_notes', 'raw_updated_criteria', 'source_sheet',
    'is_active', 'account_age_months', 'parent_group',
    'reject_if_in_dmp', 'reject_if_never_made_payment',
    'reject_if_ie_doesnt_match_application', 'reject_if_debt_repayable_within_months',
    'reject_if_client_still_has_asset', 'reject_if_majority_share_exceeds_pct',
    'reject_if_second_iva', 'reject_if_police_employed', 'reject_if_equity_exceeds_debt',
    'reject_if_ccj', 'reject_if_aoe',
    'requires_pg_called_up', 'requires_arrangement_call_before_proposing',
    'requires_grant_overpayment_only', 'vehicle_arrears_repossession_months',
    'fees_cap_percentage', 'min_di_for_fees_pence',
    'termination_risk_if_vehicle_on_finance', 'conditional_voter',
    'conditional_voter_min_dividend_pence', 'open_banking_access', 'fraud_claim_risk',
    'blocked_until_cleared', 'blocked_reason', 'last_reviewed',
]


class CreditorListView(APIView):
    authentication_classes = [JWTAuthentication]
    required_feature = 'general_creditors'

    def get_permissions(self):
        if self.request.method == 'GET':
            return [IsAuthenticated(), HasReadPermission()]
        return [IsAuthenticated(), HasWritePermission()]

    def get(self, request):
        search = request.query_params.get('search', '')
        representative = request.query_params.get('representative', '')
        page = int(request.query_params.get('page', 1))
        page_size = min(int(request.query_params.get('page_size', 100)), 500)

        queryset = CreditorCriteria.objects.all().order_by('creditor_name')

        if search:
            queryset = queryset.filter(
                Q(creditor_name__icontains=search) |
                Q(trading_names__icontains=search)
            )

        if representative:
            queryset = queryset.filter(representative=representative)

        queryset = filter_by_department(
            queryset, CreditorCriteria, request.user,
            DepartmentCreditorVisibility, 'creditor',
        )

        from django.core.paginator import Paginator
        paginator = Paginator(queryset, page_size)
        page_obj = paginator.get_page(page)

        return Response({
            "count": paginator.count,
            "next": f"{request.build_absolute_uri(request.path)}?page={page + 1}" if page_obj.has_next() else None,
            "previous": f"{request.build_absolute_uri(request.path)}?page={page - 1}" if page_obj.has_previous() else None,
            "results": [_creditor_to_dict(c) for c in page_obj],
        }, status=status.HTTP_200_OK)

    def post(self, request):
        data = request.data
        required = ['creditor_name']
        for field in required:
            if not data.get(field):
                return Response({"detail": f"{field} is required."}, status=status.HTTP_400_BAD_REQUEST)

        if CreditorCriteria.objects.filter(creditor_name=data['creditor_name']).exists():
            return Response({"detail": "A creditor with this name already exists."}, status=status.HTTP_400_BAD_REQUEST)

        creditor = CreditorCriteria()
        for field in _CREDITOR_WRITABLE_FIELDS:
            if field in data:
                setattr(creditor, field, data[field])
        creditor.updated_by = request.user

        try:
            creditor.full_clean()
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        creditor.save()
        return Response(_creditor_to_dict(creditor), status=status.HTTP_201_CREATED)


class CreditorDetailView(APIView):
    authentication_classes = [JWTAuthentication]
    required_feature = 'general_creditors'

    def get_permissions(self):
        if self.request.method == 'GET':
            return [IsAuthenticated(), HasReadPermission()]
        return [IsAuthenticated(), HasWritePermission()]

    def _get_object(self, id):
        try:
            return CreditorCriteria.objects.get(id=id)
        except CreditorCriteria.DoesNotExist:
            return None

    def get(self, request, id):
        creditor = self._get_object(id)
        if creditor is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(_creditor_to_dict(creditor), status=status.HTTP_200_OK)

    def put(self, request, id):
        creditor = self._get_object(id)
        if creditor is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        # Snapshot old values before mutation for audit trail
        _old = {
            field: str(getattr(creditor, field, ''))
            for field in _CREDITOR_WRITABLE_FIELDS
            if field in request.data
        }

        for field in _CREDITOR_WRITABLE_FIELDS:
            if field in request.data:
                setattr(creditor, field, request.data[field])

        try:
            creditor.full_clean()
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        # Audit trail — log every changed field
        for field in _CREDITOR_WRITABLE_FIELDS:
            if field in request.data:
                old_val = _old[field]
                new_val = str(request.data[field])
                if old_val != new_val:
                    CriteriaAuditLog.objects.create(
                        creditor=creditor,
                        changed_by=request.user,
                        field_name=field,
                        old_value=old_val,
                        new_value=new_val,
                        action='update',
                    )

        creditor.updated_by = request.user
        creditor.save()
        return Response(_creditor_to_dict(creditor), status=status.HTTP_200_OK)

    def delete(self, request, id):
        creditor = self._get_object(id)
        if creditor is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        creditor.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


def _rule_obj_to_dict(rule, include_full=False):
    """
    Convert a GlobalCriteria object to a dictionary.
    
    Args:
        rule: GlobalCriteria instance
        include_full: If True, include all documentation and reference fields
    """
    basic = {
        "id": rule.id,
        "rule_key": rule.rule_key,
        "rule_name": rule.rule_name,
        "name": rule.rule_name,  # Backward compatibility
        "criteria_set": rule.criteria_set,
        "severity": rule.severity,
        "is_active": rule.is_active,
        "threshold_value": float(rule.threshold_value) if rule.threshold_value else None,
        "description": rule.description,
        "action": rule.action,
        "last_updated": rule.last_updated.isoformat(),
        # threshold_value and severity mirror the literals hardcoded in each rule
        # function — the engine does NOT read these columns (verified 2026-06-21).
        # They are reference/documentation only; the UI should render them
        # read-only. Only is_active actually drives the engine (disable toggle).
        "code_managed_fields": ["threshold_value", "severity"],
    }
    
    if include_full:
        basic.update({
            "implementation_notes": rule.implementation_notes,
            "category": rule.category,
            "example_case": rule.example_case,
            "rejection_message": rule.rejection_message,
            "flag_message": rule.flag_message,
            "is_creditor_specific": rule.is_creditor_specific,
            "applies_to_creditors": rule.applies_to_creditors or [],
            "references": rule.references or [],
            "execution_order": rule.execution_order,
            "depends_on_rules": rule.depends_on_rules or [],
            "related_rules": rule.related_rules or [],
            "last_reviewed": rule.last_reviewed.isoformat() if rule.last_reviewed else None,
            "review_notes": rule.review_notes,
        })
    
    return basic


class RulesListView(APIView):
    authentication_classes = [JWTAuthentication]
    required_feature = 'global_rules'

    def get_permissions(self):
        if self.request.method == 'GET':
            return [IsAuthenticated(), HasReadPermission()]
        return [IsAuthenticated(), HasWritePermission()]

    def get(self, request):
        page = int(request.query_params.get('page', 1))
        page_size = min(int(request.query_params.get('page_size', 100)), 500)
        include_full = request.query_params.get('include', '').lower() == 'full'

        # Apply filters
        queryset = GlobalCriteria.objects.all()

        # Filter by criteria_set
        criteria_set = request.query_params.get('criteria_set')
        if criteria_set:
            queryset = queryset.filter(criteria_set=criteria_set)

        # Filter by severity
        severity = request.query_params.get('severity')
        if severity:
            queryset = queryset.filter(severity=severity)

        # Filter by category
        category = request.query_params.get('category')
        if category:
            queryset = queryset.filter(category=category)

        # Filter by is_active
        is_active = request.query_params.get('is_active')
        if is_active:
            queryset = queryset.filter(is_active=is_active.lower() == 'true')

        # Search by rule_key or rule_name
        search = request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(rule_key__icontains=search) | Q(rule_name__icontains=search)
            )

        queryset = filter_by_department(
            queryset, GlobalCriteria, request.user,
            DepartmentRuleVisibility, 'rule_key',
        )

        queryset = queryset.order_by('criteria_set', 'rule_key')

        from django.core.paginator import Paginator
        paginator = Paginator(queryset, page_size)
        page_obj = paginator.get_page(page)

        return Response({
            "count": paginator.count,
            "next": f"{request.build_absolute_uri(request.path)}?page={page + 1}" if page_obj.has_next() else None,
            "previous": f"{request.build_absolute_uri(request.path)}?page={page - 1}" if page_obj.has_previous() else None,
            "results": [_rule_obj_to_dict(r, include_full=include_full) for r in page_obj],
        }, status=status.HTTP_200_OK)

    def post(self, request):
        data = request.data
        required = ['rule_key', 'rule_name', 'criteria_set', 'severity']
        for field in required:
            if not data.get(field):
                return Response({"detail": f"{field} is required."}, status=status.HTTP_400_BAD_REQUEST)

        if GlobalCriteria.objects.filter(rule_key=data['rule_key']).exists():
            return Response({"detail": "A rule with this rule_key already exists."}, status=status.HTTP_400_BAD_REQUEST)

        rule = GlobalCriteria(
            rule_key=data['rule_key'],
            rule_name=data['rule_name'],
            criteria_set=data['criteria_set'],
            severity=data['severity'],
            is_active=data.get('is_active', True),
            threshold_value=data.get('threshold_value'),
            description=data.get('description'),
            implementation_notes=data.get('implementation_notes'),
            category=data.get('category'),
            example_case=data.get('example_case'),
            rejection_message=data.get('rejection_message'),
            flag_message=data.get('flag_message'),
            is_creditor_specific=data.get('is_creditor_specific', False),
            applies_to_creditors=data.get('applies_to_creditors'),
            references=data.get('references'),
            execution_order=data.get('execution_order'),
            depends_on_rules=data.get('depends_on_rules'),
            related_rules=data.get('related_rules'),
            last_reviewed=data.get('last_reviewed'),
            review_notes=data.get('review_notes'),
            updated_by=request.user,
        )

        try:
            rule.full_clean()
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        rule.save()
        return Response(_rule_obj_to_dict(rule, include_full=True), status=status.HTTP_201_CREATED)


class RulesDetailView(APIView):
    authentication_classes = [JWTAuthentication]
    required_feature = 'global_rules'

    def get_permissions(self):
        if self.request.method == 'GET':
            return [IsAuthenticated(), HasReadPermission()]
        return [IsAuthenticated(), HasWritePermission()]

    def _get_object(self, rule_key):
        try:
            return GlobalCriteria.objects.get(rule_key=rule_key)
        except GlobalCriteria.DoesNotExist:
            return None

    def get(self, request, rule_key):
        rule = self._get_object(rule_key)
        if rule is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(_rule_obj_to_dict(rule, include_full=True), status=status.HTTP_200_OK)

    def put(self, request, rule_key):
        rule = self._get_object(rule_key)
        if rule is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        # is_active is the ONLY field that drives the engine (disable toggle).
        if 'is_active' in request.data:
            rule.is_active = request.data['is_active']

        # threshold_value and severity are CODE-MANAGED: the engine uses the
        # literals hardcoded in each rule function, not these columns (verified
        # 2026-06-21). Editing them here used to silently no-op. We now allow an
        # unchanged value (so the edit form can still save is_active/docs) but
        # reject an actual change rather than pretend it took effect.
        if 'threshold_value' in request.data:
            incoming = request.data['threshold_value']
            current = float(rule.threshold_value) if rule.threshold_value is not None else None
            incoming_f = float(incoming) if incoming is not None else None
            if incoming_f != current:
                return Response(
                    {"detail": "threshold_value is code-managed and cannot be edited here. "
                               "It mirrors the literal used by the rule engine; change it in "
                               "the rule function (and re-verify)."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        if 'severity' in request.data and request.data['severity'] != rule.severity:
            return Response(
                {"detail": "severity is code-managed and cannot be edited here. "
                           "It mirrors the rule engine's behaviour for this rule."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if 'rule_name' in request.data:
            rule.rule_name = request.data['rule_name']
        if 'criteria_set' in request.data:
            rule.criteria_set = request.data['criteria_set']

        # Update documentation fields
        if 'description' in request.data:
            rule.description = request.data['description']
        if 'implementation_notes' in request.data:
            rule.implementation_notes = request.data['implementation_notes']
        if 'example_case' in request.data:
            rule.example_case = request.data['example_case']
        if 'rejection_message' in request.data:
            rule.rejection_message = request.data['rejection_message']
        if 'flag_message' in request.data:
            rule.flag_message = request.data['flag_message']

        # Update organization fields
        if 'category' in request.data:
            rule.category = request.data['category']
        if 'is_creditor_specific' in request.data:
            rule.is_creditor_specific = request.data['is_creditor_specific']
        if 'applies_to_creditors' in request.data:
            rule.applies_to_creditors = request.data['applies_to_creditors']
        if 'execution_order' in request.data:
            rule.execution_order = request.data['execution_order']

        # Update reference fields
        if 'references' in request.data:
            rule.references = request.data['references']
        if 'related_rules' in request.data:
            rule.related_rules = request.data['related_rules']
        if 'depends_on_rules' in request.data:
            rule.depends_on_rules = request.data['depends_on_rules']

        # Update review fields
        if 'last_reviewed' in request.data:
            val = request.data['last_reviewed']
            rule.last_reviewed = val if val else None
        if 'review_notes' in request.data:
            rule.review_notes = request.data['review_notes']

        rule.updated_by = request.user
        rule.save()
        return Response(_rule_obj_to_dict(rule, include_full=True), status=status.HTTP_200_OK)

    def delete(self, request, rule_key):
        rule = self._get_object(rule_key)
        if rule is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        rule.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


def _council_to_dict(c):
    return {
        "id": c.id,
        "council_name": c.council_name,
        "status": c.status,
        "min_dividend_pence": c.min_dividend_pence,
        "do_not_chase": c.do_not_chase,
        "include_current_year_ct": c.include_current_year_ct,
        "reject_if_employed": c.reject_if_employed,
        "reject_if_unemployed_and_homeowner": c.reject_if_unemployed_and_homeowner,
        "reject_if_benefits_only": c.reject_if_benefits_only,
        "reject_if_any_benefits": c.reject_if_any_benefits,
        "reject_if_previous_iva": c.reject_if_previous_iva,
        "reject_if_dro_criteria_met": c.reject_if_dro_criteria_met,
        "reject_if_aoe_in_place": c.reject_if_aoe_in_place,
        "reject_if_joint_one_party_only": c.reject_if_joint_one_party_only,
        "reject_if_joint_both_parties": c.reject_if_joint_both_parties,
        "reject_if_joint_one_employed": c.reject_if_joint_one_employed,
        "reject_if_sole": c.reject_if_sole,
        "blocked_reason": c.blocked_reason,
        "criteria_changed_from_rej_date": c.criteria_changed_from_rej_date,
        "contact_name": c.contact_name,
        "contact_number": c.contact_number,
        "source_priority": c.source_priority,
        "last_reviewed": c.last_reviewed.isoformat() if c.last_reviewed else None,
    }


_COUNCIL_WRITABLE_FIELDS = [
    'council_name', 'status', 'min_dividend_pence', 'do_not_chase',
    'include_current_year_ct', 'reject_if_employed', 'reject_if_unemployed_and_homeowner',
    'reject_if_benefits_only', 'reject_if_any_benefits', 'reject_if_previous_iva',
    'reject_if_dro_criteria_met', 'reject_if_aoe_in_place', 'reject_if_joint_one_party_only',
    'reject_if_joint_both_parties', 'reject_if_sole', 'reject_if_joint_one_employed',
    'blocked_reason', 'criteria_changed_from_rej_date', 'contact_name', 'contact_number',
    'source_priority', 'last_reviewed',
]


class CouncilRuleListView(APIView):
    authentication_classes = [JWTAuthentication]
    required_feature = 'councils'

    def get_permissions(self):
        if self.request.method == 'GET':
            return [IsAuthenticated(), HasReadPermission()]
        return [IsAuthenticated(), HasWritePermission()]

    def get(self, request):
        page = int(request.query_params.get('page', 1))
        page_size = min(int(request.query_params.get('page_size', 100)), 500)
        search = request.query_params.get('search', '')

        queryset = CouncilRule.objects.all().order_by('council_name')
        if search:
            queryset = queryset.filter(council_name__icontains=search)

        queryset = filter_by_department(
            queryset, CouncilRule, request.user,
            DepartmentCouncilVisibility, 'council',
        )

        from django.core.paginator import Paginator
        paginator = Paginator(queryset, page_size)
        page_obj = paginator.get_page(page)

        return Response({
            "count": paginator.count,
            "next": f"{request.build_absolute_uri(request.path)}?page={page + 1}" if page_obj.has_next() else None,
            "previous": f"{request.build_absolute_uri(request.path)}?page={page - 1}" if page_obj.has_previous() else None,
            "results": [_council_to_dict(c) for c in page_obj],
        }, status=status.HTTP_200_OK)

    def post(self, request):
        data = request.data
        if not data.get('council_name'):
            return Response({"detail": "council_name is required."}, status=status.HTTP_400_BAD_REQUEST)

        if CouncilRule.objects.filter(council_name=data['council_name']).exists():
            return Response({"detail": "A council with this name already exists."}, status=status.HTTP_400_BAD_REQUEST)

        council = CouncilRule()
        for field in _COUNCIL_WRITABLE_FIELDS:
            if field in data:
                setattr(council, field, data[field])

        try:
            council.full_clean()
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        council.save()
        return Response(_council_to_dict(council), status=status.HTTP_201_CREATED)


class CouncilRuleDetailView(APIView):
    authentication_classes = [JWTAuthentication]
    required_feature = 'councils'

    def get_permissions(self):
        if self.request.method == 'GET':
            return [IsAuthenticated(), HasReadPermission()]
        return [IsAuthenticated(), HasWritePermission()]

    def _get_object(self, pk):
        try:
            return CouncilRule.objects.get(id=pk)
        except CouncilRule.DoesNotExist:
            return None

    def get(self, request, pk):
        council = self._get_object(pk)
        if council is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(_council_to_dict(council), status=status.HTTP_200_OK)

    def put(self, request, pk):
        council = self._get_object(pk)
        if council is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        for field in _COUNCIL_WRITABLE_FIELDS:
            if field in request.data:
                setattr(council, field, request.data[field])

        try:
            council.full_clean()
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        council.save()
        return Response(_council_to_dict(council), status=status.HTTP_200_OK)

    def delete(self, request, pk):
        council = self._get_object(pk)
        if council is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        council.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# County Council CRUD
#
# A CountyCouncil is the two-tier parent authority (e.g. Buckinghamshire
# County Council) — distinct from CouncilRule, which represents the
# council-tax-collecting district/borough/city/unitary authorities. Most
# county councils delegate council tax to their districts (routed via
# CountyCouncilRouting) but can still carry their own IVA voting criteria.
# ---------------------------------------------------------------------------

def _county_council_to_dict(c, include_districts=False):
    data = {
        "id": c.id,
        "county_name": c.county_name,
        "status": c.status,
        "deals_with_council_tax": c.deals_with_council_tax,
        "min_dividend_pence": c.min_dividend_pence,
        "blocked_reason": c.blocked_reason,
        "contact_name": c.contact_name,
        "contact_number": c.contact_number,
        "last_reviewed": c.last_reviewed.isoformat() if c.last_reviewed else None,
    }
    if include_districts:
        districts = [
            {
                "id": d.id,
                "district_name": d.district_name,
                "council_rule_id": d.council_rule_id,
                "council_rule_name": d.council_rule.council_name if d.council_rule_id else None,
                "council_rule_status": d.council_rule.status if d.council_rule_id else None,
            }
            for d in sorted(c.districts.all(), key=lambda d: d.district_name)
        ]
        data["districts"] = districts
        data["district_count"] = len(districts)
    else:
        data["district_count"] = c.districts.count()
    return data


_COUNTY_COUNCIL_WRITABLE_FIELDS = [
    'county_name', 'status', 'deals_with_council_tax', 'min_dividend_pence',
    'blocked_reason', 'contact_name', 'contact_number', 'last_reviewed',
]


class CountyCouncilListView(APIView):
    authentication_classes = [JWTAuthentication]
    required_feature = 'councils'

    def get_permissions(self):
        if self.request.method == 'GET':
            return [IsAuthenticated(), HasReadPermission()]
        return [IsAuthenticated(), HasWritePermission()]

    def get(self, request):
        page = int(request.query_params.get('page', 1))
        page_size = min(int(request.query_params.get('page_size', 100)), 500)
        search = request.query_params.get('search', '')

        queryset = CountyCouncil.objects.all().order_by('county_name').prefetch_related(
            'districts', 'districts__council_rule',
        )
        if search:
            queryset = queryset.filter(county_name__icontains=search)

        from django.core.paginator import Paginator
        paginator = Paginator(queryset, page_size)
        page_obj = paginator.get_page(page)

        return Response({
            "count": paginator.count,
            "next": f"{request.build_absolute_uri(request.path)}?page={page + 1}" if page_obj.has_next() else None,
            "previous": f"{request.build_absolute_uri(request.path)}?page={page - 1}" if page_obj.has_previous() else None,
            "results": [_county_council_to_dict(c, include_districts=True) for c in page_obj],
        }, status=status.HTTP_200_OK)

    def post(self, request):
        data = request.data
        if not data.get('county_name'):
            return Response({"detail": "county_name is required."}, status=status.HTTP_400_BAD_REQUEST)

        if CountyCouncil.objects.filter(county_name=data['county_name']).exists():
            return Response({"detail": "A county council with this name already exists."}, status=status.HTTP_400_BAD_REQUEST)

        county = CountyCouncil()
        for field in _COUNTY_COUNCIL_WRITABLE_FIELDS:
            if field in data:
                setattr(county, field, data[field])

        try:
            county.full_clean()
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        county.save()
        return Response(_county_council_to_dict(county), status=status.HTTP_201_CREATED)


class CountyCouncilDetailView(APIView):
    authentication_classes = [JWTAuthentication]
    required_feature = 'councils'

    def get_permissions(self):
        if self.request.method == 'GET':
            return [IsAuthenticated(), HasReadPermission()]
        return [IsAuthenticated(), HasWritePermission()]

    def _get_object(self, pk):
        try:
            return CountyCouncil.objects.get(id=pk)
        except CountyCouncil.DoesNotExist:
            return None

    def get(self, request, pk):
        county = self._get_object(pk)
        if county is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(_county_council_to_dict(county, include_districts=True), status=status.HTTP_200_OK)

    def put(self, request, pk):
        county = self._get_object(pk)
        if county is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        for field in _COUNTY_COUNCIL_WRITABLE_FIELDS:
            if field in request.data:
                setattr(county, field, request.data[field])

        try:
            county.full_clean()
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        county.save()
        return Response(_county_council_to_dict(county, include_districts=True), status=status.HTTP_200_OK)

    def delete(self, request, pk):
        county = self._get_object(pk)
        if county is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        county.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Application CRUD
# ---------------------------------------------------------------------------

def _application_to_dict(app):
    return {
        "id": app.id,
        "aryza_reference": app.aryza_reference,
        "client_name": app.client_name,
        "created_at": app.created_at.isoformat(),
    }


class ApplicationListView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAdminUser]

    def get(self, request):
        page = int(request.query_params.get('page', 1))
        page_size = min(int(request.query_params.get('page_size', 100)), 500)
        search = request.query_params.get('search', '')

        queryset = Application.objects.all().order_by('-created_at')
        if search:
            queryset = queryset.filter(
                Q(aryza_reference__icontains=search) | Q(client_name__icontains=search)
            )

        from django.core.paginator import Paginator
        paginator = Paginator(queryset, page_size)
        page_obj = paginator.get_page(page)

        return Response({
            "count": paginator.count,
            "next": f"{request.build_absolute_uri(request.path)}?page={page + 1}" if page_obj.has_next() else None,
            "previous": f"{request.build_absolute_uri(request.path)}?page={page - 1}" if page_obj.has_previous() else None,
            "results": [_application_to_dict(a) for a in page_obj],
        }, status=status.HTTP_200_OK)

    def post(self, request):
        data = request.data
        required = ['aryza_reference', 'client_name']
        for field in required:
            if not data.get(field):
                return Response({"detail": f"{field} is required."}, status=status.HTTP_400_BAD_REQUEST)

        if Application.objects.filter(aryza_reference=data['aryza_reference']).exists():
            return Response({"detail": "An application with this aryza_reference already exists."}, status=status.HTTP_400_BAD_REQUEST)

        app = Application(
            aryza_reference=data['aryza_reference'],
            client_name=data['client_name'],
        )

        try:
            app.full_clean()
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        app.save()
        return Response(_application_to_dict(app), status=status.HTTP_201_CREATED)


class ApplicationDetailView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAdminUser]

    def _get_object(self, pk):
        try:
            return Application.objects.get(id=pk)
        except Application.DoesNotExist:
            return None

    def get(self, request, pk):
        app = self._get_object(pk)
        if app is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(_application_to_dict(app), status=status.HTTP_200_OK)

    def put(self, request, pk):
        app = self._get_object(pk)
        if app is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        for field in ['aryza_reference', 'client_name']:
            if field in request.data:
                setattr(app, field, request.data[field])

        try:
            app.full_clean()
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        app.save()
        return Response(_application_to_dict(app), status=status.HTTP_200_OK)

    def delete(self, request, pk):
        app = self._get_object(pk)
        if app is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        app.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# EvidenceLedger CRUD
# ---------------------------------------------------------------------------

def _evidence_to_dict(e):
    return {
        "id": e.id,
        "application": e.application_id,
        "entry_type": e.entry_type,
        "created_at": e.created_at.isoformat(),
    }


class EvidenceLedgerListView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated, HasFeatureAccess]
    required_feature = 'evidence'

    def get(self, request):
        page = int(request.query_params.get('page', 1))
        page_size = min(int(request.query_params.get('page_size', 100)), 500)
        application_id = request.query_params.get('application_id')

        queryset = EvidenceLedger.objects.all().order_by('-created_at')
        if application_id:
            queryset = queryset.filter(application_id=application_id)

        from django.core.paginator import Paginator
        paginator = Paginator(queryset, page_size)
        page_obj = paginator.get_page(page)

        return Response({
            "count": paginator.count,
            "next": f"{request.build_absolute_uri(request.path)}?page={page + 1}" if page_obj.has_next() else None,
            "previous": f"{request.build_absolute_uri(request.path)}?page={page - 1}" if page_obj.has_previous() else None,
            "results": [_evidence_to_dict(e) for e in page_obj],
        }, status=status.HTTP_200_OK)

    def post(self, request):
        data = request.data
        required = ['application', 'entry_type']
        for field in required:
            if not data.get(field):
                return Response({"detail": f"{field} is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            app = Application.objects.get(id=data['application'])
        except Application.DoesNotExist:
            return Response({"detail": "Application not found."}, status=status.HTTP_400_BAD_REQUEST)

        evidence = EvidenceLedger(
            application=app,
            entry_type=data['entry_type'],
        )

        try:
            evidence.full_clean()
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        evidence.save()
        return Response(_evidence_to_dict(evidence), status=status.HTTP_201_CREATED)


class EvidenceLedgerDetailView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAdminUser]

    def _get_object(self, pk):
        try:
            return EvidenceLedger.objects.get(id=pk)
        except EvidenceLedger.DoesNotExist:
            return None

    def get(self, request, pk):
        evidence = self._get_object(pk)
        if evidence is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(_evidence_to_dict(evidence), status=status.HTTP_200_OK)

    def put(self, request, pk):
        evidence = self._get_object(pk)
        if evidence is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        if 'entry_type' in request.data:
            evidence.entry_type = request.data['entry_type']

        if 'application' in request.data:
            try:
                evidence.application = Application.objects.get(id=request.data['application'])
            except Application.DoesNotExist:
                return Response({"detail": "Application not found."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            evidence.full_clean()
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        evidence.save()
        return Response(_evidence_to_dict(evidence), status=status.HTTP_200_OK)

    def delete(self, request, pk):
        evidence = self._get_object(pk)
        if evidence is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        evidence.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Voter CRUD
# ---------------------------------------------------------------------------

def _voter_to_dict(v):
    return {
        "id": v.id,
        "name": v.name,
        "is_joint": v.is_joint,
        "last_payment_date": v.last_payment_date.isoformat() if v.last_payment_date else None,
        "first_payment_made": v.first_payment_made,
        "vehicle_arrears_months": v.vehicle_arrears_months,
        "ie_matches_loan_application": v.ie_matches_loan_application,
        "arrangement_confirmed_before_proposing": v.arrangement_confirmed_before_proposing,
        "client_still_has_asset_in_possession": v.client_still_has_asset_in_possession,
        "is_grant_overpayment": v.is_grant_overpayment,
        "guarantee_called_up": v.guarantee_called_up,
    }


_VOTER_WRITABLE_FIELDS = [
    'name', 'is_joint', 'last_payment_date', 'first_payment_made',
    'vehicle_arrears_months', 'ie_matches_loan_application',
    'arrangement_confirmed_before_proposing', 'client_still_has_asset_in_possession',
    'is_grant_overpayment', 'guarantee_called_up',
]


class VoterListView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAdminUser]

    def get(self, request):
        page = int(request.query_params.get('page', 1))
        page_size = min(int(request.query_params.get('page_size', 100)), 500)
        search = request.query_params.get('search', '')

        queryset = Voter.objects.all().order_by('name')
        if search:
            queryset = queryset.filter(name__icontains=search)

        from django.core.paginator import Paginator
        paginator = Paginator(queryset, page_size)
        page_obj = paginator.get_page(page)

        return Response({
            "count": paginator.count,
            "next": f"{request.build_absolute_uri(request.path)}?page={page + 1}" if page_obj.has_next() else None,
            "previous": f"{request.build_absolute_uri(request.path)}?page={page - 1}" if page_obj.has_previous() else None,
            "results": [_voter_to_dict(v) for v in page_obj],
        }, status=status.HTTP_200_OK)

    def post(self, request):
        data = request.data
        if not data.get('name'):
            return Response({"detail": "name is required."}, status=status.HTTP_400_BAD_REQUEST)

        voter = Voter()
        for field in _VOTER_WRITABLE_FIELDS:
            if field in data:
                setattr(voter, field, data[field])

        try:
            voter.full_clean()
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        voter.save()
        return Response(_voter_to_dict(voter), status=status.HTTP_201_CREATED)


class VoterDetailView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAdminUser]

    def _get_object(self, pk):
        try:
            return Voter.objects.get(id=pk)
        except Voter.DoesNotExist:
            return None

    def get(self, request, pk):
        voter = self._get_object(pk)
        if voter is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(_voter_to_dict(voter), status=status.HTTP_200_OK)

    def put(self, request, pk):
        voter = self._get_object(pk)
        if voter is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        for field in _VOTER_WRITABLE_FIELDS:
            if field in request.data:
                setattr(voter, field, request.data[field])

        try:
            voter.full_clean()
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        voter.save()
        return Response(_voter_to_dict(voter), status=status.HTTP_200_OK)

    def delete(self, request, pk):
        voter = self._get_object(pk)
        if voter is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        voter.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# User CRUD
# ---------------------------------------------------------------------------

def _user_to_dict(user):
    dept = None
    try:
        profile = user.profile
        if profile.department_id:
            dept = {'id': profile.department.id, 'name': profile.department.name}
    except Exception:
        pass
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "is_staff": user.is_staff,
        "role": 'admin' if user.is_staff else 'assessor',
        "is_active": user.is_active,
        "date_joined": user.date_joined.isoformat(),
        "department": dept,
    }


class UserListView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAdminUser]

    def get(self, request):
        page = int(request.query_params.get('page', 1))
        page_size = min(int(request.query_params.get('page_size', 100)), 500)
        search = request.query_params.get('search', '')

        queryset = User.objects.select_related('profile__department').all().order_by('username')
        if search:
            queryset = queryset.filter(
                Q(username__icontains=search) |
                Q(email__icontains=search) |
                Q(first_name__icontains=search) |
                Q(last_name__icontains=search)
            )

        from django.core.paginator import Paginator
        paginator = Paginator(queryset, page_size)
        page_obj = paginator.get_page(page)

        return Response({
            "count": paginator.count,
            "next": f"{request.build_absolute_uri(request.path)}?page={page + 1}" if page_obj.has_next() else None,
            "previous": f"{request.build_absolute_uri(request.path)}?page={page - 1}" if page_obj.has_previous() else None,
            "results": [_user_to_dict(u) for u in page_obj],
        }, status=status.HTTP_200_OK)

    def post(self, request):
        data = request.data
        required = ['username', 'email', 'password']
        for field in required:
            if not data.get(field):
                return Response({"detail": f"{field} is required."}, status=status.HTTP_400_BAD_REQUEST)

        if User.objects.filter(username=data['username']).exists():
            return Response({"detail": "A user with this username already exists."}, status=status.HTTP_400_BAD_REQUEST)

        if User.objects.filter(email=data['email']).exists():
            return Response({"detail": "A user with this email already exists."}, status=status.HTTP_400_BAD_REQUEST)

        user = User(
            username=data['username'],
            email=data['email'],
            first_name=data.get('first_name', ''),
            last_name=data.get('last_name', ''),
            is_staff=data.get('is_staff', False),
            is_active=data.get('is_active', True),
        )
        user.set_password(data['password'])

        try:
            user.full_clean()
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        user.save()
        return Response(_user_to_dict(user), status=status.HTTP_201_CREATED)


class UserDetailView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAdminUser]

    def _get_object(self, pk):
        try:
            return User.objects.get(id=pk)
        except User.DoesNotExist:
            return None

    def get(self, request, pk):
        user = self._get_object(pk)
        if user is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(_user_to_dict(user), status=status.HTTP_200_OK)

    def put(self, request, pk):
        user = self._get_object(pk)
        if user is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        for field in ['username', 'email', 'first_name', 'last_name', 'is_staff', 'is_active']:
            if field in request.data:
                setattr(user, field, request.data[field])

        if 'password' in request.data and request.data['password']:
            user.set_password(request.data['password'])

        try:
            user.full_clean()
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        user.save()
        return Response(_user_to_dict(user), status=status.HTTP_200_OK)

    def delete(self, request, pk):
        user = self._get_object(pk)
        if user is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        # Prevent self-deletion
        if user == request.user:
            return Response({"detail": "You cannot delete your own account."}, status=status.HTTP_400_BAD_REQUEST)
        user.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class RuleHistoryView(APIView):
    """
    Returns trigger history for a single rule_key.
    Queries CriteriaDecision.decision_output JSON to find
    how many times a rule was triggered and when last.
    """
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, rule_key):
        from debt_app.models import CriteriaDecision
        from django.utils import timezone
        from datetime import timedelta

        thirty_days_ago = timezone.now() - timedelta(days=30)

        all_decisions = CriteriaDecision.objects.all().order_by(
            '-triggered_at'
        )

        last_triggered = None
        count_30d = 0
        latest_case_id = None

        for decision in all_decisions:
            output = decision.decision_output or {}

            all_rules = (
                output.get('hard_blocks', []) +
                output.get('flags', []) +
                output.get('passed', []) +
                output.get('info', [])
            )

            rule_found = any(
                r.get('rule_id') == rule_key and r.get('triggered')
                for r in all_rules
            )

            if rule_found:
                if last_triggered is None:
                    last_triggered = decision.triggered_at
                    latest_case_id = decision.application_id
                if decision.triggered_at >= thirty_days_ago:
                    count_30d += 1

        return Response({
            "rule_key": rule_key,
            "last_triggered": last_triggered.isoformat()
                if last_triggered else None,
            "times_triggered_30d": count_30d,
            "latest_case_id": latest_case_id,
        })


# ---------------------------------------------------------------------------
# SFS Expenditure Guidelines
# ---------------------------------------------------------------------------

def _guideline_to_dict(g) -> dict:
    return {
        "id": g.id,
        "category": g.category,
        "label": g.label,
        "category_group": g.category_group_id,
        "max": g.max,
        "min": g.min,
        "sort_order": g.sort_order,
        "adult_1": float(g.adult_1),
        "adult_2": float(g.adult_2),
        "adult_1_child_1": float(g.adult_1_child_1),
        "adult_1_child_2": float(g.adult_1_child_2),
        "adult_1_child_3": float(g.adult_1_child_3),
        "adult_1_child_4": float(g.adult_1_child_4),
        "adult_1_child_5": float(g.adult_1_child_5),
        "adult_2_child_1": float(g.adult_2_child_1),
        "adult_2_child_2": float(g.adult_2_child_2),
        "adult_2_child_3": float(g.adult_2_child_3),
        "adult_2_child_4": float(g.adult_2_child_4),
        "adult_2_child_5": float(g.adult_2_child_5),
        "per_child": float(g.per_child),
        "per_vehicle": float(g.per_vehicle),
        "per_vehicle_max": float(g.per_vehicle_max),
        "first_adult": float(g.first_adult),
        "additional_adult": float(g.additional_adult),
        "child_under_16": float(g.child_under_16),
        "child_16_18": float(g.child_16_18),
        "watch_per_adult": float(g.watch_per_adult),
        "non_watch_per_adult": float(g.non_watch_per_adult),
        "watch_per_vehicle": float(g.watch_per_vehicle),
        "non_watch_per_vehicle": float(g.non_watch_per_vehicle),
        "one_adult_cap": float(g.one_adult_cap),
        "two_adults_cap": float(g.two_adults_cap),
        "formula": g.formula,
        "below_action": g.below_action,
        "above_action": g.above_action,
        "mismatch_action": g.mismatch_action,
        "notes": g.notes,
        "aryza_aliases": g.aryza_aliases,
        "created_at": g.created_at.isoformat(),
        "updated_at": g.updated_at.isoformat(),
    }


def _guideline_category_to_dict(cat, include_guidelines=False) -> dict:
    d = {
        "id": cat.id,
        "name": cat.name,
        "upper_cap": float(cat.upper_cap) if cat.upper_cap is not None else None,
        "sort_order": cat.sort_order,
    }
    if include_guidelines:
        d["guidelines"] = [_guideline_to_dict(g) for g in cat.guidelines.all()]
    return d


class ExpenditureGuidelineCategoryListView(APIView):
    authentication_classes = [JWTAuthentication]
    required_feature = 'sfs_guidelines'

    def get_permissions(self):
        if self.request.method == 'GET':
            return [IsAuthenticated(), HasFeatureAccess()]
        return [IsAdminUser()]

    def get(self, request):
        qs = GuidelineCategory.objects.prefetch_related('guidelines').order_by('sort_order', 'name')

        # For non-admins, filter nested guidelines by department visibility
        if not request.user.is_staff:
            from debt_app.helpers import get_user_department
            dept = get_user_department(request.user)
            results = []
            for cat in qs:
                guidelines_qs = filter_by_department(
                    cat.guidelines.all(), ExpenditureGuideline, request.user,
                    DepartmentSFSVisibility, 'guideline',
                )
                cat_dict = _guideline_category_to_dict(cat)
                cat_dict['guidelines'] = [_guideline_to_dict(g) for g in guidelines_qs]
                results.append(cat_dict)
            return Response({"count": len(results), "results": results}, status=status.HTTP_200_OK)

        return Response({
            "count": qs.count(),
            "results": [_guideline_category_to_dict(c, include_guidelines=True) for c in qs],
        }, status=status.HTTP_200_OK)

    def post(self, request):
        data = request.data
        name = data.get('name', '').strip()
        if not name:
            return error_response("name is required", "MISSING_NAME", status.HTTP_400_BAD_REQUEST)
        cat = GuidelineCategory.objects.create(
            name=name,
            upper_cap=data.get('upper_cap') or None,
            sort_order=int(data.get('sort_order', 0)),
        )
        return Response(_guideline_category_to_dict(cat), status=status.HTTP_201_CREATED)


class ExpenditureGuidelineCategoryDetailView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAdminUser]

    def _get_object(self, pk):
        try:
            return GuidelineCategory.objects.prefetch_related('guidelines').get(pk=pk)
        except GuidelineCategory.DoesNotExist:
            return None

    def get(self, request, pk):
        cat = self._get_object(pk)
        if cat is None:
            return error_response("Category not found", "NOT_FOUND", status.HTTP_404_NOT_FOUND)
        return Response(_guideline_category_to_dict(cat, include_guidelines=True), status=status.HTTP_200_OK)

    def patch(self, request, pk):
        cat = self._get_object(pk)
        if cat is None:
            return error_response("Category not found", "NOT_FOUND", status.HTTP_404_NOT_FOUND)
        data = request.data
        if 'name' in data:
            cat.name = data['name']
        if 'upper_cap' in data:
            cat.upper_cap = data['upper_cap'] or None
        if 'sort_order' in data:
            cat.sort_order = int(data['sort_order'])
        cat.save()
        return Response(_guideline_category_to_dict(cat, include_guidelines=True), status=status.HTTP_200_OK)

    def delete(self, request, pk):
        cat = self._get_object(pk)
        if cat is None:
            return error_response("Category not found", "NOT_FOUND", status.HTTP_404_NOT_FOUND)
        cat.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ExpenditureGuidelineListView(APIView):
    authentication_classes = [JWTAuthentication]
    required_feature = 'sfs_guidelines'

    def get_permissions(self):
        if self.request.method == 'GET':
            return [IsAuthenticated(), HasReadPermission()]
        return [IsAuthenticated(), HasWritePermission()]

    def get(self, request):
        qs = ExpenditureGuideline.objects.select_related('category_group').order_by(
            'category_group__sort_order', 'sort_order', 'category'
        )
        category_filter = request.query_params.get('category')
        if category_filter:
            qs = qs.filter(category=category_filter)

        qs = filter_by_department(
            qs, ExpenditureGuideline, request.user,
            DepartmentSFSVisibility, 'guideline',
        )

        return Response({
            "count": qs.count(),
            "results": [_guideline_to_dict(g) for g in qs],
        }, status=status.HTTP_200_OK)

    def post(self, request):
        data = request.data
        category = data.get('category', '').strip()
        label = data.get('label', '').strip()
        if not category:
            return error_response("category is required", "MISSING_CATEGORY", status.HTTP_400_BAD_REQUEST)
        if not label:
            return error_response("label is required", "MISSING_LABEL", status.HTTP_400_BAD_REQUEST)
        if ExpenditureGuideline.objects.filter(category=category).exists():
            return error_response("A guideline with this category already exists", "DUPLICATE_CATEGORY", status.HTTP_400_BAD_REQUEST)

        category_group = None
        if data.get('category_group'):
            try:
                category_group = GuidelineCategory.objects.get(pk=data['category_group'])
            except GuidelineCategory.DoesNotExist:
                return error_response("category_group not found", "INVALID_CATEGORY_GROUP", status.HTTP_400_BAD_REQUEST)

        decimal_fields = [
            'adult_1', 'adult_2',
            'adult_1_child_1', 'adult_1_child_2', 'adult_1_child_3', 'adult_1_child_4', 'adult_1_child_5',
            'adult_2_child_1', 'adult_2_child_2', 'adult_2_child_3', 'adult_2_child_4', 'adult_2_child_5',
            'per_child', 'per_vehicle', 'per_vehicle_max', 'first_adult', 'additional_adult',
            'child_under_16', 'child_16_18',
            'watch_per_adult', 'non_watch_per_adult', 'watch_per_vehicle', 'non_watch_per_vehicle',
            'one_adult_cap', 'two_adults_cap',
        ]
        kwargs = {
            'category': category,
            'label': label,
            'category_group': category_group,
            'max': bool(data.get('max', False)),
            'min': bool(data.get('min', False)),
            'sort_order': int(data.get('sort_order', 0)),
            'formula': data.get('formula', ''),
            'below_action': data.get('below_action', ''),
            'above_action': data.get('above_action', ''),
            'mismatch_action': data.get('mismatch_action', ''),
            'notes': data.get('notes', ''),
            'aryza_aliases': data.get('aryza_aliases', ''),
        }
        for f in decimal_fields:
            kwargs[f] = data.get(f, 0) or 0

        g = ExpenditureGuideline.objects.create(**kwargs)
        return Response(_guideline_to_dict(g), status=status.HTTP_201_CREATED)


class ExpenditureGuidelineDetailView(APIView):
    authentication_classes = [JWTAuthentication]
    required_feature = 'sfs_guidelines'

    def get_permissions(self):
        if self.request.method == 'GET':
            return [IsAuthenticated(), HasReadPermission()]
        return [IsAuthenticated(), HasWritePermission()]

    def _get_object(self, pk):
        try:
            return ExpenditureGuideline.objects.select_related('category_group').get(pk=pk)
        except ExpenditureGuideline.DoesNotExist:
            return None

    def get(self, request, pk):
        g = self._get_object(pk)
        if g is None:
            return error_response("Guideline not found", "NOT_FOUND", status.HTTP_404_NOT_FOUND)
        return Response(_guideline_to_dict(g), status=status.HTTP_200_OK)

    def patch(self, request, pk):
        g = self._get_object(pk)
        if g is None:
            return error_response("Guideline not found", "NOT_FOUND", status.HTTP_404_NOT_FOUND)
        data = request.data
        updatable = [
            'label', 'max', 'min', 'sort_order', 'formula',
            'below_action', 'above_action', 'mismatch_action', 'notes', 'aryza_aliases',
            'adult_1', 'adult_2',
            'adult_1_child_1', 'adult_1_child_2', 'adult_1_child_3', 'adult_1_child_4', 'adult_1_child_5',
            'adult_2_child_1', 'adult_2_child_2', 'adult_2_child_3', 'adult_2_child_4', 'adult_2_child_5',
            'per_child', 'per_vehicle', 'per_vehicle_max', 'first_adult', 'additional_adult',
            'child_under_16', 'child_16_18',
            'watch_per_adult', 'non_watch_per_adult', 'watch_per_vehicle', 'non_watch_per_vehicle',
            'one_adult_cap', 'two_adults_cap',
        ]
        for field in updatable:
            if field in data:
                setattr(g, field, data[field])
        if 'category_group' in data:
            if data['category_group'] is None:
                g.category_group = None
            else:
                try:
                    g.category_group = GuidelineCategory.objects.get(pk=data['category_group'])
                except GuidelineCategory.DoesNotExist:
                    return error_response("category_group not found", "INVALID_CATEGORY_GROUP", status.HTTP_400_BAD_REQUEST)
        g.save()
        return Response(_guideline_to_dict(g), status=status.HTTP_200_OK)

    def delete(self, request, pk):
        g = self._get_object(pk)
        if g is None:
            return error_response("Guideline not found", "NOT_FOUND", status.HTTP_404_NOT_FOUND)
        g.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class _InternalKeyOrAuthenticated(BasePermission):
    """
    Grants access when a valid X-Internal-Key header is present (service-to-service),
    or when the request carries a valid JWT (human user via browser/API).
    """
    def has_permission(self, request, view):
        internal_key = request.headers.get("X-Internal-Key", "")
        expected = getattr(django_settings, "DEBT_CRITERIA_INTERNAL_KEY", "")
        if internal_key and expected and internal_key == expected:
            return True
        return bool(request.user and request.user.is_authenticated)


class CreditReportUploadView(APIView):
    """
    POST /api/v1/criteria/credit-report/upload/
    Open endpoint — no JWT required. The CA backend can upload credit
    report PDFs without a token, matching /api/v1/assess/ behaviour.
    """
    authentication_classes = []
    permission_classes = [AllowAny]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        aryza_reference = (request.data.get("aryza_reference") or "").strip()
        if not aryza_reference:
            return Response(
                {"success": False, "error": "aryza_reference is required.", "code": "MISSING_REFERENCE"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        uploaded_file = request.FILES.get("credit_report")
        if not uploaded_file:
            return Response(
                {"success": False, "error": "credit_report file is required.", "code": "MISSING_FILE"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        name_lower = uploaded_file.name.lower()
        if not name_lower.endswith(".pdf"):
            return Response(
                {"success": False, "error": "File must be a PDF (.pdf extension required).", "code": "INVALID_FILE_TYPE"},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        header = uploaded_file.read(4)
        uploaded_file.seek(0)
        if header != b"%PDF":
            return Response(
                {"success": False, "error": "File does not appear to be a valid PDF.", "code": "INVALID_PDF"},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        if uploaded_file.size == 0:
            return Response(
                {"success": False, "error": "Uploaded file is empty.", "code": "INVALID_PDF"},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        # uploaded_by is nullable — None when the request comes from the internal service key
        uploader = request.user if (request.user and request.user.is_authenticated) else None
        record = CreditReport.objects.create(
            aryza_reference=aryza_reference,
            uploaded_file=uploaded_file,
            extraction_status="pending",
            uploaded_by=uploader,
        )

        try:
            result = extract_credit_report(record.uploaded_file.path)
            if "extraction_error" in result:
                record.extraction_status = "failed"
                record.extraction_error = result["extraction_error"]
                record.save(update_fields=["extraction_status", "extraction_error", "updated_at"])
                return Response({
                    "success": True,
                    "credit_report_id": record.id,
                    "aryza_reference": aryza_reference,
                    "agency": "",
                    "extraction_status": "failed",
                    "accounts_found": 0,
                    "client_name_on_report": "",
                    "unmatched_accounts": [],
                    "message": "Credit report uploaded but extraction failed",
                })

            record.extracted_data = result
            record.agency = result.get("agency", "")
            record.client_name_on_report = result.get("client_name", "")
            record.extraction_status = "extracted"
            record.save(update_fields=["extracted_data", "agency", "client_name_on_report", "extraction_status", "updated_at"])

            logger.info(
                "[CREDIT REPORT EXTRACT] ref=%s agency=%s accounts=%d unmatched=%s matched=%s",
                aryza_reference,
                record.agency,
                len(result.get("accounts", [])),
                result.get("unmatched_accounts", []),
                [a.get("matched_creditor") for a in result.get("accounts", [])],
            )

            return Response({
                "success": True,
                "credit_report_id": record.id,
                "aryza_reference": aryza_reference,
                "agency": record.agency,
                "extraction_status": "extracted",
                "accounts_found": len(result.get("accounts", [])),
                "client_name_on_report": record.client_name_on_report,
                "unmatched_accounts": result.get("unmatched_accounts", []),
                "accounts": result.get("accounts", []),
                "mortgage_accounts": result.get("mortgage_accounts", []),
                "other_accounts": result.get("other_accounts", []),
                "public_information": result.get("public_information", {}),
                "message": "Credit report uploaded and extracted successfully",
            })

        except Exception as exc:
            logger.error("Credit report extraction failed: %s", exc, exc_info=True)
            record.extraction_status = "failed"
            record.extraction_error = str(exc)
            record.save(update_fields=["extraction_status", "extraction_error", "updated_at"])
            return Response({
                "success": True,
                "credit_report_id": record.id,
                "aryza_reference": aryza_reference,
                "agency": "",
                "extraction_status": "failed",
                "accounts_found": 0,
                "client_name_on_report": "",
                "unmatched_accounts": [],
                "message": "Credit report uploaded but extraction failed",
            })


# ---------------------------------------------------------------------------
# My Department
# ---------------------------------------------------------------------------

class MyDepartmentView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        dept = get_user_department(request.user)
        if dept is None:
            return Response({"department": None}, status=status.HTTP_200_OK)
        return Response({
            "department": {
                "id": dept.id,
                "name": dept.name,
                "slug": dept.slug,
                "description": dept.description,
            }
        }, status=status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# Creditor Outcome Tracker
# ---------------------------------------------------------------------------

class CreditorOutcomeListView(APIView):
    authentication_classes = [JWTAuthentication]
    required_feature = 'general_creditors'

    def get_permissions(self):
        if self.request.method == 'GET':
            return [IsAuthenticated(), HasReadPermission()]
        return [IsAuthenticated(), HasWritePermission()]

    def get(self, request, id):
        creditor = CreditorCriteria.objects.filter(id=id).first()
        if not creditor:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        outcomes = creditor.outcomes.select_related('submitted_by').all()
        approved = outcomes.filter(outcome='approved').count()
        disapproved = outcomes.filter(outcome='disapproved').count()

        return Response({
            "tally": {
                "approved": approved,
                "disapproved": disapproved,
                "total": approved + disapproved,
            },
            "outcomes": [
                {
                    "id": o.id,
                    "case_reference": o.case_reference,
                    "outcome": o.outcome,
                    "outcome_date": o.outcome_date,
                    "comment": o.comment,
                    "submitted_by": o.submitted_by.get_full_name() or o.submitted_by.username if o.submitted_by else None,
                    "submitted_at": o.submitted_at,
                }
                for o in outcomes
            ]
        })

    def post(self, request, id):
        creditor = CreditorCriteria.objects.filter(id=id).first()
        if not creditor:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        case_reference = request.data.get("case_reference", "").strip()
        outcome = request.data.get("outcome", "").strip()
        outcome_date = request.data.get("outcome_date")
        comment = request.data.get("comment", "").strip()

        if not case_reference:
            return Response({"detail": "case_reference is required."}, status=status.HTTP_400_BAD_REQUEST)
        if outcome not in ('approved', 'disapproved'):
            return Response({"detail": "outcome must be 'approved' or 'disapproved'."}, status=status.HTTP_400_BAD_REQUEST)
        if not outcome_date:
            return Response({"detail": "outcome_date is required."}, status=status.HTTP_400_BAD_REQUEST)

        # Validate the case reference exists in Aryza before saving
        try:
            fetch_case_by_reference(case_reference)
        except AryzaCaseNotFoundError:
            return Response(
                {
                    "detail": f"Case reference '{case_reference}' was not found in Aryza. "
                              "Please check the reference and try again.",
                    "field": "case_reference",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        except (AryzaConnectionError, AryaTimeoutError, AryzaDataError, Exception):
            return Response(
                {
                    "detail": "Unable to validate case reference against Aryza. Please try again.",
                    "field": "case_reference",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        outcome_obj = CreditorOutcome.objects.create(
            creditor=creditor,
            case_reference=case_reference,
            outcome=outcome,
            outcome_date=outcome_date,
            comment=comment,
            submitted_by=request.user,
        )

        return Response({
            "id": outcome_obj.id,
            "case_reference": outcome_obj.case_reference,
            "outcome": outcome_obj.outcome,
            "outcome_date": outcome_obj.outcome_date,
            "comment": outcome_obj.comment,
            "submitted_by": request.user.get_full_name() or request.user.username,
            "submitted_at": outcome_obj.submitted_at,
        }, status=status.HTTP_201_CREATED)

    def delete(self, request, id):
        outcome_id = request.data.get("outcome_id")
        if not outcome_id:
            return Response({"detail": "outcome_id is required."}, status=status.HTTP_400_BAD_REQUEST)

        outcome = CreditorOutcome.objects.filter(id=outcome_id, creditor__id=id).first()
        if not outcome:
            return Response({"detail": "Outcome not found."}, status=status.HTTP_404_NOT_FOUND)

        outcome.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

class CreditorAuditLogView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated, HasReadPermission]
    required_feature = 'general_creditors'

    def get(self, request, id):
        creditor = CreditorCriteria.objects.filter(id=id).first()
        if not creditor:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        logs = creditor.audit_logs.select_related('changed_by').order_by('-changed_at')

        return Response([
            {
                "id": log.id,
                "field_name": log.field_name,
                "old_value": log.old_value,
                "new_value": log.new_value,
                "action": log.action,
                "changed_by": log.changed_by.get_full_name() or log.changed_by.username if log.changed_by else None,
                "changed_at": log.changed_at,
            }
            for log in logs
        ])


# ---------------------------------------------------------------------------
# Creditor Vote Summary
# ---------------------------------------------------------------------------

def _vote_summary_to_dict(summary) -> dict:
    if not summary:
        return None
    return {
        "id": summary.id,
        "total_votes": summary.total_votes,
        "accepted_count": summary.accepted_count,
        "rejected_count": summary.rejected_count,
        "modified_count": summary.modified_count,
        "pod_count": summary.pod_count,
        "latest_vote_date": summary.latest_vote_date.isoformat() if summary.latest_vote_date else None,
        "latest_vote_outcome": summary.latest_vote_outcome,
        "crm_rows_covered": summary.crm_rows_covered,
        "last_synced_at": summary.last_synced_at.isoformat(),
        "recent_tally": get_recent_vote_tally(summary),
        "last_5_tally": get_last_5_tally(summary),
    }


class CreditorVoteSummaryView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated, HasReadPermission]

    def get_permissions(self):
        # Determine required feature based on creditor type
        creditor_type = self.kwargs.get('type', '')
        if creditor_type == 'councils':
            self.required_feature = 'councils'
        elif creditor_type == 'county-councils':
            self.required_feature = 'councils'
        else:  # general creditors, which representative, etc.
            self.required_feature = 'general_creditors'
        return [IsAuthenticated(), HasReadPermission()]

    def get(self, request, type, id):
        creditor_obj = None
        if type == 'creditors':
            creditor_obj = CreditorCriteria.objects.filter(id=id).first()
            if not creditor_obj:
                return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
            summary = creditor_obj.vote_summaries.first()
        elif type == 'councils':
            creditor_obj = CouncilRule.objects.filter(id=id).first()
            if not creditor_obj:
                return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
            summary = creditor_obj.vote_summaries.first()
        elif type == 'county-councils':
            creditor_obj = CountyCouncil.objects.filter(id=id).first()
            if not creditor_obj:
                return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
            summary = creditor_obj.vote_summaries.first()
        else:
            return Response({"detail": "Invalid creditor type."}, status=status.HTTP_400_BAD_REQUEST)

        return Response(_vote_summary_to_dict(summary))


def _crm_sync_run_to_dict(run) -> dict:
    duration_seconds = None
    if run.finished_at:
        duration_seconds = (run.finished_at - run.started_at).total_seconds()
    return {
        "id": run.id,
        "status": run.status,
        "stage": run.stage,
        "trigger_source": run.trigger_source,
        "started_at": run.started_at.isoformat(),
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "duration_seconds": duration_seconds,
        "dry_run": run.dry_run,
        "crm_rows_fetched": run.crm_rows_fetched,
        "records_created": run.records_created,
        "records_updated": run.records_updated,
        "creditor_criteria_count": run.creditor_criteria_count,
        "council_rule_count": run.council_rule_count,
        "county_council_count": run.county_council_count,
        "error_message": run.error_message,
        "triggered_by": run.triggered_by.username if run.triggered_by else None,
    }


def _run_crm_sync_in_background(run_id):
    """
    Thread target: runs the CRM vote sync for the given CrmSyncRun id and updates
    its status on completion/failure. Runs in its own thread, so it must close its
    own DB connections when done (this isn't a request-response cycle).
    """
    from django.db import connections
    try:
        run = CrmSyncRun.objects.get(pk=run_id)
        try:
            run_crm_vote_sync(run=run, dry_run=run.dry_run)
            run.status = "SUCCESS"
            run.finished_at = timezone.now()
            run.save(update_fields=["status", "finished_at"])
        except Exception as e:
            run.status = "FAILED"
            run.finished_at = timezone.now()
            run.error_message = str(e)
            run.save(update_fields=["status", "finished_at", "error_message"])
    finally:
        connections.close_all()


# A real sync (background thread or CLI) finishes in well under a minute in
# practice (see CrmSyncRun history), and the CRM query itself is capped at
# MAX_EXECUTION_TIME=600000ms (10 min) in crm_vote_sync.py. A RUNNING row
# older than this is not a slow sync - it's one whose process was killed
# (Ctrl+C, dev-server reload, crash) before it could mark itself FAILED, and
# would otherwise block every future trigger with a 409 forever.
STALE_RUN_THRESHOLD = timedelta(minutes=30)


class CrmSyncTriggerView(APIView):
    authentication_classes = [JWTAuthentication]
    required_feature = 'global_rules'

    def get_permissions(self):
        return [IsAuthenticated(), HasWritePermission()]

    def post(self, request):
        CrmSyncRun.objects.filter(
            status='RUNNING', started_at__lt=timezone.now() - STALE_RUN_THRESHOLD,
        ).update(
            status='FAILED',
            error_message='Orphaned - process terminated before completion (auto-detected as stale)',
            finished_at=timezone.now(),
        )

        existing = CrmSyncRun.objects.filter(status='RUNNING').first()
        if existing:
            return Response(
                {"detail": "A sync is already running.", "id": existing.id, "status": existing.status},
                status=status.HTTP_409_CONFLICT,
            )

        run = CrmSyncRun.objects.create(trigger_source='MANUAL', triggered_by=request.user)

        thread = threading.Thread(target=_run_crm_sync_in_background, args=(run.id,), daemon=True)
        thread.start()

        return Response({"id": run.id, "status": "RUNNING"}, status=status.HTTP_202_ACCEPTED)


class CrmSyncStatusView(APIView):
    authentication_classes = [JWTAuthentication]
    required_feature = 'global_rules'

    def get_permissions(self):
        return [IsAuthenticated(), HasReadPermission()]

    def get(self, request, pk):
        run = CrmSyncRun.objects.filter(pk=pk).first()
        if not run:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(_crm_sync_run_to_dict(run))


class CrmSyncHistoryView(APIView):
    authentication_classes = [JWTAuthentication]
    required_feature = 'global_rules'

    def get_permissions(self):
        return [IsAuthenticated(), HasReadPermission()]

    def get(self, request):
        page = int(request.query_params.get('page', 1))
        page_size = min(int(request.query_params.get('page_size', 100)), 500)

        queryset = CrmSyncRun.objects.all()

        from django.core.paginator import Paginator
        paginator = Paginator(queryset, page_size)
        page_obj = paginator.get_page(page)

        return Response({
            "count": paginator.count,
            "next": f"{request.build_absolute_uri(request.path)}?page={page + 1}" if page_obj.has_next() else None,
            "previous": f"{request.build_absolute_uri(request.path)}?page={page - 1}" if page_obj.has_previous() else None,
            "results": [_crm_sync_run_to_dict(r) for r in page_obj],
        }, status=status.HTTP_200_OK)


class CrmSyncRunCreditorBreakdownView(APIView):
    authentication_classes = [JWTAuthentication]
    required_feature = 'global_rules'

    def get_permissions(self):
        return [IsAuthenticated(), HasReadPermission()]

    def get(self, request, run_id):
        if not CrmSyncRun.objects.filter(pk=run_id).exists():
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        # Single aggregate query: counts per (vote_summary, status) for this run.
        # Avoids the N+1 that calling get_recent_vote_tally() per creditor would cause.
        counts_by_summary_and_status = (
            CreditorVoteChangeEvent.objects
            .filter(sync_run_id=run_id)
            .values('vote_summary_id', 'status')
            .annotate(count=Count('id'))
        )

        summary_ids = {row['vote_summary_id'] for row in counts_by_summary_and_status}
        summaries = CreditorVoteSummary.objects.filter(id__in=summary_ids).select_related(
            'creditor_criteria', 'council_rule', 'county_council'
        )

        creditor_info_by_summary_id = {}
        for summary in summaries:
            if summary.creditor_criteria:
                creditor_info_by_summary_id[summary.id] = {
                    "creditor_id": summary.creditor_criteria_id,
                    "creditor_name": summary.creditor_criteria.creditor_name,
                    "creditor_type": "creditors",
                }
            elif summary.council_rule:
                creditor_info_by_summary_id[summary.id] = {
                    "creditor_id": summary.council_rule_id,
                    "creditor_name": summary.council_rule.council_name,
                    "creditor_type": "councils",
                }
            elif summary.county_council:
                creditor_info_by_summary_id[summary.id] = {
                    "creditor_id": summary.county_council_id,
                    "creditor_name": summary.county_council.county_name,
                    "creditor_type": "county-councils",
                }

        results_by_summary_id = {}
        for row in counts_by_summary_and_status:
            summary_id = row['vote_summary_id']
            info = creditor_info_by_summary_id.get(summary_id)
            if not info:
                continue
            entry = results_by_summary_id.setdefault(summary_id, {
                "vote_summary_id": summary_id,
                **info,
                "accepted": 0,
                "rejected": 0,
                "modified": 0,
                "pod": 0,
            })
            entry[row['status']] = row['count']

        return Response({
            "run_id": run_id,
            "creditors": list(results_by_summary_id.values()),
        })


class CrmSyncTodayView(APIView):
    """
    Rolled-up totals for "today" (Europe/London calendar day), across ALL
    CrmSyncRun runs that occurred today - not a single run.
    """
    authentication_classes = [JWTAuthentication]
    required_feature = 'global_rules'

    def get_permissions(self):
        return [IsAuthenticated(), HasReadPermission()]

    def get(self, request):
        from debt_app.services.daily_digest import compute_daily_stats

        # Same computation as crm_vote_sync.py's _create_moc_alerts_for_run
        # (Prompt 10a): timezone.now().date() would give the UTC calendar
        # date, which disagrees with the Europe/London calendar date for part
        # of every day during BST. localtime() converts to the active
        # Europe/London time first, so this always matches the calendar day
        # site users actually experience. compute_daily_stats() does the same
        # local-day-bounds computation (shared with send_moc_daily_digest) so
        # this tile and the emailed digest can never show different numbers.
        stats = compute_daily_stats()
        today = stats["date"]

        return Response({
            "date": today.isoformat(),
            "vote_change_events": stats["vote_change_events"],
            "moc_alerts_today": stats["moc_alerts_today"],
            "sync_runs_today": stats["sync_runs_today"],
            "distinct_creditors_affected": stats["distinct_creditors_affected"],
            # Alerts/milestones are only emailed once a day by the
            # send_moc_daily_digest management command, which flips
            # emailed=True on every row it just sent. So "email_sent_today"
            # reflects whether that digest has actually gone out today, not
            # just whether alert rows exist yet.
            "email_sent_today": (
                CreditorMocAlert.objects.filter(alert_date=today, emailed=True).exists()
                or CreditorNonAcceptMilestone.objects.filter(milestone_date=today, emailed=True).exists()
            ),
        })


NON_ACCEPT_STATUSES = ('rejected', 'modified', 'pod')


def check_non_accept_milestone(vote_summary, sync_run):
    """
    Check each non-accepted status (rejected, modified, pod) independently for
    this creditor. Any status that reaches 3+ events within a single UK
    calendar day - and hasn't already triggered a milestone today for that
    status - gets its own CreditorNonAcceptMilestone row.

    Returns a list of newly created milestones (may be empty, or contain more
    than one if several statuses cross the threshold in the same check).
    """
    from django.db import IntegrityError, transaction
    from debt_app.helpers import get_london_day_boundary

    # Get London calendar day boundaries
    day_start, day_end, today_date = get_london_day_boundary()

    created_milestones = []

    for status in NON_ACCEPT_STATUSES:
        # Query this vote_summary's CreditorVoteChangeEvent rows for this exact
        # status, within today's London day, ordered by detected_at ascending.
        events = list(
            CreditorVoteChangeEvent.objects.filter(
                vote_summary=vote_summary,
                status=status,
                detected_at__gte=day_start,
                detected_at__lt=day_end
            )
            .order_by('detected_at')
        )

        if len(events) < 3:
            continue

        first_event_at = events[0].detected_at
        third_event_at = events[2].detected_at

        try:
            # Wrapped in its own savepoint so a duplicate-today IntegrityError
            # only rolls back this insert, not any outer transaction the
            # caller may be running inside (e.g. a test harness).
            with transaction.atomic():
                milestone = CreditorNonAcceptMilestone.objects.create(
                    vote_summary=vote_summary,
                    milestone_date=today_date,
                    status=status,
                    first_event_at=first_event_at,
                    third_event_at=third_event_at,
                    count=len(events),
                )
            created_milestones.append(milestone)
        except IntegrityError:
            # Already triggered today for this status - expected/normal, not an error.
            continue

    return created_milestones
