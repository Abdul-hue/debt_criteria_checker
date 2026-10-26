"""
BANK-STATEMENTS tests.

Every active or defaulted bank account on the credit report (current, savings,
basic bank account) needs bank statements covering the 12 months before the
case was added to CAT - from the account's opening date if that is later. A
missing statement, a gap, a statement that cannot be tied to one account or
whose period cannot be read leaves the account flagged. Flag only, one
case-level result for all affected accounts.

The anchor date throughout is 21 Oct 2026, so the window is
21 Oct 2025 - 20 Oct 2026.
"""
from datetime import date
from unittest import mock

from django.test import SimpleTestCase, TestCase

from debt_app.engine import criteria
from debt_app.engine.criteria import (
    _account_numbers_match,
    _add_months,
    _bank_statements,
    _coverage_gaps,
    _credit_report_bank_accounts,
    _normalise_bank_account_status,
    _parse_any_date,
    _parse_case,
    assess_case,
)
from debt_app.models import CreditReport, GlobalCriteria

ANCHOR = date(2026, 10, 21)


def _acct(name="Barclays Bank", type_code="CA", status="active", number=None, start=None, matched=None,
          raw_status=None):
    return {
        "name": name, "matched_creditor": matched, "type_code": type_code, "source_agency": "Experian",
        "status_normalised": status, "raw_status": raw_status if raw_status is not None else status.title(),
        "account_number": number, "start_date": start, "last_reported": None,
    }


def _stmt(start, end, number=None, bank=None):
    return {"account_number": number, "sort_code": None, "account_holder": None, "bank_name": bank,
            "period_start": start, "period_end": end, "statement_date": end}


def _monthly(first: date, last: date, **kw):
    """Calendar-month statements from the month of `first` to the month of `last`."""
    out, d = [], date(first.year, first.month, 1)
    while d <= last:
        nxt = _add_months(d, 1)
        out.append(_stmt(d, date.fromordinal(nxt.toordinal() - 1), **kw))
        d = nxt
    return out


FULL_YEAR = dict(first=date(2025, 10, 1), last=date(2026, 10, 1))


def _case(accounts, statements, case_created=ANCHOR, assessment=None):
    return {
        "cr_bank_accounts": accounts,
        "bank_statements": statements,
        "case_created_date": case_created,
        "assessment_date": assessment or date(2026, 11, 30),
    }


