"""
The Experian credit-search integration's configuration and read-only
database layer (debt_app/integrations/experian_db.py).

No live server: pymssql.connect is mocked throughout. Credentials below are
fakes, chosen to be easy to spot if they ever leak into a message or log.
"""
import importlib.util
import json
import os
import re
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pymssql
from django.conf import settings
from django.test import SimpleTestCase
from pymssql import _mssql

from debt_app.integrations import experian_db
from debt_app.integrations.experian_db import (
    ACCOUNT_TYPE_CODES_SQL,
    CANDIDATE_SEARCHES_SQL,
    PUBLIC_INFO_TYPE_CODES_SQL,
    SEARCH_DOCUMENT_SQL,
    STORED_SEARCHES_SQL,
    ExperianConnectionError,
    ExperianDataError,
    ExperianDBClient,
    ExperianError,
    RequestScopedClient,
)

SETTINGS_PATH = Path(settings.BASE_DIR) / "debt_project" / "settings.py"

FAKE_CONFIG = {
    "HOST": "experian.example.test",
    "PORT": "6000",
    "NAME": "ExperianTest",
    "USER": "fake_reader",
    "PASSWORD": "Fake-Pa55word!",
    "CONNECT_TIMEOUT": 5,
    "QUERY_TIMEOUT": 10,
}


def _load_settings(env):
    """Execute settings.py against exactly `env`, ignoring any local .env file."""
    with patch.dict(os.environ, env, clear=True), patch("dotenv.load_dotenv"):
        spec = importlib.util.spec_from_file_location("_settings_under_test", SETTINGS_PATH)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module


def _fake_connection(rows):
    cursor = MagicMock()
    cursor.fetchall.return_value = rows
    connection = MagicMock()
    connection.cursor.return_value.__enter__.return_value = cursor
    return connection, cursor


class ExperianSettingsTests(SimpleTestCase):
    def test_connection_settings_read_from_environment(self):
        loaded = _load_settings({
            "EXPERIAN_DB_HOST": "db.example.test",
            "EXPERIAN_DB_PORT": "6035",
            "EXPERIAN_DB_NAME": "Experian",
            "EXPERIAN_DB_USER": "reader",
            "EXPERIAN_DB_PASSWORD": "secret",
        })
        self.assertEqual(loaded.EXPERIAN_DB["HOST"], "db.example.test")
        self.assertEqual(loaded.EXPERIAN_DB["PORT"], "6035")
        self.assertEqual(loaded.EXPERIAN_DB["NAME"], "Experian")
        self.assertEqual(loaded.EXPERIAN_DB["USER"], "reader")
        self.assertEqual(loaded.EXPERIAN_DB["PASSWORD"], "secret")
        self.assertEqual(loaded.EXPERIAN_DB["CONNECT_TIMEOUT"], 5)
        self.assertEqual(loaded.EXPERIAN_DB["QUERY_TIMEOUT"], 10)

    def test_unset_environment_leaves_connection_unconfigured(self):
        loaded = _load_settings({})
        self.assertEqual(loaded.EXPERIAN_DB["HOST"], "")
        self.assertEqual(loaded.EXPERIAN_DB["PASSWORD"], "")
        self.assertEqual(loaded.EXPERIAN_DB["PORT"], "1433")

    def test_auto_credit_report_flag_defaults_to_false(self):
        self.assertIs(_load_settings({}).EXPERIAN_AUTO_CREDIT_REPORT, False)

    def test_auto_credit_report_flag_parsed_case_insensitively(self):
        self.assertIs(_load_settings({"EXPERIAN_AUTO_CREDIT_REPORT": "TRUE"}).EXPERIAN_AUTO_CREDIT_REPORT, True)
        self.assertIs(_load_settings({"EXPERIAN_AUTO_CREDIT_REPORT": "false"}).EXPERIAN_AUTO_CREDIT_REPORT, False)

    def test_experian_is_not_a_django_database(self):
        self.assertNotIn("experian", settings.DATABASES)


