"""
Experian search document (Credit_Searches.JsonData) -> CreditReport.extracted_data
(debt_app/integrations/experian_mapper.py).

The PDF path is the source of truth: the parity tests at the bottom render the
same synthetic search as report text and run it through the real
extract_credit_report() (pdfplumber mocked), then compare field by field.
The code tables are the real dbo.experian_codes / dbo.PublicInfo_Type_Codes
reference data. Every person and account below is invented.
"""
import json
from copy import deepcopy
from datetime import date
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from debt_app.integrations.credit_report import CREDITOR_ALIAS_MAP, extract_credit_report
from debt_app.integrations.experian_db import ExperianCodeTables, ExperianDataError
from debt_app.integrations.experian_mapper import (
    ACCOUNT_STATUS_LABELS,
    WORST_STATUS_LABELS,
    map_search_to_extracted_data,
)

# dbo.experian_codes (EXPERIAN_CODE -> EXPERIAN_DESC), as loaded (padding stripped).
ACCOUNT_TYPES = {
    "00": "Bank", "01": "Hire Purchase / Conditional Sale", "02": "Unsecured Loan (Personal Loan)",
    "03": "Mortgage", "04": "Budget (Revolving Account)", "05": "Credit Card / Store Card",
    "06": "Charge Card", "07": "Rental (TV, Brown and White Goods)", "08": "Mail Order",
    "11": "Overdraft", "12": "CML Member Possession Order", "13": "CML Member Voluntary Surrender",
    "14": "CML Member Arrears Move", "15": "Current Accounts", "16": "Second Mortgage",
    "17": "Credit Sale Fixed Term", "18": "Communications", "19": "Fixed Term Deferred Payment",
    "20": "Variable Subscription", "21": "Public Utility", "22": "Finance Lease", "23": "Operating Lease",
    "24": "Unpresentable - Cheques", "25": "Flexible Mortgages", "26": "Consolidated Debt",
    "27": "Combined Credit Account", "28": "Pay Day Loans", "29": "Balloon HP", "30": "Residential Mortgage",
    "31": "Buy To Let Mortgage", "32": "LTV Mortgage", "33": "Current Account Offset Mortgage",
    "34": "Investment Offset Mortgage", "35": "Shared Ownership Mortgage", "36": "Contingency Liability",
    "37": "Store Card", "38": "Multi Function Card", "39": "Water", "40": "Gas", "41": "Electricity",
    "42": "Oil", "43": "Duel Fuel", "44": "Fuel Card (not motor fuel)", "45": "House Insurance",
    "46": "Car Insurance", "47": "Life Insurance", "48": "Health Insurance", "49": "Card Protection",
    "50": "Mortgage Protection", "51": "Payment Protection", "52": "Tax", "53": "Mobile", "54": "Fixed Line",
    "55": "Cable", "56": "Satellite", "57": "Business Line", "58": "Broadband", "59": "Multi Communications",
    "60": "Student Loan", "61": "Home Credit", "62": "Education", "63": "Property Rental",
    "64": "Other Rental", "65": "Fines", "66": "Court Actions", "67": "Child Maintenance", "68": "Asset",
    "69": "Mortgage and Unsecured Loan", "70": "Gambling", "71": "Basic Bank Account",
}

# dbo.PublicInfo_Type_Codes (Code -> Type).
PUBLIC_INFO_TYPES = {
    "02": "Judgement", "16": "Judgement", "17": "Judgement",
    "18": "Liability Order", "19": "Liability Order", "20": "Liability Order",
    "26": "Bankruptcy", "29": "Bankruptcy", "30": "Bankruptcy", "31": "Bankruptcy", "33": "Bankruptcy",
    "36": "Bankruptcy", "38": "Bankruptcy", "40": "Bankruptcy", "41": "Bankruptcy", "42": "Bankruptcy",
    "43": "Bankruptcy", "45": "Bankruptcy", "46": "Bankruptcy", "60": "Bankruptcy", "61": "Bankruptcy",
    "65": "Debt Arrangement", "66": "Debt Arrangement", "70": "IVA", "72": "Bankruptcy",
    "74": "CCJ", "75": "CCJ", "76": "CCJ", "77": "Bankruptcy", "78": "Bankruptcy",
}

CODE_TABLES = ExperianCodeTables(ACCOUNT_TYPES, PUBLIC_INFO_TYPES)

