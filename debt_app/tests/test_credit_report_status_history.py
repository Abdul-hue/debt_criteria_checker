"""
The Aryza Advize month-by-month status history, the agreed monthly payment and
the account's Last Update (`integrations/credit_report.py`).

What these pin down
-------------------
The text layer flattens a partial year ("2026 - - - - - -") so that a status
can no longer be tied to its month: Jan-Jun 2026 sit at the LEFT of their row
and May-Dec 2024 at the RIGHT, and only the x-position tells them apart. The
history is therefore read from word POSITIONS, and these tests drive it with
pages built from the geometry of a real report (Shuttleworth, page 7: month
header x0 = 108 + ~34.7 per month, year label x0 = 83, a row's balance ~5pt
above its label and its status ~5pt below, rows ~21.5pt apart). Figures and
names are invented. No PDF fixtures: media/ is gitignored.

The status is the DIGIT as printed, never the cell colour -- the colour is only
the report's drawing of the digit. A "-" cell is no data and is not a month.
"""
from unittest import mock

from django.test import SimpleTestCase

from debt_app.integrations import credit_report as cr
from debt_app.integrations.credit_report import (
    _extract_agreed_monthly_payment_pence,
    _extract_status_histories,
    _parse_account_block,
)

MONTH_X0 = [108, 143, 177, 212, 247, 281, 316, 351, 386, 420, 455, 490]
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def _word(text, x0, top, width=None):
    width = width if width is not None else 4.5 * len(text)
    return {"text": text, "x0": float(x0), "x1": float(x0 + width),
            "top": float(top), "bottom": float(top + 7)}


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


class _Writer:
    """Lays words out top to bottom the way an Aryza Advize page does."""

    def __init__(self, top=60.0):
        self.top = top
        self.words = []

    def line(self, *parts, gap=14.0):
        for text, x0 in parts:
            self.words.append(_word(text, x0, self.top))
        self.top += gap

    def header(self, name, code, *, payments="Monthly X £308", last_update="2026-06-30",
               balance="£16375"):
        self.line((name, 73), (code, 73 + 5 * len(name) + 5), gap=33)
        self.line(("Account", 73), ("Details:", 104), gap=15)
        self.line(("Credit", 73), ("Limit:", 96), ("N/A", 148), ("Payments:", 298),
                  *[(p, 374 + 30 * i) for i, p in enumerate(payments.split())])
        self.line(("Current", 73), ("Balance:", 101), (balance, 148), ("Last", 298),
                  ("Update:", 314), (last_update, 374))

    def section(self, title, months=MONTHS):
        self.line((title, 72), gap=29.6)
        self.line(*[(m, x) for m, x in zip(months, MONTH_X0)], gap=11.8)

    def row(self, year, cells, *, label_on_balance_line=False):
        """`cells`: 12 entries, each `(balance, status)` or None for a "-"
        cell. The year label sits between the balance and the status, as on
        the real page -- or on the balance's own line, as on chelsea_bone's
        2022 row, with the status ~10pt below it."""
        balance_top, label_top = self.top, self.top + (0 if label_on_balance_line else 4.8)
        status_top = label_top + (9.7 if label_on_balance_line else 4.9)
        self.words.append(_word(year, 83, label_top, width=17))
        for x0, cell in zip(MONTH_X0, cells):
            if cell is None:
                self.words.append(_word("-", x0 + 16, label_top, width=3))
                continue
            balance, status = cell
            if balance is not None:
                self.words.append(_word(balance, x0 + 5, balance_top))
            if status is not None:
                self.words.append(_word(status, x0 + 15, status_top, width=4))
        self.top = balance_top + 21.5

    def page(self):
        page, self.words = _Page(self.words), []
        return page


def _year(statuses, balance="£1,000"):
    """12 cells from a 12-character status string; "-" is a no-data cell."""
    return [None if s == "-" else (balance, s) for s in statuses]


