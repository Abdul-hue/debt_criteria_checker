"""
The TransUnion "SHARE" credit report (2026-11-25, case 438769).

Before this, a TransUnion report fell through to the Aryza Advize reader and
came out with no accounts at all: 438769's five Aryza debts (Abound £13,897,
MBNA £8,059, Monzo £6,775, Payment Assist £106, PayPal £131), all on the
report to the pound, read "Aryza only, needs proof of debt".

The pages here use the geometry of that real report -- field labels at x0 21
and 304, year labels at 28, month headers centred over columns of UNEVEN
width (Monzo's grid: Sep at 346, Oct at 421, Nov at 496), statuses centred
in their cell, sub-sections at 16, top-level headings at 5. Names and figures
are invented; no PDF fixtures (client documents).

Pinned:
  * the report is read by its own reader, every account kept, agency TransUnion;
  * the balance is the account's own "Balance:" line; the grid's newest month
    only when none is printed;
  * a month is its POSITION under the header, never its place in the row;
  * a wrapped status joins its cell; a long one is placed by its centre;
  * a grid crossing a page keeps its columns and year;
  * MODA's repeated accounts are never read (no double count);
  * printed statuses become the bureau codes CAT reads; an unknown one is
    kept as printed, never "0";
  * every printed field is kept; the account line beside a field is split;
  * a judgment or insolvency of an unseen layout is taken as present.
"""
from unittest import mock

from django.test import SimpleTestCase

from debt_app.integrations import credit_report as cr
from debt_app.integrations import transunion_report as tu
from debt_app.integrations.account_categories import SOURCE_TRANSUNION_PDF

CHAR = 2.6          # points per character: "Dormant/inactive" is 41.5pt on the report
SPACE = 1.2         # the gap between two words of one phrase

#: Month header centres from the real report's Monzo Loans grid -- uneven.
COLS = {1: 59, 2: 92, 3: 125.6, 4: 158.5, 5: 193, 6: 228, 7: 258.5,
        8: 290.5, 9: 346, 10: 421, 11: 496, 12: 551}
#: NewDay's dormant grid: the centres of its real "Dormant/inactive" cells
#: (x0 45, 91, 136 ... 546, each 41.5pt wide) -- ~5pt apart, the tightest.
WIDE_COLS = {m: x0 + 20.75 for m, x0 in enumerate(
    (45, 91, 136, 182, 227, 273, 318, 364, 409, 455, 500, 546), 1)}
#: Lendable's grid: May widened to hold its long status, the rest squeezed.
LENDABLE_COLS = {m: x0 + 5 for m, x0 in enumerate(
    (50, 73, 96, 120, 266, 413, 437, 459, 482, 506, 529, 552), 1)}
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def _phrase(text, x0, top):
    words, x = [], x0
    for token in text.split():
        word = {"text": token, "x0": float(x), "x1": float(x + CHAR * len(token)),
                "top": float(top), "bottom": float(top + 7)}
        words.append(word)
        x = word["x1"] + SPACE
    return words


def _width(text):
    return CHAR * len(text.replace(" ", "")) + SPACE * text.count(" ")


class _Page:
    def __init__(self, words):
        self._words = words

    def extract_words(self):
        return list(self._words)

    def extract_text(self):
        lines = {}
        for w in sorted(self._words, key=lambda w: (w["top"], w["x0"])):
            key = next((k for k in lines if abs(k - w["top"]) <= 1.0), w["top"])
            lines.setdefault(key, []).append(w["text"])
        return "\n".join(" ".join(lines[k]) for k in sorted(lines))


