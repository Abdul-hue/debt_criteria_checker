"""
Phase 4 edge cases of the Experian import, end to end through the public CAT
assessment (and the Lead Gen check):

  * Changed Aryza identity: a stored import is checked again against the
    client's CURRENT name and date of birth. One that no longer matches is
    marked identity_mismatch and never used, so an older search that now
    matches can become active; it is used again if the identity matches again.
  * No candidate window: a newer matching search stays visible however many
    other people's searches are filed under the same reference (live
    references hold up to ~110).
  * Lead Gen's VAT re-run imports through one shared Experian connection.

Experian is faked (FakeExperian models the real query's identity gating); the
Aryza fetch is mocked. No live system is used.
"""
from datetime import datetime, timedelta
from unittest.mock import patch

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from debt_app.engine.criteria import _enrich_from_credit_report
from debt_app.models import CreditorCriteria, CreditReport
from debt_app.services import experian_credit_report as service
from debt_app.tests.test_experian_assessment_wiring import REF, URL, _case, _positions
from debt_app.tests.test_experian_credit_report import FakeClient
from debt_app.tests.test_experian_response_contract import MATCH, FakeExperian, _document, _search
from debt_app.tests.test_experian_cat_access_and_d5 import _search as _candidate_search
from debt_app.tests.test_experian_cat_access_and_d5 import _document as _plain_document
from debt_app.tests_lead_gen import _LeadGenFixture
from debt_app.views.criteria_views import select_credit_report

ONE_DAY = 24 * 60 * 60


def _case_with(last_name=None, dob_shift_days=0):
    """The test client after an Aryza correction of their surname or date of birth."""
    case = _case()
    if last_name is not None:
        case.last_name = last_name
    case.dob_timestamp += dob_shift_days * ONE_DAY
    return case


def _status(search_id):
    return CreditReport.objects.get(aryza_reference=REF, source_report_id=search_id).extraction_status


@override_settings(EXPERIAN_AUTO_CREDIT_REPORT=True)
class Base(TestCase):
    def setUp(self):
        for name in ("Alpha Bank", "Beta Loans"):
            CreditorCriteria.objects.create(creditor_name=name, representative="NONE", status="ACCEPT", is_active=True)

    def _assess(self, store, case=None):
        with patch.object(service, "ExperianDBClient", return_value=store), \
                patch("debt_app.views.criteria_views.fetch_case_by_reference", return_value=case or _case()):
            resp = APIClient().post(URL, data={"aryza_reference": REF}, format="json")
        self.assertEqual(resp.status_code, 200, resp.content[:300])
        return resp.json()

    def _active_name(self, body):
        return _positions(body)["Alpha Bank"].get("cr_raw_name")