@patch("debt_app.integrations.experian_db.pymssql.connect")
class ExperianDBClientTests(SimpleTestCase):
    def test_connection_settings_passed_to_driver(self, connect):
        connect.return_value, _ = _fake_connection([(1,)])
        ExperianDBClient(FAKE_CONFIG).ping()
        connect.assert_called_once_with(
            server="experian.example.test",
            port="6000",
            database="ExperianTest",
            user="fake_reader",
            password="Fake-Pa55word!",
            login_timeout=5,
            timeout=10,
            read_only=True,
            encryption="require",
        )

    def test_default_client_uses_django_settings(self, connect):
        connect.return_value, _ = _fake_connection([(1,)])
        with self.settings(EXPERIAN_DB=FAKE_CONFIG):
            ExperianDBClient().ping()
        self.assertEqual(connect.call_args.kwargs["server"], "experian.example.test")

    def test_ping_success_runs_select_1_and_closes(self, connect):
        connection, cursor = _fake_connection([(1,)])
        connect.return_value = connection
        self.assertIs(ExperianDBClient(FAKE_CONFIG).ping(), True)
        cursor.execute.assert_called_once_with("SELECT 1", ())
        connection.close.assert_called_once()

    def test_unexpected_ping_result_is_an_error(self, connect):
        connect.return_value, _ = _fake_connection([])
        with self.assertRaises(ExperianConnectionError):
            ExperianDBClient(FAKE_CONFIG).ping()

    def test_missing_configuration_fails_without_connecting(self, connect):
        config = {**FAKE_CONFIG, "HOST": "", "PASSWORD": ""}
        with self.assertLogs("debt_app.integrations.experian_db", level="ERROR"):
            with self.assertRaises(ExperianConnectionError) as ctx:
                ExperianDBClient(config).ping()
        self.assertIn("HOST", str(ctx.exception))
        self.assertIn("PASSWORD", str(ctx.exception))
        connect.assert_not_called()

    def test_connection_failure_raises_controlled_error(self, connect):
        connect.side_effect = pymssql.OperationalError(20009, b"Unable to connect: Adaptive Server is unavailable")
        with self.assertLogs("debt_app.integrations.experian_db", level="ERROR"):
            with self.assertRaises(ExperianConnectionError) as ctx:
                ExperianDBClient(FAKE_CONFIG).ping()
        self.assertIn("connection failed", str(ctx.exception))
        self.assertIsNone(ctx.exception.__cause__)

    def test_credentials_never_in_error_or_log(self, connect):
        connect.side_effect = pymssql.OperationalError(
            18456, b"Login failed for user 'fake_reader' (password 'Fake-Pa55word!')"
        )
        with self.assertLogs("debt_app.integrations.experian_db", level="ERROR") as logs:
            with self.assertRaises(ExperianConnectionError) as ctx:
                ExperianDBClient(FAKE_CONFIG).ping()
        for text in [str(ctx.exception), *logs.output]:
            self.assertNotIn("Fake-Pa55word!", text)
            self.assertNotIn("fake_reader", text)
            self.assertIn("<redacted>", text)

    def test_query_failure_raises_controlled_error_and_closes(self, connect):
        connection, cursor = _fake_connection([])
        cursor.execute.side_effect = pymssql.OperationalError(20003, b"Adaptive Server connection timed out")
        connect.return_value = connection
        with self.assertLogs("debt_app.integrations.experian_db", level="ERROR"):
            with self.assertRaises(ExperianConnectionError) as ctx:
                ExperianDBClient(FAKE_CONFIG).ping()
        self.assertIn("query failed", str(ctx.exception))
        connection.close.assert_called_once()


ALL_QUERIES = (CANDIDATE_SEARCHES_SQL, STORED_SEARCHES_SQL, SEARCH_DOCUMENT_SQL, ACCOUNT_TYPE_CODES_SQL,
               PUBLIC_INFO_TYPE_CODES_SQL)


def _scripted_connection(*results):
    """A fake connection whose successive execute() calls return `results` in order."""
    cursor = MagicMock()
    cursor.fetchall.side_effect = list(results)
    connection = MagicMock()
    connection.cursor.return_value.__enter__.return_value = cursor
    return connection, cursor


