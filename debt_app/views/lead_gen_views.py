"""
Lead Generation pre-screen endpoints.

POST /api/v1/criteria/lead-gen/check/
GET  /api/v1/criteria/lead-gen/credit-report-status/?aryza_reference=
GET  /api/v1/criteria/lead-gen/activity/?date_from=YYYY-MM-DD&date_to=YYYY-MM-DD

The check runs the SAME shared orchestration as the CAT assessment
(criteria_views.run_standalone_assessment) and the same engine, then returns
only a minimal Lead Gen result. It never writes Application.source_department
and never touches the case's saved CAT decision (CriteriaDecision).
"""

import datetime
import logging

from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework import status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication

from debt_app.aryza_client import (
    AryaTimeoutError,
    AryzaCaseNotFoundError,
    AryzaConnectionError,
    AryzaDataError,
)
from debt_app.helpers import get_user_department
from debt_app.models import CreditReport, LeadGenCheck
from debt_app.permissions import HasEnabledFeature
from debt_app.services.criteria_versioning import current_criteria_version, get_code_version
from debt_app.services.lead_gen import (
    LEAD_GEN_DEPARTMENT,
    display_client_name,
    summarise_activity,
    to_lead_gen_result,
)
from debt_app.views import criteria_views

logger = logging.getLogger(__name__)

# Aryza failures -> (status code, LeadGenCheck.status, HTTP status, user message).
# Error codes/messages mirror AssessCaseView's so both tools report alike.
_ARYZA_ERRORS = (
    (AryzaCaseNotFoundError, "CASE_NOT_FOUND", status.HTTP_404_NOT_FOUND,
     "Case {ref} was not found in Aryza. Check the case reference."),
    (AryaTimeoutError, "ARYZA_TIMEOUT", status.HTTP_503_SERVICE_UNAVAILABLE,
     "Aryza database timed out. Please try again."),
    (AryzaConnectionError, "ARYZA_UNAVAILABLE", status.HTTP_503_SERVICE_UNAVAILABLE,
     "Unable to connect to Aryza database."),
    (AryzaDataError, "ARYZA_DATA_ERROR", status.HTTP_500_INTERNAL_SERVER_ERROR,
     "Data error reading case. Contact support."),
)


def _error(message, code, http_status, check_id=None):
    body = {"success": False, "error": message, "code": code}
    if check_id is not None:
        body["check_id"] = check_id
    return Response(body, status=http_status)


def _department_name(user):
    dept = get_user_department(user)
    return dept.name if dept else ""


def _record(user, reference, status_code, **fields):
    """Append one LeadGenCheck row. A logging failure never breaks the check."""
    try:
        version, fp = current_criteria_version()
        return LeadGenCheck.objects.create(
            user=user,
            username=user.get_username(),
            department_name=_department_name(user),
            aryza_reference=reference,
            status=status_code,
            criteria_version=version,
            criteria_fingerprint=fp,
            code_version=get_code_version(),
            **fields,
        )
    except Exception:
        logger.exception("[LEAD GEN] failed to record check for %s", reference)
        return None


