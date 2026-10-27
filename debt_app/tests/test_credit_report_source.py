"""
CreditReport.source / source_report_id (migration 0092): a report can come from
an uploaded PDF or from the Experian database, and one Experian search is
imported at most once per case.

Existing PDF rows must come through the migration unchanged, and the PDF
upload path must behave exactly as before.
"""
import shutil
import tempfile

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase, override_settings

from debt_app.models import (
    CREDIT_REPORT_SOURCE_EXPERIAN_DB,
    CREDIT_REPORT_SOURCE_PDF_UPLOAD,
    CreditReport,
)
from debt_app.views import criteria_views

BEFORE = ("debt_app", "0091_phase9_creditor_decisions")
AFTER = ("debt_app", "0092_creditreport_source")

EXTRACTED = {"agency": "Experian", "client_name": "JANE DOE", "accounts": [{"raw_name": "HALIFAX"}]}


def _experian_row(reference="349223", search_id=912, **extra):
    return CreditReport.objects.create(
        aryza_reference=reference,
        source=CREDIT_REPORT_SOURCE_EXPERIAN_DB,
        source_report_id=search_id,
        agency="Experian",
        extraction_status="extracted",
        extracted_data=EXTRACTED,
        **extra,
    )


class MigrationTests(TransactionTestCase):
    """Runs 0091 -> 0092 against a pre-existing PDF row."""

    def setUp(self):
        executor = MigrationExecutor(connection)
        executor.migrate([BEFORE])
        old_apps = executor.loader.project_state([BEFORE]).apps
        OldCreditReport = old_apps.get_model("debt_app", "CreditReport")
        self.old_row = OldCreditReport.objects.create(
            aryza_reference="411322",
            uploaded_file="credit_reports/2026/09/report.pdf",
            agency="Experian",
            client_name_on_report="JANE DOE",
            client_address_on_report="12 HIGH STREET, LEEDS, LS1 1AA",
            extraction_status="extracted",
            extracted_data=EXTRACTED,
            extraction_error="",
        )
        self.old_values = {
            field: getattr(self.old_row, field)
            for field in ("aryza_reference", "agency", "client_name_on_report", "client_address_on_report",
                          "extraction_status", "extracted_data", "extraction_error", "created_at",
                          "updated_at", "uploaded_by_id")
        }

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes("debt_app"))

    def _migrate_forward(self):
        executor = MigrationExecutor(connection)
        executor.migrate([AFTER])
        return executor.loader.project_state([AFTER]).apps.get_model("debt_app", "CreditReport")

    def test_existing_pdf_row_is_unchanged_and_becomes_pdf_upload(self):
        NewCreditReport = self._migrate_forward()
        row = NewCreditReport.objects.get(pk=self.old_row.pk)
        self.assertEqual(row.uploaded_file.name, "credit_reports/2026/09/report.pdf")
        for field, value in self.old_values.items():
            self.assertEqual(getattr(row, field), value, field)
        self.assertEqual(row.source, "pdf_upload")
        self.assertIsNone(row.source_report_id)

    def test_migration_creates_the_partial_unique_index(self):
        self._migrate_forward()
        with connection.cursor() as cursor:
            constraints = connection.introspection.get_constraints(cursor, "debt_app_creditreport")
        constraint = constraints["uniq_experian_credit_report_per_search"]
        self.assertTrue(constraint["unique"])
        self.assertEqual(constraint["columns"], ["aryza_reference", "source", "source_report_id"])

    def test_migration_reverses_cleanly_with_pdf_rows_only(self):
        self._migrate_forward()
        executor = MigrationExecutor(connection)
        executor.migrate([BEFORE])
        OldCreditReport = executor.loader.project_state([BEFORE]).apps.get_model("debt_app", "CreditReport")
        row = OldCreditReport.objects.get(pk=self.old_row.pk)
        self.assertEqual(row.uploaded_file.name, "credit_reports/2026/09/report.pdf")
        self.assertEqual(row.extracted_data, EXTRACTED)


