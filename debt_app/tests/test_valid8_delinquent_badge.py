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

    def test_the_badges_are_experians_account_statuses(self):
        self.assertEqual(_VALID8_STATUS_WORDS, set(ACCOUNT_STATUS_LABELS.values()))
