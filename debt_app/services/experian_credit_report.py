"""
services/experian_credit_report.py

Imports a case's newest Experian credit search that is about the same person
as the Aryza client, unless that search is already stored.

    ensure_experian_credit_report(aryza_reference, case_data_obj, credit_report_id=None)

Newest matching search wins (D5): each imported search is its own
CreditReport row whose created_at is the time the search was run, so the
usual "newest usable report" selection makes the newest matched search the
active report. Older imports are kept as history; a PDF uploaded after a
search is still newer and stays active. The import time is in updated_at.

"Matching" is always against the client's CURRENT Aryza identity: every
stored import is checked again on each run, and one whose person no longer
matches (a name or date of birth changed in Aryza) is marked
identity_mismatch, so no report selection uses it, and gets its status back
if it matches again.

Never raises for an Experian failure (unreachable, timeout, unusable data):
those end as "no report imported" with a reason code. Any other exception is
a bug and propagates.

Logs reason codes, case references and Experian search IDs only -- never
names, dates of birth, account data or the search document.
"""

import logging
import re
import unicodedata
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from debt_app.aryza_client import aryza_dob_to_date
from debt_app.integrations.experian_db import (
    CandidateSearch,
    ExperianDataError,
    ExperianDBClient,
    ExperianError,
    RequestScopedClient,
)
from debt_app.integrations.experian_mapper import map_search_to_extracted_data
from debt_app.models import (
    CREDIT_REPORT_SOURCE_EXPERIAN_DB,
    EXTRACTION_STATUS_IDENTITY_MISMATCH,
    CreditReport,
)

logger = logging.getLogger(__name__)

# Credit_Searches.DateCreated is UK wall-clock time (it matches Experian's own
# SearchDate/SearchTime in both BST and GMT).
_EXPERIAN_SEARCH_TZ = ZoneInfo("Europe/London")

# Outcome reason codes.
FLAG_DISABLED = "flag_disabled"
NO_REFERENCE = "no_reference"
PINNED_REPORT = "pinned_report"
IDENTITY_UNAVAILABLE = "identity_unavailable"
NO_CANDIDATES = "no_candidates"
NO_IDENTITY_MATCH = "no_identity_match"
ALREADY_IMPORTED = "already_imported"
IMPORTED = "imported"
EXPERIAN_UNAVAILABLE = "experian_unavailable"
EXPERIAN_DATA_ERROR = "experian_data_error"

# A stored import re-checked against the client's current identity.
IMPORT_NO_LONGER_MATCHES = "import_no_longer_matches"
IMPORT_MATCHES_AGAIN = "import_matches_again"

# Identity-check reason codes.
MATCH = "match"
SECOND_APPLICANT = "second_applicant"
EXPERIAN_NAME_MISSING = "experian_name_missing"
EXPERIAN_DOB_MISSING = "experian_dob_missing"
FORENAME_MISMATCH = "forename_mismatch"
SURNAME_MISMATCH = "surname_mismatch"
DOB_MISMATCH = "dob_mismatch"


@dataclass(frozen=True)
class ExperianImportResult:
    """report is the imported (or previously imported) Experian report, else None."""
    report: CreditReport | None
    reason: str
    created: bool = False


def _name_tokens(value) -> list[str]:
    """Accents removed, lower case, anything but letters is a separator."""
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z]+", " ", text.lower()).split()