class StatusHistoryTests(SimpleTestCase):
    def _history(self, *pages):
        histories = _extract_status_histories(_Pdf(list(pages)))
        return histories

    def test_partial_current_year_keeps_its_months(self):
        # "2026 - - - - - -" with Jan-Jun reported: the old text reader never
        # recognised that line as a year at all.
        w = _Writer()
        w.header("Lloyds Banking Group Asset Finance", "HP")
        w.section("Balance")
        w.row("2026", _year("000000------"))
        w.row("2025", _year("000000000000"))
        [(header, history)] = self._history(w.page())
        self.assertEqual(header, "Lloyds Banking Group Asset Finance HP")
        months = [e["month"] for e in history]
        self.assertEqual(months[-6:], ["2026-01", "2026-02", "2026-03",
                                       "2026-04", "2026-05", "2026-06"])
        self.assertEqual(len(history), 18)
        self.assertNotIn("2026-07", months)

    def test_months_come_from_position_not_order(self):
        # May-Dec at the RIGHT of the row: eight values, but not Jan-Aug.
        w = _Writer()
        w.header("Motonovo Finance", "HP", payments="Monthly X £120")
        w.section("Balance")
        w.row("2024", _year("----00000000"))
        [(_, history)] = self._history(w.page())
        self.assertEqual([e["month"] for e in history],
                         [f"2024-{m:02d}" for m in range(5, 13)])

    def test_each_status_is_tied_to_its_own_month(self):
        w = _Writer()
        w.header("Moneybarn", "HP")
        w.section("Balance")
        w.row("2026", _year("0012DU?0----"))
        [(_, history)] = self._history(w.page())
        self.assertEqual({e["month"]: e["status"] for e in history}, {
            "2026-01": "0", "2026-02": "0", "2026-03": "1", "2026-04": "2",
            "2026-05": "D", "2026-06": "U", "2026-07": "?", "2026-08": "0"})

    def test_statuses_are_returned_raw_and_dashes_are_not_months(self):
        # Nothing is translated: an unknown code is kept as printed for the
        # caller to refuse; "-" means the lender reported nothing that month.
        w = _Writer()
        w.header("Advantage Finance", "HP")
        w.section("Balance")
        w.row("2026", [None] * 5 + [("£16,010", "AP")] + [None] * 6)
        [(_, history)] = self._history(w.page())
        self.assertEqual(history, [{"month": "2026-06", "status": "AP", "balance": 1601000}])

    def test_balance_is_kept_in_pence_beside_its_status(self):
        w = _Writer()
        w.header("Lloyds Banking Group Asset Finance", "HP")
        w.section("Balance")
        w.row("2026", [("£17,918", "0"), ("£17,609", "0"), ("£17,301", "0")] + [None] * 9)
        [(_, history)] = self._history(w.page())
        self.assertEqual([e["balance"] for e in history], [1791800, 1760900, 1730100])

    def test_label_on_the_balance_line_still_finds_its_statuses(self):
        # chelsea_bone, 2022: the label shares the balance's line and the
        # statuses sit ~10pt below -- an 8pt reach lost all twelve.
        w = _Writer()
        w.header("Everyday Loans LTD", "UL")
        w.section("Balance")
        w.row("2023", _year("000000000000"))
        w.row("2022", _year("220001234566"), label_on_balance_line=True)
        w.row("2021", _year("000000000000"))
        [(_, history)] = self._history(w.page())
        by_month = {e["month"]: e["status"] for e in history}
        self.assertEqual("".join(by_month[f"2022-{m:02d}"] for m in range(1, 13)), "220001234566")
        self.assertEqual(by_month["2021-12"], "0")
        self.assertEqual(by_month["2023-01"], "0")

    def test_a_row_cut_by_a_page_break_is_completed_from_the_next_page(self):
        # Topp, page 1 -> 2: the 2023 balances end page 1; their statuses
        # open page 2 with no year label and no month header.
        w = _Writer()
        w.header("Lloyds Bank Mortgages LTD", "MG", payments="Monthly X £839")
        w.section("Balance")
        w.row("2024", _year("000000000000"))
        w.words.append(_word("2023", 83, w.top, width=17))
        for x0 in MONTH_X0:
            w.words.append(_word("£113,365", x0 + 3, w.top))
        first = w.page()
        second = _Writer(top=76.2)
        second.line(*[("1" if i == 11 else "0", x0 + 15) for i, x0 in enumerate(MONTH_X0)])
        [(_, history)] = self._history(first, second.page())
        by_month = {e["month"]: e for e in history}
        self.assertEqual(by_month["2023-01"], {"month": "2023-01", "status": "0", "balance": 11336500})
        self.assertEqual(by_month["2023-12"]["status"], "1")
        self.assertEqual(len(history), 24)

    def test_a_short_month_header_still_places_every_column(self):
        # Price, Loans 2 Go: the header's text layer stops at "Oct".
        w = _Writer()
        w.header("Loans 2 Go LTD", "UL")
        w.section("Balance", months=MONTHS[:10])
        w.row("2025", _year("000000000011"))
        [(_, history)] = self._history(w.page())
        self.assertEqual([e["status"] for e in history if e["month"] >= "2025-11"], ["1", "1"])

    def test_only_the_balance_grid_is_read_and_accounts_do_not_bleed(self):
        w = _Writer()
        w.header("Capital One", "CC", payments="Monthly")
        w.section("Balance")
        w.row("2026", _year("000---------"))
        w.section("Payment Amount")
        w.row("2026", _year("111---------"))
        w.header("Moneybarn", "HP")
        w.section("Balance")
        w.row("2026", _year("0D0---------"))
        histories = self._history(w.page())
        self.assertEqual([h for h, _ in histories], ["Capital One CC", "Moneybarn HP"])
        self.assertEqual([e["status"] for e in histories[0][1]], ["0", "0", "0"])
        self.assertEqual([e["status"] for e in histories[1][1]], ["0", "D", "0"])


