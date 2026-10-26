"""
BANK-STATEMENTS with several accounts in one bank statement document.

CAT sends each statement document's accounts in `extracted_data.bank_accounts`
(one per statement file: account_number, sort_code, bank_name, iban,
statement_start, statement_end, file). The engine turns a document into one
statement entry PER ACCOUNT (`_bank_statement_entries`), so each account is
matched and its coverage checked on its own period. The document list
(`bank_stmt_docs`, read by TIG-06/08/11) is not split.

Same anchor as test_bank_statement_coverage: 21 Oct 2026, window
21 Oct 2025 - 20 Oct 2026.
"""
from datetime import date

from django.test import SimpleTestCase, TestCase

from debt_app.engine.criteria import (
    _bank_statement_entries,
    _bank_statements,
    _normalise_bank_statement,
    _parse_case,
    assess_case,
)
from debt_app.models import CreditReport
from debt_app.tests.test_bank_statement_coverage import ANCHOR, _acct

FULL = ("2025-10-01", "2026-10-31")       # covers the whole window
HALF = ("2026-04-01", "2026-10-31")       # leaves 21 Oct 2025 - 31 Mar 2026 uncovered


def _account(number, start_end=FULL, bank=None, sort_code=None, file="statement.pdf"):
    out = {"file": file, "account_number": number, "statement_start": start_end[0], "statement_end": start_end[1]}
    if bank:
        out["bank_name"] = bank
    if sort_code:
        out["sort_code"] = sort_code
    return out


def _doc(accounts=None, **top_level):
    ext = dict(top_level)
    if accounts is not None:
        ext["bank_accounts"] = accounts
    return {"document_type": "bank_statement", "is_valid": True, "document_date": "2026-10-31",
            "extracted_data": ext}


def _parsed(*docs):
    return _parse_case({"case_created_date": ANCHOR.isoformat(), "documents": list(docs)})


def _rule(cr_accounts, *docs):
    c = _parsed(*docs)
    c["cr_bank_accounts"] = cr_accounts
    return _bank_statements(c)


BARCLAYS = _acct(name="Barclays Bank", number="11112222")
HSBC = _acct(name="HSBC UK Bank plc", number="33334444", status="default")


