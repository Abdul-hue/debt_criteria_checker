"""
CAT uses Experian reports, and the newest matched Experian search is the active
report (D5).

  * The public CAT assessment imports (flag on) and uses an Experian report;
    with none, the PDF behaviour is unchanged; a pinned report is honoured.
  * An imported search's created_at is the time the search was run, so the
    usual "newest usable report first (then highest id)" selection makes the
    newest matched search active, keeps older imports as history, and lets a
    PDF uploaded after a search stay active.
  * A report is only ever imported for the Aryza client it matches, and is
    scoped to that case's reference.

Experian is faked; the Aryza fetch is mocked. No live system is used.
"""
import json
from datetime import datetime, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from debt_app.criteria_engine import assess_case
from debt_app.engine.criteria import _enrich_from_credit_report
from debt_app.integrations.experian_db import CandidateSearch
from debt_app.models import CreditorCriteria, CreditReport
from debt_app.services import experian_credit_report as service
from debt_app.services.experian_credit_report import ensure_experian_credit_report
from debt_app.tests.test_experian_assessment_wiring import REF, URL, _case, _is_cr_only, _positions
from debt_app.tests.test_experian_credit_report import FakeClient
from debt_app.tests.test_experian_mapper import _detail, _doc
from debt_app.tests_lead_gen import _LeadGenFixture
from debt_app.views import criteria_views

LONDON = ZoneInfo("Europe/London")


def _search(search_id, created, forename="ZEPHYRINA", surname="QUILLFEATHER", dob="1980-07-15"):
    return CandidateSearch(search_id, created, forename, surname, dob, False)


def _document(name="ALPHA BANK PLC", pounds="0006000", accounts=True):
    details = [_detail(SupplyCompanyName=name, AccountType="02",
                       AccountBalances=[{"AccountBalance": pounds, "Status": "0"}])] if accounts else []
    return _doc(details)


def _experian_report(search_id=912, name="ALPHA BANK PLC", status="extracted", reference=REF):
    return CreditReport.objects.create(
        aryza_reference=reference, source="experian_db", source_report_id=search_id, agency="Experian",
        extraction_status=status, extracted_data={"agency": "Experian", "accounts": [
            {"raw_name": name, "matched_creditor": "Alpha Bank", "type_code": "PL",
             "current_balance": 600000, "account_status": "Default", "start_date": "2021-09-16"}],
            "mortgage_accounts": [], "other_accounts": [], "has_ccj": True,
            "public_information": {"has_ccj": True}})


def _pdf_report(name="ALPHA BANK (PDF)", reference=REF):
    return CreditReport.objects.create(
        aryza_reference=reference, uploaded_file="credit_reports/2026/10/r.pdf", agency="Experian",
        extraction_status="extracted", extracted_data={"agency": "Experian", "accounts": [
            {"raw_name": name, "matched_creditor": "Alpha Bank", "type_code": "PL",
             "current_balance": 600000, "account_status": "Active", "start_date": "2022-01-01"}],
            "mortgage_accounts": [], "other_accounts": []})


def _set_created(report, when):
    """Explicit created_at: rows created back to back can share a timestamp
    (the Windows clock ticks every ~15 ms)."""
    CreditReport.objects.filter(pk=report.pk).update(created_at=when)
    report.refresh_from_db()
    return report


def _days_ago(n):
    return timezone.now() - timedelta(days=n)


class Base(TestCase):
    def setUp(self):
        for name in ("Alpha Bank", "Beta Loans"):
            CreditorCriteria.objects.create(creditor_name=name, representative="NONE", status="ACCEPT", is_active=True)

    def _assess(self, body=None):
        with patch("debt_app.views.criteria_views.fetch_case_by_reference", return_value=_case()):
            resp = APIClient().post(URL, data={"aryza_reference": REF, **(body or {})}, format="json")
        self.assertEqual(resp.status_code, 200, resp.content[:300])
        return resp.json()

    def _import(self, client):
        return ensure_experian_credit_report(REF, _case(), client=client)


