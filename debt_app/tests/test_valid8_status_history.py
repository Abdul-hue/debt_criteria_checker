"""
The Valid8 month-by-month record and agreed monthly payment (2026-11-25).

Before this, only the Aryza Advize layout was read for the month-by-month
status, so CAT's 12-month payment check (mortgage, secured loan, vehicle
finance -- `ledger/secured_payments.py`) raised "the credit report shows no
month-by-month payment record for it" on every such account of a Valid8
report (case 438519: three First Response Finance HP agreements), and its
Assets card showed no grid. "Payment Terms: £250 X 48 (Monthly)" was never
read either.

The pages here use the geometry of a real Valid8 report (month letters at
x0 = 78 + ~41.5 per month, year label at x0 = 40, statuses ~5pt above the
year label, balances ~5pt below it and a few points left of their letter).
Names and figures are invented; no PDF fixtures (client documents).

Pinned:
  * a month is its POSITION: a part newest year runs from January, a part
    oldest year ends in December;
  * a grid crossing a page keeps its columns and its account;
  * each account gets its own months, and none when grids and accounts
    differ in number, when a record disagrees with the account's balance,
    or when the reader fails -- the accounts themselves are always kept;
  * the balance (latest month, Rule 1) does not move;
  * only a MONTHLY payment term is read -- nothing is converted.
"""
from unittest import mock

from django.test import SimpleTestCase

from debt_app.integrations import credit_report as cr
from debt_app.integrations.credit_report import _valid8_agreed_monthly_payment_pence

COLS = [78, 119, 160, 202, 243, 286, 327, 368, 410, 451, 493, 534]
LETTERS = "J F M A M J J A S O N D".split()


