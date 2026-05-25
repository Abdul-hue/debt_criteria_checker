"""
Tests for the credit report upload and engine enrichment feature.
"""
import io
import pytest
from unittest.mock import patch, MagicMock

from debt_app.credit_report_extractor import (
    detect_agency,
    normalise_creditor_name,
    match_creditor,
    extract_credit_report,
)


# ---------------------------------------------------------------------------
# TestCreditReportExtractor
# ---------------------------------------------------------------------------

class TestCreditReportExtractor:

    def test_detect_agency_experian(self):
        assert detect_agency("experian credit report for john smith") == "Experian"

    def test_detect_agency_equifax(self):
        assert detect_agency("equifax credit score report") == "Equifax"

    def test_detect_agency_transunion(self):
        assert detect_agency("transunion credit report") == "TransUnion"

    def test_detect_agency_clearscore(self):
        assert detect_agency("clearscore powered by equifax") == "Equifax"

    def test_detect_agency_unknown(self):
        assert detect_agency("some random document with no agency name") == "Unknown"

    def test_normalise_creditor_name(self):
        assert normalise_creditor_name("BARCLAYCARD UK LTD") == "barclaycardukltd"

    def test_normalise_creditor_name_strips_spaces(self):
        assert normalise_creditor_name("  Lloyds Bank  ") == "lloydsbank"

    def test_normalise_creditor_name_removes_punctuation(self):
        assert normalise_creditor_name("HSBC Bank (UK) Ltd.") == "hsbcbankukltd"

    def test_match_creditor_hit(self):
        assert match_creditor("BARCLAYCARD") == "Barclaycard"

    def test_match_creditor_lloyds(self):
        assert match_creditor("LLOYDS BANK") == "Lloyds Bank"

    def test_match_creditor_miss(self):
        result = match_creditor("COMPLETELY UNKNOWN LENDER")
        assert result == "COMPLETELY UNKNOWN LENDER"

    def test_match_creditor_never_raises(self):
        result = match_creditor(None)
        # Should return empty string for None input, never raise
        assert result == ""

    def test_extract_never_raises(self):
        result = extract_credit_report("/nonexistent/path/report.pdf")
        assert isinstance(result, dict)
        assert "extraction_error" in result
        assert result["accounts"] == []
        assert result["agency"] == "Unknown"