class ChangedAryzaIdentityTests(Base):

    def test_older_search_that_matches_the_corrected_identity_replaces_the_stale_import(self):
        # 950 was run on the date of birth Aryza held (15th); 901 on the
        # correct one (16th). Aryza is then corrected to the 16th.
        store = FakeExperian([
            _search(901, datetime(2026, 8, 1, 9), _document("CORRECT ALPHA BANK", "0006100"),
                    identity=dict(MATCH, dob="1980-07-16")),
            _search(950, datetime(2026, 10, 1, 9), _document("WRONG DOB ALPHA BANK", "0006000")),
        ])
        self.assertEqual(self._active_name(self._assess(store)), "WRONG DOB ALPHA BANK")

        body = self._assess(store, case=_case_with(dob_shift_days=1))

        self.assertEqual(self._active_name(body), "CORRECT ALPHA BANK")
        self.assertEqual((_status(950), _status(901)), ("identity_mismatch", "extracted"))
        self.assertEqual(select_credit_report(REF).source_report_id, 901)
        self.assertEqual(store.document_reads, [950, 901])
        self.assertNotIn("WRONG DOB ALPHA BANK", str(body))

    def test_with_no_matching_search_left_no_experian_report_is_used(self):
        store = FakeExperian([_search(950, datetime(2026, 10, 1, 9), _document("ALPHA BANK PLC", "0006000"))])
        self._assess(store)

        body = self._assess(store, case=_case_with(last_name="Newsurname"))

        self.assertFalse(self._active_name(body))
        self.assertEqual(_status(950), "identity_mismatch")
        self.assertIsNone(select_credit_report(REF))
        # The case has no report of its own: "absent", not a failed extraction.
        self.assertEqual(_enrich_from_credit_report({"aryza_reference": REF, "creditors": []}), "absent")

    def test_import_is_used_again_when_the_identity_matches_again(self):
        store = FakeExperian([_search(950, datetime(2026, 10, 1, 9), _document("ALPHA BANK PLC", "0006000"))])
        self._assess(store)
        self._assess(store, case=_case_with(last_name="Newsurname"))

        body = self._assess(store)

        self.assertEqual(self._active_name(body), "ALPHA BANK PLC")
        self.assertEqual(_status(950), "extracted")
        self.assertEqual(store.document_reads, [950])          # restored, never re-fetched
        self.assertEqual(CreditReport.objects.count(), 1)

    def test_older_stored_import_becomes_active_again_when_the_newer_one_fails_identity(self):
        # 901 was imported while Aryza held the 16th, 950 after it was changed
        # to the 15th; changing it back makes 950 fail and 901 the active one.
        store = FakeExperian([
            _search(901, datetime(2026, 8, 1, 9), _document("OLDER ALPHA BANK", "0006100"),
                    identity=dict(MATCH, dob="1980-07-16")),
        ])
        self._assess(store, case=_case_with(dob_shift_days=1))
        store.searches.append(_search(950, datetime(2026, 10, 1, 9), _document("NEWER ALPHA BANK", "0006000")))
        self.assertEqual(self._active_name(self._assess(store)), "NEWER ALPHA BANK")
        self.assertEqual(_status(901), "identity_mismatch")

        body = self._assess(store, case=_case_with(dob_shift_days=1))

        self.assertEqual(self._active_name(body), "OLDER ALPHA BANK")
        self.assertEqual((_status(950), _status(901)), ("identity_mismatch", "extracted"))
        self.assertEqual(store.document_reads, [901, 950])      # neither is fetched again
        self.assertEqual(CreditReport.objects.count(), 2)

    def test_unchanged_identity_keeps_the_stored_import_without_reading_older_searches(self):
        store = FakeExperian([
            _search(901, datetime(2026, 8, 1, 9), _document("OLDER ALPHA BANK", "0006100")),
            _search(950, datetime(2026, 10, 1, 9), _document("ALPHA BANK PLC", "0006000")),
        ])
        self._assess(store)
        self.assertEqual(store.stored_reads, [])             # nothing stored yet
        store.identity_reads.clear()

        body = self._assess(store)

        self.assertEqual(self._active_name(body), "ALPHA BANK PLC")
        self.assertEqual(store.stored_reads, [950])          # the stored import is re-checked
        self.assertEqual(store.identity_reads, [])           # nothing newer, nothing older read
        self.assertEqual(store.document_reads, [950])


class NoCandidateWindowTests(Base):

    def test_newer_matching_search_behind_25_other_peoples_searches_becomes_active(self):
        store = FakeExperian([_search(901, datetime(2026, 8, 1, 9), _document("OLDER ALPHA BANK", "0006100"))])
        self._assess(store)
        store.searches.append(_search(950, datetime(2026, 9, 1, 9), _document("NEWER ALPHA BANK", "0006000")))
        for n in range(25):                                   # pushes 950 to position 26
            store.searches.append(_search(1000 + n, datetime(2026, 10, 1, 9) + timedelta(hours=n),
                                          _document("SOMEONE ELSE", "0001000"),
                                          identity=dict(MATCH, surname=f"OTHERPERSON{n}")))

        body = self._assess(store)

        self.assertEqual(self._active_name(body), "NEWER ALPHA BANK")
        self.assertEqual(select_credit_report(REF).source_report_id, 950)
        self.assertEqual(store.document_reads, [901, 950])

    def test_only_match_behind_25_other_peoples_searches_is_imported(self):
        store = FakeExperian([_search(901, datetime(2026, 8, 1, 9), _document("OWN ALPHA BANK", "0006100"))] + [
            _search(1000 + n, datetime(2026, 10, 1, 9) + timedelta(hours=n), _document("SOMEONE ELSE", "0001000"),
                    identity=dict(MATCH, surname=f"OTHERPERSON{n}"))
            for n in range(25)])

        self.assertEqual(self._active_name(self._assess(store)), "OWN ALPHA BANK")


@override_settings(EXPERIAN_AUTO_CREDIT_REPORT=True)
class LeadGenVatRerunSharesOneConnectionTests(_LeadGenFixture):

    def test_both_runs_import_through_one_experian_session(self):
        case = self._good_case("LG-EXP-VAT")     # no HMRC creditor: the VAT ticks force a re-run
        case.first_name, case.last_name, case.dob_timestamp = "Zephyrina", "Quillfeather", _case().dob_timestamp
        client = FakeClient([_candidate_search(912, datetime(2026, 10, 1))], {912: _plain_document()})
        with patch.object(service, "ExperianDBClient", return_value=client):
            resp = self._check(case, data={"dmp_checklist": {"hmrc_debt_has_vat": True,
                                                             "hmrc_previous_year_vat": True}})
        self.assertEqual(resp.status_code, 200, resp.content[:300])
        self.assertIs(resp.json()["hmrc_is_creditor"], False)
        # Run 1 imports; run 2 (the VAT re-run) re-checks it -- on the same session.
        self.assertEqual(client.calls, [("candidates", "LG-EXP-VAT"), ("code_tables",),
                                        ("document", 912, "LG-EXP-VAT"),
                                        ("stored", "LG-EXP-VAT"), ("candidates", "LG-EXP-VAT")])
        self.assertEqual(client.sessions, 1)
        self.assertEqual(CreditReport.objects.filter(aryza_reference="LG-EXP-VAT").count(), 1)
        self.assertEqual(resp.json()["credit_report"]["status"], "on_file")

    def test_a_check_without_a_re_run_still_opens_one_session(self):
        case = self._good_case("LG-EXP-ONE")
        case.first_name, case.last_name, case.dob_timestamp = "Zephyrina", "Quillfeather", _case().dob_timestamp
        client = FakeClient([_candidate_search(912, datetime(2026, 10, 1))], {912: _plain_document()})
        with patch.object(service, "ExperianDBClient", return_value=client):
            resp = self._check(case)
        self.assertEqual(resp.status_code, 200, resp.content[:300])
        self.assertEqual(client.sessions, 1)
        self.assertEqual([c[0] for c in client.calls], ["candidates", "code_tables", "document"])


