"""
Previous IVA: read the factfind's own yes/no answer, and never treat a missing
answer as "no" silently.

Evidence (read-only Aryza check, 2026-10-13): all 8 trial cases saved before
2026-07-15 carried previous_iva=True from the old import, yet each has an
explicit "No" in iva_factfind.factfind_financial_have_you_ever_had_an_iva and no
detail row. Case 117016 has no iva_factfind row at all: the question was never
answered, and the import used to report that as "no previous IVA".
"""

from unittest.mock import patch

from django.test import TestCase

from debt_app.aryza_client import AryzaClient, CaseData
from debt_app.engine.criteria import assess_case
from debt_app.models import CreditorCriteria
from debt_app.tests_cat_assessment_golden import _case, _creditor, _FixedDate
from debt_app.views.criteria_views import AssessCaseView


class _Cursor:
    """Answers each query by a substring of its SQL; anything else returns no row."""

    def __init__(self, answers):
        self.answers, self.sql = answers, ""

    def execute(self, sql, params=None):
        self.sql = sql

    def fetchone(self):
        for key, row in self.answers.items():
            if key in self.sql:
                return row
        return None

    def fetchall(self):
        row = self.fetchone()
        return [row] if row else []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _Conn:
    def __init__(self, answers):
        self.answers = answers

    def cursor(self):
        return _Cursor(self.answers)


def _flags(answers):
    client = AryzaClient.__new__(AryzaClient)
    case = CaseData()
    client._fetch_flags_data(_Conn(answers), case, clientid=1)
    return case.flags


class AryzaPreviousIvaAnswerTests(TestCase):
    def test_explicit_no_is_answered_and_not_a_previous_iva(self):
        f = _flags({"FROM iva_factfind WHERE": (0,)})
        self.assertFalse(f["previous_iva"])
        self.assertTrue(f["previous_iva_answered"])

    def test_explicit_yes_counts_even_without_a_detail_row(self):
        f = _flags({"FROM iva_factfind WHERE": (1,)})
        self.assertTrue(f["previous_iva"])
        self.assertTrue(f["previous_iva_answered"])

    def test_no_answer_is_recorded_as_unanswered(self):
        f = _flags({})
        self.assertFalse(f["previous_iva"])
        self.assertFalse(f["previous_iva_answered"])

    def test_detail_row_or_failure_reason_is_an_answer(self):
        self.assertTrue(_flags({"iva_factfind_have_you_ever_had_an_ivas": ("Breached",)})["previous_iva_answered"])
        f = _flags({"SELECT iva_failure_reason FROM iva_client": ("Missed payments",)})
        self.assertTrue(f["previous_iva"])
        self.assertTrue(f["previous_iva_answered"])

    def test_own_iva_client_row_without_a_failure_reason_is_not_a_previous_iva(self):
        """The pre-2026-07-15 bug: the client's own iva_client row set previous_iva."""
        f = _flags({"SELECT iva_failure_reason FROM iva_client": (None,), "FROM iva_factfind WHERE": (0,)})
        self.assertFalse(f["previous_iva"])


class EngineSurfacesUnansweredPreviousIvaTests(TestCase):
    def setUp(self):
        patcher = patch("debt_app.engine.criteria.date", _FixedDate)
        patcher.start()
        self.addCleanup(patcher.stop)
        CreditorCriteria.objects.update_or_create(creditor_name="Admiral Loans", defaults=dict(
            status="WILL_CONSIDER", representative="NONE", is_active=True, criteria_notes="",
            reject_if_second_iva=True))
        CreditorCriteria.objects.update_or_create(creditor_name="Capital One", defaults=dict(
            status="ACCEPT", representative="NONE", is_active=True, criteria_notes=""))

    def _assess(self, answered, previous_iva=False):
        case = _case("PI-1", [_creditor("Admiral Loans", 637_900), _creditor("Capital One", 222_000)],
                     previous_iva=previous_iva)
        if answered is not None:
            case.flags["previous_iva_answered"] = answered
        payload, _p, _u = AssessCaseView()._prepare_engine_payload(case)
        result = assess_case(payload, detected_representatives=set())
        admiral = next(p for p in result["creditor_positions"] if p["creditor_name"] == "Admiral Loans")
        return result, {f["code"] for f in admiral["findings"]}, admiral["effective_status"]

    def test_unanswered_is_flagged_and_admiral_is_not_given_a_pass(self):
        result, codes, status = self._assess(answered=False)
        self.assertIn("PREVIOUS-IVA-UNCONFIRMED", {r.rule_id for r in result["flags"]})
        self.assertIn("CREDITOR-SECOND-IVA-UNCONFIRMED", codes)
        self.assertNotIn("CREDITOR-SECOND-IVA-PASS", codes)
        self.assertEqual(status, "WILL_CONSIDER")             # not rejected on an unknown

    def test_answered_no_passes_quietly(self):
        result, codes, status = self._assess(answered=True)
        self.assertNotIn("PREVIOUS-IVA-UNCONFIRMED", {r.rule_id for r in result["flags"]})
        self.assertIn("CREDITOR-SECOND-IVA-PASS", codes)
        self.assertEqual(status, "WILL_CONSIDER")

    def test_confirmed_previous_iva_rejects(self):
        result, codes, status = self._assess(answered=True, previous_iva=True)
        self.assertIn("CREDITOR-SECOND-IVA-REJECT", codes)
        self.assertEqual(status, "REJECT")
        self.assertNotIn("PREVIOUS-IVA-UNCONFIRMED", {r.rule_id for r in result["flags"]})

    def test_older_payloads_without_the_answer_flag_are_not_flagged(self):
        result, codes, _ = self._assess(answered=None)
        self.assertNotIn("PREVIOUS-IVA-UNCONFIRMED", {r.rule_id for r in result["flags"]})
        self.assertIn("CREDITOR-SECOND-IVA-PASS", codes)