# ---------------------------------------------------------------------------
# TestEnrichFromCreditReport
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestEnrichFromCreditReport:

    @pytest.fixture
    def base_case_data(self):
        return {
            "aryza_reference": "ARZ-TEST-001",
            "creditors": [
                {
                    "name": "Barclaycard",
                    "balance": 150000,
                    "account_age_months": None,
                    "linked_creditor": "Barclaycard",
                },
            ],
            "evidence_ledger": [],
        }

    @pytest.fixture
    def extracted_data(self):
        return {
            "agency": "Experian",
            "client_name": "Test User",
            "report_date": "2024-01-15",
            "accounts": [
                {
                    "raw_name": "BARCLAYCARD",
                    "normalised_name": "barclaycard",
                    "matched_creditor": "Barclaycard",
                    "account_age_months": 24,
                    "missed_payments_last_3_months": 1,
                    "recent_spending": True,
                    "current_balance": 150000,
                    "credit_limit": 200000,
                    "utilisation_pct": 75.0,
                    "account_status": "open",
                    "payment_history_months": 24,
                }
            ],
            "unmatched_accounts": [],
        }

    def test_absent_when_no_reference(self, base_case_data):
        from debt_app.criteria_engine import _enrich_from_credit_report
        case_data = {**base_case_data, "aryza_reference": None}
        result = _enrich_from_credit_report(case_data)
        assert result == "absent"

    def test_absent_when_no_record(self, base_case_data):
        from debt_app.criteria_engine import _enrich_from_credit_report
        # No CreditReport in DB for this reference
        result = _enrich_from_credit_report(base_case_data)
        assert result == "absent"
        # Creditors should be unchanged
        assert base_case_data["creditors"][0]["account_age_months"] is None

    def test_enriches_account_age_when_none(self, base_case_data, extracted_data):
        from debt_app.criteria_engine import _enrich_from_credit_report
        from debt_app.models import CreditReport
        from django.contrib.auth.models import User

        CreditReport.objects.create(
            aryza_reference="ARZ-TEST-001",
            uploaded_file="credit_reports/2024/01/test.pdf",
            extraction_status="extracted",
            extracted_data=extracted_data,
        )

        result = _enrich_from_credit_report(base_case_data)
        assert result == "present"
        assert base_case_data["creditors"][0]["account_age_months"] == 24

    def test_does_not_overwrite_existing_age(self, base_case_data, extracted_data):
        from debt_app.criteria_engine import _enrich_from_credit_report
        from debt_app.models import CreditReport

        base_case_data["creditors"][0]["account_age_months"] = 12

        CreditReport.objects.create(
            aryza_reference="ARZ-TEST-001",
            uploaded_file="credit_reports/2024/01/test.pdf",
            extraction_status="extracted",
            extracted_data=extracted_data,
        )

        _enrich_from_credit_report(base_case_data)
        assert base_case_data["creditors"][0]["account_age_months"] == 12

    def test_populates_evidence_ledger(self, base_case_data, extracted_data):
        from debt_app.criteria_engine import _enrich_from_credit_report
        from debt_app.models import CreditReport

        CreditReport.objects.create(
            aryza_reference="ARZ-TEST-001",
            uploaded_file="credit_reports/2024/01/test.pdf",
            extraction_status="extracted",
            extracted_data=extracted_data,
        )

        _enrich_from_credit_report(base_case_data)
        refs = [e["ref"] for e in base_case_data["evidence_ledger"]]
        verified = [e for e in base_case_data["evidence_ledger"] if e.get("is_verified")]
        assert len(verified) > 0
        assert any(e["is_verified"] for e in base_case_data["evidence_ledger"])

    def test_no_duplicate_evidence(self, base_case_data, extracted_data):
        from debt_app.criteria_engine import _enrich_from_credit_report
        from debt_app.models import CreditReport

        # Pre-populate evidence_ledger with the same ref
        base_case_data["evidence_ledger"] = [
            {"ref": "Barclaycard", "is_verified": True, "category": "statement"}
        ]

        CreditReport.objects.create(
            aryza_reference="ARZ-TEST-001",
            uploaded_file="credit_reports/2024/01/test.pdf",
            extraction_status="extracted",
            extracted_data=extracted_data,
        )

        _enrich_from_credit_report(base_case_data)
        refs = [e["ref"] for e in base_case_data["evidence_ledger"]]
        assert refs.count("Barclaycard") == 1

    def test_returns_present_on_success(self, base_case_data, extracted_data):
        from debt_app.criteria_engine import _enrich_from_credit_report
        from debt_app.models import CreditReport

        CreditReport.objects.create(
            aryza_reference="ARZ-TEST-001",
            uploaded_file="credit_reports/2024/01/test.pdf",
            extraction_status="extracted",
            extracted_data=extracted_data,
        )

        result = _enrich_from_credit_report(base_case_data)
        assert result == "present"

    def test_returns_absent_on_no_match(self, base_case_data, extracted_data):
        from debt_app.criteria_engine import _enrich_from_credit_report
        from debt_app.models import CreditReport

        # Record exists but with a different reference
        CreditReport.objects.create(
            aryza_reference="ARZ-OTHER-999",
            uploaded_file="credit_reports/2024/01/test.pdf",
            extraction_status="extracted",
            extracted_data=extracted_data,
        )

        result = _enrich_from_credit_report(base_case_data)
        assert result == "absent"