class ExperianQueryTextTests(SimpleTestCase):
    """The SQL itself: read-only and parameterised."""

    def test_every_query_is_a_single_select(self):
        for sql in ALL_QUERIES:
            self.assertTrue(sql.strip().upper().startswith(("SELECT", "WITH")), sql)
            self.assertNotIn(";", sql)
            self.assertIsNone(
                re.search(r"\b(INSERT|UPDATE|DELETE|MERGE|DROP|ALTER|CREATE|TRUNCATE|EXEC|GRANT)\b", sql, re.I), sql)

    def test_values_only_enter_through_placeholders(self):
        # No str.format / f-string fields, and no quoted literal other than JSON paths.
        for sql in ALL_QUERIES:
            self.assertNotIn("{", sql)
            for literal in re.findall(r"'([^']*)'", sql):
                self.assertTrue(literal.startswith("$."), literal)
        self.assertEqual(CANDIDATE_SEARCHES_SQL.count("%s"), 3)
        self.assertEqual(STORED_SEARCHES_SQL.count("%s"), 2)
        self.assertEqual(SEARCH_DOCUMENT_SQL.count("%s"), 2)

    def test_candidate_query_lists_every_search_of_the_crm_ref_without_jsondata(self):
        candidates_cte = CANDIDATE_SEARCHES_SQL.split("newest_imported AS")[0]
        self.assertIn("SELECT ID, DateCreated", candidates_cte)
        self.assertIn("WHERE CRM_Ref = %s", candidates_cte)
        self.assertNotIn("JsonData", candidates_cte)
        # No row limit: other people's searches under the reference must not
        # push the client's own newer search out of view.
        self.assertNotIn("TOP", candidates_cte)
        self.assertTrue(CANDIDATE_SEARCHES_SQL.rstrip().endswith("ORDER BY c.DateCreated DESC, c.ID DESC"))

    def test_stored_search_query_is_scoped_to_the_case_and_reads_identity_safely(self):
        self.assertIn("WHERE CRM_Ref = %s AND ID IN %s", STORED_SEARCHES_SQL)
        self.assertEqual(STORED_SEARCHES_SQL.count("JSON_VALUE"),
                         STORED_SEARCHES_SQL.count("WHEN ISJSON(JsonData) = 1"))

    def test_candidate_query_reads_identity_only_for_searches_newer_than_the_newest_import(self):
        self.assertIn("WHERE CRM_Ref = %s AND ID IN %s", CANDIDATE_SEARCHES_SQL)
        apply_block = CANDIDATE_SEARCHES_SQL.split("OUTER APPLY")[1]
        self.assertIn("WHERE s.ID = c.ID", apply_block)
        self.assertIn("c.DateCreated > i.DateCreated OR (c.DateCreated = i.DateCreated AND c.ID > i.ID)",
                      apply_block)

    def test_document_query_is_scoped_to_the_case(self):
        self.assertIn("WHERE ID = %s AND CRM_Ref = %s", SEARCH_DOCUMENT_SQL)


