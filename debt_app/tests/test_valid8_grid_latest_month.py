"""
A Valid8 account's balance is its LATEST reported month (case 436969,
2026-11-19).

A settled O2 loan (Ricky Mitchell) came out at £177 -- December 2023 -- though
it was settled in November 2024 and its 2024 row ends at £0. Two faults:
"Balance: Settled" was not read as £0, so the grid was asked; and the grid's
2024 row started at the foot of a page, so its year label shared a line with
its status codes ("2024 0 0 0 ...") and the reader, matching only a year alone
on its line, skipped to 2023.

The blocks below are the report's own text, as pdfplumber reads it.
"""
from django.test import SimpleTestCase

from debt_app.integrations.credit_report import (
    _parse_valid8_account,
    _valid8_latest_grid_balance_pence,
)

#: The grid of the settled O2 loan: 2024 starts at a page break.
O2_GRID = [
    "Account Status & Balance Details",
    "J F M A M J J A S O N D",
    "2024 0 0 0 0 0 0 0 0 0 0 0 0",
    "£162 £147 £147 £147 £102 £88 £73 £58 £44 £29 £14 £0",
    "0 0 0 0 0 0 0 0 0 0 0 0",
    "2023",
    "£338 £324 £309 £294 £279 £265 £250 £235 £221 £206 £191 £177",
    "0 0 0 0 0 0 0 0 0 0 0 0",
    "2022",
    "£515 £500 £485 £471 £456 £441 £427 £412 £397 £382 £368 £353",
]

O2_SETTLED = [
    "Settled",
    "Date of Birth: 21/08/1987",
    "Company Type: Communications",
    "Account Type: Unsecured Loan (personal loans etc)",
    "Balance: Settled",
    "Company: O2",
    "Settlement Date: 28/11/2024",
    "CAIS Last Updated: 29/12/2024",
    "Account No: MS-219405933-001",
    "Start Date: 13/12/2021",
] + O2_GRID


def _grid(*rows):
    return ["Account Status & Balance Details", "J F M A M J J A S O N D", *rows]


class LatestMonthTests(SimpleTestCase):

    def test_the_settled_o2_loan_is_nil(self):
        account = _parse_valid8_account("", "\n".join(O2_SETTLED))
        self.assertEqual(account["raw_name"], "O2")
        self.assertEqual(account["account_status"], "Settled")
        self.assertEqual(account["current_balance"], 0)

    def test_a_year_label_sharing_its_status_line_is_the_newest_year(self):
        # The same grid ending £14 in 2024: the reader must land on 2024, not
        # on 2023's £177.
        grid = [line.replace("£14 £0", "£29 £14") for line in O2_GRID]
        self.assertEqual(_valid8_latest_grid_balance_pence(grid), 1400)

    def test_an_ordinary_grid_reads_the_newest_years_last_month(self):
        grid = _grid("0 0 0 0 0 0 0 0 0 0 0", "2026",
                     "£152 £61 £31 £45 £59 £105 £166 £184 £178 £173 £183",
                     "0 0 0 0 0 0 0 0 0 0 0 0", "2025",
                     "£139 £186 £191 £154 £185 £179 £174 £168 £185 £158 £165 £168")
        self.assertEqual(_valid8_latest_grid_balance_pence(grid), 18300)

    def test_a_page_header_between_year_and_amounts_is_skipped(self):
        grid = _grid("2026 0 0 0", "OXON, OX29 9QJ", "£300 £200 £100",
                     "0 0 0", "2025", "£900 £800 £700")
        self.assertEqual(_valid8_latest_grid_balance_pence(grid), 10000)

    def test_a_year_with_no_amounts_does_not_borrow_the_next_years(self):
        grid = _grid("2026 0 0", "0 0 0 0", "2025", "£500 £400")
        self.assertEqual(_valid8_latest_grid_balance_pence(grid), 40000)

    def test_a_credit_balance_keeps_its_sign(self):
        grid = _grid("0 0 0", "2025", "£0 -£112 -£16")
        self.assertEqual(_valid8_latest_grid_balance_pence(grid), -1600)

    def test_a_printed_balance_still_wins_over_the_grid(self):
        block = "\n".join(["Active", "Balance: £286.00", "Company: O2",
                           *_grid("0 0", "2026", "£334 £300")])
        self.assertEqual(_parse_valid8_account("", block)["current_balance"], 28600)

    def test_no_grid_is_no_balance(self):
        self.assertIsNone(_valid8_latest_grid_balance_pence(["Company: O2", "Is Historic: False"]))
