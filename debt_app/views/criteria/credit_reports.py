"""Credit report PDF upload and extraction."""

import logging

from rest_framework import status
from rest_framework.parsers import MultiPartParser
from rest_framework.parsers import FormParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from debt_app.models import CreditReport
from debt_app.integrations.credit_report import extract_credit_report

logger = logging.getLogger(__name__)

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
                # ⚠️ `success` MUST be False here. The case-assessment-tool's
                # CriteriaClient.upload_credit_report() treats `success` as the
                # only signal that extraction failed — it previously read
                # `True` on this branch and treated a failed extraction
                # identically to "client has no debts": empty accounts, no
                # error surfaced, and the case's existing Creditor rows got
                # deleted and replaced with nothing. See case-assessment-tool
                # docs/api-fixes.md and platform/criteria.py.
                return Response({
                    "success": False,
                    "credit_report_id": record.id,
                    "aryza_reference": aryza_reference,
                    "agency": "",
                    "extraction_status": "failed",
                    "accounts_found": 0,
                    "client_name_on_report": "",
                    "unmatched_accounts": [],
                    "accounts": [],
                    "mortgage_accounts": [],
                    "other_accounts": [],
                    "public_information": {},
                    "error": result["extraction_error"],
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
            # `success: False` — see the matching branch above for why this
            # flag has to reflect extraction failure, not just upload receipt.
            return Response({
                "success": False,
                "credit_report_id": record.id,
                "aryza_reference": aryza_reference,
                "agency": "",
                "extraction_status": "failed",
                "accounts_found": 0,
                "client_name_on_report": "",
                "unmatched_accounts": [],
                "accounts": [],
                "mortgage_accounts": [],
                "other_accounts": [],
                "public_information": {},
                "error": str(exc),
                "message": "Credit report uploaded but extraction failed",
            })
