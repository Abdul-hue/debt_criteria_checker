"""
integrations/experian_db.py

READ-ONLY client for the Experian credit-search database (SQL Server).

Connects directly with pymssql using settings.EXPERIAN_DB; it is not a Django
DATABASES entry, so migrations, the test runner and the trial router never
reach it. Driver failures surface as ExperianConnectionError and unusable
search documents as ExperianDataError, both ExperianError; their messages
never contain the configured user or password. Anything else -- a bug in this
code -- is deliberately not caught.

Tables read (all SELECT, all parameterised):
  dbo.Credit_Searches        one row per search; CRM_Ref is the Aryza case
                             reference (== Aryza client.id)
  dbo.experian_codes         CAIS account type code -> description
  dbo.PublicInfo_Type_Codes  public-record type code -> group
"""

import json
import logging
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, field
from datetime import datetime

import pymssql
from pymssql import _mssql
from django.conf import settings

logger = logging.getLogger(__name__)

_REQUIRED_SETTINGS = ("HOST", "NAME", "USER", "PASSWORD")

# Failures raised by the driver itself: connection, login, timeout, SQL error.
_DRIVER_ERRORS = (pymssql.Error, _mssql.MSSQLException)

# All of the case's searches, in one round trip. There is no row limit: other
# people's searches filed under the case's reference (real references hold up
# to ~110) must never push the client's own newer search out of view. The
# candidate list itself reads only ID and DateCreated (no JsonData). The
# identity fields -- which mean reading JsonData -- are read only for searches
# NEWER than the newest of the given imported searches (ordered by Experian's
# DateCreated, then ID): an older search can never become the active report,
# so it is not read at all. The full document is fetched separately, only for
# the search that is imported (SEARCH_DOCUMENT_SQL).
# JSON_VALUE sits behind ISJSON in a CASE because JSON_VALUE raises on
# malformed JSON. Params: crm_ref, crm_ref, imported search ids (a tuple;
# (-1,) when there are none, as SQL has no empty IN list).
CANDIDATE_SEARCHES_SQL = """
WITH candidates AS (
    SELECT ID, DateCreated
    FROM dbo.Credit_Searches
    WHERE CRM_Ref = %s
),
newest_imported AS (
    SELECT TOP (1) ID, DateCreated
    FROM dbo.Credit_Searches
    WHERE CRM_Ref = %s AND ID IN %s
    ORDER BY DateCreated DESC, ID DESC
)
SELECT
    c.ID,
    c.DateCreated,
    CASE WHEN i.ID IS NULL OR c.DateCreated > i.DateCreated
              OR (c.DateCreated = i.DateCreated AND c.ID > i.ID) THEN 1 ELSE 0 END,
    x.is_json,
    x.forename,
    x.surname,
    x.date_of_birth,
    x.second_applicant
FROM candidates c
LEFT JOIN newest_imported i ON 1 = 1
OUTER APPLY (
    SELECT
        ISJSON(s.JsonData) AS is_json,
        CASE WHEN ISJSON(s.JsonData) = 1 THEN JSON_VALUE(s.JsonData, '$.Response.Applicants[0].Person.Forename') END AS forename,
        CASE WHEN ISJSON(s.JsonData) = 1 THEN JSON_VALUE(s.JsonData, '$.Response.Applicants[0].Person.Surname') END AS surname,
        CASE WHEN ISJSON(s.JsonData) = 1 THEN JSON_VALUE(s.JsonData, '$.Response.Applicants[0].Person.DateOfBirth') END AS date_of_birth,
        CASE WHEN ISJSON(s.JsonData) = 1 THEN JSON_VALUE(s.JsonData, '$.Response.Applicants[1].ApplicantIdentifier') END AS second_applicant
    FROM dbo.Credit_Searches s
    WHERE s.ID = c.ID
      AND (i.ID IS NULL OR c.DateCreated > i.DateCreated OR (c.DateCreated = i.DateCreated AND c.ID > i.ID))
) x
ORDER BY c.DateCreated DESC, c.ID DESC
"""

# The identity fields of searches already imported for the case, so they can
# be checked again against the client's current Aryza identity. Looked up by
# ID (the primary key) and scoped to the case. Params: crm_ref, search ids.
STORED_SEARCHES_SQL = """
SELECT
    ID,
    DateCreated,
    ISJSON(JsonData),
    CASE WHEN ISJSON(JsonData) = 1 THEN JSON_VALUE(JsonData, '$.Response.Applicants[0].Person.Forename') END,
    CASE WHEN ISJSON(JsonData) = 1 THEN JSON_VALUE(JsonData, '$.Response.Applicants[0].Person.Surname') END,
    CASE WHEN ISJSON(JsonData) = 1 THEN JSON_VALUE(JsonData, '$.Response.Applicants[0].Person.DateOfBirth') END,
    CASE WHEN ISJSON(JsonData) = 1 THEN JSON_VALUE(JsonData, '$.Response.Applicants[1].ApplicantIdentifier') END
FROM dbo.Credit_Searches
WHERE CRM_Ref = %s AND ID IN %s
ORDER BY DateCreated DESC, ID DESC
"""