class _Pdf:
    def __init__(self, pages):
        self.pages = pages

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _Report:
    """Lays a TransUnion report out top to bottom, page by page."""

    def __init__(self, judgments="No data was retrieved for this section"):
        self.pages = [[]]
        self.top = 15.0
        self.cols = COLS
        self.line(("Consumer Credit Report", 5))
        self.line(("Search Details", 162))
        self.line(("Provider: TransUnion", 162))
        self.line(("Credit Score: 620", 162))
        self.line(("Name: Mr Alex Test", 162))
        self.line(("Search Date: 22/11/2026", 162))
        self.line(("Current Address: 1 Test Street, Town AB1 2CD", 162))
        self.line(("Public Information", 5))
        self.line(("Insolvencies", 16), ("No data was retrieved for this section", 249))
        self.line(("Judgments", 16), (judgments, 249) if judgments.startswith("No data")
                  else (judgments, 60))
        self.line(("Financial Account Information (SHARE)", 5))

    def line(self, *parts, step=8.0):
        for text, x0 in parts:
            self.pages[-1].extend(_phrase(text, x0, self.top))
        self.top += step

    def new_page(self):
        self.pages.append([])
        self.top = 15.0

    def section(self, name):
        self.line((name, 16))

    def account(self, lender, balance="£512.00", *, account_type="Unsecured Loan",
                status="Up to date", header="Mr Alex Test || 101 || || 1 Test Street Town AB1 2CD "
                "|| 01/01/1980 01/06/2026 00:00:00 || ||", header_with_opening=None,
                opening="£600.00", regular="£40.00", frequency="Monthly",
                acc_number="ABC123 0", extra=()):
        if header_with_opening:
            # The account line running up to the right-hand field, no gap.
            self.line((f"{header} Opening Balance: {header_with_opening}", 25))
        else:
            self.line((header, 25))
        left = [f"Lender: {lender}"]
        if balance is not None:
            left.append(f"Balance: {balance}")
        left += ["Currency Code: GBP", "Payment Start Date: 01/06/2026",
                 "Update Date: 01/11/2026", f"Status: {status}",
                 "Status Subjective Lvl: Good", f"Acc Number: {acc_number}",
                 "Start Date: 01/06/2026", *extra]
        right = [] if header_with_opening else [f"Opening Balance: {opening}"]
        right += [f"Regular Pay Amount: {regular}", f"Repayment Frequency: {frequency}",
                  f"Account Type Name: {account_type}", "Promotional Rate: False",
                  "Minimum Payment: False", "Account Id: 999"]
        for i in range(max(len(left), len(right))):
            parts = []
            if i < len(left):
                parts.append((left[i], 21))
            if i < len(right):
                parts.append((right[i], 304))
            self.line(*parts)

    def grid(self, title, rows, *, header=True, cols=None):
        """`rows` = [(year, {month: text or (line1, line2)})], newest first."""
        self.cols = cols or COLS
        self.line((f"{title} History", 26), step=12.0)
        if header:
            self.month_header()
        for year, cells in rows:
            self.year_row(year, cells)

    def month_header(self):
        self.line(*[(name, self.cols[m] - _width(name) / 2) for m, name in enumerate(MONTHS, 1)],
                  step=10.0)

    def year_row(self, year, cells):
        firsts = [(year and str(year), 28)] if year else []
        wrapped = {}
        for month, text in cells.items():
            first, second = (text, None) if isinstance(text, str) else text
            firsts.append((first, self.cols[month] - _width(first) / 2))
            if second:
                wrapped[month] = second
        self.line(*firsts, step=7.6 if wrapped else 12.6)
        if wrapped:
            self.line(*[(t, self.cols[m] - _width(t) / 2) for m, t in wrapped.items()], step=12.6)

    def extract(self):
        with mock.patch.object(cr.pdfplumber, "open",
                               return_value=_Pdf([_Page(p) for p in self.pages])):
            return cr.extract_credit_report("report.pdf")


def _all(result):
    return result["accounts"] + result["mortgage_accounts"] + result["other_accounts"]


def _named(result, name):
    return next(a for a in _all(result) if a["raw_name"] == name)


def _months(account):
    return [(e["month"], e["status"]) for e in account["status_history"]]