# ---------------------------------------------------------------------------
# CAT uses Experian
# ---------------------------------------------------------------------------

class CatUsesExperianTests(Base):

    @override_settings(EXPERIAN_AUTO_CREDIT_REPORT=True)
    def test_cat_imports_and_uses_the_matching_search(self):
        client = FakeClient([_search(912, datetime(2026, 10, 1, 9, 30))], {912: _document()})
        with patch.object(service, "ExperianDBClient", return_value=client):
            body = self._assess()
        self.assertEqual(_positions(body)["Alpha Bank"]["cr_raw_name"], "ALPHA BANK PLC")

    def test_stored_experian_report_is_used_by_cat_with_the_flag_off(self):
        _experian_report()
        alpha = _positions(self._assess())["Alpha Bank"]
        self.assertEqual((alpha["cr_raw_name"], alpha["cr_account_status"]), ("ALPHA BANK PLC", "Default"))

    def test_engine_enrichment_uses_the_experian_report(self):
        _experian_report()
        case = {"aryza_reference": REF, "creditors": []}
        self.assertEqual(_enrich_from_credit_report(case), "present")
        self.assertTrue(case["has_ccj"])

    def test_without_experian_the_pdf_is_used(self):
        _pdf_report()
        self.assertEqual(_positions(self._assess())["Alpha Bank"]["cr_raw_name"], "ALPHA BANK (PDF)")

    def test_pinned_valid_experian_report_is_honoured(self):
        pinned = _set_created(_experian_report(), _days_ago(5))
        _set_created(_pdf_report(), _days_ago(1))        # newer, would win without the pin
        body = self._assess(body={"credit_report_id": pinned.pk})
        self.assertEqual(_positions(body)["Alpha Bank"]["cr_raw_name"], "ALPHA BANK PLC")

    def test_a_pinned_report_of_another_case_is_not_used(self):
        other = _experian_report(reference="999999", name="OTHER CASE LENDER")
        _pdf_report()
        body = self._assess(body={"credit_report_id": other.pk})
        self.assertEqual(_positions(body)["Alpha Bank"]["cr_raw_name"], "ALPHA BANK (PDF)")
        self.assertNotIn("OTHER CASE LENDER", json.dumps(body))

    def test_another_cases_stored_report_is_never_used(self):
        _experian_report(reference="999999", name="OTHER CASE LENDER")
        body = self._assess()
        self.assertFalse(_positions(body)["Alpha Bank"].get("cr_raw_name"))
        self.assertNotIn("OTHER CASE LENDER", json.dumps(body))


class IdentityGuardsCatTests(Base):
    """CAT can only end up with an Experian report that matched its own Aryza client."""

    @override_settings(EXPERIAN_AUTO_CREDIT_REPORT=True)
    def test_search_about_another_person_is_not_imported_or_used(self):
        for wrong in (dict(surname="SOMEONEELSE"), dict(forename="ZARA"), dict(dob="1979-01-01")):
            client = FakeClient([_search(912, datetime(2026, 10, 1), **wrong)], {912: _document()})
            with patch.object(service, "ExperianDBClient", return_value=client):
                body = self._assess()
            self.assertFalse(CreditReport.objects.filter(source="experian_db").exists(), wrong)
            self.assertFalse(_positions(body)["Alpha Bank"].get("cr_raw_name"), wrong)
            self.assertEqual([c for c in client.calls if c[0] == "document"], [], wrong)

    @override_settings(EXPERIAN_AUTO_CREDIT_REPORT=True)
    def test_second_applicant_search_is_not_imported(self):
        search = CandidateSearch(912, datetime(2026, 10, 1), "ZEPHYRINA", "QUILLFEATHER", "1980-07-15", True)
        with patch.object(service, "ExperianDBClient", return_value=FakeClient([search], {912: _document()})):
            self._assess()
        self.assertFalse(CreditReport.objects.exists())

    @override_settings(EXPERIAN_AUTO_CREDIT_REPORT=True)
    def test_incomplete_aryza_identity_never_queries(self):
        case = _case()
        case.dob_timestamp = None
        with patch("debt_app.views.criteria_views.fetch_case_by_reference", return_value=case), \
                patch.object(service, "ExperianDBClient") as client_class:
            APIClient().post(URL, data={"aryza_reference": REF}, format="json")
        client_class.assert_not_called()