# ---------------------------------------------------------------------------
# TestCreditReportUploadView
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestCreditReportUploadView:

    @pytest.fixture
    def auth_client(self):
        import uuid
        from django.contrib.auth.models import User
        from rest_framework.test import APIClient
        user = User.objects.create_user(username=f"testuser_{uuid.uuid4().hex[:8]}", password="pass")
        client = APIClient()
        client.force_authenticate(user=user)
        return client

    def _pdf_file(self, name="report.pdf", content=b"%PDF-1.4 fake content"):
        return io.BytesIO(content), name

    def test_rejects_missing_reference(self, auth_client):
        buf, name = self._pdf_file()
        from django.core.files.uploadedfile import SimpleUploadedFile
        f = SimpleUploadedFile(name, b"%PDF-1.4 fake", content_type="application/pdf")
        resp = auth_client.post("/api/v1/criteria/upload-credit-report/", {"credit_report": f}, format="multipart")
        assert resp.status_code == 400
        assert resp.data["code"] == "MISSING_REFERENCE"

    def test_rejects_missing_file(self, auth_client):
        resp = auth_client.post(
            "/api/v1/criteria/upload-credit-report/",
            {"aryza_reference": "ARZ-001"},
            format="multipart",
        )
        assert resp.status_code == 400
        assert resp.data["code"] == "MISSING_FILE"

    def test_rejects_non_pdf_extension(self, auth_client):
        from django.core.files.uploadedfile import SimpleUploadedFile
        f = SimpleUploadedFile("report.txt", b"%PDF-1.4 fake", content_type="text/plain")
        resp = auth_client.post(
            "/api/v1/criteria/upload-credit-report/",
            {"aryza_reference": "ARZ-001", "credit_report": f},
            format="multipart",
        )
        assert resp.status_code == 422
        assert resp.data["code"] == "INVALID_FILE_TYPE"

    def test_rejects_fake_pdf(self, auth_client):
        from django.core.files.uploadedfile import SimpleUploadedFile
        f = SimpleUploadedFile("report.pdf", b"NOT A PDF FILE", content_type="application/pdf")
        resp = auth_client.post(
            "/api/v1/criteria/upload-credit-report/",
            {"aryza_reference": "ARZ-001", "credit_report": f},
            format="multipart",
        )
        assert resp.status_code == 422
        assert resp.data["code"] == "INVALID_PDF"

    @patch("debt_app.views.criteria_views.extract_credit_report")
    def test_successful_upload_returns_correct_shape(self, mock_extract, auth_client):
        mock_extract.return_value = {
            "agency": "Experian",
            "client_name": "John Smith",
            "report_date": "2024-01-15",
            "accounts": [{"matched_creditor": "Barclaycard"}],
            "unmatched_accounts": [],
        }
        from django.core.files.uploadedfile import SimpleUploadedFile
        f = SimpleUploadedFile("report.pdf", b"%PDF-1.4 real content", content_type="application/pdf")
        resp = auth_client.post(
            "/api/v1/criteria/upload-credit-report/",
            {"aryza_reference": "ARZ-001", "credit_report": f},
            format="multipart",
        )
        assert resp.status_code == 200
        data = resp.data
        assert data["success"] is True
        assert "credit_report_id" in data
        assert data["aryza_reference"] == "ARZ-001"
        assert data["agency"] == "Experian"
        assert data["extraction_status"] == "extracted"
        assert data["accounts_found"] == 1
        assert "client_name_on_report" in data
        assert "unmatched_accounts" in data
        assert "message" in data

    @patch("debt_app.views.criteria_views.extract_credit_report")
    def test_extraction_failure_handled_gracefully(self, mock_extract, auth_client):
        mock_extract.side_effect = RuntimeError("PDF parsing blew up")
        from django.core.files.uploadedfile import SimpleUploadedFile
        f = SimpleUploadedFile("report.pdf", b"%PDF-1.4 real content", content_type="application/pdf")
        resp = auth_client.post(
            "/api/v1/criteria/upload-credit-report/",
            {"aryza_reference": "ARZ-001", "credit_report": f},
            format="multipart",
        )
        assert resp.status_code == 200
        data = resp.data
        assert data["success"] is True
        assert data["extraction_status"] == "failed"
        assert "Credit report uploaded but extraction failed" in data["message"]
