"""
Experian credit-report import (debt_app/services/experian_credit_report.py):
Aryza date-of-birth conversion, the identity check, and
ensure_experian_credit_report().

Experian is faked throughout (one test drives the real read layer with
pymssql mocked). Every person below is invented; the distinctive values exist
so the log tests can prove none of them is ever written.
"""
import json
import logging
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, TestCase, override_settings

from debt_app.aryza_client import AryzaClient, CaseData
from debt_app.integrations import experian_db
from debt_app.integrations.experian_db import (
    CandidateSearch,
    ExperianConnectionError,
    ExperianDataError,
)
from debt_app.integrations.experian_mapper import map_search_to_extracted_data
from debt_app.models import CreditReport
from debt_app.services import experian_credit_report as service
from debt_app.services.experian_credit_report import (
    AryzaIdentity,
    aryza_dob_to_date,
    ensure_experian_credit_report,
    identity_matches,
)
from debt_app.tests.test_experian_mapper import ACCOUNT_TYPES, CODE_TABLES, PUBLIC_INFO_TYPES, _detail, _doc

EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
REF = "349223"
FORENAME, SURNAME, DOB = "Zephyrina", "Quillfeather", date(1980, 7, 15)
ACCOUNT_NUMBER = "ACCT-998877"


def _ts(utc_datetime):
    return int((utc_datetime - EPOCH).total_seconds())


# 1980-07-15 00:00 British Summer Time == 1980-07-14 23:00 UTC, as Aryza stores it.
DOB_TIMESTAMP = _ts(datetime(1980, 7, 14, 23, 0, tzinfo=timezone.utc))


def _case(first=FORENAME, last=SURNAME, dob_timestamp=DOB_TIMESTAMP):
    case = CaseData()
    case.aryza_reference = REF
    case.first_name, case.last_name, case.dob_timestamp = first, last, dob_timestamp
    return case


def _candidate(search_id=912, forename="ZEPHYRINA", surname="QUILLFEATHER", dob="1980-07-15T00:00:00",
               second=False, created=datetime(2026, 10, 1)):
    return CandidateSearch(search_id=search_id, date_created=created, forename=forename, surname=surname,
                           date_of_birth=dob, has_second_applicant=second)


def _document(*details):
    document = _doc(details or [_detail(AccountNumber=ACCOUNT_NUMBER)])
    person = document["Response"]["Applicants"][0]["Person"]
    person.update(Forename="ZEPHYRINA", Surname="QUILLFEATHER", DateOfBirth="1980-07-15")
    return document


class FakeSession:
    def __init__(self, client):
        self.client = client

    def find_candidate_searches(self, crm_ref, imported_ids=()):
        # Returns every candidate with its identity read; the real query skips
        # reading searches older than the newest imported one
        # (see test_experian_response_contract.FakeExperian for that).
        self.client.calls.append(("candidates", crm_ref))
        if isinstance(self.client.candidates, Exception):
            raise self.client.candidates
        return list(self.client.candidates)

    def read_stored_searches(self, crm_ref, search_ids):
        # As the real method: no query when nothing is stored.
        ids = {i for i in search_ids if i is not None}
        if not ids:
            return []
        self.client.calls.append(("stored", crm_ref))
        if isinstance(self.client.candidates, Exception):
            raise self.client.candidates
        return [c for c in self.client.candidates if c.search_id in ids]

    def load_code_tables(self, refresh=False):
        self.client.calls.append(("code_tables",))
        return CODE_TABLES

    def fetch_search_document(self, search_id, crm_ref):
        self.client.calls.append(("document", search_id, crm_ref))
        result = self.client.documents[search_id]
        if isinstance(result, Exception):
            raise result
        return result


class FakeClient:
    """Stands in for ExperianDBClient; records every call."""

    def __init__(self, candidates=(), documents=None, session_error=None):
        self.candidates = candidates if isinstance(candidates, Exception) else list(candidates)
        self.documents = documents or {}
        self.session_error = session_error
        self.calls = []
        self.sessions = 0

    @contextmanager
    def session(self):
        self.sessions += 1
        if self.session_error:
            raise self.session_error
        yield FakeSession(self)