class CoverageRuleTests(SimpleTestCase):
    def assertPasses(self, r):
        self.assertEqual("BANK-STATEMENTS", r.rule_id)
        self.assertFalse(r.triggered, r.message)
        self.assertEqual("pass", r.severity)

    def assertFlags(self, r):
        self.assertEqual("BANK-STATEMENTS", r.rule_id)
        self.assertTrue(r.triggered)
        self.assertEqual("flag", r.severity)

    # 1, 2
    def test_active_and_default_accounts_with_full_12_months_pass(self):
        for status in ("active", "default"):
            r = _bank_statements(_case([_acct(number="12345678", status=status)],
                                       _monthly(**FULL_YEAR, number="12345678")))
            self.assertPasses(r)

    def test_exactly_the_window_passes(self):
        r = _bank_statements(_case([_acct(number="12345678")], [
            _stmt(date(2025, 10, 21), date(2026, 3, 31), number="12345678"),
            _stmt(date(2026, 4, 1), date(2026, 10, 20), number="12345678"),
        ]))
        self.assertPasses(r)

    # 3, 4, 5, 8 - eligibility is the type code and status, never the balance
    def test_savings_and_basic_bank_accounts_are_required(self):
        for type_code, status in (("CA", "active"), ("CA", "default"), ("BK", "active")):
            r = _bank_statements(_case([_acct(type_code=type_code, status=status)], []))
            self.assertFlags(r)
        self.assertIn("basic bank account", _bank_statements(_case([_acct(type_code="BK")], [])).message)

    def test_zero_balance_active_account_from_report_is_still_required(self):
        accounts = _credit_report_bank_accounts({"agency": "Experian", "accounts": [
            {"raw_name": "MONZO BANK LTD", "type_code": "CA", "account_status": "Active", "current_balance": 0},
        ]})
        self.assertFlags(_bank_statements(_case(accounts, [])))

    # 6, 7
    def test_settled_closed_and_unknown_accounts_are_ignored(self):
        for status in ("settled_closed", "unknown"):
            self.assertPasses(_bank_statements(_case([_acct(status=status)], [])))

    # 9
    def test_no_statements_flags_the_account(self):
        r = _bank_statements(_case([_acct(name="Barclays Bank", number="12345678")], []))
        self.assertFlags(r)
        self.assertIn("- Barclays Bank (bank account, Active, account ending 5678): no bank statements matched", r.message)
        self.assertIn("21 Oct 2025 to 20 Oct 2026", r.message)
        self.assertIn("the date the case was added to CAT", r.message)
        self.assertEqual(["Barclays Bank"], r.creditors)

    # 10
    def test_one_month_gap_flags_with_the_dates(self):
        stmts = [s for s in _monthly(**FULL_YEAR, number="12345678") if s["period_start"] != date(2026, 3, 1)]
        r = _bank_statements(_case([_acct(number="12345678")], stmts))
        self.assertFlags(r)
        self.assertIn("no statement coverage for 1 Mar 2026 to 31 Mar 2026", r.message)

    # 11
    def test_multiple_gaps_are_all_listed(self):
        drop = {date(2025, 12, 1), date(2026, 5, 1), date(2026, 6, 1)}
        stmts = [s for s in _monthly(**FULL_YEAR, number="12345678") if s["period_start"] not in drop]
        r = _bank_statements(_case([_acct(number="12345678")], stmts))
        self.assertFlags(r)
        self.assertIn("1 Dec 2025 to 31 Dec 2025; 1 May 2026 to 30 Jun 2026", r.message)

    def test_mid_month_start_does_not_cover_the_whole_month(self):
        r = _bank_statements(_case([_acct(number="12345678")], [
            _stmt(date(2025, 11, 15), date(2026, 10, 31), number="12345678"),
        ]))
        self.assertFlags(r)
        self.assertIn("no statement coverage for 21 Oct 2025 to 14 Nov 2025", r.message)

    def test_statements_ending_before_the_anchor_leave_the_last_days_uncovered(self):
        r = _bank_statements(_case([_acct(number="12345678")], [
            _stmt(date(2025, 10, 1), date(2026, 9, 30), number="12345678"),
        ]))
        self.assertFlags(r)
        self.assertIn("1 Oct 2026 to 20 Oct 2026", r.message)

    # 12
    def test_overlapping_statements_pass(self):
        r = _bank_statements(_case([_acct(number="12345678")], [
            _stmt(date(2025, 10, 1), date(2026, 1, 31), number="12345678"),
            _stmt(date(2025, 12, 1), date(2026, 6, 30), number="12345678"),
            _stmt(date(2026, 6, 1), date(2026, 10, 31), number="12345678"),
        ]))
        self.assertPasses(r)

    # 13
    def test_account_opened_six_months_ago_needs_only_six_months(self):
        opened = date(2026, 4, 21)
        acct = _acct(number="12345678", start=opened)
        covered = [_stmt(opened, date(2026, 10, 20), number="12345678")]
        self.assertPasses(_bank_statements(_case([acct], covered)))
        r = _bank_statements(_case([acct], [_stmt(date(2026, 6, 1), date(2026, 10, 20), number="12345678")]))
        self.assertFlags(r)
        self.assertIn("opened 21 Apr 2026", r.message)
        self.assertIn("no statement coverage for 21 Apr 2026 to 31 May 2026", r.message)

    def test_account_opened_after_the_anchor_needs_nothing(self):
        self.assertPasses(_bank_statements(_case([_acct(start=date(2026, 10, 25))], [])))

    # 14
    def test_statement_for_another_account_does_not_count(self):
        r = _bank_statements(_case([_acct(number="12345678")], _monthly(**FULL_YEAR, number="87654321")))
        self.assertFlags(r)
        self.assertIn("no bank statements matched", r.message)

    def test_statement_with_no_number_or_bank_name_does_not_count(self):
        self.assertFlags(_bank_statements(_case([_acct(number="12345678")], _monthly(**FULL_YEAR))))

    def test_different_numbers_never_fall_back_to_bank_name(self):
        r = _bank_statements(_case([_acct(name="Barclays Bank", number="12345678")],
                                   _monthly(**FULL_YEAR, number="87654321", bank="Barclays")))
        self.assertFlags(r)

    # 15
    def test_each_account_is_checked_independently(self):
        accounts = [_acct(name="Barclays Bank", number="11112222"),
                    _acct(name="HSBC UK Bank plc", number="33334444", status="default")]
        r = _bank_statements(_case(accounts, _monthly(**FULL_YEAR, number="11112222")))
        self.assertFlags(r)
        self.assertEqual(["HSBC UK Bank plc"], r.creditors)
        self.assertNotIn("Barclays", r.message)

        stmts = [s for s in _monthly(**FULL_YEAR, number="33334444") if s["period_start"] != date(2026, 2, 1)]
        r = _bank_statements(_case(accounts, stmts))
        self.assertEqual(["Barclays Bank", "HSBC UK Bank plc"], r.creditors)
        self.assertIn("- Barclays Bank", r.message)
        self.assertIn("1 Feb 2026 to 28 Feb 2026", r.message)

    # 16
    def test_no_bank_accounts_or_no_report_passes(self):
        self.assertPasses(_bank_statements(_case([], [])))
        self.assertPasses(_bank_statements({"cr_bank_accounts": None, "bank_statements": []}))
        self.assertIn("No extracted credit report",
                      _bank_statements({"bank_statements": [], "assessment_date": ANCHOR}).message)

    # 17
    def test_statements_without_a_period_cannot_prove_coverage(self):
        undated = [_stmt(None, None, number="12345678") for _ in range(12)]
        r = _bank_statements(_case([_acct(number="12345678")], undated))
        self.assertFlags(r)
        self.assertIn("12 statement(s) matched, but no statement period could be read", r.message)

    def test_undated_statements_are_mentioned_beside_a_gap(self):
        stmts = [_stmt(date(2025, 10, 1), date(2026, 5, 31), number="12345678"), _stmt(None, None, number="12345678")]
        r = _bank_statements(_case([_acct(number="12345678")], stmts))
        self.assertIn("(1 further matched statement(s) had no readable statement period)", r.message)

    def test_a_reversed_period_is_not_coverage(self):
        r = _bank_statements(_case([_acct(number="12345678")],
                                   [_stmt(date(2026, 10, 20), date(2025, 10, 21), number="12345678")]))
        self.assertFlags(r)

    def test_falls_back_to_the_assessment_date(self):
        r = _bank_statements(_case([_acct()], [], case_created=None, assessment=ANCHOR))
        self.assertIn("the 12 months before the assessment date, 21 Oct 2026", r.message)

    def test_all_affected_accounts_share_one_result(self):
        r = _bank_statements(_case([_acct(name="A Bank"), _acct(name="B Bank"), _acct(name="C Bank")], []))
        self.assertEqual(3, sum(line.startswith("- ") for line in r.message.splitlines()))