class LeadGenCheckView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated, HasEnabledFeature]
    required_feature = "lead_gen_check"
    parser_classes = [JSONParser, MultiPartParser, FormParser]
    throttle_classes = [criteria_views.AssessRateThrottle]

    def post(self, request):
        reference = (request.data.get("aryza_reference") or "").strip()
        if not reference:
            return _error("Enter a case reference.", "MISSING_REFERENCE", status.HTTP_422_UNPROCESSABLE_ENTITY)
        user = request.user
        credit_report_id = request.data.get("credit_report_id") or None
        uploaded_file = request.FILES.get("credit_report")

        # 1. Resolve the case first, so a PDF is never stored against a bad reference.
        try:
            case_obj = criteria_views.fetch_case_by_reference(reference)
        except Exception as exc:
            for exc_type, code, http_status, message in _ARYZA_ERRORS:
                if isinstance(exc, exc_type):
                    if exc_type is AryzaDataError:
                        logger.error("[LEAD GEN] Aryza data error for %s: %s", reference, exc)
                    rec = _record(user, reference, code, error_code=code)
                    return _error(message.format(ref=reference), code, http_status, rec and rec.pk)
            raise

        # 2. Upload/extract a credit report when one is supplied (existing parser).
        credit_report_status = ""
        credit_report_warning = None
        if uploaded_file is not None:
            upload = criteria_views.process_credit_report_upload(
                reference, uploaded_file, user, criteria_views.extract_credit_report,
            )
            body = upload.data or {}
            if upload.status_code != 200:
                rec = _record(user, reference, "CREDIT_REPORT_INVALID",
                              error_code=body.get("code", "INVALID_FILE"))
                return _error(body.get("error") or "The credit report file was rejected.",
                              body.get("code", "INVALID_FILE"), upload.status_code, rec and rec.pk)
            if not body.get("success"):
                rec = _record(user, reference, "CREDIT_REPORT_FAILED", error_code="EXTRACTION_FAILED",
                              credit_report_id=body.get("credit_report_id"), credit_report_status="failed")
                return _error(
                    "The credit report could not be read. Check it is an Experian or Aryza Advize "
                    "credit report PDF, or pass the case to a caseworker.",
                    "EXTRACTION_FAILED", status.HTTP_422_UNPROCESSABLE_ENTITY, rec and rec.pk,
                )
            credit_report_id = body.get("credit_report_id")
            credit_report_status = body.get("extraction_status", "extracted")
            if credit_report_status == "extracted_empty":
                credit_report_warning = (
                    "The credit report was read but no accounts were found in it. "
                    "A caseworker should review the report."
                )

        # 3. Shared assessment, Lead Gen context, no persistent side effects.
        try:
            outcome = criteria_views.run_standalone_assessment(
                reference,
                user=user,
                credit_report_id=credit_report_id,
                case_data_obj=case_obj,
                source_department_override=LEAD_GEN_DEPARTMENT,
                persist_source_department=False,
                save_decision=False,
            )
            lead_gen = to_lead_gen_result(outcome)
        except Exception:
            logger.exception("[LEAD GEN] assessment failed for %s", reference)
            rec = _record(user, reference, "ENGINE_ERROR", error_code="ENGINE_ERROR",
                          credit_report_id=credit_report_id)
            return _error("The check could not be completed. Please try again or pass the case to a caseworker.",
                          "ENGINE_ERROR", status.HTTP_500_INTERNAL_SERVER_ERROR, rec and rec.pk)

        # 4. Which report the assessment actually used (same selection logic).
        used_report = criteria_views.select_credit_report(reference, credit_report_id)
        if not credit_report_status:
            credit_report_status = "on_file" if used_report else "none"
        elif credit_report_status == "extracted":
            credit_report_status = "uploaded"

        rec = _record(
            user, reference, LeadGenCheck.STATUS_OK,
            iva_outcome=lead_gen["iva"]["code"],
            dmp_outcome=lead_gen["dmp"]["code"],
            dro_referral=lead_gen["dro"] is not None,
            overall_outcome=lead_gen["overall"]["code"],
            engine_recommended_solution=str(outcome.engine_recommended_solution or ""),
            reason_codes=lead_gen["reason_codes"] + lead_gen["evidence_codes"],
            evidence_required=lead_gen["evidence_required_later"],
            credit_report_id=used_report.id if used_report else credit_report_id,
            credit_report_status=credit_report_status,
        )

        credit_report = {"status": credit_report_status}
        if credit_report_status == "none":
            credit_report["message"] = (
                "No credit report on file — checks that rely on the credit report could not be completed."
            )
        if credit_report_warning:
            credit_report["warning"] = credit_report_warning

        return Response({
            "success": True,
            "check_id": rec.pk if rec else None,
            "aryza_reference": reference,
            "client": display_client_name(case_obj.client_name),
            "checked_at": timezone.localtime(rec.checked_at if rec else timezone.now()).isoformat(),
            "overall": lead_gen["overall"],
            "iva": lead_gen["iva"],
            "dmp": lead_gen["dmp"],
            "dro": lead_gen["dro"],
            "reasons": lead_gen["reasons"],
            "review_reasons": lead_gen["review_reasons"],
            "evidence_required_later": lead_gen["evidence_required_later"],
            "credit_report": credit_report,
            "criteria_version": rec.criteria_version if rec else None,
        }, status=status.HTTP_200_OK)