# ---------------------------------------------------------------------------
# D5: newest matched search wins
# ---------------------------------------------------------------------------

@override_settings(EXPERIAN_AUTO_CREDIT_REPORT=True)
class NewestMatchedSearchWinsTests(Base):

    def test_one_experian_report_is_selected(self):
        report = self._import(FakeClient([_search(912, datetime(2026, 10, 1, 9))], {912: _document()})).report
        self.assertEqual(criteria_views.select_credit_report(REF), report)

    def test_imported_row_is_dated_by_its_search(self):
        report = self._import(FakeClient([_search(912, datetime(2026, 7, 10, 8, 33))], {912: _document()})).report
        self.assertEqual(report.created_at, datetime(2026, 7, 10, 8, 33, tzinfo=LONDON))
        self.assertGreater(report.updated_at, report.created_at)   # import time kept in updated_at

    def test_newer_matched_search_becomes_active_and_older_is_kept(self):
        older = self._import(FakeClient([_search(912, datetime(2026, 9, 1, 9))], {912: _document()})).report
        newer = self._import(FakeClient(
            [_search(950, datetime(2026, 10, 20, 9)), _search(912, datetime(2026, 9, 1, 9))],
            {950: _document(name="ALPHA BANK PLC NEW"), 912: _document()})).report
        self.assertNotEqual(newer, older)
        self.assertEqual(criteria_views.select_credit_report(REF), newer)
        self.assertTrue(CreditReport.objects.filter(pk=older.pk).exists())
        self.assertEqual(CreditReport.objects.get(pk=older.pk).extracted_data, older.extracted_data)
        self.assertEqual(CreditReport.objects.filter(source="experian_db").count(), 2)
        self.assertEqual(_positions(self._assess_no_import())["Alpha Bank"]["cr_raw_name"], "ALPHA BANK PLC NEW")

    def _assess_no_import(self):
        with patch.object(service, "ExperianDBClient", return_value=FakeClient([])):
            return self._assess()

    def test_identical_timestamps_resolve_to_the_higher_id(self):
        same = _days_ago(3)
        first = _set_created(_experian_report(912, name="FIRST"), same)
        second = _set_created(_experian_report(913, name="SECOND"), same)
        self.assertGreater(second.pk, first.pk)
        for _ in range(3):
            self.assertEqual(criteria_views.select_credit_report(REF), second)
        # The whole CAT assessment resolves the tie the same way.
        self.assertEqual(_positions(self._assess_no_import())["Alpha Bank"]["cr_raw_name"], "SECOND")

    def test_newer_unusable_search_does_not_replace_the_latest_usable_one(self):
        usable = self._import(FakeClient([_search(912, datetime(2026, 9, 1, 9))], {912: _document()})).report
        empty = self._import(FakeClient(
            [_search(950, datetime(2026, 10, 20, 9)), _search(912, datetime(2026, 9, 1, 9))],
            {950: _document(accounts=False)})).report
        self.assertEqual(empty.extraction_status, "extracted_empty")
        self.assertEqual(criteria_views.select_credit_report(REF), usable)

    def test_newer_search_about_another_person_does_not_replace_it(self):
        usable = self._import(FakeClient([_search(912, datetime(2026, 9, 1, 9))], {912: _document()})).report
        result = self._import(FakeClient(
            [_search(950, datetime(2026, 10, 20, 9), surname="SOMEONEELSE"), _search(912, datetime(2026, 9, 1, 9))],
            {950: _document(name="WRONG PERSON"), 912: _document()}))
        self.assertEqual(result.reason, "already_imported")
        self.assertEqual(criteria_views.select_credit_report(REF), usable)
        self.assertFalse(CreditReport.objects.filter(source_report_id=950).exists())

    def test_pdf_is_used_when_no_eligible_experian_report_exists(self):
        pdf = _set_created(_pdf_report(), _days_ago(30))
        _set_created(_experian_report(950, status="extracted_empty"), _days_ago(1))
        _set_created(_experian_report(951, status="failed"), _days_ago(1))
        self.assertEqual(criteria_views.select_credit_report(REF), pdf)

    def test_pdf_uploaded_after_the_search_stays_active(self):
        imported = self._import(FakeClient([_search(912, datetime(2026, 9, 1, 9))], {912: _document()})).report
        pdf = _pdf_report()     # uploaded now, after the search
        self.assertGreater(pdf.created_at, imported.created_at)
        self.assertEqual(criteria_views.select_credit_report(REF), pdf)
        # An older search imported only now is dated by its search, so it cannot displace the PDF.
        self._import(FakeClient([_search(800, datetime(2026, 8, 1, 9))], {800: _document(name="OLD SEARCH")}))
        self.assertEqual(criteria_views.select_credit_report(REF), pdf)

    def test_search_run_after_the_pdf_becomes_active(self):
        _set_created(_pdf_report(), datetime(2026, 9, 1, 9, tzinfo=LONDON))
        newer = self._import(FakeClient([_search(950, datetime(2026, 10, 20, 9))], {950: _document()})).report
        self.assertEqual(criteria_views.select_credit_report(REF), newer)

    def test_pinned_valid_experian_report_is_honoured_over_a_newer_one(self):
        older = _set_created(_experian_report(912, name="OLDER"), _days_ago(10))
        _set_created(_experian_report(950, name="NEWER"), _days_ago(1))
        self.assertEqual(criteria_views.select_credit_report(REF, older.pk), older)

    def test_duplicate_import_attempts_produce_one_row(self):
        for _ in range(3):
            self._import(FakeClient([_search(912, datetime(2026, 10, 1, 9))], {912: _document()}))
        self.assertEqual(CreditReport.objects.filter(source="experian_db", source_report_id=912).count(), 1)


