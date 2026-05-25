import logging
from decimal import Decimal
from django.contrib.auth.models import User
from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework import status
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import IsAuthenticated, IsAdminUser
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
from debt_app.criteria_engine import assess_case
from debt_app.recommendation_engine import get_recommendation
from debt_app.helpers import (
    GlobalCriteria, CreditorCriteria, CriteriaDecision, CouncilRule,
    Application, EvidenceLedger, Voter,
)
from debt_app.models import GuidelineCategory, ExpenditureGuideline, CreditReport
from debt_app.credit_report_extractor import extract_credit_report

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
    }


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


def build_rules_config() -> dict:
    """
    Load all active GlobalCriteria records and convert to
    the rules_config dict format expected by assess_case().
    Keyed by rule_key. Inactive rules are included with
    is_active=False so the engine can skip them.
    """
    rules_config = {}
    for rule in GlobalCriteria.objects.all():
        rules_config[rule.rule_key] = {
            "rule_key":        rule.rule_key,
            "rule_name":       rule.rule_name,
            "criteria_set":    rule.criteria_set,
            "severity":        rule.severity,
            "is_active":       rule.is_active,
            "threshold_value": rule.threshold_value or 0,
        }
    return rules_config


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
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]
    throttle_classes = [AssessRateThrottle]

    def _prepare_engine_payload(self, case_data_obj):
        """
        Transforms Aryza CaseData object into the payload format expected by the criteria engine.
        
        Converts pence (int) to pounds (float).
        Excludes secured debt types (mortgage, hp, etc).
        Deduplicates on (creditor_name, debt_type, reference) — same name + type + reference = skip.
        Applies CREDITOR_ALIAS_MAP to resolve names BEFORE passing to engine.
        This ensures detect_representatives() matches correctly.
        
        Returns: (payload, prepared_creditors)
          payload: dict for assess_case()
          prepared_creditors: list of creditor dicts, used for ACCEPT creditor restoration
        """
        from debt_app.helpers import CREDITOR_ALIAS_MAP

        # Secured debt types — exclude ONLY if debt type confirms it
        _SECURED_DEBT_TYPES = frozenset({
            'mortgage', 'hire_purchase', 'hp', 'secured_loan',
            'secured', 'charge', 'second_charge', 'secured loan'
        })

        # Convert pence to pounds for all financial fields
        _income_total_pence = (case_data_obj.income or {}).get("total", 0) or 0
        _expenditure_total_pence = (case_data_obj.expenditure or {}).get("total", 0) or 0
        if _expenditure_total_pence > 0:
            di_pounds = (_income_total_pence - _expenditure_total_pence) / 100.0
        else:
            di_pounds = case_data_obj.disposable_income / 100.0
        
        # Deduplication on (name, type, reference) — same entry only counted once
        seen_keys = set()
        prepared_creditors = []
        unsecured_debt_pounds = 0

        raw_creditors = case_data_obj.creditors or []

        for creditor in raw_creditors:
            raw_name = (creditor.get('name') or '').strip()
            if not raw_name:
                continue

            raw_lower = raw_name.lower()
            debt_type = (creditor.get('type') or creditor.get('creditor_type') or '').strip().lower()
            ref = (creditor.get('ref') or creditor.get('reference') or '').strip().lower()

            # STEP 4 — HP Exclusion: ONLY if debt_type confirms it is secured
            if debt_type in _SECURED_DEBT_TYPES:
                logger.warning(
                    f"[EXCLUDE SECURED] '{raw_name}' type='{debt_type}'"
                )
                continue

            # Log anomaly: HP in name but unsecured type — keep it
            is_hp_name = 'hp' in raw_lower.split()
            if is_hp_name and debt_type not in _SECURED_DEBT_TYPES:
                logger.warning(
                    f"[KEEP HP NAME UNSECURED] '{raw_name}' "
                    f"type='{debt_type}' — name has HP but type is unsecured"
                )

            # Apply alias map — deterministic, no false positives
            resolved_name = CREDITOR_ALIAS_MAP.get(raw_lower, raw_name)

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
            unsecured_debt_pounds += balance_pounds

            creditor_dict = {
                **creditor,
                'creditor_name': resolved_name,  # engine uses this for detection
                'original_name': raw_name,       # preserve raw for reference
                'crm_balance': balance_pounds,
                'balance': balance_pounds,
                'debt_type_normalised': debt_type,
            }
            prepared_creditors.append(creditor_dict)
            
            logger.warning(
                f"[PASS TO ENGINE] '{raw_name}' → '{resolved_name}' "
                f"balance=£{balance_pounds:,.2f} type='{debt_type}'"
            )

        logger.warning(
            f"[PREPARED] {len(prepared_creditors)} creditors → engine"
        )

        # Build the engine payload matching CASE_ASSESSMENT_PAYLOAD.md
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
                "total_income": case_data_obj.income["total"] / 100.0,
                "income_source": case_data_obj.employment_status,
            },
            "crm_data": {
                "total_unsecured_debt": unsecured_debt_pounds,
            },
            "creditors": prepared_creditors,
            "income": {k: v/100.0 for k, v in case_data_obj.income.items()},
            "expenditure": {k: v/100.0 for k, v in case_data_obj.expenditure.items()},
            "third_party_contribution": case_data_obj.income.get("third_party_contribution", 0) / 100.0,
            "property": {
                "owns_property": case_data_obj.property.get("owns_property", False),
                "property_value": (case_data_obj.property.get("property_value") or 0) / 100.0 if case_data_obj.property.get("property_value") is not None else 0.0,
                "mortgage_balance": (
                    (case_data_obj.property.get("mortgage_balance") or 0) / 100.0
                    or sum(
                        float(cr.get("balance") or 0) / 100.0
                        for cr in (case_data_obj.creditors or [])
                        if (cr.get("type") or cr.get("creditor_type") or "").lower()
                        in {"mortgage", "secured", "secured_loan", "second_charge"}
                    )
                ),
                "equity": (case_data_obj.property.get("equity") or 0) / 100.0 if case_data_obj.property.get("equity") is not None else 0.0,
            },
            "vehicle": {
                "has_vehicle": case_data_obj.vehicle.get("has_vehicle", False),
                "vehicle_value": (case_data_obj.vehicle.get("vehicle_value") or 0) / 100.0 if case_data_obj.vehicle.get("vehicle_value") else None,
                "hp_monthly_payment": (case_data_obj.vehicle.get("hp_monthly_payment") or 0) / 100.0 if case_data_obj.vehicle.get("hp_monthly_payment") else None,
            },
            "sfs_expenditure_breakdown": case_data_obj.sfs_expenditure_breakdown,
            "gold_transactions": case_data_obj.gold_transactions,
            "flags": case_data_obj.flags,
            "previous_iva_failed_reason": case_data_obj.flags.get("previous_iva_failed_reason"),
            "dependants": case_data_obj.dependants,
        }

        # Step 6 — Calculate aggregated benefit income for TIG-21.4
        # Rule TIG-21.4 requires the sum of all benefit components
        benefit_income_pence = (
            case_data_obj.income.get("universal_credit", 0) or 0
        ) + (
            case_data_obj.income.get("dla", 0) or 0
        ) + (
            case_data_obj.income.get("pip", 0) or 0
        ) + (
            case_data_obj.income.get("other_benefits", 0) or 0
        )

        benefit_income_pounds = benefit_income_pence / 100.0
        payload["benefit_income_amount"] = benefit_income_pounds if benefit_income_pounds > 0 else None
             
        return payload, prepared_creditors


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

        # Step 2 — Fetch from Aryza
        try:
            case_data_obj = fetch_case_by_reference(aryza_reference)
            case_data, prepared_creditors = self._prepare_engine_payload(case_data_obj)
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

        result = assess_case(case_data)
        
        # STEP 7 — Add back ACCEPT creditors filtered out by engine
        engine_positions = result.get("creditor_positions", [])

        # Collect names already in engine output
        positioned_names = {
            p.get("creditor_name", "").strip().lower()
            for p in engine_positions
        }

        # Add back creditors that engine filtered (ACCEPT, no findings)
        accept_positions = []
        for c in prepared_creditors:
            # Use resolved name (creditor_name field) not raw name
            cname = (c.get("creditor_name") or "").strip()
            original = (c.get("original_name") or cname).strip()
            if not cname:
                continue
            if cname.lower() not in positioned_names:
                accept_positions.append({
                    "creditor_name": cname,           # resolved canonical name
                    "resolved_canonical_name": cname,
                    "original_aryza_name": original,  # raw Aryza name for reference
                    "effective_status": "ACCEPT",
                    "findings": [],
                    "reason": "Creditor accepted — no conditions apply",
                    "rule_ids": [],
                    "balance": float(c.get("crm_balance") or c.get("balance") or 0),
                })
                logger.warning(f"[ACCEPT RESTORED] '{cname}'")

        all_creditor_positions = engine_positions + accept_positions
        logger.warning(
            f"[POSITIONS TOTAL] {len(engine_positions)} engine + "
            f"{len(accept_positions)} restored = "
            f"{len(all_creditor_positions)} total"
        )

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
            
        recommendations = get_recommendation(decision, result, case_data)
        result["recommended_solution"] = recommendations.get("recommended_solution")
        result["alternative_solutions"] = recommendations.get("alternative_solutions", [])

        serialized = build_phase7_response_fields(result)

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
                triggered_by=request.user,
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
    permission_classes = [IsAdminUser]

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
    'requires_pg_called_up', 'requires_arrangement_call_before_proposing',
    'requires_grant_overpayment_only', 'vehicle_arrears_repossession_months',
    'fees_cap_percentage', 'min_di_for_fees_pence',
    'termination_risk_if_vehicle_on_finance', 'conditional_voter',
    'conditional_voter_min_dividend_pence', 'open_banking_access', 'fraud_claim_risk',
    'blocked_until_cleared', 'blocked_reason', 'last_reviewed',
]