class ReadByItsOwnReaderTests(SimpleTestCase):

    def test_the_accounts_are_read_and_the_agency_is_transunion(self):
        report = _Report()
        report.section("Personal Loans")
        report.account("Monzo Loans", "£6,775.00", opening="£7,000.00", regular="£185.00")
        report.grid("Balance", [(2026, {9: "£7,000", 10: "£6,887", 11: "£6,775"})])
        report.grid("Status", [(2026, {9: "Ok", 10: "Ok", 11: "Ok"})])
        result = report.extract()

        self.assertEqual(result["agency"], "TransUnion")
        self.assertEqual(result["report_date"], "2026-11-22")
        self.assertEqual(result["credit_score"], 620)
        account = _named(result, "Monzo Loans")
        self.assertEqual(account["current_balance"], 677500)
        self.assertEqual(account["start_balance"], 700000)
        self.assertEqual(account["agreed_monthly_payment"], 18500)
        self.assertEqual(account["type_code"], "UL")
        self.assertEqual(account["source_system"], SOURCE_TRANSUNION_PDF)
        self.assertEqual(account["source_account_type"], "Unsecured Loan")
        self.assertEqual(account["account_status"], "Up to date")
        self.assertEqual(account["start_date"], "2026-06-01")
        self.assertEqual(account["last_update"], "2026-11-01")
        self.assertEqual(account["report_section"], "Personal Loans")
        self.assertIn(account, result["accounts"])

    def test_every_printed_field_is_kept_as_printed(self):
        report = _Report()
        report.account("Lender One", extra=("Default Date: 01/02/2025",))
        fields = _named(report.extract(), "Lender One")["report_fields"]
        for label in ("Lender", "Balance", "Opening Balance", "Regular Pay Amount",
                      "Repayment Frequency", "Account Type Name", "Status",
                      "Status Subjective Lvl", "Acc Number", "Account Id",
                      "Promotional Rate", "Minimum Payment", "Default Date"):
            self.assertIn(label, fields)
        self.assertEqual(fields["Acc Number"], "ABC123 0")

    def test_the_account_line_running_into_a_field_keeps_both(self):
        report = _Report()
        report.account("Fintern LTD T/A Abound Loans", "£13,897.00",
                       header_with_opening="£14,958.00")
        account = _named(report.extract(), "Fintern LTD T/A Abound Loans")
        self.assertEqual(account["start_balance"], 1495800)
        self.assertEqual(account["current_balance"], 1389700)
        self.assertEqual(account["account_holder"], "Mr Alex Test")
        self.assertEqual(account["address"], "1 Test Street Town AB1 2CD")
        self.assertEqual(account["date_of_birth"], "1980-01-01")

    def test_the_account_number_loses_its_separate_suffix_digit(self):
        for printed, expected in (("100227757920 0", "100227757920"),
                                  ("609468744 2", "609468744"),
                                  ("2201682625 000 0", "2201682625 000")):
            report = _Report()
            report.account("Lender One", acc_number=printed)
            self.assertEqual(_named(report.extract(), "Lender One")["account_number"], expected)


class BalanceTests(SimpleTestCase):

    def test_the_balance_line_wins_over_the_grid(self):
        report = _Report()
        report.account("Lender One", "£500.00")
        report.grid("Balance", [(2026, {10: "£520", 11: "£510"})])
        self.assertEqual(_named(report.extract(), "Lender One")["current_balance"], 50000)

    def test_no_balance_line_reads_the_grids_newest_month(self):
        report = _Report()
        report.account("Lender One", None)
        report.grid("Balance", [(2026, {9: "£530", 10: "£520"}), (2025, {12: "£900"})])
        self.assertEqual(_named(report.extract(), "Lender One")["current_balance"], 52000)

    def test_a_settled_balance_is_nothing_owed(self):
        report = _Report()
        report.account("Lender One", "Settled", status="Settled")
        self.assertEqual(_named(report.extract(), "Lender One")["current_balance"], 0)


