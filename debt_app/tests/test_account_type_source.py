"""
Track A of the account-type mapping (2026-11-19): every credit-report account
keeps its source, and carries a canonical category -- additively.

Pinned:
  * each extraction path (Aryza Advize PDF, Experian PDF, Experian Valid8 PDF,
    Experian JSON) adds `source_account_type`, `source_account_code`,
    `source_system`, `account_category` and `type_unmapped` beside `type_code`;
  * the source is kept exactly as given; an unknown code or wording stays
    identifiable (`type_unmapped`) instead of disappearing into "OT";
  * `type_code` is unchanged for all 70 Experian codes;
  * the category is only what the existing `type_code` already means --
    everything undecided is `unknown`;
  * a case JSON with or without `account_category` assesses identically.
"""
import json
import re
from pathlib import Path

from django.test import SimpleTestCase, TestCase

from debt_app.engine.criteria import _parse_case, assess_case
from debt_app.integrations.account_categories import (
    ACCOUNT_CATEGORIES, CATEGORY_BY_TYPE_CODE, UNKNOWN, account_category,
)
from debt_app.integrations.credit_report import (
    _ADVIZE_TYPE_CODES, _TYPE_CODE_RE, _parse_account_block, _parse_experian_account,
    _parse_valid8_account, _split_into_account_blocks,
)
from debt_app.integrations.experian_db import ExperianCodeTables
from debt_app.integrations.experian_mapper import _map_account
from debt_app.tests.test_experian_mapper import ACCOUNT_TYPES, EXPECTED_TYPE_CODE

SOURCE_KEYS = ("source_account_type", "source_account_code", "source_system",
               "account_category", "type_unmapped")
TABLES = ExperianCodeTables(ACCOUNT_TYPES, {})


def _json(code, name="SOME LENDER"):
    return _map_account({"SupplyCompanyName": name, "AccountType": code}, TABLES)


def _experian_pdf(category):
    header = f"SOME LENDER - {category}"
    return _parse_experian_account(header, "\n".join([header, "Current Balance: £120"]))


def _valid8(account_type):
    return _parse_valid8_account("1 High Street", "\n".join(
        ["Active", "Company: SOME LENDER", f"Account Type: {account_type}", "Current Balance: £250"]))


def _advize(code, type_line=None):
    text = "\n".join([f"Some Lender {code}", "Account Details:",
                      *([type_line] if type_line else []), "Current Balance: £300"])
    blocks = _split_into_account_blocks(text)
    return _parse_account_block(*blocks[0])


class EveryPathCarriesTheSourceTests(SimpleTestCase):

    def test_experian_json_keeps_the_numeric_code_and_description(self):
        account = _json("53")
        self.assertEqual({k: account[k] for k in SOURCE_KEYS}, {
            "source_account_type": "Mobile", "source_account_code": "53",
            "source_system": "experian_json", "account_category": "telecom", "type_unmapped": False})

    def test_experian_pdf_keeps_the_printed_category(self):
        account = _experian_pdf("Credit Cards")
        self.assertEqual((account["source_account_type"], account["source_account_code"],
                          account["source_system"], account["account_category"]),
                         ("Credit Cards", None, "experian_pdf", "card"))

    def test_valid8_keeps_the_printed_type(self):
        account = _valid8("Electricity")
        self.assertEqual((account["source_account_type"], account["source_system"],
                          account["account_category"]), ("Electricity", "experian_valid8_pdf", "utility"))

    def test_advize_keeps_its_printed_code(self):
        account = _advize("CC")
        self.assertEqual((account["type_code"], account["source_account_code"], account["source_account_type"],
                          account["source_system"], account["type_unmapped"]),
                         ("CC", "CC", "", "aryza_advize_pdf", False))

    def test_advize_keeps_its_printed_wording_and_never_a_number(self):
        self.assertEqual(_advize("CC", "Account Type: Budget Account")["source_account_type"], "Budget Account")
        self.assertEqual(_advize("CC", "Account Type: Credit Card Account Number: 4321")["source_account_type"],
                         "", "another field on the line: where the type ends is unknown, so nothing is kept")
        self.assertEqual(_advize("CC", "Account Type: 12345678")["source_account_type"], "")

    def test_advize_category_follows_the_printed_code_not_the_wording(self):
        # CAT classifies an Advize account by its code (ledger/credit_report.py ::
        # _family_wording); the category must agree, whatever the lender wrote.
        for code, wording, category in (("UT", "Communications", "utility"),
                                        ("EE", "Budget Account", "utility"),
                                        ("TM", "Communications", "telecom"),
                                        ("CC", "Gambling", "card")):
            account = _advize(code, f"Account Type: {wording}")
            self.assertEqual((account["source_account_type"], account["account_category"]),
                             (wording, category), code)