def _pdf_report(status="extracted", accounts=({"raw_name": "HALIFAX"},)):
    return CreditReport.objects.create(
        aryza_reference=REF, uploaded_file="credit_reports/2026/10/report.pdf", agency="Experian",
        extraction_status=status, extracted_data={"accounts": list(accounts)})


# ---------------------------------------------------------------------------
# Aryza date of birth
# ---------------------------------------------------------------------------

class AryzaDobToDateTests(SimpleTestCase):
    def test_bst_midnight_stored_as_23_00_utc(self):
        self.assertEqual(aryza_dob_to_date(DOB_TIMESTAMP), date(1980, 7, 15))

    def test_gmt_midnight_stored_as_00_00_utc(self):
        self.assertEqual(aryza_dob_to_date(_ts(datetime(1980, 1, 15, tzinfo=timezone.utc))), date(1980, 1, 15))

    def test_pre_1970_negative_timestamps(self):
        self.assertEqual(aryza_dob_to_date(_ts(datetime(1955, 3, 2, tzinfo=timezone.utc))), date(1955, 3, 2))
        self.assertLess(_ts(datetime(1955, 3, 2, tzinfo=timezone.utc)), 0)
        # 1968-71 British Standard Time: UK clocks were UTC+1 all year.
        self.assertEqual(aryza_dob_to_date(_ts(datetime(1969, 12, 24, 23, tzinfo=timezone.utc))), date(1969, 12, 25))

    def test_odd_time_of_day_keeps_its_own_date(self):
        self.assertEqual(aryza_dob_to_date(_ts(datetime(1980, 1, 15, 20, 30, tzinfo=timezone.utc))), date(1980, 1, 15))

    def test_string_timestamp(self):
        self.assertEqual(aryza_dob_to_date(str(DOB_TIMESTAMP)), date(1980, 7, 15))

    def test_missing_or_invalid_is_none(self):
        for value in (None, 0, "0", "", "not a number", 10 ** 20):
            self.assertIsNone(aryza_dob_to_date(value), value)


# ---------------------------------------------------------------------------
# Identity check
# ---------------------------------------------------------------------------