class StatementMatchingTests(SimpleTestCase):
    def test_masked_numbers_match_on_their_visible_digits(self):
        self.assertTrue(_account_numbers_match("****5678", "12345678"))
        self.assertTrue(_account_numbers_match("XXXX 5678", "0004000012345678"))
        self.assertTrue(_account_numbers_match("12-34-56 12345678", "12345678"))
        self.assertFalse(_account_numbers_match("****5679", "12345678"))

    def test_too_few_digits_say_nothing(self):
        self.assertIsNone(_account_numbers_match("***78", "12345678"))
        self.assertIsNone(_account_numbers_match(None, "12345678"))

    def test_bank_name_matches_when_the_report_has_no_number(self):
        # Aryza reports carry no account number.
        r = _bank_statements(_case([_acct(name="BARCLAYS BANK UK PLC")],
                                   _monthly(**FULL_YEAR, number="12345678", bank="Barclays")))
        self.assertFalse(r.triggered, r.message)

    def test_bank_name_must_be_the_same_bank(self):
        # "Bank of Scotland" must not prove "Royal Bank of Scotland".
        r = _bank_statements(_case([_acct(name="Royal Bank of Scotland")],
                                   _monthly(**FULL_YEAR, bank="Bank of Scotland")))
        self.assertTrue(r.triggered)

    def test_two_accounts_at_one_bank_cannot_be_told_apart_by_name(self):
        accounts = [_acct(name="Barclays Bank"), _acct(name="Barclays Bank UK PLC")]
        r = _bank_statements(_case(accounts, _monthly(**FULL_YEAR, bank="Barclays")))
        self.assertTrue(r.triggered)
        self.assertIn("could not be assigned", r.message)

    def test_number_decides_between_two_accounts_at_one_bank(self):
        accounts = [_acct(name="Barclays Bank", number="11112222"), _acct(name="Barclays Bank", number="33334444")]
        stmts = _monthly(**FULL_YEAR, number="11112222") + _monthly(**FULL_YEAR, number="33334444")
        self.assertFalse(_bank_statements(_case(accounts, stmts)).triggered)