class UnmappedStaysIdentifiableTests(SimpleTestCase):
    """The type_code is still "OT" exactly as before; the source is not lost."""

    def test_an_unknown_experian_code_keeps_its_code(self):
        account = _json("99")
        self.assertEqual((account["type_code"], account["source_account_code"], account["source_account_type"],
                          account["type_unmapped"], account["account_category"]),
                         ("OT", "99", "", True, UNKNOWN))

    def test_a_listed_code_the_map_does_not_cover(self):
        account = _json("45")                 # House Insurance
        self.assertEqual((account["type_code"], account["source_account_type"], account["type_unmapped"]),
                         ("OT", "House Insurance", True))

    def test_an_unlisted_pdf_wording_is_kept(self):
        account = _experian_pdf("Satellite")
        self.assertEqual((account["type_code"], account["source_account_type"], account["type_unmapped"]),
                         ("OT", "Satellite", True))
        account = _valid8("Something New")
        self.assertEqual((account["type_code"], account["source_account_type"], account["type_unmapped"]),
                         ("OT", "Something New", True))

    def test_an_advize_code_outside_the_list(self):
        account = _advize("AL")
        self.assertEqual((account["type_code"], account["source_account_code"], account["type_unmapped"],
                          account["account_category"]), ("AL", "AL", True, UNKNOWN))

    def test_a_mapped_code_is_not_unmapped(self):
        self.assertFalse(_json("05")["type_unmapped"])
        self.assertFalse(_advize("UT")["type_unmapped"])


class TypeCodeUnchangedTests(SimpleTestCase):

    def test_every_experian_code_keeps_its_type_code(self):
        for code in ACCOUNT_TYPES:
            with self.subTest(code=code):
                self.assertEqual(_json(code)["type_code"], EXPECTED_TYPE_CODE[code])

    def test_the_advize_code_set_is_the_regex_s(self):
        listed = set(re.search(r"\(([A-Z|]+)\)\$", _TYPE_CODE_RE.pattern).group(1).split("|"))
        self.assertEqual(listed, set(_ADVIZE_TYPE_CODES))


class CategoryIsOnlyWhatTheCodeMeansTests(SimpleTestCase):

    def test_every_mapped_category_is_in_the_vocabulary(self):
        self.assertTrue(set(CATEGORY_BY_TYPE_CODE.values()) <= set(ACCOUNT_CATEGORIES))
        self.assertEqual(len(ACCOUNT_CATEGORIES), len(set(ACCOUNT_CATEGORIES)))

    def test_undecided_codes_are_unknown(self):
        for code in ("OT", "BD", "DP", "IL", "MU", "AL", "TA", "", None):
            self.assertEqual(account_category(code), UNKNOWN, code)

    def test_an_open_wording_is_unknown_whatever_its_code(self):
        self.assertEqual(_json("18")["type_code"], "UT", "type_code untouched")
        self.assertEqual(_json("18")["account_category"], UNKNOWN, "Communications is an open decision")
        self.assertEqual(account_category("UT", "Cable"), UNKNOWN)

    def test_vehicle_insurance_and_vehicle_finance_stay_apart(self):
        self.assertEqual(_json("46")["account_category"], "vehicle_insurance")
        self.assertEqual(_json("01")["account_category"], "hire_purchase")