# What each Experian account type becomes through the existing PDF category
# map. "OT" rows that are really mortgages, insurance or bank accounts are the
# PDF path's own behaviour, kept for parity (open business decision D1).
EXPECTED_TYPE_CODE = {
    "00": "OT", "01": "HP", "02": "PL", "03": "MG", "04": "OT", "05": "CC", "06": "CC", "07": "OT",
    "08": "MO", "11": "OT", "12": "OT", "13": "OT", "14": "OT", "15": "CA", "16": "OT", "17": "OT",
    "18": "UT", "19": "OT", "20": "OT", "21": "UT", "22": "OT", "23": "OT", "24": "OT", "25": "OT",
    "26": "OT", "27": "OT", "28": "OT", "29": "OT", "30": "OT", "31": "OT", "32": "OT", "33": "OT",
    "34": "OT", "35": "OT", "36": "OT", "37": "CC", "38": "OT", "39": "UT", "40": "UT", "41": "UT",
    "42": "OT", "43": "OT", "44": "OT", "45": "OT", "46": "MI", "47": "OT", "48": "OT", "49": "OT",
    "50": "OT", "51": "OT", "52": "OT", "53": "OT", "54": "OT", "55": "OT", "56": "OT", "57": "OT",
    "58": "OT", "59": "MU", "60": "UL", "61": "UL", "62": "OT", "63": "OT", "64": "OT", "65": "OT",
    "66": "OT", "67": "OT", "68": "OT", "69": "OT", "70": "OT", "71": "OT",
}

TOP_LEVEL_KEYS = [
    "agency", "client_name", "client_address", "report_date", "printed_report_date", "accounts",
    "mortgage_accounts", "other_accounts", "unmatched_accounts", "public_information", "has_ccj",
    "aoe_in_place",
]
ACCOUNT_KEYS = [
    "raw_name", "type_code", "normalised_name", "matched_creditor", "account_age_months",
    "missed_payments_last_3_months", "recent_spending", "current_balance", "start_balance",
    "credit_limit", "utilisation_pct", "account_status", "account_status_subjective", "worst_status",
    "payment_history_months", "monthly_payment", "account_number", "start_date", "cais_last_updated",
    "reconciliation_only",
]
PUBLIC_INFO_KEYS = ["has_ccj", "ccj_count", "ccj_total_pence", "ccjs", "iva_or_bankruptcy",
                    "debt_management", "aoe_in_place"]


def _detail(**overrides):
    """One CAISDetails record. Balances are Experian's zero-padded whole pounds, newest first."""
    detail = {
        "SupplyCompanyName": "HALIFAX",
        "AccountType": "05",
        "AccountStatus": "A",
        "WorstStatus": "0",
        "AccountNumber": "4462000011112222",
        "CAISAccStartDate": "2021-09-16",
        "LastUpdatedDate": "2026-03-05",
        "AccountBalances": [
            {"AccountBalance": "0000350", "Status": "0"},
            {"AccountBalance": "0000400", "Status": "0"},
            {"AccountBalance": "0001200", "Status": "0"},
        ],
        "AccountStatusCodes": "000",
        "NumAccountBalances": 3,
        # Fields present in real records that the mapper must not copy through.
        "Name": {"Forename": "JANE", "Surname": "DOE"},
        "DateOfBirth": "1980-05-05",
        "Location": {"Postcode": "LS1 1AA"},
    }
    detail.update(overrides)
    return detail


def _public(info_type, pounds="£557", camera="K1234", info_date="2024-02-01"):
    return {"InformationType": info_type, "AmountPounds": pounds, "AmountPence": 0,
            "InformationDate": info_date, "CameraNumber": camera, "DataSource": "LCH",
            "Name": {"Forename": "JANE", "Surname": "DOE"}}


def _doc(details=(), public=(), debt_management="N", public_number=None, search_date="2026-03-04"):
    """A minimal Experian response shaped like Credit_Searches.JsonData."""
    return {
        "Response": {
            "Applicants": [{"ApplicantIdentifier": 1, "Person": {
                "Title": "MS", "Forename": "JANE", "Surname": "DOE", "DateOfBirth": "1980-05-05"}}],
            "Locations": [
                {"LocationIdentifier": 1, "UKLocation": {
                    "HouseNumber": "12", "Street": "HIGH STREET", "PostTown": "LEEDS", "Postcode": "LS1 1AA"}},
                {"LocationIdentifier": 2, "UKLocation": {
                    "HouseNumber": "9", "Street": "OLD ROAD", "PostTown": "YORK", "Postcode": "YO1 1AA"}},
            ],
            "Residencies": [
                {"ApplicantIdentifier": 1, "LocationIdentifier": 2, "Type": "P"},
                {"ApplicantIdentifier": 1, "LocationIdentifier": 1, "Type": "C"},
            ],
            "FullConsumerData": {
                "ConsumerData": {
                    "CAIS": [{"ApplicantIndicator": "1", "CAISDetails": list(details)}],
                    "PublicInformation": [{"ApplicantIndicator": "1", "PublicInfoDetails": list(public)}],
                    "Association": [{"AssociationDetails": [{"AssociateName": {"Forename": "JOHN"}}]}],
                },
                "ConsumerDataSummary": {"SummaryDetails": {
                    "SummaryFlags": {"DebtManagement": debt_management},
                    "PublicInfoSummary": {"Number": len(public) if public_number is None else public_number},
                }},
                "ControlDetails": {"SearchDate": f"{search_date}T17:26:04" if search_date else None},
            },
        }
    }