def _iso_date(value) -> date | None:
    try:
        return datetime.strptime(str(value or "")[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


@dataclass(frozen=True)
class AryzaIdentity:
    forename: str            # first word of the Aryza first name, normalised
    surname: str             # whole Aryza last name, normalised, separators removed
    date_of_birth: date | None

    @classmethod
    def from_case(cls, case_data_obj) -> "AryzaIdentity":
        first = _name_tokens(getattr(case_data_obj, "first_name", None))
        last = _name_tokens(getattr(case_data_obj, "last_name", None))
        return cls(
            forename=first[0] if first else "",
            surname="".join(last),
            date_of_birth=aryza_dob_to_date(getattr(case_data_obj, "dob_timestamp", None)),
        )

    @property
    def complete(self) -> bool:
        return bool(self.forename and self.surname and self.date_of_birth)

    # Never show personal data if this object is ever logged.
    def __repr__(self):
        return f"AryzaIdentity(complete={self.complete})"


def identity_matches(identity: AryzaIdentity, candidate: CandidateSearch) -> tuple[bool, str]:
    """Is this search about the Aryza client? Returns (passed, reason code).

    All three must hold: the first word of the forename is equal, the whole
    surname is equal ignoring spaces / hyphens / apostrophes, and the date of
    birth is the same day. Case and accents never matter. A search with a
    second applicant is never used.
    """
    if candidate.has_second_applicant:
        return False, SECOND_APPLICANT
    forename = _name_tokens(candidate.forename)
    surname = "".join(_name_tokens(candidate.surname))
    if not forename or not surname:
        return False, EXPERIAN_NAME_MISSING
    candidate_dob = _iso_date(candidate.date_of_birth)
    if candidate_dob is None:
        return False, EXPERIAN_DOB_MISSING
    if forename[0] != identity.forename:
        return False, FORENAME_MISMATCH
    if surname != identity.surname:
        return False, SURNAME_MISMATCH
    if candidate_dob != identity.date_of_birth:
        return False, DOB_MISMATCH
    return True, MATCH


def _log(reference, reason, **details):
    extra = "".join(f" {key}={value}" for key, value in details.items())
    logger.info("[EXPERIAN IMPORT] ref=%s reason=%s%s", reference, reason, extra)


def _search_time(search: CandidateSearch):
    """The moment the search was run (aware), or None if unknown."""
    value = search.date_created
    if not isinstance(value, datetime):
        return None
    return value if timezone.is_aware(value) else timezone.make_aware(value, _EXPERIAN_SEARCH_TZ)


def _imported_status(extracted) -> str:
    """As the PDF upload does for a recognised bureau with nothing in it."""
    found_anything = bool(extracted.get("accounts") or extracted.get("mortgage_accounts")
                          or extracted.get("other_accounts"))
    return "extracted" if found_anything else "extracted_empty"


def _recheck_imports(reference, identity: AryzaIdentity, imported: dict, stored: list[CandidateSearch]) -> set:
    """Check the stored imports again against the client's current identity.

    imported: source_report_id -> CreditReport; stored: those searches as
    Experian holds them now. One that no longer matches is marked
    identity_mismatch; one that matches again gets its status back. A search
    Experian no longer holds is left as it is. Returns the IDs that match.
    """
    still_matching = set()
    for search in stored:
        report = imported.get(search.search_id)
        if report is None:
            continue
        passed, why = identity_matches(identity, search)
        if passed:
            still_matching.add(search.search_id)
            wanted = _imported_status(report.extracted_data or {})
        else:
            wanted = EXTRACTION_STATUS_IDENTITY_MISMATCH
        if report.extraction_status != wanted:
            # update(), not save(): updated_at keeps the import time.
            CreditReport.objects.filter(pk=report.pk).update(extraction_status=wanted)
            _log(reference, IMPORT_MATCHES_AGAIN if passed else IMPORT_NO_LONGER_MATCHES,
                 search_id=search.search_id, check=why)
    return still_matching


def _save(reference, search: CandidateSearch, extracted) -> tuple[CreditReport, bool]:
    """Create the Experian report row, or return the one a concurrent call made."""
    try:
        with transaction.atomic():
            report = CreditReport.objects.create(
                aryza_reference=reference,
                source=CREDIT_REPORT_SOURCE_EXPERIAN_DB,
                source_report_id=search.search_id,
                agency=extracted["agency"],
                client_name_on_report=extracted["client_name"],
                client_address_on_report=extracted["client_address"],
                extraction_status=_imported_status(extracted),
                extracted_data=extracted,
            )
            # created_at = when the search was run, so report selection (newest
            # usable first) ranks it by the age of its data, not the import.
            # auto_now_add ignores a value passed to create(), hence update().
            searched_at = _search_time(search)
            if searched_at is not None:
                CreditReport.objects.filter(pk=report.pk).update(created_at=searched_at)
                report.refresh_from_db()
        return report, True
    except IntegrityError:
        # uniq_experian_credit_report_per_search: another call imported it first.
        return CreditReport.objects.get(
            aryza_reference=reference, source=CREDIT_REPORT_SOURCE_EXPERIAN_DB, source_report_id=search.search_id,
        ), False


@contextmanager
def experian_request_scope():
    """An Experian client for every import in ONE request: they share one
    connection, closed when the block ends. Pass it as `client`. Never keep it
    beyond the request (see RequestScopedClient)."""
    scoped = RequestScopedClient(ExperianDBClient())
    try:
        yield scoped
    finally:
        scoped.close()


def ensure_experian_credit_report(aryza_reference, case_data_obj, credit_report_id=None,
                                  client: ExperianDBClient | None = None) -> ExperianImportResult:
    """Import the case's newest identity-matched Experian search unless it is already stored.

    Checked on every assessment (not only when the case has no report), so a
    newer search replaces the active report as soon as it exists. Does nothing
    (and never touches Experian) when the feature flag is off, a
    credit_report_id is pinned, or the Aryza client has no complete name and
    date of birth to match on.
    """
    if not settings.EXPERIAN_AUTO_CREDIT_REPORT:
        return ExperianImportResult(None, FLAG_DISABLED)
    reference = str(aryza_reference or "").strip()
    if not reference:
        return ExperianImportResult(None, NO_REFERENCE)
    if credit_report_id:
        _log(reference, PINNED_REPORT)
        return ExperianImportResult(None, PINNED_REPORT)
    identity = AryzaIdentity.from_case(case_data_obj)
    if not identity.complete:
        _log(reference, IDENTITY_UNAVAILABLE)
        return ExperianImportResult(None, IDENTITY_UNAVAILABLE)

    imported = {report.source_report_id: report for report in CreditReport.objects.filter(
        aryza_reference=reference, source=CREDIT_REPORT_SOURCE_EXPERIAN_DB,
    )}

    client = client or ExperianDBClient()
    try:
        with client.session() as session:
            # Only stored searches that still match the client's current
            # identity count as imported, so a newer -- or, after an identity
            # change, an older -- matching search is not hidden behind one
            # that no longer matches.
            matching_ids = _recheck_imports(
                reference, identity, imported, session.read_stored_searches(reference, imported))
            # Searches with malformed JsonData are not candidates (as when the
            # query filtered them out); validity is only known where the
            # identity was read.
            candidates = [
                c for c in session.find_candidate_searches(reference, imported_ids=matching_ids)
                if not (c.identity_loaded and c.is_json is False)
            ]
            if not candidates:
                _log(reference, NO_CANDIDATES)
                return ExperianImportResult(None, NO_CANDIDATES)

            # Newest first. The first search that matches the client wins;
            # reaching the newest still-matching import first means no newer
            # one matched, and anything older can never be active.
            chosen, rejected = None, {}
            for candidate in candidates:
                if candidate.search_id in matching_ids or not candidate.identity_loaded:
                    existing = CreditReport.objects.filter(
                        aryza_reference=reference, source=CREDIT_REPORT_SOURCE_EXPERIAN_DB,
                        source_report_id=candidate.search_id,
                    ).first()
                    if existing is not None and candidate.search_id in matching_ids:
                        _log(reference, ALREADY_IMPORTED, search_id=candidate.search_id)
                        return ExperianImportResult(existing, ALREADY_IMPORTED)
                    continue
                passed, why = identity_matches(identity, candidate)
                if passed:
                    chosen = candidate
                    break
                rejected[why] = rejected.get(why, 0) + 1
            if chosen is None:
                _log(reference, NO_IDENTITY_MATCH, candidates=len(candidates),
                     rejected=",".join(f"{k}:{v}" for k, v in sorted(rejected.items())))
                return ExperianImportResult(None, NO_IDENTITY_MATCH)

            code_tables = session.load_code_tables()
            document = session.fetch_search_document(chosen.search_id, reference)
    except ExperianError as exc:
        reason = EXPERIAN_DATA_ERROR if isinstance(exc, ExperianDataError) else EXPERIAN_UNAVAILABLE
        _log(reference, reason, error=type(exc).__name__)
        return ExperianImportResult(None, reason)

    try:
        extracted = map_search_to_extracted_data(document, code_tables)
    except ExperianError as exc:
        _log(reference, EXPERIAN_DATA_ERROR, search_id=chosen.search_id, error=type(exc).__name__)
        return ExperianImportResult(None, EXPERIAN_DATA_ERROR)

    report, created = _save(reference, chosen, extracted)
    reason = IMPORTED if created else ALREADY_IMPORTED
    _log(reference, reason, search_id=chosen.search_id, status=report.extraction_status,
         skipped_newer=candidates.index(chosen))
    return ExperianImportResult(report, reason, created)