class CreditorListView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAdminUser]

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
    permission_classes = [IsAdminUser]

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

        for field in _CREDITOR_WRITABLE_FIELDS:
            if field in request.data:
                setattr(creditor, field, request.data[field])

        try:
            creditor.full_clean()
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

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
    permission_classes = [IsAdminUser]

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
    permission_classes = [IsAdminUser]

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

        # Update basic fields
        if 'is_active' in request.data:
            rule.is_active = request.data['is_active']
        if 'threshold_value' in request.data:
            threshold = request.data['threshold_value']
            if threshold is not None and threshold < 0:
                return Response({"detail": "threshold_value must be >= 0"}, status=status.HTTP_400_BAD_REQUEST)
            rule.threshold_value = threshold
        if 'rule_name' in request.data:
            rule.rule_name = request.data['rule_name']
        if 'severity' in request.data:
            rule.severity = request.data['severity']
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
            rule.last_reviewed = request.data['last_reviewed']
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
    permission_classes = [IsAdminUser]

    def get(self, request):
        page = int(request.query_params.get('page', 1))
        page_size = min(int(request.query_params.get('page_size', 100)), 500)
        search = request.query_params.get('search', '')

        queryset = CouncilRule.objects.all().order_by('council_name')
        if search:
            queryset = queryset.filter(council_name__icontains=search)

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
    permission_classes = [IsAdminUser]

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
    permission_classes = [IsAdminUser]

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
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "is_staff": user.is_staff,
        "is_active": user.is_active,
        "date_joined": user.date_joined.isoformat(),
    }