def _map(*details, **kwargs):
    return map_search_to_extracted_data(_doc(details, **kwargs), CODE_TABLES)


def _account(**overrides):
    result = _map(_detail(**overrides))
    rows = result["accounts"] + result["mortgage_accounts"] + result["other_accounts"]
    assert len(rows) == 1, rows
    return rows[0]


class OutputContractTests(SimpleTestCase):
    def test_top_level_account_and_public_info_keys(self):
        result = _map(_detail(), public=[_public("02")])
        self.assertEqual(list(result), TOP_LEVEL_KEYS)
        self.assertEqual(list(result["accounts"][0]), ACCOUNT_KEYS)
        self.assertEqual(list(result["public_information"]), PUBLIC_INFO_KEYS)
        self.assertEqual(list(result["public_information"]["ccjs"][0]),
                         ["amount_pence", "settled", "date", "case_number", "court_name"])

    def test_agency_is_exactly_experian(self):
        # The upload view's empty / unrecognised-report handling keys on this value.
        self.assertEqual(_map()["agency"], "Experian")

    def test_raw_document_and_personal_extras_are_not_copied(self):
        result = _map(_detail(), public=[_public("02")])
        text = json.dumps(result)
        for absent in ("Response", "JsonData", "1980-05-05", "JOHN", "Association", "DateOfBirth"):
            self.assertNotIn(absent, text)

    def test_money_is_integer_pence(self):
        account = _account()
        self.assertIsInstance(account["current_balance"], int)
        self.assertIsInstance(account["start_balance"], int)

    def test_input_document_is_not_modified(self):
        document = _doc([_detail()], [_public("02")])
        before = deepcopy(document)
        map_search_to_extracted_data(document, CODE_TABLES)
        self.assertEqual(document, before)


class AccountTypeTests(SimpleTestCase):
    def test_every_experian_account_type(self):
        for code, expected in EXPECTED_TYPE_CODE.items():
            with self.subTest(code=code, desc=ACCOUNT_TYPES[code]):
                self.assertEqual(_account(AccountType=code)["type_code"], expected)

    def test_every_code_table_entry_is_covered(self):
        self.assertEqual(set(EXPECTED_TYPE_CODE), set(ACCOUNT_TYPES))

    def test_code_missing_from_table_is_ot(self):
        self.assertEqual(_account(AccountType="99")["type_code"], "OT")
        self.assertEqual(_account(AccountType=None)["type_code"], "OT")


class RoutingTests(SimpleTestCase):
    def test_accounts_route_like_the_pdf_path(self):
        result = _map(
            _detail(SupplyCompanyName="CARD CO", AccountType="05"),       # CC  -> accounts
            _detail(SupplyCompanyName="BUILDING SOC", AccountType="03"),  # MG  -> mortgage_accounts
            _detail(SupplyCompanyName="INSURER", AccountType="46"),       # MI  -> other_accounts
            _detail(SupplyCompanyName="TELCO", AccountType="59"),         # MU  -> other_accounts
            _detail(SupplyCompanyName="BANK", AccountType="15"),          # CA  -> accounts
            _detail(SupplyCompanyName="LENDER", AccountType="30"),        # OT  -> accounts (D1)
        )
        self.assertEqual([a["raw_name"] for a in result["accounts"]], ["CARD CO", "BANK", "LENDER"])
        self.assertEqual([a["raw_name"] for a in result["mortgage_accounts"]], ["BUILDING SOC"])
        self.assertEqual([a["raw_name"] for a in result["other_accounts"]], ["INSURER", "TELCO"])
        self.assertTrue(all(a["reconciliation_only"] for a in result["other_accounts"]))
        self.assertFalse(any(a["reconciliation_only"] for a in result["accounts"] + result["mortgage_accounts"]))

    def test_accounts_from_every_cais_block_are_included_in_order(self):
        document = _doc([_detail(SupplyCompanyName="FIRST")])
        document["Response"]["FullConsumerData"]["ConsumerData"]["CAIS"].append(
            # ApplicantIndicator "U": a linked-address block; the rendered report includes it.
            {"ApplicantIndicator": "U", "CAISDetails": [_detail(SupplyCompanyName="SECOND")]})
        result = map_search_to_extracted_data(document, CODE_TABLES)
        self.assertEqual([a["raw_name"] for a in result["accounts"]], ["FIRST", "SECOND"])

    def test_creditor_matching_uses_the_existing_alias_map(self):
        alias = next(k for k, v in CREDITOR_ALIAS_MAP.items() if v != k and v.lower() != k)
        result = _map(_detail(SupplyCompanyName=f"  {alias.upper()}  "), _detail(SupplyCompanyName="NO SUCH LENDER"))
        matched, unmatched = result["accounts"]
        self.assertEqual(matched["raw_name"], alias.upper())
        self.assertEqual(matched["normalised_name"], alias)
        self.assertEqual(matched["matched_creditor"], CREDITOR_ALIAS_MAP[alias])
        self.assertEqual(unmatched["matched_creditor"], "NO SUCH LENDER")
        self.assertEqual(result["unmatched_accounts"], ["NO SUCH LENDER"])

    def test_unmatched_lists_only_debt_accounts(self):
        result = _map(_detail(SupplyCompanyName="ODD MORTGAGE CO", AccountType="03"),
                      _detail(SupplyCompanyName="ODD INSURER", AccountType="46"))
        self.assertEqual(result["unmatched_accounts"], [])

    def test_record_without_a_creditor_name_is_skipped(self):
        with self.assertLogs("debt_app.integrations.experian_mapper", level="WARNING"):
            result = _map(_detail(SupplyCompanyName="  "), _detail(SupplyCompanyName="KEPT"))
        self.assertEqual([a["raw_name"] for a in result["accounts"]], ["KEPT"])