def _word(text, x0, top):
    return {"text": text, "x0": float(x0), "x1": float(x0 + 4.5 * len(text)),
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


class _Report:
    """Lays a Valid8 report out top to bottom, page by page."""

    def __init__(self):
        self.pages = [[]]
        self.top = 40.0
        self.text("Experian Valid8IP bureau search")

    def _put(self, text, x0):
        self.pages[-1].append(_word(text, x0, self.top))

    def text(self, line):
        self._put(line, 40)
        self.top += 14

    def account(self, company, account_type="Hire Purchase/Conditional Sale",
                balance="Balance: £512.00", terms="Payment Terms: £250 X 48 (Monthly)", grid=True):
        for line in ("MR A TEST", "Address: 1 HIGH STREET, TOWN, AB1 2CD", "Active",
                     "Date of Birth: 01/01/1980", f"Company: {company}",
                     f"Account Type: {account_type}", balance, "Start Date: 01/01/2023",
                     terms, "Account Status & Balance Details"):
            if line:
                self.text(line)
        if not grid:
            return
        for x0, letter in zip(COLS, LETTERS):
            self._put(letter, x0)
        self.top += 14

    def statuses(self, months):
        for month, code in months.items():
            self._put(code, COLS[month - 1] + 1)
        self.top += 5

    def year_label(self, year):
        self._put(str(year), 40)
        self.top += 5

    def balances(self, months):
        for month, amount in months.items():
            self._put(amount, COLS[month - 1] - 4)
        self.top += 17

    def year(self, year, months):
        """`months` = {month: (status, "£balance")}."""
        self.statuses({m: s for m, (s, _b) in months.items()})
        self.year_label(year)
        self.balances({m: b for m, (_s, b) in months.items()})

    def new_page(self):
        self.pages.append([])
        self.top = 40.0

    def extract(self):
        with mock.patch.object(cr.pdfplumber, "open",
                               return_value=_Pdf([_Page(p) for p in self.pages])):
            return cr.extract_credit_report("report.pdf")


def _all(result):
    return result["accounts"] + result["mortgage_accounts"] + result["other_accounts"]


def _by_name(result, name):
    return next(a for a in _all(result) if a["raw_name"] == name)


def _months(account):
    return [(e["month"], e["status"], e["balance"]) for e in account["status_history"]]


class MonthPositionTests(SimpleTestCase):

    def test_a_part_newest_year_runs_from_january_and_a_full_year_is_all_twelve(self):
        report = _Report()
        report.account("FIRST RESPONSE FINANCE LTD")
        report.year(2026, {m: ("0", f"£{600 - m}") for m in range(1, 11)})          # Jan-Oct
        report.year(2025, {m: ("1" if m == 6 else "0", f"£{700 - m}") for m in range(1, 13)})
        account = _by_name(report.extract(), "FIRST RESPONSE FINANCE LTD")
        months = _months(account)
        self.assertEqual(len(months), 22)
        self.assertEqual(months[0], ("2025-01", "0", 69900))
        self.assertEqual(months[5], ("2025-06", "1", 69400))
        self.assertEqual(months[-1], ("2026-10", "0", 59000))
        self.assertEqual(account["latest_reported_month"], "2026-10")

    def test_a_part_oldest_year_ends_in_december_not_january(self):
        report = _Report()
        report.account("FIRST RESPONSE FINANCE LTD")
        report.year(2024, {m: ("0", "£512") for m in range(1, 13)})
        report.year(2023, {11: ("U", "£900"), 12: ("0", "£880")})                 # Nov, Dec only
        months = _months(_by_name(report.extract(), "FIRST RESPONSE FINANCE LTD"))
        self.assertEqual(months[:2], [("2023-11", "U", 90000), ("2023-12", "0", 88000)])

    def test_a_question_mark_month_is_kept_as_printed_like_the_experian_api_route(self):
        report = _Report()
        report.account("LOWELL PORTFOLIO I LTD", account_type="Current Accounts", balance=None)
        report.year(2025, {**{m: ("?", "£0") for m in range(1, 12)}, 12: ("8", "£0")})
        report.year(2024, {8: ("8", "£400"), 9: ("?", "£0")})
        months = _months(_by_name(report.extract(), "LOWELL PORTFOLIO I LTD"))
        self.assertEqual(len(months), 14)
        self.assertEqual(months[:2], [("2024-08", "8", 40000), ("2024-09", "?", 0)])
        self.assertEqual(months[-1], ("2025-12", "8", 0))

    def test_the_balance_is_still_the_latest_month_rule_one(self):
        report = _Report()
        report.account("FIRST RESPONSE FINANCE LTD", balance=None)    # no printed balance
        report.year(2026, {1: ("0", "£530"), 2: ("0", "£512")})
        report.year(2025, {12: ("0", "£550")})
        account = _by_name(report.extract(), "FIRST RESPONSE FINANCE LTD")
        self.assertEqual(account["current_balance"], 51200)
        self.assertEqual(account["status_history"][-1]["balance"], 51200)


class PageBreakTests(SimpleTestCase):

    def test_a_year_whose_balances_open_the_next_page(self):
        report = _Report()
        report.account("FIRST RESPONSE FINANCE LTD")
        report.year(2026, {m: ("0", "£512") for m in range(1, 4)})
        report.statuses({m: "2" if m == 12 else "0" for m in range(1, 13)})
        report.year_label(2025)
        report.new_page()                                   # no header on the new page
        report.balances({m: "£600" for m in range(1, 13)})
        report.year(2024, {12: ("0", "£650")})
        months = _months(_by_name(report.extract(), "FIRST RESPONSE FINANCE LTD"))
        self.assertIn(("2025-12", "2", 60000), months)
        self.assertEqual(months[0], ("2024-12", "0", 65000))
        self.assertEqual(len(months), 1 + 12 + 3)


class OneAccountsMonthsTests(SimpleTestCase):

    def _two_accounts(self):
        report = _Report()
        report.account("FIRST RESPONSE FINANCE LTD")
        report.year(2026, {1: ("0", "£530"), 2: ("0", "£512")})
        report.account("SANTANDER CONSUMER", balance="Balance: £4,100.00")
        report.year(2026, {1: ("3", "£4,200"), 2: ("4", "£4,100")})
        return report

    def test_each_account_gets_its_own_months(self):
        result = self._two_accounts().extract()
        self.assertEqual(_months(_by_name(result, "FIRST RESPONSE FINANCE LTD")),
                         [("2026-01", "0", 53000), ("2026-02", "0", 51200)])
        self.assertEqual(_months(_by_name(result, "SANTANDER CONSUMER")),
                         [("2026-01", "3", 420000), ("2026-02", "4", 410000)])

    def test_grids_and_accounts_differing_in_number_give_no_account_a_record(self):
        report = _Report()
        report.account("FIRST RESPONSE FINANCE LTD")
        report.year(2026, {1: ("0", "£530"), 2: ("0", "£512")})
        report.account("SANTANDER CONSUMER", balance="Balance: £4,100.00", grid=False)
        result = report.extract()
        self.assertEqual(len(_all(result)), 2)
        for account in _all(result):
            self.assertEqual(account["status_history"], [])
            self.assertIsNone(account["latest_reported_month"])

    def test_a_record_that_disagrees_with_its_account_is_dropped(self):
        wrong = [[{"month": "2026-02", "status": "0", "balance": 99900}],
                 [{"month": "2026-02", "status": "4", "balance": 410000}]]
        with mock.patch.object(cr, "_extract_valid8_status_histories", return_value=wrong):
            result = self._two_accounts().extract()
        self.assertEqual(_by_name(result, "FIRST RESPONSE FINANCE LTD")["status_history"], [])
        self.assertEqual(len(_by_name(result, "SANTANDER CONSUMER")["status_history"]), 1)

    def test_a_failed_read_keeps_every_account_and_balance(self):
        with mock.patch.object(cr, "_extract_valid8_status_histories", side_effect=RuntimeError("boom")):
            result = self._two_accounts().extract()
        self.assertEqual(len(_all(result)), 2)
        self.assertEqual(_by_name(result, "SANTANDER CONSUMER")["current_balance"], 410000)
        self.assertEqual(_by_name(result, "SANTANDER CONSUMER")["status_history"], [])


class AgreedMonthlyPaymentTests(SimpleTestCase):

    def _terms(self, value):
        return _valid8_agreed_monthly_payment_pence([f"Payment Terms: {value}"])

    def test_a_monthly_term_is_read_in_pence(self):
        self.assertEqual(self._terms("£250 X 48 (Monthly)"), 25000)
        self.assertEqual(self._terms("£1,020 X 9 (Monthly)"), 102000)

    def test_the_mojibake_pound_sign_is_read(self):
        self.assertEqual(self._terms("�85 X 12 (Monthly)"), 8500)

    def test_a_weekly_term_is_not_converted(self):
        self.assertIsNone(self._terms("£30 X 9 (Weekly)"))

    def test_no_terms_is_none(self):
        self.assertIsNone(_valid8_agreed_monthly_payment_pence(["Balance: £512.00"]))

    def test_it_reaches_the_account(self):
        report = _Report()
        report.account("FIRST RESPONSE FINANCE LTD")
        report.year(2026, {1: ("0", "£512")})
        self.assertEqual(_by_name(report.extract(), "FIRST RESPONSE FINANCE LTD")["agreed_monthly_payment"],
                         25000)