class DateHandlingTests(SimpleTestCase):
    def test_parses_the_formats_cat_stores(self):
        for raw in ("2026-01-31", "2026-01-31T09:00:00Z", "31/01/2026", "31-01-2026", "31 Jan 2026",
                    "31st January 2026", "31 jan 26", "31.01.2026"):
            self.assertEqual(date(2026, 1, 31), _parse_any_date(raw), raw)

    def test_unreadable_dates_are_none(self):
        for raw in (None, "", "N/A", "31/02/2026", "Jan 2026", "2026-13-01", 42):
            self.assertIsNone(_parse_any_date(raw), raw)

    def test_calendar_months(self):
        self.assertEqual(date(2025, 10, 21), _add_months(date(2026, 10, 21), -12))
        self.assertEqual(date(2025, 2, 28), _add_months(date(2026, 2, 28), -12))
        self.assertEqual(date(2026, 2, 28), _add_months(date(2026, 3, 31), -1))
        self.assertEqual(date(2023, 2, 28), _add_months(date(2024, 2, 29), -12))

    def test_gaps_merge_overlapping_and_back_to_back_periods(self):
        s, e = date(2026, 1, 1), date(2026, 1, 31)
        self.assertEqual([], _coverage_gaps([(date(2026, 1, 1), date(2026, 1, 15)),
                                             (date(2026, 1, 16), date(2026, 1, 31))], s, e))
        self.assertEqual([(date(2026, 1, 11), date(2026, 1, 19))],
                         _coverage_gaps([(date(2026, 1, 1), date(2026, 1, 10)),
                                         (date(2026, 1, 5), date(2026, 1, 8)),
                                         (date(2026, 1, 20), date(2026, 2, 5))], s, e))
        self.assertEqual([(s, e)], _coverage_gaps([], s, e))