class StatusTests(SimpleTestCase):
    def test_account_status_codes(self):
        self.assertEqual(ACCOUNT_STATUS_LABELS, {"A": "Active", "D": "Delinquent", "F": "Default", "S": "Settled"})
        for code, label in ACCOUNT_STATUS_LABELS.items():
            self.assertEqual(_account(AccountStatus=code)["account_status"], label)

    def test_worst_status_codes(self):
        for code, label in WORST_STATUS_LABELS.items():
            self.assertEqual(_account(WorstStatus=code)["worst_status"], label)
        self.assertEqual(WORST_STATUS_LABELS["1"], "Month Delinquent")  # printed without its digit
        self.assertEqual(WORST_STATUS_LABELS["8"], "Default")
        self.assertEqual(WORST_STATUS_LABELS["D"], "Dormant")

    def test_unknown_worst_status_is_none_and_logged(self):
        with self.assertLogs("debt_app.integrations.experian_mapper", level="WARNING"):
            self.assertIsNone(_account(WorstStatus="Z")["worst_status"])
        self.assertIsNone(_account(WorstStatus=None)["worst_status"])

    def test_missing_or_unknown_account_status_uses_the_pdf_fallback(self):
        self.assertEqual(_account(AccountStatus=None, WorstStatus="0")["account_status"], "Open")
        self.assertEqual(_account(AccountStatus=None, WorstStatus="8")["account_status"], "Default")
        with self.assertLogs("debt_app.integrations.experian_mapper", level="WARNING"):
            self.assertEqual(_account(AccountStatus="Q", WorstStatus="0")["account_status"], "Open")

    def test_fields_the_experian_report_never_prints(self):
        account = _account()
        self.assertEqual(account["account_status_subjective"], "")
        self.assertIsNone(account["credit_limit"])
        self.assertIsNone(account["utilisation_pct"])
        self.assertIsNone(account["monthly_payment"])
        self.assertIs(account["recent_spending"], False)
        self.assertEqual(account["payment_history_months"], 0)


class BalanceTests(SimpleTestCase):
    def test_current_is_newest_and_start_is_oldest_in_pence(self):
        account = _account(AccountBalances=[
            {"AccountBalance": "0000350", "Status": "0"},
            {"AccountBalance": "0001200", "Status": "0"},
        ])
        self.assertEqual(account["current_balance"], 35000)
        self.assertEqual(account["start_balance"], 120000)

    def test_single_balance_is_both(self):
        account = _account(AccountBalances=[{"AccountBalance": "0000075", "Status": "0"}])
        self.assertEqual((account["current_balance"], account["start_balance"]), (7500, 7500))

    def test_zero_and_negative_balances(self):
        self.assertEqual(_account(AccountBalances=[{"AccountBalance": "0000000"}])["current_balance"], 0)
        self.assertEqual(_account(AccountBalances=[{"AccountBalance": "-000050"}])["current_balance"], -5000)

    def test_missing_balances_are_none(self):
        for balances in ([], None, "garbage", [{"Status": "0"}]):
            account = _account(AccountBalances=balances)
            self.assertIsNone(account["current_balance"], balances)
            self.assertIsNone(account["start_balance"], balances)