class LeadGenCreditReportStatusView(APIView):
    """Is there a usable credit report on file for this case? (No Aryza call,
    no account data — just enough to decide whether to show the upload box.)"""

    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated, HasEnabledFeature]
    required_feature = "lead_gen_check"

    def get(self, request):
        reference = (request.query_params.get("aryza_reference") or "").strip()
        if not reference:
            return _error("Enter a case reference.", "MISSING_REFERENCE", status.HTTP_422_UNPROCESSABLE_ENTITY)
        report = criteria_views.select_credit_report(reference)
        latest = CreditReport.objects.filter(aryza_reference=reference).order_by("-created_at").first()
        return Response({
            "aryza_reference": reference,
            "has_usable_report": report is not None,
            "credit_report_id": report.id if report else None,
            "agency": report.agency if report else None,
            "uploaded_at": timezone.localtime(report.created_at).isoformat() if report else None,
            # Latest upload may be unusable (failed / no accounts) — say so.
            "latest_upload_status": latest.extraction_status if latest else None,
        })


def _london_day_bounds(day_from, day_to):
    tz = timezone.get_current_timezone()  # Europe/London (settings.TIME_ZONE)
    start = timezone.make_aware(datetime.datetime.combine(day_from, datetime.time.min), tz)
    end = timezone.make_aware(datetime.datetime.combine(day_to + datetime.timedelta(days=1), datetime.time.min), tz)
    return start, end


class LeadGenActivityView(APIView):
    """Manager view: cases checked per Lead Gen user over a London date range."""

    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated, HasEnabledFeature]
    required_feature = "lead_gen_reporting"

    def get(self, request):
        today = timezone.localdate()
        raw_from = request.query_params.get("date_from")
        raw_to = request.query_params.get("date_to")
        day_from = parse_date(raw_from) if raw_from else today
        day_to = parse_date(raw_to) if raw_to else day_from
        if day_from is None or day_to is None:
            return _error("Dates must be YYYY-MM-DD.", "INVALID_DATE", status.HTTP_400_BAD_REQUEST)
        if day_to < day_from:
            return _error("date_to must be on or after date_from.", "INVALID_DATE", status.HTTP_400_BAD_REQUEST)
        if (day_to - day_from).days > 366:
            return _error("The date range cannot exceed one year.", "INVALID_DATE", status.HTTP_400_BAD_REQUEST)

        start, end = _london_day_bounds(day_from, day_to)
        checks = list(LeadGenCheck.objects.filter(checked_at__gte=start, checked_at__lt=end))
        rows = summarise_activity(checks)
        totals = {k: sum(r[k] for r in rows) for k in (
            "cases_checked", "iva_potential", "iva_needs_review", "dmp_potential",
            "dro_referral", "no_solution", "failed_attempts",
        )}
        return Response({
            "date_from": day_from.isoformat(),
            "date_to": day_to.isoformat(),
            "timezone": str(timezone.get_current_timezone()),
            "definition": (
                "A case checked is one distinct case reference successfully checked by a user on a "
                "London calendar day. Repeat checks of the same case by the same user that day count once."
            ),
            "users": rows,
            "totals": totals,
        })
