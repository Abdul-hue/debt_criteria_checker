"""
A Valid8 record with a "Delinquent" badge is its own account (case 436877,
2026-11-19).

The splitter opened a record only on "Active" / "Settled" / "Default". The
British Gas record's badge was "Delinquent", so its lines were glued onto the
dormant ZILCH record above it, and `_parse_valid8_account` -- first of every
field -- read one account: ZILCH's name, number, start date and type with
British Gas's £13,218 balance (Zilch prints no "Balance:" line). CAT showed a
£13,218 Zilch credit card that is not on the report, and the real British Gas
debt was missing.

The two records below are the report's own text, as the screenshots show it.
"""
from django.test import SimpleTestCase

from debt_app.integrations.credit_report import (
    _VALID8_STATUS_WORDS,
    _parse_valid8_account,
    _split_valid8_accounts,
)
from debt_app.integrations.experian_mapper import ACCOUNT_STATUS_LABELS

ZILCH = [
    "CHRISTOPHER BOARDMAN",
    "Address: 35, THE AVENUE, PRESTON, PR1 0SU",
    "Active",
    "Date of Birth: 04/01/1990",
    "Company Type: Finance House",
    "Account Type: Budget (revolving account)",
    "Company: ZILCH TECHNOLOGY LIMITED",
    "CAIS Last Updated: 01/11/2026",
    "Account No: C01927833",
    "Credit Limit: £180.00",
    "Start Date: 20/12/2021",
    "Joint Account: No",
    "Is Historic: False",
    "Worst Status: D (Dormant)",
    "Account Status & Balance Details",
]


def _british_gas(badge="Delinquent"):
    return [
        "MR CHRISTOPHER PAUL BOARDMAN",
        "Address: 35, THE AVENUE, PRESTON, PR1 0SU",
        badge,
        "Date of Birth: 04/01/1990",
        "Company Type: Utility",
        "Account Type: Public Utility",
        "Balance: £13,218.00",
        "Company: BRITISH GAS",
        "CAIS Last Updated: 01/11/2026",
    ]


def _accounts(text):
    return [_parse_valid8_account(address, block)
            for address, block in _split_valid8_accounts(text)]


class DelinquentBadgeTests(SimpleTestCase):

    def test_a_delinquent_record_is_not_merged_into_the_one_above(self):
        zilch, gas = _accounts("\n".join(ZILCH + _british_gas()))

        self.assertEqual(zilch["raw_name"], "ZILCH TECHNOLOGY LIMITED")
        self.assertEqual(zilch["account_number"], "C01927833")
        self.assertIsNone(zilch["current_balance"])
        self.assertEqual(zilch["type_code"], "CC")

        self.assertEqual(gas["raw_name"], "BRITISH GAS")
        self.assertEqual(gas["account_status"], "Delinquent")
        self.assertEqual(gas["current_balance"], 1321800)
        self.assertEqual(gas["type_code"], "UT")
        self.assertIsNone(gas["account_number"])

    def test_an_unknown_badge_before_date_of_birth_still_opens_a_record(self):
        names = [a["raw_name"] for a in _accounts("\n".join(ZILCH + _british_gas("Arrangement")))]
        self.assertEqual(names, ["ZILCH TECHNOLOGY LIMITED", "BRITISH GAS"])

    def test_a_field_line_after_address_does_not_open_a_record(self):
        text = "\n".join(["Address: 1 HIGH ST", "Balance: £5.00", "Date of Birth: 01/01/1990"])
        self.assertEqual(_split_valid8_accounts(text), [])

    def test_a_sold_default_account_reads_the_latest_month_not_the_default_balance(self):
        # JACAMO on a Valid8 report: no balance of its own, debt sold 8/8/2023,
        # £0 in the grid from August. CAT read its £1,580 default balance.
        block = "\n".join([
            "Default", "Company Type: Mail Order", "Account Type: Mail Order",
            "Default Balance: £1,580.00", "Company: JACAMO", "Default Date: 22/06/2023",
            "Indicators", "Type: Debt sold to a CAIS member",
            "Account Status & Balance Details", "J F M A M J J A S O N D",
            "2 3 4 6 6 6 8 8", "2023", "£1,372 £1,421 £1,473 £1,580 £1,580 £1,580 £1,580 £0",
            "0 0 0 0 0 0 0 0 0 0 1 1", "2022",
            "£523 £561 £561 £578 £660 £780 £1,150 £1,102 £1,201 £1,247 £1,254 £1,313",
        ])
        account = _parse_valid8_account("", block)
        self.assertEqual(account["current_balance"], 0)
        self.assertEqual(account["default_balance"], 158000)

    def test_a_printed_current_balance_still_wins(self):
        # CABOT, the purchaser: prints its own current balance beside the default.
        block = "\n".join(["Default", "Current Balance: £1,941.00", "Default Balance: £1,579.00",
                           "Company: CABOT FINANCIAL (EUROPE) LTD", "2026", "£1,941 £1,941"])
        self.assertEqual(_parse_valid8_account("", block)["current_balance"], 194100)

    def test_the_badges_are_experians_account_statuses(self):
        self.assertEqual(_VALID8_STATUS_WORDS, set(ACCOUNT_STATUS_LABELS.values()))
