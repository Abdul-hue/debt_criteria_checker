"""
The CAT response with Experian reports, end to end:

    Experian search -> import -> active-report selection -> assessment -> response

Each scenario runs the public POST /api/v1/criteria/assess/ against a fake
Experian holding a fixed set of searches, and checks the response reflects the
ACTIVE report (newest matched search, unless a newer PDF), the stored history,
and which searches had their identity fields or full document read.

Set EXPERIAN_RESPONSE_DUMP=<path> to write every scenario's stable response
to a JSON file (used to compare the response before/after a change).
"""
import json
import os
from contextlib import contextmanager
from datetime import date, datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from debt_app.integrations.experian_db import CandidateSearch, ExperianDataError
from debt_app.models import CreditorCriteria, CreditReport
from debt_app.services import experian_credit_report as service
from debt_app.tests.test_experian_assessment_wiring import REF, URL, _case, _is_cr_only, _positions
from debt_app.tests.test_experian_mapper import CODE_TABLES, _detail, _doc
from debt_app.views import criteria_views

LONDON = ZoneInfo("Europe/London")
_VOLATILE = {"evaluated_at", "decision_id"}
DUMP_PATH = os.environ.get("EXPERIAN_RESPONSE_DUMP")
_DUMP = {}


class _FixedDate(date):
    @classmethod
    def today(cls):
        return cls(2026, 10, 26)


def _stable(body):
    return json.loads(json.dumps({k: v for k, v in body.items() if k not in _VOLATILE}, sort_keys=True))


def _document(name, pounds, extra=()):
    details = [_detail(SupplyCompanyName=name, AccountType="02", AccountNumber=f"ACC-{name[:5]}",
                       AccountBalances=[{"AccountBalance": pounds, "Status": "0"}],
                       LastUpdatedDate="2026-09-30", CAISAccStartDate="2021-09-16")]
    details += [_detail(**e) for e in extra]
    return _doc(details)


MATCH = dict(forename="ZEPHYRINA", surname="QUILLFEATHER", dob="1980-07-15")


class FakeExperian:
    """A Credit_Searches table in memory. Records what each session read."""

    def __init__(self, searches):
        # searches: dicts with id, created (naive UK time), forename, surname, dob,
        # second (bool), document (dict) or None for malformed JsonData.
        self.searches = searches
        self.sessions = 0
        self.identity_reads = []     # search ids whose identity fields were read as candidates
        self.stored_reads = []       # stored (imported) search ids re-checked against the client
        self.document_reads = []     # search ids whose full JsonData was read

    def _ordered(self):
        return sorted(self.searches, key=lambda s: (s["created"], s["id"]), reverse=True)

    @contextmanager
    def session(self):
        self.sessions += 1
        yield _FakeSession(self)


class _FakeSession:
    def __init__(self, store):
        self.store = store

    def find_candidate_searches(self, crm_ref, imported_ids=None):
        rows = self.store._ordered()
        newest_imported = None
        if imported_ids:
            known = [s for s in rows if s["id"] in imported_ids]
            newest_imported = known[0] if known else None
        out = []
        for s in rows:
            newer = newest_imported is None or (s["created"], s["id"]) > (newest_imported["created"], newest_imported["id"])
            valid = s["document"] is not None
            if imported_ids is None and not valid:
                continue                                   # the pre-optimisation query filtered ISJSON in WHERE
            if newer:
                self.store.identity_reads.append(s["id"])
            out.append(_candidate(s, newer, valid))
        return out

    def read_stored_searches(self, crm_ref, search_ids):
        ids = {i for i in search_ids if i is not None}
        rows = [s for s in self.store._ordered() if s["id"] in ids]
        self.store.stored_reads.extend(s["id"] for s in rows)
        return [_candidate(s, True, s["document"] is not None) for s in rows]

    def load_code_tables(self, refresh=False):
        return CODE_TABLES

    def fetch_search_document(self, search_id, crm_ref):
        self.store.document_reads.append(search_id)
        doc = next(s["document"] for s in self.store.searches if s["id"] == search_id)
        if doc is None:
            raise ExperianDataError(f"Experian search {search_id} has malformed JsonData")
        return doc


def _candidate(s, identity_loaded, valid):
    fields = dict(search_id=s["id"], date_created=s["created"],
                  forename=s["forename"] if identity_loaded and valid else None,
                  surname=s["surname"] if identity_loaded and valid else None,
                  date_of_birth=s["dob"] if identity_loaded and valid else None,
                  has_second_applicant=bool(s.get("second")) if identity_loaded and valid else False)
    extra = {}
    if "identity_loaded" in CandidateSearch.__dataclass_fields__:
        extra = dict(identity_loaded=identity_loaded, is_json=valid if identity_loaded else None)
    return CandidateSearch(**fields, **extra)