class IdentityMatchTests(SimpleTestCase):
    def _match(self, case=None, **candidate):
        return identity_matches(AryzaIdentity.from_case(case or _case()), _candidate(**candidate))

    def test_exact_match(self):
        self.assertEqual(self._match(), (True, "match"))

    def test_case_and_spacing_do_not_matter(self):
        self.assertEqual(self._match(forename="  zephyrina ", surname=" quillFEATHER  "), (True, "match"))

    def test_accents_do_not_matter(self):
        case = _case(first="Zéphyrina", last="Quillféather")
        self.assertEqual(self._match(case), (True, "match"))
        self.assertEqual(self._match(forename="ZÉPHYRINA"), (True, "match"))

    def test_hyphenated_and_spaced_surnames_are_equal(self):
        case = _case(last="Smith-Jones")
        for surname in ("SMITH JONES", "SMITH-JONES", "SMITHJONES", "Smith - Jones"):
            self.assertEqual(self._match(case, surname=surname), (True, "match"), surname)
        self.assertEqual(self._match(_case(last="O'Neill"), surname="ONEILL"), (True, "match"))

    def test_two_word_forename_compares_first_word(self):
        self.assertEqual(self._match(_case(first="Mary Ann"), forename="MARY"), (True, "match"))
        self.assertEqual(self._match(forename="ZEPHYRINA ROSE"), (True, "match"))
        self.assertEqual(self._match(_case(first="Mary Ann"), forename="ANN"), (False, "forename_mismatch"))

    def test_surname_mismatch(self):
        self.assertEqual(self._match(surname="QUILL"), (False, "surname_mismatch"))
        # A partial surname is not enough.
        self.assertEqual(self._match(_case(last="Smith-Jones"), surname="SMITH"), (False, "surname_mismatch"))

    def test_forename_mismatch(self):
        self.assertEqual(self._match(forename="ZARA"), (False, "forename_mismatch"))

    def test_dob_must_be_the_same_day(self):
        self.assertEqual(self._match(dob="1980-07-15"), (True, "match"))
        self.assertEqual(self._match(dob="1980-07-14T00:00:00"), (False, "dob_mismatch"))
        self.assertEqual(self._match(dob="1980-07-16"), (False, "dob_mismatch"))

    def test_bst_stored_aryza_dob_matches_experian_calendar_date(self):
        # A naive UTC conversion would give 1980-07-14 and fail.
        self.assertEqual(datetime.fromtimestamp(DOB_TIMESTAMP, tz=timezone.utc).date(), date(1980, 7, 14))
        self.assertEqual(self._match(dob="1980-07-15"), (True, "match"))

    def test_pre_1970_dob(self):
        case = _case(dob_timestamp=_ts(datetime(1955, 3, 2, tzinfo=timezone.utc)))
        self.assertEqual(self._match(case, dob="1955-03-02T00:00:00"), (True, "match"))

    def test_experian_side_missing_or_unusable(self):
        self.assertEqual(self._match(dob=None), (False, "experian_dob_missing"))
        self.assertEqual(self._match(dob="garbage"), (False, "experian_dob_missing"))
        self.assertEqual(self._match(forename=None), (False, "experian_name_missing"))
        self.assertEqual(self._match(surname="  "), (False, "experian_name_missing"))

    def test_search_with_a_second_applicant_is_never_used(self):
        self.assertEqual(self._match(second=True), (False, "second_applicant"))

    def test_aryza_identity_completeness(self):
        self.assertTrue(AryzaIdentity.from_case(_case()).complete)
        self.assertFalse(AryzaIdentity.from_case(_case(dob_timestamp=None)).complete)
        self.assertFalse(AryzaIdentity.from_case(_case(first="")).complete)
        self.assertFalse(AryzaIdentity.from_case(_case(last=None)).complete)
        self.assertFalse(AryzaIdentity.from_case(CaseData()).complete)
        self.assertFalse(AryzaIdentity.from_case(object()).complete)

    def test_identity_repr_has_no_personal_data(self):
        text = repr(AryzaIdentity.from_case(_case()))
        for personal in ("zephyrina", "quillfeather", "1980"):
            self.assertNotIn(personal, text.lower())


class AryzaClientIdentityFieldsTests(SimpleTestCase):
    def test_client_row_name_parts_and_dob_timestamp_are_kept(self):
        cursor = MagicMock()
        cursor.fetchone.side_effect = [(5, FORENAME, SURNAME, DOB_TIMESTAMP)] + [None] * 10
        cursor.fetchall.return_value = []
        connection = MagicMock()
        connection.cursor.return_value.__enter__.return_value = cursor
        case = CaseData()
        AryzaClient()._fetch_client_data(connection, case, 5)
        self.assertEqual((case.first_name, case.last_name, case.dob_timestamp), (FORENAME, SURNAME, DOB_TIMESTAMP))
        self.assertEqual(case.client_name, f"{FORENAME} {SURNAME}")

    def test_engine_payload_is_unchanged(self):
        payload = _case().to_dict()
        for key in ("first_name", "last_name", "dob_timestamp"):
            self.assertNotIn(key, payload)


# ---------------------------------------------------------------------------
# ensure_experian_credit_report
# ---------------------------------------------------------------------------