# CRM_Ref is repeated so a search ID can never return another case's document.
SEARCH_DOCUMENT_SQL = "SELECT JsonData FROM dbo.Credit_Searches WHERE ID = %s AND CRM_Ref = %s"

ACCOUNT_TYPE_CODES_SQL = "SELECT EXPERIAN_CODE, EXPERIAN_DESC FROM dbo.experian_codes"
PUBLIC_INFO_TYPE_CODES_SQL = "SELECT Code, Type FROM dbo.PublicInfo_Type_Codes"


class ExperianError(Exception):
    """Base for expected Experian integration failures."""


class ExperianConnectionError(ExperianError):
    """Experian database unconfigured, unreachable, or a query failed.

    The message never contains the configured user or password.
    """


class ExperianDataError(ExperianError):
    """A search document is missing, malformed, or not an Experian response."""


@dataclass(frozen=True)
class CandidateSearch:
    """One search for a case, with just the fields the identity check needs.

    identity_loaded is False for a search no newer than the newest one already
    imported: its identity fields were not read (they are None) and is_json is
    unknown (None). Otherwise is_json says whether its JsonData is valid JSON.

    Personal fields are kept out of repr() so a logged candidate never
    carries a name or date of birth.
    """
    search_id: int
    date_created: datetime
    forename: str | None = field(repr=False)
    surname: str | None = field(repr=False)
    date_of_birth: str | None = field(repr=False)
    has_second_applicant: bool
    identity_loaded: bool = True
    is_json: bool | None = True


@dataclass(frozen=True)
class ExperianCodeTables:
    """account_types: CAIS AccountType -> description (the category the
    rendered report prints). public_info_types: InformationType -> group
    (Judgement, Bankruptcy, IVA, ...)."""
    account_types: dict[str, str]
    public_info_types: dict[str, str]


# Reference data only (no personal data); loaded once per process.
_code_tables_cache: ExperianCodeTables | None = None


class ExperianSession:
    """One open connection; every query on it is read-only and parameterised."""

    def __init__(self, client: "ExperianDBClient", connection):
        self._client = client
        self._connection = connection

    def query(self, sql: str, params: tuple = ()) -> list[tuple]:
        """Run one read query and return all rows.

        Values must be passed in `params` (pymssql %s placeholders), never
        formatted into `sql`.
        """
        try:
            with self._connection.cursor() as cursor:
                cursor.execute(sql, params)
                return cursor.fetchall()
        except _DRIVER_ERRORS as exc:
            raise self._client._fail("query", exc) from None

    def find_candidate_searches(self, crm_ref: str, imported_ids=()) -> list[CandidateSearch]:
        """All of the case's searches, newest first.

        imported_ids: Credit_Searches IDs already stored for this case (that
        still match the client). Only searches newer than the newest of them
        have their identity read.
        """
        ref = str(crm_ref).strip()
        ids = tuple(sorted({int(i) for i in imported_ids if i is not None})) or (-1,)
        rows = self.query(CANDIDATE_SEARCHES_SQL, (ref, ref, ids))
        return [
            CandidateSearch(
                search_id=row[0],
                date_created=row[1],
                forename=row[4],
                surname=row[5],
                date_of_birth=row[6],
                has_second_applicant=row[7] is not None,
                identity_loaded=bool(row[2]),
                is_json=(row[3] == 1) if row[2] else None,
            )
            for row in rows
        ]

    def read_stored_searches(self, crm_ref: str, search_ids) -> list[CandidateSearch]:
        """These searches of `crm_ref`, newest first, with their identity read.

        An ID that is not (or is no longer) a search of `crm_ref` is left out.
        No query is run when there are no IDs.
        """
        ids = tuple(sorted({int(i) for i in search_ids if i is not None}))
        if not ids:
            return []
        rows = self.query(STORED_SEARCHES_SQL, (str(crm_ref).strip(), ids))
        return [
            CandidateSearch(
                search_id=row[0],
                date_created=row[1],
                forename=row[3],
                surname=row[4],
                date_of_birth=row[5],
                has_second_applicant=row[6] is not None,
                is_json=row[2] == 1,
            )
            for row in rows
        ]

    def fetch_search_document(self, search_id: int, crm_ref: str) -> dict:
        """The parsed JsonData of one search belonging to `crm_ref`.

        The document is returned to the caller only; it is never stored.
        """
        rows = self.query(SEARCH_DOCUMENT_SQL, (int(search_id), str(crm_ref).strip()))
        if not rows or rows[0][0] is None:
            raise ExperianDataError(f"Experian search {search_id} not found for this case")
        try:
            document = json.loads(rows[0][0])
        except (TypeError, ValueError):
            raise ExperianDataError(f"Experian search {search_id} has malformed JsonData") from None
        if not isinstance(document, dict) or not isinstance(document.get("Response"), dict):
            raise ExperianDataError(f"Experian search {search_id} has no Response object")
        return document

    def load_code_tables(self, refresh: bool = False) -> ExperianCodeTables:
        """Account-type and public-record code tables, cached per process."""
        global _code_tables_cache
        if _code_tables_cache is None or refresh:
            account_types = {
                str(code).strip(): str(desc).strip()
                for code, desc in self.query(ACCOUNT_TYPE_CODES_SQL)
                if code is not None and desc is not None
            }
            public_info_types = {
                str(code).strip(): str(group).strip()
                for code, group in self.query(PUBLIC_INFO_TYPE_CODES_SQL)
                if code is not None and group is not None
            }
            if not account_types or not public_info_types:
                raise ExperianDataError("Experian code tables are empty")
            _code_tables_cache = ExperianCodeTables(account_types, public_info_types)
        return _code_tables_cache


