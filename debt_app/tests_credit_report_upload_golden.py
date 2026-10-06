"""
Golden-output regression tests for /api/v1/criteria/upload-credit-report/.

Captured from the pre-refactor CreditReportUploadView so the upload/extraction
logic can be shared with the Lead Gen check without changing what the
case-assessment backend (which calls this endpoint without a token) receives.

Regenerate ONLY for an intentional behaviour change:

    REGENERATE_UPLOAD_GOLDEN=1 python manage.py test debt_app.tests_credit_report_upload_golden
"""

import json
import os
from pathlib import Path

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from debt_app.models import CreditReport
from debt_app.views import criteria_views

GOLDEN_PATH = Path(__file__).parent / "fixtures" / "credit_report_upload_golden.json"
REGENERATE = os.environ.get("REGENERATE_UPLOAD_GOLDEN") == "1"

_GOOD_RESULT = {
    "agency": "Experian",
    "client_name": "Jane Doe",
    "client_address": "1 Test Street",
    "printed_report_date": "2026-09-01",
    "accounts": [{"raw_name": "ALPHA BANK", "matched_creditor": "Alpha Bank", "current_balance": 100000}],
    "mortgage_accounts": [],
    "other_accounts": [],
    "unmatched_accounts": [],
    "public_information": {"ccjs": 0},
}


def _pdf(name="report.pdf", content=b"%PDF-1.4\n%%EOF"):
    return SimpleUploadedFile(name, content, content_type="application/pdf")


class CreditReportUploadGoldenTests(TestCase):
    url = "/api/v1/criteria/upload-credit-report/"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._golden = json.loads(GOLDEN_PATH.read_text(encoding="utf-8")) if GOLDEN_PATH.exists() else {}
        cls._captured = {}

    @classmethod
    def tearDownClass(cls):
        if REGENERATE:
            merged = dict(cls._golden)
            merged.update(cls._captured)
            GOLDEN_PATH.write_text(json.dumps(merged, indent=2, sort_keys=True), encoding="utf-8")
        super().tearDownClass()

    def _post(self, scenario, data, extractor=None):
        original = criteria_views.extract_credit_report
        if extractor is not None:
            criteria_views.extract_credit_report = extractor
        try:
            resp = self.client.post(self.url, data=data, format="multipart")
        finally:
            criteria_views.extract_credit_report = original
        body = resp.json()
        body.pop("credit_report_id", None)
        record = CreditReport.objects.order_by("-id").first()
        snapshot = {
            "status_code": resp.status_code,
            "body": json.loads(json.dumps(body, sort_keys=True)),
            "record": None if record is None else {
                "aryza_reference": record.aryza_reference,
                "extraction_status": record.extraction_status,
                "extraction_error": record.extraction_error,
                "agency": record.agency,
                "client_name_on_report": record.client_name_on_report,
                "client_address_on_report": record.client_address_on_report,
                "has_extracted_data": bool(record.extracted_data),
                "uploaded_by": record.uploaded_by_id,
            },
        }
        self.__class__._captured[scenario] = snapshot
        if not REGENERATE:
            self.assertEqual(snapshot, self._golden[scenario], f"Upload output changed for {scenario!r}")
        return snapshot

    def test_missing_reference(self):
        self._post("missing_reference", {"credit_report": _pdf()})

    def test_missing_file(self):
        self._post("missing_file", {"aryza_reference": "UP-1"})

    def test_wrong_extension(self):
        self._post("wrong_extension", {"aryza_reference": "UP-2", "credit_report": _pdf(name="report.txt")})

    def test_bad_header(self):
        self._post("bad_header", {"aryza_reference": "UP-3", "credit_report": _pdf(content=b"NOTAPDF")})

    def test_extraction_error_key(self):
        self._post("extraction_error_key", {"aryza_reference": "UP-4", "credit_report": _pdf()},
                   extractor=lambda path: {"extraction_error": "Unrecognised layout"})

    def test_extraction_exception(self):
        def boom(path):
            raise ValueError("parser exploded")
        self._post("extraction_exception", {"aryza_reference": "UP-5", "credit_report": _pdf()},
                   extractor=boom)

    def test_success(self):
        self._post("success", {"aryza_reference": "UP-6", "credit_report": _pdf()},
                   extractor=lambda path: dict(_GOOD_RESULT))

    def test_extracted_empty(self):
        self._post("extracted_empty", {"aryza_reference": "UP-7", "credit_report": _pdf()},
                   extractor=lambda path: dict(_GOOD_RESULT, accounts=[]))
