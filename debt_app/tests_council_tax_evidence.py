"""
Tests for council-tax evidence extraction (integrations/council_tax_evidence.py)
and its upload endpoint (CouncilTaxEvidenceUploadView).

Field-extraction tests run against the REAL OCR text captured from the
reference file (ctax1.png, a phone screenshot of a council liability-order
email) — hardcoded here so they run in any environment, without needing
Tesseract installed. The end-to-end OCR test additionally exercises the
real file through the real Tesseract binary and is skipped where either
isn't present, since that's a genuine environment dependency (see the
module docstring in integrations/council_tax_evidence.py for how it was
verified: locally, via `winget install UB-Mannheim.TesseractOCR`).
"""
import os
import shutil

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from debt_app.integrations import council_tax_evidence as cte
from debt_app.views import criteria_views

# Verbatim OCR output from the reference screenshot (see module docstring).
REFERENCE_OCR_TEXT = (
    "14:53 8 Fea\n"
    "< Council Tax Account - 801302683\n\n"
    "From: Local Taxation\n"
    "<local.taxation@flintshire.gov.uk>\n"
    "Sent: Thursday, June 25, 2026 9:40 am\n"
    "To: Karen Wylie <Karen@kicare,co,uk>\n"
    "Subject: RE: Council Tax Account -\n"
    "801302683\n\n"
    "Dear MISS WYLIE,\n\n"
    "1am contacting you with regards to\n"
    "outstanding balance on your 2025/26\n"
    "Council Tax account.\n\n"
    "A Liability Order was granted at Mold\n"
    "Magistrates Court on 17th February 2026\n"
    "for non-payment of your Council Tax. The\n"
    "remaining balance on your account is\n"
    "currently \u00a32,047.00.\n\n"
    "Please contact the Council Tax section\n"
    "before 5pm Monday 29th June 2026 on\n\n"
    "ev Repy.. SW & em\n"
)

SAMPLE_IMAGE = r"C:\Users\Canton Computers\Desktop\ctax1.png"
TESSERACT_AVAILABLE = shutil.which("tesseract") is not None or os.path.exists(
    r"C:\Program Files\Tesseract-OCR\tesseract.exe"
)


class FieldExtractionTests(TestCase):
    """Pure regex-extraction tests — no OCR/Tesseract dependency."""

    def test_account_reference(self):
        assert cte.extract_account_reference(REFERENCE_OCR_TEXT) == "801302683"

    def test_balance(self):
        assert cte.extract_balance_pence(REFERENCE_OCR_TEXT) == 204700

    def test_liability_order(self):
        result = cte.extract_liability_order(REFERENCE_OCR_TEXT)
        assert result["court"] == "Mold Magistrates Court"
        assert result["date_iso"] == "2026-02-17"

    def test_salutation_name(self):
        assert cte.extract_client_salutation_name(REFERENCE_OCR_TEXT) == "MISS WYLIE"

    def test_council_name(self):
        assert cte.extract_council_name(REFERENCE_OCR_TEXT) == "Flintshire"

    def test_line_wrap_does_not_break_multiword_anchors(self):
        # Regression guard for the bug this suite caught during development:
        # "granted at Mold\nMagistrates Court on..." — a phrase OCR line-
        # wrapped mid-court-name — must still resolve via _flatten(), not
        # silently return None the way a raw-text, non-DOTALL regex would.
        wrapped = "Liability Order was granted at Mold\nMagistrates Court on 1st January 2026"
        result = cte.extract_liability_order(wrapped)
        assert result["court"] == "Mold Magistrates Court"
        assert result["date_iso"] == "2026-01-01"


@pytest.mark.skipif(not os.path.exists(SAMPLE_IMAGE), reason="sample image not present on this machine")
@pytest.mark.skipif(not TESSERACT_AVAILABLE, reason="tesseract binary not installed on this machine")
class EndToEndOcrTests(TestCase):
    def test_extract_council_tax_evidence_from_real_screenshot(self):
        result = cte.extract_council_tax_evidence(SAMPLE_IMAGE, is_image=True)
        assert "extraction_error" not in result
        assert result["account_reference"] == "801302683"
        assert result["balance_pence"] == 204700
        assert result["liability_order"]["date_iso"] == "2026-02-17"
        assert result["client_salutation_name"] == "MISS WYLIE"
        assert result["council_name"] == "Flintshire"


class CouncilTaxEvidenceUploadViewTests(TestCase):
    url = "/api/v1/criteria/council-tax-evidence/upload/"

    def _post(self, monkeypatch_result, filename="evidence.png", content=b"\x89PNG\r\n\x1a\nrest"):
        original = criteria_views.extract_council_tax_evidence
        criteria_views.extract_council_tax_evidence = lambda path, is_image=True: monkeypatch_result
        try:
            return self.client.post(
                self.url,
                data={
                    "aryza_reference": "TEST-REF-1",
                    "evidence": SimpleUploadedFile(filename, content, content_type="image/png"),
                },
                format="multipart",
            )
        finally:
            criteria_views.extract_council_tax_evidence = original

    def test_successful_extraction(self):
        resp = self._post({
            "raw_text": REFERENCE_OCR_TEXT,
            "account_reference": "801302683",
            "balance_pence": 204700,
            "liability_order": {"court": "Mold Magistrates Court", "date_raw": "17th February 2026", "date_iso": "2026-02-17"},
            "client_salutation_name": "MISS WYLIE",
            "council_name": "Flintshire",
        })
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["success"])
        self.assertEqual(body["extraction_status"], "extracted")
        self.assertNotIn("warning", body)
        self.assertEqual(body["account_reference"], "801302683")
        self.assertEqual(body["balance_pence"], 204700)

    def test_nothing_found_is_flagged(self):
        resp = self._post({
            "raw_text": "illegible",
            "account_reference": None,
            "balance_pence": None,
            "liability_order": {"court": None, "date_raw": None, "date_iso": None},
            "client_salutation_name": None,
            "council_name": None,
        })
        body = resp.json()
        self.assertTrue(body["success"])
        self.assertEqual(body["extraction_status"], "extracted_empty")
        self.assertIn("warning", body)

    def test_rejects_non_image_non_pdf_file(self):
        resp = self.client.post(
            self.url,
            data={
                "aryza_reference": "TEST-REF-1",
                "evidence": SimpleUploadedFile("evidence.txt", b"not an image", content_type="text/plain"),
            },
            format="multipart",
        )
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(resp.json()["code"], "INVALID_FILE_TYPE")

    def test_missing_reference_rejected(self):
        resp = self.client.post(
            self.url,
            data={"evidence": SimpleUploadedFile("evidence.png", b"\x89PNG\r\n\x1a\nrest", content_type="image/png")},
            format="multipart",
        )
        self.assertEqual(resp.status_code, 400)