class DateAndIdentifierTests(SimpleTestCase):
    def test_start_date_iso_and_age(self):
        account = _account(CAISAccStartDate="2021-09-16T00:00:00")
        self.assertEqual(account["start_date"], "2021-09-16")
        today = date.today()
        self.assertEqual(account["account_age_months"], (today.year - 2021) * 12 + (today.month - 9))

    def test_cais_last_updated_is_day_first_like_the_pdf(self):
        self.assertEqual(_account(LastUpdatedDate="2026-03-05")["cais_last_updated"], "05-03-2026")

    def test_missing_or_invalid_dates_are_none(self):
        for bad in (None, "", "not a date", "2026-13-40"):
            account = _account(CAISAccStartDate=bad, LastUpdatedDate=bad)
            self.assertIsNone(account["start_date"], bad)
            self.assertIsNone(account["account_age_months"], bad)
            self.assertIsNone(account["cais_last_updated"], bad)

    def test_account_number(self):
        self.assertEqual(_account(AccountNumber=" 12345 ")["account_number"], "12345")
        self.assertIsNone(_account(AccountNumber="")["account_number"])
        self.assertIsNone(_account(AccountNumber=None)["account_number"])


class MissedPaymentTests(SimpleTestCase):
    """Same answer the PDF parser gives for the same grid."""

    def _missed(self, codes, last_updated="2026-10-05"):
        return _account(AccountStatusCodes=codes, LastUpdatedDate=last_updated)["missed_payments_last_3_months"]

    def test_last_three_months_of_the_latest_year_are_summed(self):
        # Newest first: Oct=2, Sep=1, Aug=1, Jul=0 ...
        self.assertEqual(self._missed("211000000"), 4)

    def test_clean_history_is_zero(self):
        self.assertEqual(self._missed("000000000000"), 0)

    def test_d_counts_one_and_codes_above_6_are_ignored(self):
        self.assertEqual(self._missed("D80"), 1)

    def test_only_the_latest_years_row_is_read(self):
        # Last updated Feb 2026: the 2026 row is [Jan=0, Feb=0]; the 6s in 2025 are not counted.
        self.assertEqual(self._missed("00666", last_updated="2026-02-01"), 0)

    def test_latest_year_without_a_usable_code_falls_back_to_the_year_before(self):
        # 2026 row is only "8" (not a missed-payment code), so the parser uses 2025: [..., 3, 0].
        self.assertEqual(self._missed("803", last_updated="2026-01-01"), 3)

    def test_falls_back_to_balance_statuses_when_codes_are_absent(self):
        account = _account(AccountStatusCodes="", LastUpdatedDate="2026-10-05", AccountBalances=[
            {"AccountBalance": "0000100", "Status": "2"}, {"AccountBalance": "0000100", "Status": "1"}])
        self.assertEqual(account["missed_payments_last_3_months"], 3)

    def test_no_codes_or_no_last_updated_is_zero(self):
        self.assertEqual(self._missed("", last_updated="2026-10-05"), 0)
        self.assertEqual(self._missed("222", last_updated=None), 0)