@patch("debt_app.integrations.experian_db.pymssql.connect")
class ExperianSessionTests(SimpleTestCase):
    def setUp(self):
        experian_db._code_tables_cache = None

    def tearDown(self):
        experian_db._code_tables_cache = None

    def test_session_runs_several_queries_on_one_connection(self, connect):
        connection, cursor = _scripted_connection([(1,)], [(2,)])
        connect.return_value = connection
        with ExperianDBClient(FAKE_CONFIG).session() as session:
            self.assertEqual(session.query("SELECT 1"), [(1,)])
            self.assertEqual(session.query("SELECT 2"), [(2,)])
        connect.assert_called_once()
        connection.close.assert_called_once()

    def test_session_closes_connection_when_caller_raises(self, connect):
        connection, _ = _scripted_connection()
        connect.return_value = connection
        with self.assertRaises(RuntimeError):
            with ExperianDBClient(FAKE_CONFIG).session():
                raise RuntimeError("caller bug")
        connection.close.assert_called_once()

    def test_find_candidate_searches_parameters_and_rows(self, connect):
        created = datetime(2026, 10, 1, 9, 30)
        # Columns: ID, DateCreated, identity read?, ISJSON, forename, surname, dob, second applicant.
        connection, cursor = _scripted_connection([
            (950, created, 1, 0, None, None, None, None),
            (912, created, 1, 1, "JANE", "DOE", "1980-05-05T00:00:00", None),
            (870, created, 1, 1, "JANE", "DOE", "1980-05-05T00:00:00", "2"),
            (800, created, 0, None, None, None, None, None),
        ])
        connect.return_value = connection
        with ExperianDBClient(FAKE_CONFIG).session() as session:
            found = session.find_candidate_searches(" 349223 ", imported_ids={800, 700, None})
        cursor.execute.assert_called_once_with(CANDIDATE_SEARCHES_SQL, ("349223", "349223", (700, 800)))
        self.assertEqual([c.search_id for c in found], [950, 912, 870, 800])
        self.assertEqual(found[1].date_created, created)
        self.assertEqual((found[1].forename, found[1].surname, found[1].date_of_birth),
                         ("JANE", "DOE", "1980-05-05T00:00:00"))
        self.assertEqual([c.has_second_applicant for c in found], [False, False, True, False])
        self.assertEqual([c.identity_loaded for c in found], [True, True, True, False])
        self.assertEqual([c.is_json for c in found], [False, True, True, None])

    def test_no_imported_ids_uses_a_sentinel_and_reads_every_identity(self, connect):
        connection, cursor = _scripted_connection([])
        connect.return_value = connection
        with ExperianDBClient(FAKE_CONFIG).session() as session:
            self.assertEqual(session.find_candidate_searches("349223"), [])
        cursor.execute.assert_called_once_with(CANDIDATE_SEARCHES_SQL, ("349223", "349223", (-1,)))

    def test_read_stored_searches_parameters_and_rows(self, connect):
        created = datetime(2026, 10, 1, 9, 30)
        # Columns: ID, DateCreated, ISJSON, forename, surname, dob, second applicant.
        connection, cursor = _scripted_connection([
            (912, created, 1, "JANE", "DOE", "1980-05-05T00:00:00", None),
            (870, created, 0, None, None, None, None),
        ])
        connect.return_value = connection
        with ExperianDBClient(FAKE_CONFIG).session() as session:
            found = session.read_stored_searches(" 349223 ", {912, 870, None})
        cursor.execute.assert_called_once_with(STORED_SEARCHES_SQL, ("349223", (870, 912)))
        self.assertEqual([c.search_id for c in found], [912, 870])
        self.assertEqual((found[0].forename, found[0].surname, found[0].date_of_birth),
                         ("JANE", "DOE", "1980-05-05T00:00:00"))
        self.assertEqual([c.is_json for c in found], [True, False])
        self.assertTrue(all(c.identity_loaded for c in found))

    def test_read_stored_searches_runs_no_query_without_ids(self, connect):
        connection, cursor = _scripted_connection()
        connect.return_value = connection
        with ExperianDBClient(FAKE_CONFIG).session() as session:
            self.assertEqual(session.read_stored_searches("349223", {None}), [])
        cursor.execute.assert_not_called()

    def test_candidate_repr_never_shows_personal_fields(self, connect):
        connection, _ = _scripted_connection([(1, datetime(2026, 1, 1), 1, 1, "JANE", "DOE", "1980-05-05", None)])
        connect.return_value = connection
        with ExperianDBClient(FAKE_CONFIG).session() as session:
            text = repr(session.find_candidate_searches("1"))
        for personal in ("JANE", "DOE", "1980-05-05"):
            self.assertNotIn(personal, text)

    def test_fetch_search_document_parameters_and_parse(self, connect):
        document = {"Response": {"Applicants": []}}
        connection, cursor = _scripted_connection([(json.dumps(document),)])
        connect.return_value = connection
        with ExperianDBClient(FAKE_CONFIG).session() as session:
            self.assertEqual(session.fetch_search_document(912, "349223 "), document)
        cursor.execute.assert_called_once_with(SEARCH_DOCUMENT_SQL, (912, "349223"))

    def test_fetch_search_document_rejects_missing_and_malformed(self, connect):
        for rows, reason in (
            ([], "not found"),
            ([(None,)], "not found"),
            ([("{not json",)], "malformed"),
            ([("[1, 2]",)], "no Response"),
            ([('{"Response": "text"}',)], "no Response"),
        ):
            connection, _ = _scripted_connection(rows)
            connect.return_value = connection
            with ExperianDBClient(FAKE_CONFIG).session() as session:
                with self.assertRaises(ExperianDataError) as ctx:
                    session.fetch_search_document(912, "349223")
            self.assertIn(reason, str(ctx.exception))

    def test_code_tables_strip_padding_and_are_cached(self, connect):
        connection, cursor = _scripted_connection(
            [("05", "Credit Card / Store Card"), ("71", "Basic Bank Account ")],
            [("02", "Judgement"), ("72", "Bankruptcy")],
        )
        connect.return_value = connection
        client = ExperianDBClient(FAKE_CONFIG)
        with client.session() as session:
            tables = session.load_code_tables()
        self.assertEqual(tables.account_types, {"05": "Credit Card / Store Card", "71": "Basic Bank Account"})
        self.assertEqual(tables.public_info_types, {"02": "Judgement", "72": "Bankruptcy"})
        self.assertEqual([c.args for c in cursor.execute.call_args_list],
                         [(ACCOUNT_TYPE_CODES_SQL, ()), (PUBLIC_INFO_TYPE_CODES_SQL, ())])
        with client.session() as session:
            self.assertIs(session.load_code_tables(), tables)
        self.assertEqual(cursor.execute.call_count, 2)

    def test_empty_code_tables_are_a_data_error(self, connect):
        connection, _ = _scripted_connection([], [])
        connect.return_value = connection
        with ExperianDBClient(FAKE_CONFIG).session() as session:
            with self.assertRaises(ExperianDataError):
                session.load_code_tables()
        self.assertIsNone(experian_db._code_tables_cache)

    def test_driver_level_mssql_exception_is_controlled(self, connect):
        connection, cursor = _scripted_connection()
        cursor.execute.side_effect = _mssql.MSSQLDatabaseException((208, b"Invalid object name"))
        connect.return_value = connection
        with self.assertLogs("debt_app.integrations.experian_db", level="ERROR"):
            with self.assertRaises(ExperianConnectionError):
                with ExperianDBClient(FAKE_CONFIG).session() as session:
                    session.find_candidate_searches("349223")
        connection.close.assert_called_once()