class MonthPositionTests(SimpleTestCase):

    def test_a_part_year_lands_under_its_own_months(self):
        report = _Report()
        report.account("Monzo Loans", "£6,775.00")
        report.grid("Balance", [(2026, {9: "£7,000", 10: "£6,887", 11: "£6,775"})])
        report.grid("Status", [(2026, {9: "Ok", 10: "Ok", 11: "Ok"})])
        account = _named(report.extract(), "Monzo Loans")
        self.assertEqual(_months(account), [("2026-09", "0"), ("2026-10", "0"), ("2026-11", "0")])
        self.assertEqual([e["balance"] for e in account["status_history"]], [700000, 688700, 677500])
        self.assertEqual(account["latest_reported_month"], "2026-11")

    def test_an_oldest_part_year_ends_in_december(self):
        report = _Report()
        report.account("Rci Financial Services LTD", "£2,998.00", account_type="Hire Purchase")
        report.grid("Status", [(2026, {m: "Ok" for m in range(1, 11)}),
                               (2024, {10: "Ok", 11: "Ok", 12: "Ok"})])
        account = _named(report.extract(), "Rci Financial Services LTD")
        self.assertEqual(account["type_code"], "HP")
        self.assertEqual(_months(account)[:3], [("2024-10", "0"), ("2024-11", "0"), ("2024-12", "0")])
        self.assertEqual(_months(account)[-1], ("2026-10", "0"))

    def test_a_wrapped_status_joins_its_cell(self):
        report = _Report()
        report.account("Newday LTD", "£0.00", account_type="Credit Card")
        report.grid("Status", [(2026, {m: ("Dormant/inactive", "account") for m in range(1, 11)})],
                    cols=WIDE_COLS)
        account = _named(report.extract(), "Newday LTD")
        self.assertEqual(_months(account), [(f"2026-{m:02d}", "D") for m in range(1, 11)])
        self.assertEqual(account["status_history"][0]["status_printed"], "Dormant/inactive account")

    def test_a_long_status_is_placed_by_its_centre(self):
        report = _Report()
        report.account("Lendable LTD", "£0.00")
        report.grid("Status", [(2021, {5: "Unclassified or recently opened account payment delay",
                                       6: "Ok", 7: "Ok"})], cols=LENDABLE_COLS)
        self.assertEqual(_months(_named(report.extract(), "Lendable LTD")),
                         [("2021-05", "U"), ("2021-06", "0"), ("2021-07", "0")])

    def test_a_grid_crossing_a_page_keeps_its_columns(self):
        report = _Report()
        report.account("Lender One", "£25.00")
        report.grid("Status", [])
        report.new_page()
        report.year_row(2024, {8: "Ok", 9: "Ok", 10: "Settled/closed"})
        self.assertEqual(_months(_named(report.extract(), "Lender One")),
                         [("2024-08", "0"), ("2024-09", "0"), ("2024-10", "S")])


class StatusCodeTests(SimpleTestCase):

    def test_known_words_become_the_codes_cat_reads(self):
        self.assertEqual(tu.status_code("Ok"), "0")
        self.assertEqual(tu.status_code("Dormant/inactive  account"), "D")
        self.assertEqual(tu.status_code("Settled/closed"), "S")
        self.assertEqual(tu.status_code("Default"), "8")
        self.assertEqual(tu.status_code("2 payments late"), "2")

    def test_an_unknown_word_is_kept_as_printed_never_paid(self):
        self.assertEqual(tu.status_code("Query"), "Query")
        self.assertNotEqual(tu.status_code("Arrangement"), "0")

    def test_worst_status_and_missed_payments_follow_the_codes(self):
        report = _Report()
        report.account("Lender One", "£900.00")
        report.grid("Status", [(2026, {8: "Ok", 9: "1 payment late", 10: "2 payments late"})])
        account = _named(report.extract(), "Lender One")
        self.assertEqual(account["worst_status"], "2 Months Delinquent")
        self.assertEqual(account["missed_payments_last_3_months"], 3)