class MortgageProductsTests(SimpleTestCase):
    """Decision D-01 (agreed 2026-11-19): genuine mortgage products are the
    Mortgage category -- category only; type code and bucket unchanged."""

    GENUINE = ("03", "16", "25", "30", "31", "32", "33", "34", "35")
    STILL_OPEN = ("12", "13", "14", "69")

    def test_every_genuine_mortgage_product_is_the_mortgage_category(self):
        for code in self.GENUINE:
            account = _json(code)
            self.assertEqual(account["account_category"], "mortgage", code)
            self.assertEqual(account["source_account_type"], ACCOUNT_TYPES[code], code)

    def test_their_type_code_is_unchanged(self):
        # "OT" stays "OT": moving one to MG is the secured decision (D-13).
        for code in self.GENUINE:
            self.assertEqual(_json(code)["type_code"], EXPECTED_TYPE_CODE[code], code)

    def test_cml_events_and_mortgage_plus_loan_stay_unknown(self):
        for code in self.STILL_OPEN:
            self.assertEqual(_json(code)["account_category"], UNKNOWN, code)

    def test_the_same_wording_on_a_pdf_or_valid8_report(self):
        self.assertEqual(account_category("OT", "Buy To Let Mortgage"), "mortgage")
        self.assertEqual(_valid8("Residential Mortgage")["account_category"], "mortgage")

    def test_an_advize_account_is_still_read_by_its_code(self):
        # The lender's wording never classifies an Advize account.
        self.assertEqual(_advize("CC", "Account Type: Second Mortgage")["account_category"], "card")
        self.assertEqual(_advize("MG")["account_category"], "mortgage")


class CaseJsonCompatibilityTests(SimpleTestCase):

    def test_an_old_payload_parses_with_no_category(self):
        [creditor] = _parse_case({"creditors": [{"creditor_name": "Lender", "balance": 500,
                                                 "creditor_type": "credit_card"}]})["creditors"]
        self.assertIsNone(creditor["account_category"])
        self.assertEqual(creditor["creditor_type"], "credit_card")

    def test_a_new_payload_carries_it_beside_creditor_type(self):
        [creditor] = _parse_case({"creditors": [{"creditor_name": "Lender", "balance": 500,
                                                 "creditor_type": "credit_card",
                                                 "account_category": "card"}]})["creditors"]
        self.assertEqual((creditor["account_category"], creditor["creditor_type"]), ("card", "credit_card"))


class SameAssessmentWithOrWithoutTheCategoryTests(TestCase):

    def _case(self, **extra):
        return {"aryza_reference": "TA-1", "creditors": [
            {"creditor_name": "Barclaycard", "balance": 2500.0, "creditor_type": "credit_card", **extra},
            {"creditor_name": "EE Limited", "balance": 180.0, "creditor_type": "", **extra}]}

    def test_the_result_is_identical(self):
        old = assess_case(self._case(), set())
        new = assess_case(self._case(account_category="card"), set())
        dump = lambda r: json.dumps(r, sort_keys=True, default=str)  # noqa: E731
        self.assertEqual(dump(old), dump(new))


class VocabularyMatchesCatTests(SimpleTestCase):
    """The same vocabulary on both sides. Read from CAT's checkout when it sits
    beside this one (a developer machine); skipped where it does not (CI)."""

    CAT = (Path(__file__).resolve().parents[3] / "case-assessment-tool" / "case-assessment-backend"
           / "case_assesment" / "common" / "account_categories.py")

    def test_identical_vocabulary(self):
        if not self.CAT.exists():
            self.skipTest("CAT checkout not beside this one")
        match = re.search(r"ACCOUNT_CATEGORIES = \((.*?)\)\n", self.CAT.read_text(encoding="utf-8"), re.S)
        self.assertEqual(tuple(re.findall(r'"([a-z_]+)"', match.group(1))), ACCOUNT_CATEGORIES)
