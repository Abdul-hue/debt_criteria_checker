"""
Utility and telecom accounts keep a type CAT can tell apart (2026-11-19).

CAT raises a credit-report-only utility account and a telecom account as two
separate Soft Flags, configured independently (`cr_utility` / `cr_telecom`).
It reads the type code: UT (and EW / EE) a utility, TM a telecom. On an
Experian report Mobile, Fixed Line and Broadband were unlisted and fell to
"OT", and telecoms read as "UT" -- so a mobile contract was "Other" and a
telecoms account a utility.

Pinned here:
  * Mobile / Fixed Line / Broadband / telecoms -> TM; Duel Fuel -> UT;
  * the categories left for the business -- Communications (UT), Cable,
    Satellite, Business Line, Oil (OT) -- unchanged;
  * every Experian account carries `source_account_type`, the report's own
    wording, on the PDF path, the Valid8 path and the JSON import alike.
"""
from django.test import SimpleTestCase

from debt_app.integrations.credit_report import (
    DEBT_TYPE_CODES,
    RECONCILIATION_ONLY_TYPE_CODES,
    _EXPERIAN_CATEGORY_TO_TYPE,
    _VALID8_CATEGORY_TO_TYPE,
    _parse_experian_account,
    _parse_valid8_account,
)
from debt_app.integrations.experian_db import ExperianCodeTables
from debt_app.integrations.experian_mapper import _map_account


def _experian(category, name="VODAFONE LIMITED"):
    header = f"{name} - {category}"
    block = "\n".join([header, "Start Date: 20-01-2024", "Current Balance: £120",
                       "Status: Up to date", "Account Number: ****3160"])
    return header, block


def _valid8(account_type):
    return "\n".join(["Active", "Company: SCOTTISHPOWER", f"Account Type: {account_type}",
                      "Current Balance: £250", "Start Date: 20-01-2024"])


class TelecomCategoriesTests(SimpleTestCase):

    def test_mobile_fixed_line_broadband_and_telecoms_are_tm(self):
        for category in ("mobile", "fixed line", "broadband", "telecoms", "telecommunications"):
            self.assertEqual(_EXPERIAN_CATEGORY_TO_TYPE[category], "TM", category)

    def test_a_cais_mobile_account_is_telecom_debt(self):
        parsed = _parse_experian_account(*_experian("Mobile"))
        self.assertEqual(parsed["type_code"], "TM")
        self.assertFalse(parsed["reconciliation_only"])
        self.assertIn("TM", DEBT_TYPE_CODES)

    def test_the_singular_header_the_strict_regex_accepts_is_tm(self):
        # `_EXPERIAN_HEADER_RE` lists "Telecom"; the map had only the plural.
        self.assertEqual(_parse_experian_account(*_experian("Telecom"))["type_code"], "TM")

    def test_valid8_maps_the_same_telecom_wordings(self):
        for category in ("Mobile", "Fixed Line", "Broadband", "Telecom", "Telecoms", "Telecommunications"):
            parsed = _parse_valid8_account("1 High Street", _valid8(category))
            self.assertEqual(parsed["type_code"], "TM", category)
            self.assertFalse(parsed["reconciliation_only"], category)


class UtilityCategoriesTests(SimpleTestCase):

    def test_water_gas_electricity_public_utility_and_dual_fuel_are_ut(self):
        for category in ("water", "gas", "electricity", "public utility", "utility",
                         "duel fuel", "dual fuel"):
            self.assertEqual(_EXPERIAN_CATEGORY_TO_TYPE[category], "UT", category)

    def test_valid8_maps_dual_fuel_as_a_utility(self):
        for category in ("Duel Fuel", "Dual Fuel", "Electricity", "Gas", "Water", "Public Utility"):
            self.assertEqual(_parse_valid8_account("1 High Street", _valid8(category))["type_code"], "UT",
                             category)


class LeftForTheBusinessTests(SimpleTestCase):
    """Not classified on this change -- their meaning is not settled."""

    def test_communications_stays_ut(self):
        self.assertEqual(_EXPERIAN_CATEGORY_TO_TYPE["communications"], "UT")
        self.assertEqual(_VALID8_CATEGORY_TO_TYPE["communications"], "UT")
        # The singular is unlisted in both maps: left as it was ("OT").
        self.assertNotIn("communication", _EXPERIAN_CATEGORY_TO_TYPE)
        self.assertNotIn("communication", _VALID8_CATEGORY_TO_TYPE)

    def test_valid8_leaves_cable_satellite_business_line_and_oil_unlisted(self):
        for category in ("Cable", "Satellite", "Business Line", "Oil"):
            self.assertEqual(_parse_valid8_account("1 High Street", _valid8(category))["type_code"], "OT",
                             category)

    def test_cable_satellite_business_line_and_oil_stay_unlisted(self):
        for category in ("cable", "satellite", "business line", "oil"):
            self.assertNotIn(category, _EXPERIAN_CATEGORY_TO_TYPE, category)
            parsed = _parse_experian_account(*_experian(category.title()))
            self.assertEqual(parsed["type_code"], "OT", category)

    def test_multi_communications_is_still_reconciliation_only(self):
        self.assertEqual(_EXPERIAN_CATEGORY_TO_TYPE["multi communications"], "MU")
        self.assertIn("MU", RECONCILIATION_ONLY_TYPE_CODES)


class SourceAccountTypeTests(SimpleTestCase):

    def test_the_pdf_path_keeps_the_printed_category(self):
        self.assertEqual(_parse_experian_account(*_experian("Mobile"))["source_account_type"], "Mobile")
        self.assertEqual(_parse_experian_account(*_experian("Satellite"))["source_account_type"],
                         "Satellite")

    def test_the_valid8_path_keeps_the_printed_type(self):
        parsed = _parse_valid8_account("1 High Street", _valid8("Electricity"))
        self.assertEqual((parsed["type_code"], parsed["source_account_type"]), ("UT", "Electricity"))

    def test_the_json_import_keeps_the_code_table_description(self):
        tables = ExperianCodeTables({"53": "Mobile", "55": "Cable"}, {})
        mobile = _map_account({"SupplyCompanyName": "VODAFONE", "AccountType": "53"}, tables)
        cable = _map_account({"SupplyCompanyName": "VIRGIN MEDIA", "AccountType": "55"}, tables)
        self.assertEqual((mobile["type_code"], mobile["source_account_type"]), ("TM", "Mobile"))
        self.assertEqual((cable["type_code"], cable["source_account_type"]), ("OT", "Cable"))