@override_settings(EXPERIAN_AUTO_CREDIT_REPORT=True)
class EnsureExperianCreditReportTests(TestCase):

    def _run(self, client, case=None, **kwargs):
        return ensure_experian_credit_report(REF, case or _case(), client=client, **kwargs)

    # -- when Experian must not be touched ---------------------------------

    @override_settings(EXPERIAN_AUTO_CREDIT_REPORT=False)
    def test_flag_disabled_never_creates_a_client(self):
        with patch.object(service, "ExperianDBClient") as client_class:
            result = ensure_experian_credit_report(REF, _case())
        client_class.assert_not_called()
        self.assertEqual((result.report, result.reason), (None, "flag_disabled"))

    def test_existing_usable_pdf_does_not_stop_the_check_for_a_newer_search(self):
        from debt_app.views.criteria_views import select_credit_report
        pdf = _pdf_report()   # uploaded now, i.e. after the search below was run
        client = FakeClient([_candidate(912, created=datetime(2026, 10, 1))], {912: _document()})
        result = self._run(client)
        self.assertEqual(result.reason, "imported")
        self.assertEqual(client.sessions, 1)
        # The search is older than the PDF, so the PDF stays the active report.
        self.assertEqual(select_credit_report(REF), pdf)

    def test_pinned_credit_report_id_means_no_experian_query(self):
        with patch.object(service, "ExperianDBClient") as client_class:
            result = ensure_experian_credit_report(REF, _case(), credit_report_id=77)
        client_class.assert_not_called()
        self.assertEqual(result.reason, "pinned_report")

    def test_incomplete_aryza_identity_means_no_experian_query(self):
        for case in (_case(dob_timestamp=None), _case(dob_timestamp=0), _case(first=""), _case(last=None)):
            with patch.object(service, "ExperianDBClient") as client_class:
                result = ensure_experian_credit_report(REF, case)
            client_class.assert_not_called()
            self.assertEqual(result.reason, "identity_unavailable")

    def test_blank_reference(self):
        with patch.object(service, "ExperianDBClient") as client_class:
            self.assertEqual(ensure_experian_credit_report("  ", _case()).reason, "no_reference")
        client_class.assert_not_called()

    # -- importing ----------------------------------------------------------

    def test_imports_the_matching_search(self):
        document = _document()
        client = FakeClient([_candidate(912)], {912: document})
        result = self._run(client)
        self.assertEqual((result.reason, result.created), ("imported", True))
        report = result.report
        report.refresh_from_db()
        self.assertEqual(report.aryza_reference, REF)
        self.assertEqual((report.source, report.source_report_id), ("experian_db", 912))
        self.assertEqual(report.agency, "Experian")
        self.assertEqual(report.extraction_status, "extracted")
        self.assertFalse(report.uploaded_file)
        self.assertIsNone(report.uploaded_by)
        self.assertEqual(report.extracted_data, map_search_to_extracted_data(document, CODE_TABLES))
        self.assertEqual(report.client_name_on_report, "ZEPHYRINA QUILLFEATHER")
        self.assertEqual(report.client_address_on_report, "12 HIGH STREET, LEEDS, LS1 1AA")
        self.assertEqual(client.sessions, 1)
        self.assertEqual(client.calls, [("candidates", REF), ("code_tables",), ("document", 912, REF)])

    def test_raw_search_document_is_not_stored(self):
        report = self._run(FakeClient([_candidate(912)], {912: _document()})).report
        stored = json.dumps(report.extracted_data)
        for raw in ("Response", "FullConsumerData", "Association", "1980-07-15", "DateOfBirth"):
            self.assertNotIn(raw, stored)

    def test_imported_report_is_selected_by_the_existing_selector(self):
        from debt_app.views.criteria_views import select_credit_report
        report = self._run(FakeClient([_candidate(912)], {912: _document()})).report
        self.assertEqual(select_credit_report(REF), report)

    def test_report_with_no_accounts_is_saved_as_extracted_empty(self):
        document = _document()
        document["Response"]["FullConsumerData"]["ConsumerData"]["CAIS"] = []
        result = self._run(FakeClient([_candidate(912)], {912: document}))
        self.assertEqual((result.reason, result.report.extraction_status), ("imported", "extracted_empty"))

    def test_existing_failed_or_empty_pdf_lets_experian_be_tried(self):
        _pdf_report(status="failed")
        _pdf_report(status="extracted_empty", accounts=())
        _pdf_report(status="extracted", accounts=())
        result = self._run(FakeClient([_candidate(912)], {912: _document()}))
        self.assertEqual(result.reason, "imported")
        self.assertEqual(CreditReport.objects.filter(source="pdf_upload").count(), 3)

    # -- choosing a search --------------------------------------------------

    def test_newest_failing_identity_is_skipped_for_an_older_match(self):
        client = FakeClient(
            [_candidate(950, surname="SOMEONEELSE"), _candidate(931, dob="1979-01-01"), _candidate(912)],
            {912: _document()})
        result = self._run(client)
        self.assertEqual(result.report.source_report_id, 912)
        self.assertEqual([c for c in client.calls if c[0] == "document"], [("document", 912, REF)])

    def test_first_passing_candidate_in_query_order_wins(self):
        # The query orders by DateCreated DESC, ID DESC; ties are already broken there.
        same_time = datetime(2026, 10, 1, 9, 0)
        client = FakeClient([_candidate(960, created=same_time), _candidate(955, created=same_time)],
                            {960: _document(), 955: _document()})
        self.assertEqual(self._run(client).report.source_report_id, 960)

    def test_no_candidates(self):
        client = FakeClient([])
        result = self._run(client)
        self.assertEqual((result.report, result.reason), (None, "no_candidates"))
        self.assertEqual(client.calls, [("candidates", REF)])
        self.assertFalse(CreditReport.objects.exists())

    def test_no_candidate_passes_identity(self):
        client = FakeClient([_candidate(950, surname="OTHER"), _candidate(940, second=True)])
        result = self._run(client)
        self.assertEqual((result.report, result.reason), (None, "no_identity_match"))
        self.assertEqual(client.calls, [("candidates", REF)])
        self.assertFalse(CreditReport.objects.exists())

    # -- Experian failures --------------------------------------------------

    def test_experian_unavailable(self):
        client = FakeClient(session_error=ExperianConnectionError("Experian database connection failed"))
        self.assertEqual(self._run(client), service.ExperianImportResult(None, "experian_unavailable"))
        self.assertFalse(CreditReport.objects.exists())

    def test_query_timeout(self):
        client = FakeClient(ExperianConnectionError("Experian database query failed: OperationalError: timed out"))
        self.assertEqual(self._run(client).reason, "experian_unavailable")
        self.assertFalse(CreditReport.objects.exists())

    def test_malformed_json(self):
        client = FakeClient([_candidate(912)], {912: ExperianDataError("Experian search 912 has malformed JsonData")})
        self.assertEqual(self._run(client).reason, "experian_data_error")
        self.assertFalse(CreditReport.objects.exists())

    def test_document_that_is_not_an_experian_response(self):
        client = FakeClient([_candidate(912)], {912: {"NotResponse": {}}})
        self.assertEqual(self._run(client).reason, "experian_data_error")
        self.assertFalse(CreditReport.objects.exists())

    def test_programming_errors_are_not_swallowed(self):
        with self.assertRaises(TypeError):
            self._run(FakeClient(TypeError("bug")))
        with patch.object(service, "map_search_to_extracted_data", side_effect=KeyError("bug")):
            with self.assertRaises(KeyError):
                self._run(FakeClient([_candidate(912)], {912: _document()}))

    # -- idempotency --------------------------------------------------------

    def test_repeated_calls_import_once(self):
        first = self._run(FakeClient([_candidate(912)], {912: _document()}))
        client = FakeClient([_candidate(912)], {912: _document()})
        second = self._run(client)
        self.assertEqual((first.reason, second.reason), ("imported", "already_imported"))
        self.assertEqual(second.report, first.report)
        # The stored search's identity is checked again and newer searches are
        # looked for, but the stored document is not re-fetched.
        self.assertEqual(client.calls, [("stored", REF), ("candidates", REF)])
        self.assertEqual(CreditReport.objects.filter(source="experian_db").count(), 1)

    def test_repeat_after_an_empty_import_does_not_refetch(self):
        document = _document()
        document["Response"]["FullConsumerData"]["ConsumerData"]["CAIS"] = []
        first = self._run(FakeClient([_candidate(912)], {912: document}))
        client = FakeClient([_candidate(912)], {912: document})
        second = self._run(client)
        self.assertEqual(second.reason, "already_imported")
        self.assertEqual(second.report, first.report)
        self.assertEqual(client.calls, [("stored", REF), ("candidates", REF)])
        self.assertEqual(CreditReport.objects.filter(source="experian_db").count(), 1)

    def test_concurrent_import_of_the_same_search(self):
        document = _document()
        real_map = service.map_search_to_extracted_data

        def other_request_wins(doc, tables):
            extracted = real_map(doc, tables)
            CreditReport.objects.create(aryza_reference=REF, source="experian_db", source_report_id=912,
                                        agency="Experian", extraction_status="extracted", extracted_data=extracted)
            return extracted

        with patch.object(service, "map_search_to_extracted_data", side_effect=other_request_wins):
            result = self._run(FakeClient([_candidate(912)], {912: document}))
        self.assertEqual((result.reason, result.created), ("already_imported", False))
        self.assertEqual(CreditReport.objects.filter(source="experian_db").count(), 1)
        self.assertEqual(result.report.source_report_id, 912)

    # -- logging ------------------------------------------------------------

    def test_logs_hold_no_personal_or_credit_data(self):
        records = []

        class Capture(logging.Handler):
            def emit(self, record):
                records.append(record.getMessage())

        handler = Capture(level=logging.DEBUG)
        debt_app_logger = logging.getLogger("debt_app")
        previous_level = debt_app_logger.level
        debt_app_logger.addHandler(handler)
        debt_app_logger.setLevel(logging.DEBUG)
        try:
            self._run(FakeClient([_candidate(950, surname="OTHERPERSON"), _candidate(912)],
                                 {912: _document(_detail(AccountNumber=ACCOUNT_NUMBER, AccountStatus="Q"))}))
            CreditReport.objects.all().delete()
            self._run(FakeClient([_candidate(950, surname="OTHERPERSON")]))
            self._run(FakeClient([_candidate(912)], {912: ExperianDataError("bad")}))
            self._run(FakeClient(session_error=ExperianConnectionError("down")))
        finally:
            debt_app_logger.removeHandler(handler)
            debt_app_logger.setLevel(previous_level)

        self.assertTrue(records)
        text = "\n".join(records).lower()
        for sensitive in ("zephyrina", "quillfeather", "otherperson", "1980", "acct-998877", "998877",
                          "halifax", "high street", "ls1 1aa", "response", "£"):
            self.assertNotIn(sensitive, text)
        self.assertIn("reason=imported", text)
        self.assertIn("reason=no_identity_match", text)
        self.assertIn("rejected=surname_mismatch:1", text)