class OtherGridsTests(SimpleTestCase):

    def test_credit_limit_and_payment_come_from_their_grids(self):
        report = _Report()
        report.account("Paypal (Europe) Sarl Et Cie Sca", "£131.00", account_type="Credit Card")
        report.grid("Balance", [(2026, {9: "£140.00", 10: "£131.00"})])
        report.grid("Payment", [(2026, {8: "£263.00", 9: "£0.00", 10: "£30.00"})])
        report.grid("Limit", [(2026, {9: "£3,500.00", 10: "£3,500.00"})])
        report.grid("Statement Balance", [(2026, {10: "£0.00"})])
        account = _named(report.extract(), "Paypal (Europe) Sarl Et Cie Sca")
        self.assertEqual(account["type_code"], "CC")
        self.assertEqual(account["credit_limit"], 350000)
        self.assertEqual(account["monthly_payment"], 3000)
        self.assertTrue(account["recent_spending"])
        self.assertEqual(account["limit_history"][-1], {"month": "2026-10", "amount": 350000})
        self.assertEqual(account["statement_balance_history"], [{"month": "2026-10", "amount": 0}])

    def test_a_payment_that_is_not_monthly_is_not_converted(self):
        report = _Report()
        report.account("Monzo Bank", "£0.00", account_type="Current Account",
                       frequency="Periodically")
        account = _named(report.extract(), "Monzo Bank")
        self.assertIsNone(account["agreed_monthly_payment"])
        self.assertEqual(account["type_code"], "CA")


class SectionTests(SimpleTestCase):

    def test_closed_accounts_are_marked_and_settled_stays_settled(self):
        report = _Report()
        report.section("Closed Accounts")
        report.account("Mbna Loans", "£0.00", status="Settled",
                       extra=("End Date: 22/01/2024",))
        report.section("Personal Loans")
        report.account("Mbna Loans", "£8,059.00")
        result = report.extract()
        closed, open_ = [a for a in _all(result) if a["raw_name"] == "Mbna Loans"]
        self.assertTrue(closed["closed"])
        self.assertEqual(closed["account_status"], "Settled")
        self.assertEqual(closed["end_date"], "2024-01-22")
        self.assertFalse(open_["closed"])
        self.assertEqual(open_["current_balance"], 805900)

    def test_moda_repeats_are_never_read(self):
        report = _Report()
        report.account("Lender One", "£500.00")
        report.line(("Search History", 5))
        report.line(("MODA", 5))
        report.section("Accounts")
        report.account("Lender One", "£500.00")
        result = report.extract()
        self.assertEqual([a["raw_name"] for a in _all(result)], ["Lender One"])

    def test_types_are_routed_like_every_other_report(self):
        report = _Report()
        report.account("Bfsl Motor & Home Insurance", "£0.00", account_type="Motor Insurance")
        report.account("Raylo Limited", "£0.00", account_type="Telecommunications Supplier")
        report.account("Klarna Pay Later", "£0.00", account_type="Deferred Payment Credit")
        report.account("M&S Bank", "£0.00", account_type="Loan (unspecified type)")
        result = report.extract()
        self.assertIn(_named(result, "Bfsl Motor & Home Insurance"), result["other_accounts"])
        self.assertEqual(_named(result, "Raylo Limited")["type_code"], "TM")
        self.assertEqual(_named(result, "Klarna Pay Later")["type_code"], "DP")
        unspecified = _named(result, "M&S Bank")
        self.assertEqual((unspecified["type_code"], unspecified["type_unmapped"]), ("OT", True))


class PublicInformationTests(SimpleTestCase):

    def test_no_data_is_a_clean_file(self):
        result = _Report().extract()
        self.assertFalse(result["has_ccj"])
        self.assertEqual(result["public_information"]["transunion_unread_records"], [])

    def test_a_judgment_of_an_unseen_layout_is_taken_as_present(self):
        result = _Report(judgments="Court: Northampton Amount: £1,200 Date: 01/03/2025").extract()
        self.assertTrue(result["has_ccj"])
        self.assertGreaterEqual(result["public_information"]["ccj_count"], 1)
        self.assertEqual(result["public_information"]["transunion_unread_records"], ["Judgments"])