class PublicInformationTests(SimpleTestCase):
    def test_judgements_are_ccjs_with_amounts_dates_and_order_numbers(self):
        info = _map(public=[_public("02", pounds="£557"), _public("17", pounds="£1,200", camera="")])["public_information"]
        self.assertTrue(info["has_ccj"])
        self.assertEqual(info["ccj_count"], 2)
        self.assertEqual(info["ccj_total_pence"], 55700 + 120000)
        self.assertEqual(info["ccjs"][0], {"amount_pence": 55700, "settled": None, "date": "01-02-2024",
                                           "case_number": "K1234", "court_name": None})
        self.assertIsNone(info["ccjs"][1]["case_number"])

    def test_amount_pence_is_the_pence_part(self):
        record = _public("02", pounds="£557")
        record["AmountPence"] = 50
        self.assertEqual(_map(public=[record])["public_information"]["ccjs"][0]["amount_pence"], 55750)

    def test_missing_amount(self):
        record = _public("02", pounds="")
        self.assertEqual(_map(public=[record])["public_information"]["ccjs"][0]["amount_pence"], 0)
        record = {"InformationType": "02"}
        info = _map(public=[record])["public_information"]
        self.assertIsNone(info["ccjs"][0]["amount_pence"])
        self.assertIsNone(info["ccj_total_pence"])

    def test_every_public_record_type(self):
        for code, group in PUBLIC_INFO_TYPES.items():
            with self.subTest(code=code, group=group):
                info = _map(public=[_public(code)])["public_information"]
                self.assertEqual(len(info["ccjs"]), 1 if group == "Judgement" else 0)
                self.assertEqual(info["iva_or_bankruptcy"], group in ("Bankruptcy", "IVA", "Debt Arrangement"))
                # Any record sets has_ccj: judgments directly, others through the
                # PDF parser's summary-count fallback (open decision D3).
                self.assertTrue(info["has_ccj"])
                self.assertIs(info["aoe_in_place"], False)

    def test_summary_count_fallback_without_judgements(self):
        info = _map(public=[_public("72")])["public_information"]
        self.assertEqual((info["has_ccj"], info["ccj_count"], info["ccjs"]), (True, 1, []))

    def test_no_public_information(self):
        result = _map()
        self.assertEqual(result["public_information"], {
            "has_ccj": False, "ccj_count": 0, "ccj_total_pence": None, "ccjs": [],
            "iva_or_bankruptcy": False, "debt_management": False, "aoe_in_place": False})
        self.assertIs(result["has_ccj"], False)
        self.assertIs(result["aoe_in_place"], False)

    def test_debt_management_flag(self):
        self.assertTrue(_map(debt_management="Y")["public_information"]["debt_management"])
        self.assertTrue(_map(debt_management="y")["public_information"]["debt_management"])
        self.assertFalse(_map(debt_management="N")["public_information"]["debt_management"])

    def test_top_level_flags_mirror_public_information(self):
        result = _map(public=[_public("02")])
        self.assertIs(result["has_ccj"], result["public_information"]["has_ccj"])
        self.assertIs(result["aoe_in_place"], result["public_information"]["aoe_in_place"])


class ReportLevelTests(SimpleTestCase):
    def test_client_name_is_the_applicant_without_title(self):
        self.assertEqual(_map()["client_name"], "JANE DOE")

    def test_client_address_is_the_current_residence(self):
        self.assertEqual(_map()["client_address"], "12 HIGH STREET, LEEDS, LS1 1AA")

    def test_client_address_part_order(self):
        document = _doc()
        document["Response"]["Locations"][0]["UKLocation"] = {
            "Flat": "FLAT 2", "HouseName": "ROSE COURT", "HouseNumber": "12", "Street": "HIGH STREET",
            "District": "HEADINGLEY", "PostTown": "LEEDS", "County": "WEST YORKSHIRE", "Postcode": "LS61AA"}
        self.assertEqual(map_search_to_extracted_data(document, CODE_TABLES)["client_address"],
                         "FLAT 2, ROSE COURT, 12 HIGH STREET, HEADINGLEY, LEEDS, WEST YORKSHIRE, LS6 1AA")

    def test_no_current_residence_gives_empty_address(self):
        document = _doc()
        document["Response"]["Residencies"] = [{"LocationIdentifier": 2, "Type": "P"}]
        self.assertEqual(map_search_to_extracted_data(document, CODE_TABLES)["client_address"], "")

    def test_report_dates_are_the_search_date(self):
        result = _map(_detail())
        self.assertEqual((result["report_date"], result["printed_report_date"]), ("2026-03-04", "2026-03-04"))

    def test_without_a_search_date_report_date_falls_back_to_latest_update(self):
        result = _map(_detail(LastUpdatedDate="2026-01-10"), _detail(LastUpdatedDate="2026-02-20"), search_date=None)
        self.assertEqual((result["report_date"], result["printed_report_date"]), ("2026-02-20", ""))
        self.assertEqual((_map(search_date=None)["report_date"]), "")


class MalformedAndIncompleteTests(SimpleTestCase):
    def test_not_an_experian_document(self):
        for document in (None, [], "text", {}, {"Response": None}, {"Response": []}):
            with self.assertRaises(ExperianDataError):
                map_search_to_extracted_data(document, CODE_TABLES)

    def test_empty_response_maps_to_an_empty_report(self):
        result = map_search_to_extracted_data({"Response": {}}, CODE_TABLES)
        self.assertEqual(list(result), TOP_LEVEL_KEYS)
        self.assertEqual((result["accounts"], result["mortgage_accounts"], result["other_accounts"]), ([], [], []))
        self.assertEqual((result["client_name"], result["client_address"], result["report_date"]), ("", "", ""))

    def test_wrongly_typed_sections_are_ignored(self):
        document = _doc([_detail()])
        consumer = document["Response"]["FullConsumerData"]["ConsumerData"]
        consumer["CAIS"].append("garbage")
        consumer["CAIS"].append({"CAISDetails": "garbage"})
        consumer["PublicInformation"] = "garbage"
        document["Response"]["Applicants"] = "garbage"
        document["Response"]["FullConsumerData"]["ConsumerDataSummary"] = []
        result = map_search_to_extracted_data(document, CODE_TABLES)
        self.assertEqual(len(result["accounts"]), 1)
        self.assertEqual(result["client_name"], "")
        self.assertFalse(result["has_ccj"])

    def test_single_object_instead_of_list_is_accepted(self):
        document = _doc()
        document["Response"]["FullConsumerData"]["ConsumerData"]["CAIS"] = {"CAISDetails": _detail()}
        self.assertEqual(len(map_search_to_extracted_data(document, CODE_TABLES)["accounts"]), 1)

    def test_unknown_public_record_code_is_counted_only_by_the_summary(self):
        info = _map(public=[_public("99")])["public_information"]
        self.assertEqual((info["ccjs"], info["iva_or_bankruptcy"]), ([], False))