# ---------------------------------------------------------------------------
# Through the real read layer (pymssql mocked): one connection per import
# ---------------------------------------------------------------------------

@override_settings(EXPERIAN_AUTO_CREDIT_REPORT=True)
class RealReadLayerTests(TestCase):
    def setUp(self):
        experian_db._code_tables_cache = None
        self.addCleanup(setattr, experian_db, "_code_tables_cache", None)

    @patch("debt_app.integrations.experian_db.pymssql.connect")
    def test_one_connection_serves_candidates_code_tables_and_document(self, connect):
        cursor = MagicMock()
        cursor.fetchall.side_effect = [
            [(950, datetime(2026, 10, 2), 1, 1, "OTHER", "PERSON", "1975-01-01", None),
             (912, datetime(2026, 10, 1), 1, 1, "ZEPHYRINA", "QUILLFEATHER", "1980-07-15T00:00:00", None)],
            list(ACCOUNT_TYPES.items()),
            list(PUBLIC_INFO_TYPES.items()),
            [(json.dumps(_document()),)],
        ]
        connection = MagicMock()
        connection.cursor.return_value.__enter__.return_value = cursor
        connect.return_value = connection
        config = {"HOST": "h", "PORT": "1", "NAME": "n", "USER": "u", "PASSWORD": "p"}
        result = ensure_experian_credit_report(REF, _case(), client=experian_db.ExperianDBClient(config))
        self.assertEqual((result.reason, result.report.source_report_id), ("imported", 912))
        connect.assert_called_once()
        connection.close.assert_called_once()
        executed = [c.args for c in cursor.execute.call_args_list]
        self.assertEqual(executed, [
            (experian_db.CANDIDATE_SEARCHES_SQL, (REF, REF, (-1,))),
            (experian_db.ACCOUNT_TYPE_CODES_SQL, ()),
            (experian_db.PUBLIC_INFO_TYPE_CODES_SQL, ()),
            (experian_db.SEARCH_DOCUMENT_SQL, (912, REF)),
        ])