class NormalisationTests(SimpleTestCase):
    def test_status_wording_across_formats(self):
        cases = {
            "Active": "active", "Open": "active", "Up to date": "active", "Late payment": "active",
            "2 Month Delinquent": "active", "Arrangement": "active",
            "Default": "default", "Defaulted": "default",
            "Settled": "settled_closed", "Closed": "settled_closed", "Satisfied": "settled_closed",
            "Default satisfied": "settled_closed",
            "": "unknown", None: "unknown", "Dormant": "unknown",
        }
        for raw, expected in cases.items():
            self.assertEqual(expected, _normalise_bank_account_status(raw), raw)

    def test_aryza_ca_and_bk(self):
        accounts = _credit_report_bank_accounts({
            "agency": "Aryza Advize",
            "accounts": [
                {"raw_name": "MONZO BANK", "matched_creditor": "Monzo Bank", "type_code": "CA",
                 "account_status": "Up to date", "start_date": "2025-11-06", "last_update": "2026-10-18"},
                {"raw_name": "VANQUIS", "type_code": "CC", "account_status": "Up to date"},
            ],
            "other_accounts": [{"raw_name": "LLOYDS BANK", "type_code": "BK", "account_status": ""}],
            "mortgage_accounts": [{"raw_name": "HALIFAX", "type_code": "MG", "account_status": "Up to date"}],
        })
        self.assertEqual(["MONZO BANK", "LLOYDS BANK"], [a["name"] for a in accounts])
        monzo, lloyds = accounts
        self.assertEqual(("CA", "active", "Up to date", None), (
            monzo["type_code"], monzo["status_normalised"], monzo["raw_status"], monzo["account_number"]))
        self.assertEqual(date(2025, 11, 6), monzo["start_date"])
        self.assertEqual("2026-10-18", monzo["last_reported"])
        self.assertEqual("Aryza Advize", monzo["source_agency"])
        self.assertEqual(("BK", "unknown"), (lloyds["type_code"], lloyds["status_normalised"]))

    def test_experian_classic_current_and_savings(self):
        accounts = _credit_report_bank_accounts({"agency": "Experian", "accounts": [
            {"raw_name": "BARCLAYS BANK", "type_code": "CA", "account_status": "Open",
             "account_number": "12345678", "start_date": "2019-03-01", "cais_last_updated": "18-10-2026"},
            {"raw_name": "NATIONWIDE", "type_code": "CA", "account_status": "Default",
             "account_number": "99990000", "start_date": None},
            {"raw_name": "HSBC", "type_code": "CA", "account_status": "Settled"},
        ]})
        self.assertEqual(["active", "default", "settled_closed"], [a["status_normalised"] for a in accounts])
        self.assertEqual("12345678", accounts[0]["account_number"])
        self.assertEqual("18-10-2026", accounts[0]["last_reported"])
        self.assertIsNone(accounts[1]["start_date"])

    def test_valid8_current_account(self):
        accounts = _credit_report_bank_accounts({"agency": "Experian", "accounts": [
            {"raw_name": "MONZO BANK LTD", "type_code": "CA", "account_status": "Active",
             "account_number": "0004000588523003", "start_date": "2025-11-06", "address": "49 Coverham Road"},
            {"raw_name": "OCTOPUS ENERGY", "type_code": "UT", "account_status": "Active"},
        ]})
        self.assertEqual(1, len(accounts))
        self.assertEqual(("active", "0004000588523003"),
                         (accounts[0]["status_normalised"], accounts[0]["account_number"]))

    def test_missing_or_malformed_data_is_safe(self):
        self.assertEqual([], _credit_report_bank_accounts({}))
        self.assertEqual([], _credit_report_bank_accounts(None))
        accounts = _credit_report_bank_accounts({"accounts": ["junk", {"type_code": "ca", "start_date": "rubbish"}]})
        self.assertEqual(1, len(accounts))
        self.assertEqual(("Unknown bank", "unknown", None),
                         (accounts[0]["name"], accounts[0]["status_normalised"], accounts[0]["start_date"]))


