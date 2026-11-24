"""
Balloon HP is hire purchase (user, 2026-11-24, case 432916).

Car finance with a large final ("balloon") payment, secured on the vehicle
like any HP. Every route read it as "OT" (Other) -- or, on an Aryza Advize
search, as the unknown code "BH" -- so CAT treated Close Brothers' £13,973
car finance as UNSECURED IVA debt: counted toward the £5,400 minimum, given a
vote and a proof-of-debt flag, and missed by every vehicle check.

Pinned, on all four routes: the type code is HP; the report's own wording or
code is kept beside it (`source_account_type` / `source_account_code`); the
account stays debt (HP is never `mortgage_accounts`).
"""
from django.test import SimpleTestCase

from debt_app.integrations.account_categories import account_category
from debt_app.integrations.credit_report import (
    _ADVIZE_TYPE_CODES,
    _EXPERIAN_CATEGORY_TO_TYPE,
    _TYPE_CODE_RE,
    _VALID8_CATEGORY_TO_TYPE,
    _parse_account_block,
    _parse_experian_account,
    _parse_valid8_account,
    _split_into_account_blocks,
)

ADVIZE = "\n".join([
    "Close Consumer Finance BH",
    "Account Details:",
    "Account Type: Balloon HP",
    "Account Status: Up to date Account Status",
    "Subjective Level: Good",
    "Credit Limit: N/A Payments: Monthly X £404",
    "Minimum Payment: No Promotional Rate: No",
    "Balances Dates",
    "Current Balance: £14377 Last Update: 2026-09-30",
    "Start Balance: £26897 Start Date: 2024-02-29",
    "Default Balance: N/A End Date: N/A",
])

EXPERIAN_BLOCK = "\n".join([
    "• Status: Active",
    "• Start Balance: £26897",
    "• Current Balance: £13973",
    "• Worst Status: Satisfactory",
])


class BalloonHpTests(SimpleTestCase):

    def test_both_experian_maps_read_it_as_hp(self):
        for wording in ("balloon hp", "balloon hire purchase"):
            self.assertEqual("HP", _EXPERIAN_CATEGORY_TO_TYPE[wording], wording)
            self.assertEqual("HP", _VALID8_CATEGORY_TO_TYPE[wording], wording)

    def test_an_experian_pdf_account(self):
        parsed = _parse_experian_account("CLOSE BROTHERS LIMITED - Balloon HP", EXPERIAN_BLOCK)
        self.assertIsNotNone(parsed)
        self.assertEqual(("HP", "Balloon HP", False),
                         (parsed["type_code"], parsed["source_account_type"], parsed["type_unmapped"]))
        self.assertEqual("hire_purchase", account_category(parsed["type_code"], parsed["source_account_type"]))

    def test_a_valid8_account(self):
        block = "\n".join(["Active", "Company: CLOSE BROTHERS LIMITED", "Account Type: Balloon HP",
                           "Balance: £13,973.00", "Start Date: 29/02/2024"])
        parsed = _parse_valid8_account("1 High Street", block)
        self.assertEqual("HP", parsed["type_code"])
        self.assertFalse(parsed.get("reconciliation_only"))

    def test_an_aryza_search_bh_account_is_hp_and_keeps_its_printed_code(self):
        self.assertIn("BH", _ADVIZE_TYPE_CODES)
        self.assertIsNotNone(_TYPE_CODE_RE.match("Close Consumer Finance BH"))
        [(header, body)] = _split_into_account_blocks(ADVIZE)
        parsed = _parse_account_block(header, body)
        self.assertEqual(("HP", "BH", False, 1437700),
                         (parsed["type_code"], parsed["source_account_code"], parsed["type_unmapped"],
                          parsed["current_balance"]))
        self.assertEqual("Close Consumer Finance", parsed["raw_name"])
