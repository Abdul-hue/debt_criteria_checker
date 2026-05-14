import logging
from django.db.models import Q
from django.utils.dateparse import parse_date
from rest_framework import status
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
from debt_app.models import GlobalCriteria, CreditorCriteria, CriteriaDecision

logger = logging.getLogger(__name__)


def error_response(message: str, code: str, status_code: int):
    return Response(
        {"success": False, "error": message, "code": code},
        status=status_code
    )


class AssessRateThrottle(UserRateThrottle):
    scope = 'assess'


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

    def post(self, request):
        # Step 1 — Validate
        aryza_reference = request.data.get("aryza_reference")
        if not aryza_reference:
            return error_response(
                "aryza_reference is required",
                "MISSING_REFERENCE",
                status.HTTP_422_UNPROCESSABLE_ENTITY
            )

        # Step 2 — Fetch from Aryza
        try:
            case_data = fetch_case_by_reference(aryza_reference).to_dict()
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
        result = assess_case(case_data)

        # Step 4 — Save to CriteriaDecision
        try:
            decision = CriteriaDecision.objects.create(
                application_id=aryza_reference,
                client_name=case_data.get("client_name", "Unknown"),
                input_snapshot=case_data,
                decision_output=result,
                recommended_solution=result.get("recommended_solution", "UNCLEAR"),
                passes_all_hard_blocks=result.get("passes_all_hard_blocks", False),
                triggered_by=request.user,
                source="STANDALONE"
            )
            decision_id = str(decision.id)
        except Exception as e:
            logger.error("Failed to save CriteriaDecision: %s", e)
            decision_id = None

        logger.info("Assessment completed for %s: %s", aryza_reference, result.get("recommended_solution"))
        return Response({
            "success": True,
            "decision_id": decision_id,
            "data": result,
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

    def get(self, request, id):
        try:
            decision = CriteriaDecision.objects.get(id=id)
        except CriteriaDecision.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        return Response({
            "id": str(decision.id),
            "application_id": decision.application_id,
            "client_name": decision.client_name,
            "input_snapshot": decision.input_snapshot,
            "decision_output": decision.decision_output,
            "recommended_solution": decision.recommended_solution,
            "passes_all_hard_blocks": decision.passes_all_hard_blocks,
            "triggered_by": decision.triggered_by.username if decision.triggered_by else None,
            "triggered_at": decision.triggered_at.isoformat(),
            "source": decision.source,
        }, status=status.HTTP_200_OK)


class CreditorListView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        search = request.query_params.get('search', '')
        representative = request.query_params.get('representative', '')
        page = int(request.query_params.get('page', 1))
        page_size = min(int(request.query_params.get('page_size', 50)), 200)

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

        results = []
        for creditor in page_obj:
            results.append({
                "id": creditor.id,
                "creditor_name": creditor.creditor_name,
                "trading_names": creditor.trading_names,
                "representative": creditor.representative,
                "min_dividend_pence": creditor.min_dividend_pence,
                "contact_email": creditor.contact_email,
                "contact_phone": creditor.contact_phone,
                "is_active": creditor.is_active,
                "parent_group": creditor.parent_group,
                "last_updated": creditor.last_updated.isoformat(),
            })

        return Response({
            "count": paginator.count,
            "next": f"{request.build_absolute_uri(request.path)}?page={page + 1}" if page_obj.has_next() else None,
            "previous": f"{request.build_absolute_uri(request.path)}?page={page - 1}" if page_obj.has_previous() else None,
            "results": results,
        }, status=status.HTTP_200_OK)


class CreditorDetailView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAdminUser]

    def put(self, request, id):
        try:
            creditor = CreditorCriteria.objects.get(id=id)
        except CreditorCriteria.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        allowed_fields = [
            'is_active', 'representative', 'min_dividend_pence',
            'trading_names', 'parent_group',
        ]

        for field in allowed_fields:
            if field in request.data:
                setattr(creditor, field, request.data[field])

        try:
            creditor.full_clean()
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        creditor.updated_by = request.user
        creditor.save()

        return Response({
            "id": creditor.id,
            "creditor_name": creditor.creditor_name,
            "trading_names": creditor.trading_names,
            "representative": creditor.representative,
            "min_dividend_pence": creditor.min_dividend_pence,
            "contact_email": creditor.contact_email,
            "contact_phone": creditor.contact_phone,
            "is_active": creditor.is_active,
            "parent_group": creditor.parent_group,
            "last_updated": creditor.last_updated.isoformat(),
        }, status=status.HTTP_200_OK)


class RulesListView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAdminUser]

    def get(self, request):
        rules = GlobalCriteria.objects.all()
        grouped = {"TIG": [], "WATCH": [], "TIX": [], "EVOLVE": []}

        for rule in rules:
            grouped[rule.criteria_set].append({
                "rule_key": rule.rule_key,
                "rule_name": rule.rule_name,
                "criteria_set": rule.criteria_set,
                "severity": rule.severity,
                "is_active": rule.is_active,
                "threshold_value": rule.threshold_value,
            })

        return Response(grouped, status=status.HTTP_200_OK)


class RulesDetailView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAdminUser]

    def put(self, request, rule_key):
        try:
            rule = GlobalCriteria.objects.get(rule_key=rule_key)
        except GlobalCriteria.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        if 'is_active' in request.data:
            rule.is_active = request.data['is_active']

        if 'threshold_value' in request.data:
            threshold = request.data['threshold_value']
            if threshold < 0:
                return Response({"detail": "threshold_value must be >= 0"}, status=status.HTTP_400_BAD_REQUEST)
            rule.threshold_value = threshold

        rule.updated_by = request.user
        rule.save()

        return Response({
            "rule_key": rule.rule_key,
            "rule_name": rule.rule_name,
            "criteria_set": rule.criteria_set,
            "severity": rule.severity,
            "is_active": rule.is_active,
            "threshold_value": rule.threshold_value,
        }, status=status.HTTP_200_OK)