class UserListView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAdminUser]

    def get(self, request):
        page = int(request.query_params.get('page', 1))
        page_size = min(int(request.query_params.get('page_size', 100)), 500)
        search = request.query_params.get('search', '')

        queryset = User.objects.all().order_by('username')
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
    permission_classes = [IsAdminUser]

    def get(self, request):
        qs = GuidelineCategory.objects.prefetch_related('guidelines').order_by('sort_order', 'name')
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
    permission_classes = [IsAdminUser]

    def get(self, request):
        qs = ExpenditureGuideline.objects.select_related('category_group').order_by(
            'category_group__sort_order', 'sort_order', 'category'
        )
        category_filter = request.query_params.get('category')
        if category_filter:
            qs = qs.filter(category=category_filter)
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
            'per_child', 'per_vehicle', 'first_adult', 'additional_adult',
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
        }
        for f in decimal_fields:
            kwargs[f] = data.get(f, 0) or 0

        g = ExpenditureGuideline.objects.create(**kwargs)
        return Response(_guideline_to_dict(g), status=status.HTTP_201_CREATED)


class ExpenditureGuidelineDetailView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAdminUser]

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
            'below_action', 'above_action', 'mismatch_action', 'notes',
            'adult_1', 'adult_2',
            'adult_1_child_1', 'adult_1_child_2', 'adult_1_child_3', 'adult_1_child_4', 'adult_1_child_5',
            'adult_2_child_1', 'adult_2_child_2', 'adult_2_child_3', 'adult_2_child_4', 'adult_2_child_5',
            'per_child', 'per_vehicle', 'first_adult', 'additional_adult',
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


class CreditReportUploadView(APIView):
    permission_classes = [IsAuthenticated]
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

        record = CreditReport.objects.create(
            aryza_reference=aryza_reference,
            uploaded_file=uploaded_file,
            extraction_status="pending",
            uploaded_by=request.user,
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