# ---------------------------------------------------------------------------
# Parity with the real PDF path
# ---------------------------------------------------------------------------

_CATEGORY = {code: desc for code, desc in ACCOUNT_TYPES.items()}


def _fake_pdf_open(text):
    page = MagicMock()
    page.extract_text.return_value = text
    pdf = MagicMock()
    pdf.pages = [page]
    pdf.__enter__.return_value = pdf
    pdf.__exit__.return_value = False
    return pdf


def _dmy(iso):
    return f"{iso[8:10]}-{iso[5:7]}-{iso[0:4]}"


def _grid_lines(codes, last_updated):
    """The payment grid as the PDF parser reads it: a year label, then that year's codes."""
    year, month = int(last_updated[:4]), int(last_updated[5:7])
    rows = {}
    for offset, code in enumerate(codes):
        y, _ = divmod((year * 12 + month - 1) - offset, 12)
        rows.setdefault(y, []).insert(0, code)
    lines = ["Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec"]
    for y in sorted(rows):
        lines += [str(y), " ".join(rows[y])]
    return lines


def _render(document):
    """The search as report text, one field per line, in the rendered report's order."""
    response = document["Response"]
    consumer = response["FullConsumerData"]["ConsumerData"]
    summary = response["FullConsumerData"]["ConsumerDataSummary"]["SummaryDetails"]
    groups = [PUBLIC_INFO_TYPES.get(p["InformationType"]) for b in consumer["PublicInformation"]
              for p in b["PublicInfoDetails"]]
    search = response["FullConsumerData"]["ControlDetails"]["SearchDate"]
    lines = [
        "Consumer Credit Report",
        "Experian Reference AB1C23D4EF",
        f"Issue Date and Time {search[8:10]}/{search[5:7]}/{search[0:4]} 17:26:04",
        "Summary",
        "Current Address: 12 HIGH STREET, LEEDS, LS1 1AA",
        "Public Information",
        f"Number: {summary['PublicInfoSummary']['Number']}",
        "IVA or Bankruptcy Detected: " + ("Y" if any(g in ("Bankruptcy", "IVA", "Debt Arrangement") for g in groups) else "N"),
        "Debt Management: " + summary["SummaryFlags"]["DebtManagement"],
    ]
    for block in consumer["PublicInformation"]:
        for record in block["PublicInfoDetails"]:
            lines += ["", "", "", "",
                      f"Type: {PUBLIC_INFO_TYPES[record['InformationType']]} - Record",
                      f"Amount: {record['AmountPounds']}.0",
                      f"Date: {_dmy(record['InformationDate'])}",
                      f"Source: {record['DataSource']}",
                      "Court Name: NORTHAMPTON",
                      f"Court Order Number: {record['CameraNumber']}"]
    lines += ["", "", "", "", "CAIS (Credit Account Information Sharing)"]
    for block in consumer["CAIS"]:
        for d in block["CAISDetails"]:
            balances = d["AccountBalances"]
            lines += [
                f"{d['SupplyCompanyName']} - {_CATEGORY[d['AccountType']]}",
                f"Status: {ACCOUNT_STATUS_LABELS[d['AccountStatus']]}",
                f"CAIS Last Updated: {_dmy(d['LastUpdatedDate'])}",
                f"Account Number: {d['AccountNumber']}",
                f"Start Date: {_dmy(d['CAISAccStartDate'])}",
                f"Start Balance: £{int(balances[-1]['AccountBalance'])}",
                f"Current Balance: £{int(balances[0]['AccountBalance'])}",
                "Payment Frequency: Monthly",
                f"Payment History: {len(balances)} Months",
                f"Worst Status: {WORST_STATUS_LABELS[d['WorstStatus']]}",
                *_grid_lines(d["AccountStatusCodes"], d["LastUpdatedDate"]),
            ]
    return "\n".join(lines)


def _bal(*pounds):
    return [{"AccountBalance": f"{p:07d}", "Status": "0"} for p in pounds]