def _mismatched_import(**extracted):
    return CreditReport.objects.create(
        aryza_reference=REF, source="experian_db", source_report_id=950, agency="Experian",
        extraction_status="identity_mismatch", extracted_data={
            "agency": "Experian", "mortgage_accounts": [], "other_accounts": [],
            "accounts": [{"raw_name": "ALPHA BANK PLC", "matched_creditor": "Alpha Bank", "type_code": "PL",
                          "current_balance": 600000, "account_status": "Default", "start_date": "2021-09-16"}],
            **extracted})


class MismatchedImportIsNeverReadTests(TestCase):
    """Every reader of CreditReport skips an identity_mismatch import."""

    def setUp(self):
        CreditorCriteria.objects.create(creditor_name="Alpha Bank", representative="NONE", status="ACCEPT",
                                        is_active=True)

    def test_a_pinned_mismatched_import_is_not_used(self):
        report = _mismatched_import()
        self.assertIsNone(select_credit_report(REF, credit_report_id=report.pk))
        with patch("debt_app.views.criteria_views.fetch_case_by_reference", return_value=_case()):
            body = APIClient().post(URL, data={"aryza_reference": REF, "credit_report_id": report.pk},
                                    format="json").json()
        self.assertFalse(_positions(body)["Alpha Bank"].get("cr_raw_name"))

    def test_a_pinned_mismatched_import_falls_back_to_the_usable_report(self):
        pdf = CreditReport.objects.create(
            aryza_reference=REF, uploaded_file="credit_reports/2026/10/r.pdf", agency="Experian",
            extraction_status="extracted", extracted_data={"accounts": [{"raw_name": "ALPHA BANK (PDF)"}]})
        self.assertEqual(select_credit_report(REF, credit_report_id=_mismatched_import().pk), pdf)

    def test_direct_assess_does_not_read_it(self):
        _mismatched_import()
        payload = {"aryza_reference": REF, "client_name": "x", "disposable_income": 300, "total_income": 2000,
                   "creditors": [{"name": "Alpha Bank", "creditor_name": "Alpha Bank", "balance": 6000,
                                  "debt_type": "personal_loan"}]}
        resp = APIClient().post("/api/v1/assess/", data=payload, format="json")
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn("ALPHA BANK PLC", resp.content.decode())

    def test_evaluate_view_takes_no_mortgage_balance_from_it(self):
        from debt_app.views.evaluate_view import EvaluateCaseView
        _mismatched_import(mortgage_accounts=[{"raw_name": "SOMEONE ELSES MORTGAGE", "current_balance": 9_000_000}])
        case = _case()
        case.property = {"owns_property": True, "property_value": 25_000_000}
        self.assertIsNone(EvaluateCaseView()._prepare_engine_payload(case)["property"]["mortgage_balance"])

    def test_evaluate_view_still_takes_it_from_a_usable_report(self):
        from debt_app.views.evaluate_view import EvaluateCaseView
        report = _mismatched_import(mortgage_accounts=[{"raw_name": "OWN MORTGAGE", "current_balance": 9_000_000}])
        CreditReport.objects.filter(pk=report.pk).update(extraction_status="extracted")
        case = _case()
        case.property = {"owns_property": True, "property_value": 25_000_000}
        self.assertEqual(EvaluateCaseView()._prepare_engine_payload(case)["property"]["mortgage_balance"], 90_000.0)


class LeadGenStatusIgnoresMismatchedImportTests(_LeadGenFixture):

    def test_status_reports_no_usable_report(self):
        _mismatched_import()
        self._jwt(self.lg_user)
        body = self.api.get("/api/v1/criteria/lead-gen/credit-report-status/", {"aryza_reference": REF}).json()
        self.assertEqual((body["has_usable_report"], body["credit_report_id"]), (False, None))