class ParseCaseTests(SimpleTestCase):
    def test_every_statement_is_normalised(self):
        c = _parse_case({
            "case_created_date": "2026-10-21T14:05:00Z",
            "documents": [
                {"document_type": "bank_statement", "is_valid": True, "document_date": "2026-09-30",
                 "extracted_data": {"account_number": "12345678", "first_name": "Rachel", "last_name": "Gwilliam",
                                    "statement_period_start": "1 Sep 2026", "statement_period_end": "30 Sep 2026"}},
                {"document_type": "bank_statement", "is_valid": True,
                 "extracted_data": {"bank_name": "Monzo", "statement_date": "2026-08-31"}},
                {"document_type": "bank_statement", "is_valid": True, "extracted_data": None},
                {"document_type": "payslip", "is_valid": True, "extracted_data": {}},
            ],
        })
        self.assertEqual(date(2026, 10, 21), c["case_created_date"])
        first, second, third = c["bank_statements"]
        self.assertEqual((date(2026, 9, 1), date(2026, 9, 30), "12345678", "Rachel Gwilliam"),
                         (first["period_start"], first["period_end"], first["account_number"],
                          first["account_holder"]))
        self.assertEqual(("Monzo", None, None, date(2026, 8, 31)),
                         (second["bank_name"], second["period_start"], second["period_end"],
                          second["statement_date"]))
        self.assertIsNone(third["period_start"])

    def test_missing_or_bad_case_created_date_is_none(self):
        self.assertIsNone(_parse_case({})["case_created_date"])
        self.assertIsNone(_parse_case({"case_created_date": "not a date"})["case_created_date"])
        self.assertEqual([], _parse_case({})["bank_statements"])


class AssessCaseTests(TestCase):
    REF = "BS-COVERAGE-1"

    def setUp(self):
        CreditReport.objects.create(
            aryza_reference=self.REF, uploaded_file="fake.pdf", extraction_status="extracted",
            extracted_data={"agency": "Experian", "accounts": [
                {"raw_name": "BARCLAYS BANK", "matched_creditor": "Barclays", "type_code": "CA",
                 "account_status": "Active", "account_number": "12345678", "current_balance": 0,
                 "start_date": "2019-03-01"},
            ], "mortgage_accounts": [], "other_accounts": []},
        )

    def _case_json(self, statements):
        return {
            "application_id": self.REF,
            "assessment_date": "2026-11-30",
            "case_created_date": "2026-10-21",
            "creditors": [{"name": "Generic Lender", "balance": 9000.0, "creditor_type": "personal_loan"}],
            "documents": [
                {"document_type": "bank_statement", "is_valid": True,
                 "extracted_data": {"account_number": "12345678",
                                    "statement_period_start": s.isoformat(), "statement_period_end": e.isoformat()}}
                for s, e in statements
            ],
            "evidence_ledger": [],
        }

    @staticmethod
    def _ids(result, key):
        return [r.rule_id for r in result[key]]

    def test_flags_through_assess_case_and_never_blocks(self):
        result = assess_case(self._case_json([(date(2026, 4, 1), date(2026, 10, 31))]), set())
        self.assertIn("BANK-STATEMENTS", self._ids(result, "flags"))
        self.assertNotIn("BANK-STATEMENTS", self._ids(result, "hard_blocks"))
        flag = next(r for r in result["flags"] if r.rule_id == "BANK-STATEMENTS")
        self.assertIn("21 Oct 2025 to 31 Mar 2026", flag.message)

    def test_full_coverage_passes_through_assess_case(self):
        result = assess_case(self._case_json([(date(2025, 10, 1), date(2026, 10, 31))]), set())
        self.assertIn("BANK-STATEMENTS", self._ids(result, "passed"))

    # 18
    def test_disabled_in_admin_does_not_run(self):
        GlobalCriteria.objects.filter(rule_key="BANK-STATEMENTS").update(is_active=False)
        spy = mock.Mock(wraps=criteria._bank_statements)
        spy.__name__ = "_bank_statements"
        with mock.patch.object(criteria, "_bank_statements", spy):
            result = assess_case(self._case_json([]), set())
        spy.assert_not_called()
        all_ids = [rid for key in ("flags", "hard_blocks", "info", "passed") for rid in self._ids(result, key)]
        self.assertNotIn("BANK-STATEMENTS", all_ids)

    def test_migration_seeds_an_active_flag_rule(self):
        row = GlobalCriteria.objects.get(rule_key="BANK-STATEMENTS")
        self.assertEqual(("flag", True, "bank_statements"), (row.severity, row.is_active, row.category))
