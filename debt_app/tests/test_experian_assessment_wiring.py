"""
The Experian credit-report import wired into run_standalone_assessment.

The import runs after the Aryza case is loaded and before the credit report is
selected for the engine payload, unless a credit_report_id is pinned. These
tests drive the public CAT endpoint POST /api/v1/criteria/assess/ with the
Aryza fetch mocked, and either mock the import service at that boundary or run
the real service with a fake Experian client. No live database is used.
"""
import json
from datetime import date, datetime, timezone
from unittest.mock import patch

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from debt_app.aryza_client import CaseData
from debt_app.models import CreditorCriteria, CreditReport
from debt_app.services import experian_credit_report as service
from debt_app.services.experian_credit_report import ExperianImportResult
from debt_app.integrations.experian_db import CandidateSearch, ExperianConnectionError
from debt_app.tests.test_experian_mapper import _detail, _doc
from debt_app.tests.test_experian_credit_report import FakeClient

REF = "349223"
URL = "/api/v1/criteria/assess/"
# 1980-07-15 00:00 BST, stored by Aryza as 23:00 UTC the day before.
DOB_TIMESTAMP = int((datetime(1980, 7, 14, 23, tzinfo=timezone.utc)
                     - datetime(1970, 1, 1, tzinfo=timezone.utc)).total_seconds())
_VOLATILE = {"evaluated_at", "decision_id"}


def _case():
    case = CaseData()
    case.aryza_reference = REF
    case.client_name = "Zephyrina Quillfeather"
    case.first_name, case.last_name, case.dob_timestamp = "Zephyrina", "Quillfeather", DOB_TIMESTAMP
    case.dob = "1980-07-15"
    # Balances and income in pence, as AryzaClient produces them.
    case.creditors = [
        {"name": "Alpha Bank", "type": "personal_loan", "balance": 600_000, "ref": "REF-ALPH"},
        {"name": "Beta Loans", "type": "personal_loan", "balance": 450_000, "ref": "REF-BETA"},
    ]
    case.income = dict(case.income, employment=250_000, total=250_000)
    case.expenditure = {"disability_expenses": 0, "total": 180_000}
    return case


def _cr_account(raw_name, matched, balance_pence, type_code="PL"):
    return {"raw_name": raw_name, "type_code": type_code, "normalised_name": raw_name.lower(),
            "matched_creditor": matched, "account_status": "Active", "current_balance": balance_pence,
            "missed_payments_last_3_months": 0, "account_age_months": 36, "start_date": "2023-06-01",
            "credit_limit": None, "recent_spending": False, "payment_history_months": 0}


def _pdf_report(**overrides):
    fields = dict(aryza_reference=REF, uploaded_file="credit_reports/2026/10/report.pdf", agency="Experian",
                  extraction_status="extracted",
                  extracted_data={"accounts": [_cr_account("ALPHA BANK (PDF)", "Alpha Bank", 600000)]})
    fields.update(overrides)
    return CreditReport.objects.create(**fields)


def _experian_import(extracted_accounts, status="extracted"):
    """What the real service leaves behind after an import."""
    def fake(aryza_reference, case_data_obj, credit_report_id=None, client=None):
        report = CreditReport.objects.create(
            aryza_reference=aryza_reference, source="experian_db", source_report_id=912, agency="Experian",
            extraction_status=status, extracted_data={"agency": "Experian", "accounts": extracted_accounts,
                                                      "mortgage_accounts": [], "other_accounts": []})
        return ExperianImportResult(report, "imported", True)
    return fake


def _is_cr_only(position):
    return "CREDITOR-CR-ONLY" in (position.get("rule_ids") or [])


def _positions(body):
    """The declared creditors' positions by name (report-only backfill rows excluded)."""
    return {p.get("creditor_name") or p.get("name"): p for p in body["creditor_positions"] if not _is_cr_only(p)}


class AssessmentWiringBase(TestCase):
    def setUp(self):
        self.client = APIClient()
        for name in ("Alpha Bank", "Beta Loans"):
            CreditorCriteria.objects.create(creditor_name=name, representative="NONE", status="ACCEPT", is_active=True)

    def _assess(self, body=None, ensure=None):
        """POST the assessment. `ensure`: a replacement for the import service, or None for the real one."""
        with patch("debt_app.views.criteria_views.fetch_case_by_reference", return_value=_case()):
            if ensure is None:
                resp = self.client.post(URL, data={"aryza_reference": REF, **(body or {})}, format="json")
            else:
                with patch("debt_app.views.criteria_views.ensure_experian_credit_report", ensure):
                    resp = self.client.post(URL, data={"aryza_reference": REF, **(body or {})}, format="json")
        self.assertEqual(resp.status_code, 200, resp.content[:500])
        return resp.json()

    @staticmethod
    def _stable(body):
        return json.loads(json.dumps({k: v for k, v in body.items() if k not in _VOLATILE}, sort_keys=True))