class CreditReportSourceModelTests(TestCase):
    def test_defaults_are_a_pdf_upload_without_a_search_id(self):
        row = CreditReport.objects.create(aryza_reference="1", uploaded_file="credit_reports/x.pdf")
        row.refresh_from_db()
        self.assertEqual(row.source, CREDIT_REPORT_SOURCE_PDF_UPLOAD)
        self.assertIsNone(row.source_report_id)

    def test_experian_row_needs_no_uploaded_file(self):
        row = _experian_row()
        row.full_clean()
        row.refresh_from_db()
        self.assertFalse(row.uploaded_file)
        self.assertEqual((row.source, row.source_report_id), ("experian_db", 912))

    def test_duplicate_experian_search_for_a_case_is_rejected(self):
        _experian_row()
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                _experian_row()
        self.assertEqual(CreditReport.objects.filter(source="experian_db").count(), 1)

    def test_duplicate_experian_search_fails_model_validation(self):
        _experian_row()
        duplicate = CreditReport(aryza_reference="349223", source="experian_db", source_report_id=912,
                                 extraction_status="extracted")
        with self.assertRaises(ValidationError):
            duplicate.full_clean()

    def test_other_searches_and_other_cases_are_allowed(self):
        _experian_row(reference="349223", search_id=912)
        _experian_row(reference="349223", search_id=870)   # older search, same case
        _experian_row(reference="411322", search_id=912)   # constraint is per case
        self.assertEqual(CreditReport.objects.filter(source="experian_db").count(), 3)

    def test_pdf_rows_are_outside_the_constraint(self):
        for _ in range(3):
            CreditReport.objects.create(aryza_reference="349223", uploaded_file="credit_reports/x.pdf")
        # Even a PDF row carrying the same id as an Experian row is unaffected.
        _experian_row(reference="349223", search_id=912)
        CreditReport.objects.create(aryza_reference="349223", uploaded_file="credit_reports/y.pdf",
                                    source_report_id=912)
        CreditReport.objects.create(aryza_reference="349223", uploaded_file="credit_reports/z.pdf",
                                    source_report_id=912)
        self.assertEqual(CreditReport.objects.filter(source="pdf_upload").count(), 5)


class PdfUploadUnchangedTests(TestCase):
    """process_credit_report_upload still stores a PDF row exactly as before."""

    def setUp(self):
        self.media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.media, ignore_errors=True)

    def test_upload_creates_a_pdf_upload_row_with_its_file(self):
        result = {"agency": "Experian", "client_name": "JANE DOE", "client_address": "",
                  "accounts": [{"raw_name": "HALIFAX", "matched_creditor": "HALIFAX"}],
                  "mortgage_accounts": [], "other_accounts": [], "unmatched_accounts": []}
        upload = SimpleUploadedFile("report.pdf", b"%PDF-1.4\n%%EOF", content_type="application/pdf")
        with override_settings(MEDIA_ROOT=self.media):
            response = criteria_views.process_credit_report_upload(
                "349223", upload, None, lambda path: dict(result))
            row = CreditReport.objects.get(pk=response.data["credit_report_id"])
            self.assertTrue(row.uploaded_file.storage.exists(row.uploaded_file.name))
        self.assertTrue(response.data["success"])
        self.assertEqual(row.extraction_status, "extracted")
        self.assertEqual(row.source, CREDIT_REPORT_SOURCE_PDF_UPLOAD)
        self.assertIsNone(row.source_report_id)
        self.assertTrue(row.uploaded_file.name.startswith("credit_reports/"))
        self.assertTrue(row.uploaded_file.name.endswith(".pdf"))
        self.assertEqual(row.extracted_data, result)

    def test_selection_still_picks_a_pdf_report(self):
        pdf = CreditReport.objects.create(aryza_reference="349223", uploaded_file="credit_reports/x.pdf",
                                          extraction_status="extracted", extracted_data=EXTRACTED)
        self.assertEqual(criteria_views.select_credit_report("349223"), pdf)