class EntriesTests(SimpleTestCase):
    """What one document becomes in `bank_statements`."""

    # Test 1
    def test_one_document_one_account(self):
        c = _parsed(_doc([_account("11112222", bank="Barclays", sort_code="20-00-00")]))
        self.assertEqual(1, len(c["bank_stmt_docs"]))
        [entry] = c["bank_statements"]
        self.assertEqual(("11112222", "20-00-00", "Barclays", date(2025, 10, 1), date(2026, 10, 31)),
                         (entry["account_number"], entry["sort_code"], entry["bank_name"],
                          entry["period_start"], entry["period_end"]))

    # Test 2
    def test_one_document_two_accounts_gives_two_entries(self):
        c = _parsed(_doc([_account("11112222", bank="Barclays", sort_code="20-00-00", file="a.pdf"),
                          _account("33334444", bank="HSBC", sort_code="40-11-22", file="b.pdf")]))
        self.assertEqual(1, len(c["bank_stmt_docs"]), "the document list is not split")
        first, second = c["bank_statements"]
        self.assertEqual(("11112222", "20-00-00", "Barclays"),
                         (first["account_number"], first["sort_code"], first["bank_name"]))
        self.assertEqual(("33334444", "40-11-22", "HSBC"),
                         (second["account_number"], second["sort_code"], second["bank_name"]))

    # Test 3
    def test_each_account_keeps_only_its_own_period(self):
        c = _parsed(_doc([_account("11112222", ("2025-01-01", "2025-06-30")),
                          _account("33334444", ("2025-07-01", "2025-12-31"))],
                         statement_period_start="2024-01-01", statement_period_end="2026-12-31",
                         account_number="99999999", bank_name="Other Bank"))
        first, second = c["bank_statements"]
        self.assertEqual((date(2025, 1, 1), date(2025, 6, 30)), (first["period_start"], first["period_end"]))
        self.assertEqual((date(2025, 7, 1), date(2025, 12, 31)), (second["period_start"], second["period_end"]))
        for entry in (first, second):
            self.assertIsNone(entry["bank_name"], "the document's own bank name is not given to either account")

    def test_an_account_with_no_period_does_not_borrow_the_document_s(self):
        c = _parsed(_doc([_account("11112222"), {"file": "b.pdf", "account_number": "33334444"}],
                         statement_period_start="2025-10-01", statement_period_end="2026-10-31"))
        self.assertEqual((None, None), (c["bank_statements"][1]["period_start"], c["bank_statements"][1]["period_end"]))

    def test_a_single_account_agreeing_with_the_document_reads_the_same(self):
        top = dict(account_number="11112222", sort_code="20-00-00", bank_name="Barclays",
                   statement_period_start=FULL[0], statement_period_end=FULL[1])
        doc = _doc([_account("11112222", bank="Barclays", sort_code="20-00-00")], **top)
        self.assertEqual([_normalise_bank_statement(_doc(**top))], _bank_statement_entries(doc))

    def test_with_one_account_the_document_s_own_value_wins(self):
        """As before, and as CAT sends it (`payload_builder.py :: _documents`:
        a key the document already has is never replaced)."""
        [entry] = _bank_statement_entries(_doc([_account("11112222", HALF, bank="HSBC", sort_code="40-11-22")],
                                               account_number="99998888", bank_name="Barclays",
                                               sort_code="20-00-00", statement_period_start=FULL[0],
                                               statement_period_end=FULL[1]))
        self.assertEqual(("99998888", "Barclays", "20-00-00", date(2025, 10, 1), date(2026, 10, 31)),
                         (entry["account_number"], entry["bank_name"], entry["sort_code"],
                          entry["period_start"], entry["period_end"]))

    def test_an_empty_document_value_is_filled_from_the_one_account(self):
        [entry] = _bank_statement_entries(_doc([_account("11112222", bank="Barclays")],
                                               account_number="", bank_name=None))
        self.assertEqual(("11112222", "Barclays"), (entry["account_number"], entry["bank_name"]))

    def test_a_single_account_is_filled_from_the_document_as_before(self):
        [entry] = _bank_statement_entries(_doc([{"file": "a.pdf", "account_number": "11112222"}],
                                               statement_period_start="2025-10-01",
                                               statement_period_end="2026-10-31", bank_name="Barclays"))
        self.assertEqual(("11112222", "Barclays", date(2025, 10, 1), date(2026, 10, 31)),
                         (entry["account_number"], entry["bank_name"], entry["period_start"], entry["period_end"]))

    def test_holder_and_statement_date_are_the_document_s(self):
        doc = _doc([_account("1"), _account("2")], first_name="Rachel", last_name="Gwilliam",
                   statement_date="2026-10-15")
        for entry in _bank_statement_entries(doc):
            self.assertEqual(("Rachel Gwilliam", date(2026, 10, 15)), (entry["account_holder"], entry["statement_date"]))

    # Test 5, 6
    def test_no_or_empty_list_is_the_document_entry_exactly(self):
        top = dict(account_number="11112222", sort_code="20-00-00", bank_name="Barclays",
                   statement_period_start="1 Oct 2025", statement_period_end="31 Oct 2026")
        for doc in (_doc(**top), _doc([], **top)):
            with self.subTest(bank_accounts=doc["extracted_data"].get("bank_accounts", "missing")):
                self.assertEqual([_normalise_bank_statement(doc)], _bank_statement_entries(doc))

    # Test 9
    def test_malformed_lists_fall_back_to_the_document(self):
        for junk in ("Barclays", None, {"account_number": "1"}, [None, "x", 3]):
            doc = _doc(junk, account_number="11112222")
            with self.subTest(bank_accounts=junk):
                self.assertEqual([_normalise_bank_statement(doc)], _bank_statement_entries(doc))
        self.assertEqual([_normalise_bank_statement({"document_type": "bank_statement", "extracted_data": None})],
                         _bank_statement_entries({"document_type": "bank_statement", "extracted_data": None}))

    def test_junk_beside_one_account_is_skipped(self):
        [entry] = _bank_statement_entries(_doc(["x", None, _account("11112222")]))
        self.assertEqual("11112222", entry["account_number"])

    def test_the_document_is_not_changed(self):
        doc = _doc([_account("1"), _account("2")], account_number="9")
        before = repr(doc)
        _bank_statement_entries(doc)
        self.assertEqual(before, repr(doc))


class TigInputsTests(SimpleTestCase):
    """Test 10 (inputs): what TIG-06/08/11 read is the same with or without the list."""

    def test_documents_date_and_holder_are_unchanged(self):
        extra = dict(first_name="Rachel", last_name="Gwilliam", statement_date="2026-10-15")
        plain = _parsed(_doc(**extra), _doc(account_number="5"))
        listed = _parsed(_doc([_account("1"), _account("2")], **extra), _doc([_account("5")], account_number="5"))
        for key in ("bank_stmt_date", "bank_stmt_holder"):
            self.assertEqual(plain[key], listed[key], key)
        self.assertEqual(2, len(listed["bank_stmt_docs"]))
        self.assertEqual(3, len(listed["bank_statements"]))