def _parity_document():
    alias = next(k for k, v in CREDITOR_ALIAS_MAP.items()
                 if v.lower() != k and k[:1].isalpha() and ":" not in k and " - " not in k)
    details = [
        _detail(SupplyCompanyName="HALIFAX", AccountType="05", AccountStatus="A", WorstStatus="0",
                AccountBalances=_bal(350, 400, 1200), AccountStatusCodes="000"),
        _detail(SupplyCompanyName="LENDABLE LTD", AccountType="02", AccountStatus="D", WorstStatus="2",
                AccountNumber="LN998877", CAISAccStartDate="2024-01-10", LastUpdatedDate="2026-03-01",
                AccountBalances=_bal(5200, 5100, 5000), AccountStatusCodes="210"),
        _detail(SupplyCompanyName="NATIONWIDE BS", AccountType="03", WorstStatus="1",
                AccountBalances=_bal(150000, 151000), AccountStatusCodes="01"),
        _detail(SupplyCompanyName="ADMIRAL INSURANCE SERVICES", AccountType="46", AccountStatus="S",
                LastUpdatedDate="2025-04-01", AccountBalances=_bal(0, 120), AccountStatusCodes="00"),
        _detail(SupplyCompanyName="CAPITAL ONE", AccountType="05", AccountStatus="F", WorstStatus="8",
                LastUpdatedDate="2026-01-15", AccountBalances=_bal(900, 900, 850), AccountStatusCodes="8D3"),
        _detail(SupplyCompanyName="EE LIMITED", AccountType="18", WorstStatus="U",
                AccountBalances=_bal(45, 30), AccountStatusCodes="U0"),
        _detail(SupplyCompanyName="BARCLAYS BANK UK PLC", AccountType="15", WorstStatus="D",
                AccountBalances=_bal(0), AccountStatusCodes="D"),
        _detail(SupplyCompanyName="SANTANDER UK PLC", AccountType="30",
                AccountBalances=_bal(98000, 99000), AccountStatusCodes="00"),
        _detail(SupplyCompanyName=alias.upper(), AccountType="05", AccountBalances=_bal(75, 80), AccountStatusCodes="00"),
    ]
    public = [_public("02", pounds="£557"), _public("17", pounds="£1200", camera="L7KQ4M25", info_date="2023-06-30"),
              _public("72", pounds="", camera="")]
    return _doc(details, public, debt_management="Y")


class PdfParityTests(SimpleTestCase):
    """The same search through extract_credit_report() (as report text) and through the mapper.

    Assumes the PDF text comes out one field per line, as the existing parser
    tests do; real Experian PDFs were not available to confirm the layout.
    """

    def _both(self, document):
        with patch("debt_app.integrations.credit_report.pdfplumber.open",
                   return_value=_fake_pdf_open(_render(document))):
            pdf = extract_credit_report("ignored.pdf")
        return pdf, map_search_to_extracted_data(document, CODE_TABLES)

    def test_same_output_as_the_pdf_path(self):
        pdf, mapped = self._both(_parity_document())
        self.assertNotIn("extraction_error", pdf)
        self.assertEqual(pdf["agency"], "Experian")
        self.assertEqual(len(pdf["accounts"]) + len(pdf["mortgage_accounts"]) + len(pdf["other_accounts"]), 9)

        # Documented, intended differences.
        # PDF: the first line containing "Name:" -- here a public record's "Court Name:".
        self.assertEqual(pdf["client_name"], "NORTHAMPTON")
        self.assertEqual(mapped["client_name"], "JANE DOE")
        self.assertEqual([c["court_name"] for c in pdf["public_information"]["ccjs"]], ["NORTHAMPTON"] * 2)
        self.assertEqual([c["court_name"] for c in mapped["public_information"]["ccjs"]], [None, None])

        for result in (pdf, mapped):
            result.pop("client_name")
            for ccj in result["public_information"]["ccjs"]:
                ccj.pop("court_name")
        self.assertEqual(list(mapped), list(pdf))
        for key in pdf:
            with self.subTest(key=key):
                self.assertEqual(mapped[key], pdf[key])

    def test_summary_count_fallback_matches_the_pdf_path(self):
        pdf, mapped = self._both(_doc([_detail()], [_public("72", pounds="", camera="")]))
        self.assertEqual(mapped["public_information"], pdf["public_information"])
        self.assertEqual((mapped["has_ccj"], mapped["public_information"]["ccj_count"]), (True, 1))

    def test_clean_report_matches_the_pdf_path(self):
        pdf, mapped = self._both(_doc([_detail()]))
        pdf.pop("client_name"), mapped.pop("client_name")
        self.assertEqual(mapped, pdf)