# ---------------------------------------------------------------------------
# Other consumers keep their access
# ---------------------------------------------------------------------------

class ConsumersSeeExperianTests(Base):

    def test_assess_case_default_sees_experian(self):
        # /api/assess/, EvaluateCaseView, criteria replay and pre_deploy_audit all
        # call assess_case without a source restriction.
        _experian_report()
        result = assess_case({"aryza_reference": REF, "client_name": "x", "creditors": [],
                              "disposable_income": 300, "total_income": 2000}, set())
        self.assertIsNotNone(result)
        case = {"aryza_reference": REF, "creditors": []}
        self.assertEqual(_enrich_from_credit_report(case), "present")

    def test_direct_assess_reads_the_experian_report(self):
        _experian_report()
        payload = {"aryza_reference": REF, "client_name": "x", "disposable_income": 300, "total_income": 2000,
                   "creditors": [{"name": "Alpha Bank", "creditor_name": "Alpha Bank", "balance": 6000,
                                  "debt_type": "personal_loan"}]}
        resp = APIClient().post("/api/v1/assess/", data=payload, format="json")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("ALPHA BANK PLC", resp.content.decode())


@override_settings(EXPERIAN_AUTO_CREDIT_REPORT=True)
class LeadGenCheckStillUsesExperianTests(_LeadGenFixture):
    """The logged-in Lead Gen check imports and uses Experian through the same runner."""

    def test_lead_gen_check_imports_and_reports_it_on_file(self):
        case = self._good_case("LG-EXP")
        case.first_name, case.last_name, case.dob_timestamp = "Zephyrina", "Quillfeather", _case().dob_timestamp
        client = FakeClient([_search(912, datetime(2026, 10, 1))], {912: _document()})
        with patch.object(service, "ExperianDBClient", return_value=client):
            resp = self._check(case)
        self.assertEqual(resp.status_code, 200, resp.content[:300])
        report = CreditReport.objects.get(aryza_reference="LG-EXP")
        self.assertEqual((report.source, report.source_report_id), ("experian_db", 912))
        self.assertEqual(resp.json()["credit_report"]["status"], "on_file")