class RuleTests(SimpleTestCase):
    """Document -> bank_accounts -> entries -> matching -> coverage -> result."""

    def assertPasses(self, r):
        self.assertFalse(r.triggered, r.message)
        self.assertEqual("pass", r.severity)

    # Test 2 (rule)
    def test_two_accounts_in_one_document_both_covered(self):
        self.assertPasses(_rule([BARCLAYS, HSBC], _doc([_account("11112222"), _account("33334444")])))

    # Test 3 (rule) -- the false pass a shared period would give
    def test_a_short_account_is_flagged_even_when_the_document_covers_the_year(self):
        r = _rule([BARCLAYS, HSBC], _doc([_account("11112222", FULL), _account("33334444", HALF)],
                                         statement_period_start=FULL[0], statement_period_end=FULL[1]))
        self.assertTrue(r.triggered)
        self.assertEqual(["HSBC UK Bank plc"], r.creditors)
        self.assertIn("21 Oct 2025 to 31 Mar 2026", r.message)

    # Test 4
    def test_two_accounts_at_one_bank_are_matched_by_number(self):
        a = _acct(name="Barclays Bank", number="11112222")
        b = _acct(name="Barclays Bank", number="55556666")
        self.assertPasses(_rule([a, b], _doc([_account("11112222", bank="Barclays"),
                                              _account("55556666", bank="Barclays")])))
        r = _rule([a, b], _doc([_account("11112222", bank="Barclays"), _account("55556666", HALF, bank="Barclays")]))
        self.assertEqual(["Barclays Bank"], r.creditors)
        self.assertIn("account ending 6666", r.message)

    # Test 5 (rule)
    def test_top_level_fields_still_work_without_a_list(self):
        self.assertPasses(_rule([BARCLAYS], _doc(account_number="11112222",
                                                 statement_period_start=FULL[0], statement_period_end=FULL[1])))

    # Test 7
    def test_two_documents_one_account_each(self):
        self.assertPasses(_rule([BARCLAYS, HSBC], _doc([_account("11112222")]), _doc([_account("33334444")])))

    # Test 8
    def test_one_account_across_documents_merges_its_periods(self):
        self.assertPasses(_rule([BARCLAYS], _doc([_account("11112222", ("2025-10-01", "2026-03-31"))]),
                                _doc([_account("11112222", ("2026-04-01", "2026-10-31"))])))
        r = _rule([BARCLAYS], _doc([_account("11112222", ("2025-10-01", "2026-02-28"))]),
                  _doc([_account("11112222", ("2026-04-01", "2026-10-31"))]))
        self.assertIn("1 Mar 2026 to 31 Mar 2026", r.message)

    # Test 9 (rule)
    def test_an_account_with_no_number_or_bank_counts_for_nothing(self):
        r = _rule([BARCLAYS, HSBC], _doc([_account("11112222"), {"file": "b.pdf", "statement_start": FULL[0],
                                                                  "statement_end": FULL[1]}]))
        self.assertEqual(["HSBC UK Bank plc"], r.creditors)


class AssessCaseMultiAccountTests(TestCase):
    """The whole flow through `assess_case`, credit report included."""
    REF = "BS-MULTI-1"

    def setUp(self):
        CreditReport.objects.create(
            aryza_reference=self.REF, uploaded_file="fake.pdf", extraction_status="extracted",
            extracted_data={"agency": "Experian", "accounts": [
                {"raw_name": "BARCLAYS BANK", "matched_creditor": "Barclays", "type_code": "CA",
                 "account_status": "Active", "account_number": "11112222", "start_date": "2019-03-01"},
                {"raw_name": "HSBC UK BANK", "matched_creditor": "HSBC", "type_code": "CA",
                 "account_status": "Default", "account_number": "33334444", "start_date": "2018-01-01"},
            ], "mortgage_accounts": [], "other_accounts": []},
        )

    def _result(self, accounts):
        return assess_case({
            "application_id": self.REF, "assessment_date": "2026-11-30", "case_created_date": ANCHOR.isoformat(),
            "creditors": [{"name": "Generic Lender", "balance": 9000.0, "creditor_type": "personal_loan"}],
            "documents": [_doc(accounts)], "evidence_ledger": [],
        }, set())

    @staticmethod
    def _ids(result, key):
        return [r.rule_id for r in result[key]]

    def test_one_document_with_both_accounts_passes(self):
        result = self._result([_account("11112222"), _account("33334444")])
        self.assertIn("BANK-STATEMENTS", self._ids(result, "passed"))

    def test_the_short_account_alone_is_flagged(self):
        result = self._result([_account("11112222"), _account("33334444", HALF)])
        flag = next(r for r in result["flags"] if r.rule_id == "BANK-STATEMENTS")
        self.assertEqual(["HSBC UK BANK"], flag.creditors)
        self.assertNotIn("BANK-STATEMENTS", self._ids(result, "hard_blocks"))