@patch("debt_app.integrations.experian_db.pymssql.connect")
class RequestScopedClientTests(SimpleTestCase):
    """One connection per request, shared by its sessions; never a broken one."""

    def test_sessions_share_one_connection_until_closed(self, connect):
        connection, _ = _scripted_connection([(1,)], [(2,)])
        connect.return_value = connection
        scoped = RequestScopedClient(ExperianDBClient(FAKE_CONFIG))
        with scoped.session() as first:
            first.query("SELECT 1")
        with scoped.session() as second:
            second.query("SELECT 2")
        connect.assert_called_once()
        connection.close.assert_not_called()
        scoped.close()
        connection.close.assert_called_once()
        scoped.close()                                   # closing twice is harmless
        connection.close.assert_called_once()

    def test_no_session_means_no_connection(self, connect):
        RequestScopedClient(ExperianDBClient(FAKE_CONFIG)).close()
        connect.assert_not_called()

    def test_a_failed_session_closes_the_connection_and_the_next_one_reconnects(self, connect):
        broken, broken_cursor = _scripted_connection()
        broken_cursor.execute.side_effect = pymssql.OperationalError(20003, b"timed out")
        fresh, _ = _scripted_connection([(1,)])
        connect.side_effect = [broken, fresh]
        scoped = RequestScopedClient(ExperianDBClient(FAKE_CONFIG))
        with self.assertLogs("debt_app.integrations.experian_db", level="ERROR"):
            with self.assertRaises(ExperianConnectionError):
                with scoped.session() as session:
                    session.query("SELECT 1")
        broken.close.assert_called_once()
        with scoped.session() as session:
            self.assertEqual(session.query("SELECT 1"), [(1,)])
        self.assertEqual(connect.call_count, 2)
        scoped.close()
        fresh.close.assert_called_once()

    def test_a_failed_connect_is_retried_by_the_next_session(self, connect):
        connection, _ = _scripted_connection([(1,)])
        connect.side_effect = [pymssql.OperationalError(20009, b"unreachable"), connection]
        scoped = RequestScopedClient(ExperianDBClient(FAKE_CONFIG))
        with self.assertLogs("debt_app.integrations.experian_db", level="ERROR"):
            with self.assertRaises(ExperianConnectionError):
                with scoped.session():
                    pass
        with scoped.session() as session:
            session.query("SELECT 1")
        scoped.close()
        connection.close.assert_called_once()


@patch("debt_app.integrations.experian_db.pymssql.connect")
class ExperianProgrammingErrorsPropagate(SimpleTestCase):
    """Only driver failures become ExperianError; bugs are not hidden."""

    def test_error_types_share_one_base(self, connect):
        self.assertTrue(issubclass(ExperianConnectionError, ExperianError))
        self.assertTrue(issubclass(ExperianDataError, ExperianError))

    def test_non_driver_error_during_query_propagates(self, connect):
        connection, cursor = _scripted_connection()
        cursor.execute.side_effect = TypeError("bad argument")
        connect.return_value = connection
        with self.assertRaises(TypeError):
            ExperianDBClient(FAKE_CONFIG).ping()
        connection.close.assert_called_once()

    def test_non_driver_error_during_connect_propagates(self, connect):
        connect.side_effect = TypeError("bad argument")
        with self.assertRaises(TypeError):
            ExperianDBClient(FAKE_CONFIG).ping()