def _search(search_id, created, document, identity=MATCH, second=False):
    return dict(id=search_id, created=created, document=document, second=second, **identity)


@override_settings(EXPERIAN_AUTO_CREDIT_REPORT=True)
class ResponseContractTests(TestCase):

    @classmethod
    def tearDownClass(cls):
        if DUMP_PATH:
            with open(DUMP_PATH, "w", encoding="utf-8") as fh:
                json.dump(_DUMP, fh, indent=2, sort_keys=True, default=str)
        super().tearDownClass()

    def setUp(self):
        for name in ("Alpha Bank", "Beta Loans"):
            CreditorCriteria.objects.create(creditor_name=name, representative="NONE", status="ACCEPT", is_active=True)
        for target in ("debt_app.engine.criteria.date", "debt_app.integrations.credit_report.date"):
            p = patch(target, _FixedDate)
            p.start()
            self.addCleanup(p.stop)

    def _assess(self, store, scenario, body=None):
        with patch.object(service, "ExperianDBClient", return_value=store), \
                patch("debt_app.views.criteria_views.fetch_case_by_reference", return_value=_case()):
            resp = APIClient().post(URL, data={"aryza_reference": REF, **(body or {})}, format="json")
        self.assertEqual(resp.status_code, 200, resp.content[:300])
        body = resp.json()
        rows = list(CreditReport.objects.filter(aryza_reference=REF).order_by("id").values_list(
            "source", "source_report_id", "extraction_status"))
        _DUMP.setdefault(scenario, []).append({"status": resp.status_code, "body": _stable(body), "rows": rows})
        return body

    # -- the sequence end to end --------------------------------------------

    def test_fresh_import_reaches_the_response(self):
        store = FakeExperian([_search(912, datetime(2026, 10, 1, 9, 30), _document("ALPHA BANK PLC", "0006000"))])
        body = self._assess(store, "fresh_import")
        alpha = _positions(body)["Alpha Bank"]
        self.assertEqual((alpha["cr_raw_name"], alpha["cr_balance"]), ("ALPHA BANK PLC", 600000))
        self.assertEqual(store.document_reads, [912])
        self.assertEqual(CreditReport.objects.get().source_report_id, 912)

    def test_newer_matched_search_replaces_the_active_report_in_the_response(self):
        store = FakeExperian([_search(912, datetime(2026, 9, 1, 9), _document("OLD LENDER ALPHA BANK", "0006000"))])
        first = self._assess(store, "newer_search")
        self.assertEqual(_positions(first)["Alpha Bank"]["cr_raw_name"], "OLD LENDER ALPHA BANK")
        store.searches.append(_search(950, datetime(2026, 10, 20, 9), _document("NEW ALPHA BANK PLC", "0005900")))
        store.identity_reads.clear()
        second = self._assess(store, "newer_search")
        self.assertEqual(store.identity_reads, [950])      # the stored search 912 is not re-read
        alpha = _positions(second)["Alpha Bank"]
        self.assertEqual((alpha["cr_raw_name"], alpha["cr_balance"]), ("NEW ALPHA BANK PLC", 590000))
        self.assertEqual(store.document_reads, [912, 950])
        self.assertEqual(list(CreditReport.objects.order_by("id").values_list("source_report_id", flat=True)), [912, 950])
        self.assertNotIn("OLD LENDER ALPHA BANK", json.dumps(second))

    def test_unmatched_newer_search_leaves_the_response_unchanged(self):
        store = FakeExperian([_search(912, datetime(2026, 9, 1, 9), _document("ALPHA BANK PLC", "0006000"))])
        first = self._assess(store, "unmatched_newer")
        for i, wrong in enumerate((dict(MATCH, surname="SOMEONEELSE"), dict(MATCH, dob="1979-01-01"))):
            store.searches.append(_search(950 + i, datetime(2026, 10, 20 + i, 9), _document("WRONG PERSON", "0001000"),
                                          identity=wrong))
        store.searches.append(_search(960, datetime(2026, 10, 25, 9), _document("SECOND APPLICANT", "0001000"),
                                      second=True))
        store.searches.append(_search(961, datetime(2026, 10, 25, 10), None))     # malformed JsonData
        store.identity_reads.clear()
        second = self._assess(store, "unmatched_newer")
        self.assertEqual(_stable(second), _stable(first))
        self.assertEqual(store.document_reads, [912])
        self.assertEqual(CreditReport.objects.count(), 1)
        # Only the newer searches were read; the stored one was not.
        self.assertEqual(sorted(store.identity_reads), [950, 951, 960, 961])

    def test_newer_search_with_incomplete_identity_is_skipped(self):
        store = FakeExperian([_search(912, datetime(2026, 9, 1, 9), _document("ALPHA BANK PLC", "0006000"))])
        first = self._assess(store, "incomplete_newer")
        for i, incomplete in enumerate((dict(MATCH, dob=None), dict(MATCH, surname=None), dict(MATCH, forename=""))):
            store.searches.append(_search(970 + i, datetime(2026, 10, 20 + i, 9), _document("NO IDENTITY", "0001000"),
                                          identity=incomplete))
        second = self._assess(store, "incomplete_newer")
        self.assertEqual(_stable(second), _stable(first))
        self.assertEqual(store.document_reads, [912])
        self.assertEqual(CreditReport.objects.count(), 1)

    def test_no_identity_or_document_is_read_when_nothing_is_newer(self):
        store = FakeExperian([
            _search(901, datetime(2026, 8, 1, 9), _document("T1 ALPHA BANK", "0006100")),
            _search(903, datetime(2026, 10, 1, 9), _document("T3 ALPHA BANK", "0006000")),
        ])
        self._assess(store, "nothing_newer")
        store.identity_reads.clear()
        store.document_reads.clear()
        self._assess(store, "nothing_newer")
        self.assertEqual((store.identity_reads, store.document_reads), ([], []))
        self.assertEqual(store.sessions, 2)

    def test_repeat_assessment_reads_no_document_and_returns_the_same_response(self):
        store = FakeExperian([_search(912, datetime(2026, 10, 1, 9), _document("ALPHA BANK PLC", "0006000"))])
        first = self._assess(store, "repeat")
        store.identity_reads.clear()
        second = self._assess(store, "repeat")
        self.assertEqual(_stable(second), _stable(first))
        self.assertEqual(store.document_reads, [912])
        self.assertEqual(store.identity_reads, [])
        self.assertEqual(CreditReport.objects.count(), 1)

    def test_multiple_searches_newest_matched_wins_regardless_of_import_order(self):
        store = FakeExperian([
            _search(901, datetime(2026, 8, 1, 9), _document("T1 ALPHA BANK", "0006100")),
            _search(902, datetime(2026, 9, 1, 9), _document("T2 ALPHA BANK", "0006050")),
            _search(903, datetime(2026, 10, 1, 9), _document("T3 ALPHA BANK", "0006000")),
        ])
        body = self._assess(store, "multiple")
        self.assertEqual(_positions(body)["Alpha Bank"]["cr_raw_name"], "T3 ALPHA BANK")
        self.assertEqual(store.document_reads, [903])

    def test_pdf_uploaded_after_the_search_stays_active_in_the_response(self):
        store = FakeExperian([_search(912, datetime(2026, 9, 1, 9), _document("ALPHA BANK PLC", "0006000"))])
        self._assess(store, "pdf_newer")
        CreditReport.objects.create(
            aryza_reference=REF, uploaded_file="credit_reports/2026/10/r.pdf", agency="Experian",
            extraction_status="extracted", extracted_data={"agency": "Experian", "accounts": [
                {"raw_name": "ALPHA BANK (PDF)", "matched_creditor": "Alpha Bank", "type_code": "PL",
                 "current_balance": 600000, "account_status": "Active", "start_date": "2022-01-01"}],
                "mortgage_accounts": [], "other_accounts": []})
        body = self._assess(store, "pdf_newer")
        self.assertEqual(_positions(body)["Alpha Bank"]["cr_raw_name"], "ALPHA BANK (PDF)")

    def test_response_schema_and_cr_fields(self):
        store = FakeExperian([_search(912, datetime(2026, 10, 1, 9), _document(
            "ALPHA BANK PLC", "0006000",
            extra=[dict(SupplyCompanyName="UNDECLARED LENDER LTD", AccountType="05",
                        AccountBalances=[{"AccountBalance": "0000750", "Status": "0"}])]))])
        body = self._assess(store, "schema")
        for key in ("success", "client_name", "aryza_reference", "disposable_income", "total_unsecured_debt",
                    "overall", "overall_status", "recommended_solution", "hard_blocks", "flags", "creditor_positions"):
            self.assertIn(key, body)
        alpha = _positions(body)["Alpha Bank"]
        for key in ("cr_raw_name", "cr_balance", "cr_account_status", "cr_start_date", "cr_missed_payments_3m", "type_code"):
            self.assertIn(key, alpha)
        cr_only = [p for p in body["creditor_positions"] if _is_cr_only(p)]
        self.assertEqual([(p["cr_raw_name"], p["cr_balance"]) for p in cr_only], [("UNDECLARED LENDER LTD", 75000)])
        names = [p.get("cr_raw_name") for p in body["creditor_positions"] if p.get("cr_raw_name")]
        self.assertEqual(len(names), len(set(names)))     # no duplicated debts