class AccountHeaderFieldTests(SimpleTestCase):
    BLOCK = "\n".join([
        "Account Details:",
        "Account Type: Hire Purchase",
        "Account Status: Up to date Good",
        "Credit Limit: £N/A Payments: Monthly X £308",
        "Minimum Payment: No Promotional Rate: No",
        "Current Balance: £16375 Last Update: 2026-06-30",
        "Start Balance: £24088 Start Date: 2024-05-10",
        "Default Balance: N/A End Date: N/A",
        "Balance",
    ])

    def test_agreed_monthly_payment_from_the_header(self):
        self.assertEqual(_extract_agreed_monthly_payment_pence("Payments: Monthly X £308"), 30800)
        # The currency glyph is mojibake in some exports (see `_parse_amount`).
        self.assertEqual(_extract_agreed_monthly_payment_pence("Payments: Monthly X �120"), 12000)

    def test_no_amount_printed_is_none_not_invented(self):
        self.assertIsNone(_extract_agreed_monthly_payment_pence("Credit Limit: £7500 Payments: Monthly"))
        self.assertIsNone(_extract_agreed_monthly_payment_pence("Payments: Weekly X £70"))

    def test_account_block_carries_the_new_fields(self):
        account = _parse_account_block("Lloyds Banking Group Asset Finance HP", self.BLOCK)
        self.assertEqual(account["agreed_monthly_payment"], 30800)
        self.assertEqual(account["last_update"], "2026-06-30")
        # The block text cannot place a month; the history is filled from
        # word positions by `extract_credit_report`.
        self.assertEqual(account["status_history"], [])
        self.assertIsNone(account["latest_reported_month"])
        # Unchanged: the Payment Amount grid's figure, which an HP account
        # does not have -- the criteria engine reads this for mortgages.
        self.assertIsNone(account["monthly_payment"])

    def test_last_update_that_is_not_a_date_is_none(self):
        account = _parse_account_block("Lloyds Banking Group Asset Finance HP",
                                       self.BLOCK.replace("2026-06-30", "N/A"))
        self.assertIsNone(account["last_update"])


class ExtractCreditReportTests(SimpleTestCase):
    """End to end through `extract_credit_report`, the shape the upload
    endpoint returns to the case-assessment-tool."""

    def _extract(self, *pages):
        with mock.patch.object(cr.pdfplumber, "open", return_value=_Pdf(list(pages))):
            return cr.extract_credit_report("report.pdf")

    def test_hp_account_carries_history_payment_and_last_update(self):
        w = _Writer()
        w.line(("Debt", 78), ("Overview", 103))
        w.header("Lloyds Banking Group Asset Finance", "HP")
        w.section("Balance")
        w.row("2026", _year("000000------"))
        w.row("2025", _year("000000000000"))
        result = self._extract(w.page())
        self.assertNotIn("extraction_error", result)
        [account] = result["accounts"]
        self.assertEqual(account["type_code"], "HP")
        self.assertEqual(account["agreed_monthly_payment"], 30800)
        self.assertEqual(account["last_update"], "2026-06-30")
        self.assertEqual(account["latest_reported_month"], "2026-06")
        self.assertEqual([e["status"] for e in account["status_history"][-3:]], ["0", "0", "0"])

    def test_two_accounts_with_the_same_header_keep_their_own_history(self):
        w = _Writer()
        w.line(("Debt", 78), ("Overview", 103))
        for statuses in ("0001--------", "0D----------"):
            w.header("Klarna", "DP", payments="Monthly X £27")
            w.section("Balance")
            w.row("2026", _year(statuses))
        result = self._extract(w.page())
        self.assertEqual([[e["status"] for e in a["status_history"]] for a in result["accounts"]],
                         [["0", "0", "0", "1"], ["0", "D"]])

    def test_a_failed_position_read_never_costs_the_accounts(self):
        w = _Writer()
        w.line(("Debt", 78), ("Overview", 103))
        w.header("Moneybarn", "HP")
        with mock.patch.object(cr, "_extract_status_histories", side_effect=RuntimeError("boom")):
            result = self._extract(w.page())
        [account] = result["accounts"]
        self.assertEqual(account["status_history"], [])
        self.assertEqual(account["agreed_monthly_payment"], 30800)