class FlagDisabledTests(AssessmentWiringBase):
    """EXPERIAN_AUTO_CREDIT_REPORT is off in settings; nothing here turns it on."""

    def test_flag_is_off(self):
        from django.conf import settings
        self.assertIs(settings.EXPERIAN_AUTO_CREDIT_REPORT, False)

    def test_public_endpoint_calls_the_service_which_never_creates_a_client(self):
        with patch.object(service, "ExperianDBClient") as client_class, \
                patch("debt_app.views.criteria_views.ensure_experian_credit_report",
                      wraps=service.ensure_experian_credit_report) as ensure:
            self._assess()
        ensure.assert_called_once()
        self.assertEqual(ensure.call_args.args[0], REF)
        # CAT shares no client: the service makes its own (one connection per assessment).
        self.assertEqual(ensure.call_args.kwargs, {"credit_report_id": None, "client": None})
        client_class.assert_not_called()
        self.assertFalse(CreditReport.objects.exists())

    def test_assessment_output_is_identical_to_running_without_the_import(self):
        with_import = self._assess()
        CreditReport.objects.all().delete()
        without_import = self._assess(ensure=lambda *a, **k: None)
        self.assertEqual(self._stable(with_import), self._stable(without_import))

    def test_pdf_only_case_is_unchanged(self):
        _pdf_report()
        with_import = self._assess()
        without_import = self._assess(ensure=lambda *a, **k: None)
        self.assertEqual(self._stable(with_import), self._stable(without_import))
        self.assertEqual(_positions(with_import)["Alpha Bank"]["cr_raw_name"], "ALPHA BANK (PDF)")
        self.assertEqual(CreditReport.objects.count(), 1)


@override_settings(EXPERIAN_AUTO_CREDIT_REPORT=True)
class FlagEnabledTests(AssessmentWiringBase):

    def test_usable_pdf_stays_active_when_experian_has_no_search(self):
        # Experian is still checked for a newer search (D5), and finds none.
        _pdf_report()
        client = FakeClient([])
        with patch.object(service, "ExperianDBClient", return_value=client):
            body = self._assess()
        self.assertEqual(client.sessions, 1)
        self.assertEqual(_positions(body)["Alpha Bank"]["cr_raw_name"], "ALPHA BANK (PDF)")
        self.assertFalse(CreditReport.objects.filter(source="experian_db").exists())

    def test_pinned_credit_report_id_never_invokes_the_import(self):
        pinned = _pdf_report(extraction_status="failed", extracted_data=None)
        with patch("debt_app.views.criteria_views.ensure_experian_credit_report") as ensure:
            self._assess(body={"credit_report_id": pinned.pk})
        ensure.assert_not_called()
        self.assertFalse(CreditReport.objects.filter(source="experian_db").exists())

    def test_imported_report_reaches_the_engine_payload(self):
        ensure = _experian_import([
            _cr_account("ALPHA BANK PLC", "Alpha Bank", 600000),
            _cr_account("GAMMA CARDS LTD", "GAMMA CARDS LTD", 120000, type_code="CC"),
        ])
        body = self._assess(ensure=ensure)
        alpha = _positions(body)["Alpha Bank"]
        self.assertEqual((alpha["cr_raw_name"], alpha["cr_balance"]), ("ALPHA BANK PLC", 600000))
        # The report-only account goes through the existing CR-only backfill.
        cr_only = [p for p in body["creditor_positions"] if _is_cr_only(p)]
        self.assertEqual([p.get("cr_raw_name") for p in cr_only], ["GAMMA CARDS LTD"])

    def test_real_service_imports_from_experian_and_the_assessment_uses_it(self):
        document = _doc([_detail(SupplyCompanyName="ALPHA BANK PLC", AccountType="02",
                                 AccountBalances=[{"AccountBalance": "0006000", "Status": "0"}])])
        client = FakeClient(
            [CandidateSearch(912, datetime(2026, 10, 1), "ZEPHYRINA", "QUILLFEATHER", "1980-07-15", False)],
            {912: document})
        with patch.object(service, "ExperianDBClient", return_value=client):
            body = self._assess()
        report = CreditReport.objects.get(source="experian_db")
        self.assertEqual((report.source_report_id, report.extraction_status), (912, "extracted"))
        alpha = _positions(body)["Alpha Bank"]
        self.assertEqual((alpha["cr_raw_name"], alpha["cr_balance"]), ("ALPHA BANK PLC", 600000))
        self.assertEqual(client.sessions, 1)

    def test_experian_unavailable_assessment_continues_without_a_report(self):
        with patch.object(service, "ExperianDBClient",
                          return_value=FakeClient(session_error=ExperianConnectionError("down"))):
            body = self._assess()
        without_import = self._assess(ensure=lambda *a, **k: None)
        self.assertEqual(self._stable(body), self._stable(without_import))
        self.assertFalse(CreditReport.objects.exists())
        self.assertFalse(_positions(body)["Alpha Bank"].get("cr_raw_name"))

    def test_empty_experian_import_assessment_still_completes(self):
        body = self._assess(ensure=_experian_import([], status="extracted_empty"))
        self.assertTrue(body["success"])
        self.assertFalse(_positions(body)["Alpha Bank"].get("cr_raw_name"))
        self.assertEqual(CreditReport.objects.get().extraction_status, "extracted_empty")

    def test_repeated_assessments_create_no_duplicate_report(self):
        document = _doc([_detail(SupplyCompanyName="ALPHA BANK PLC", AccountType="02",
                                 AccountBalances=[{"AccountBalance": "0006000", "Status": "0"}])])

        def new_client():
            return FakeClient(
                [CandidateSearch(912, datetime(2026, 10, 1), "ZEPHYRINA", "QUILLFEATHER", "1980-07-15", False)],
                {912: document})

        clients = []
        with patch.object(service, "ExperianDBClient", side_effect=lambda: clients.append(new_client()) or clients[-1]):
            first = self._assess()
            second = self._assess()
            third = self._assess()
        self.assertEqual(CreditReport.objects.filter(source="experian_db").count(), 1)
        # Every run checks Experian for a newer search (D5); the same search is
        # found already imported, so its document is fetched only the first time.
        self.assertEqual(len(clients), 3)
        fetches = [c for client in clients for c in client.calls if c[0] == "document"]
        self.assertEqual(fetches, [("document", 912, REF)])
        self.assertEqual(self._stable(first)["creditor_positions"], self._stable(second)["creditor_positions"])
        self.assertEqual(self._stable(second)["creditor_positions"], self._stable(third)["creditor_positions"])