class ExperianDBClient:
    """Read-only access to the Experian SQL Server database."""

    def __init__(self, config=None):
        self.config = dict(config if config is not None else settings.EXPERIAN_DB)

    def _scrub(self, text: str) -> str:
        """Remove the configured credentials from a driver error message."""
        for key in ("PASSWORD", "USER"):
            secret = self.config.get(key)
            if secret:
                text = text.replace(str(secret), "<redacted>")
        return text

    def _fail(self, action: str, exc: Exception) -> ExperianConnectionError:
        message = self._scrub(f"Experian database {action} failed: {type(exc).__name__}: {exc}")
        logger.error(message)
        return ExperianConnectionError(message)

    def _connect(self):
        missing = [key for key in _REQUIRED_SETTINGS if not self.config.get(key)]
        if missing:
            message = f"Experian database is not configured (missing {', '.join(missing)})"
            logger.error(message)
            raise ExperianConnectionError(message)
        try:
            return pymssql.connect(
                server=self.config["HOST"],
                port=str(self.config.get("PORT") or "1433"),
                database=self.config["NAME"],
                user=self.config["USER"],
                password=self.config["PASSWORD"],
                login_timeout=self.config.get("CONNECT_TIMEOUT", 5),
                timeout=self.config.get("QUERY_TIMEOUT", 10),
                # Declares read-only intent (ApplicationIntent=ReadOnly); the
                # login itself must also be read-only.
                read_only=True,
                encryption="require",
            )
        except _DRIVER_ERRORS as exc:
            # `from None`: the driver exception is not chained, so a traceback
            # logged further up cannot reintroduce an unscrubbed message.
            raise self._fail("connection", exc) from None

    @contextmanager
    def session(self):
        """One connection for several queries; always closed on exit.

        Opening a connection costs about 2 s (TLS + login) against ~0.5 s per
        query, so a retrieval runs all its queries in one session.
        """
        connection = self._connect()
        try:
            yield ExperianSession(self, connection)
        finally:
            connection.close()

    def ping(self) -> bool:
        """Verify the database is reachable with a harmless `SELECT 1`.

        Returns True, or raises ExperianConnectionError.
        """
        with self.session() as session:
            rows = session.query("SELECT 1")
        if rows != [(1,)]:
            raise ExperianConnectionError(f"Experian database ping returned an unexpected result: {rows!r}")
        return True


class RequestScopedClient:
    """Lends one session (one connection) of `client` to every session opened
    through it, until close().

    For several imports within ONE request (Lead Gen re-runs the assessment),
    so they share one connection instead of paying the ~2 s connect each
    time. Safe because every query is a read under READ COMMITTED: shared
    locks end with each statement, so nothing is held between queries and
    each query sees the latest committed data, as on a new connection. The
    session is opened on first use (never, when no import runs), and a
    session that raises closes it, so a failed connection is never lent
    again -- the next session connects afresh.

    Not thread-safe. Create it inside the request and close it there; never
    share one between requests, threads or workers.
    """

    def __init__(self, client):
        self._client = client
        self._open = None       # ExitStack holding the client's session open
        self._session = None

    @contextmanager
    def session(self):
        if self._session is None:
            with ExitStack() as stack:
                self._session = stack.enter_context(self._client.session())
                self._open = stack.pop_all()
        try:
            yield self._session
        except BaseException:
            self.close()
            raise

    def close(self):
        held, self._open, self._session = self._open, None, None
        if held is not None:
            held.close()
