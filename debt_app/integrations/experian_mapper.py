"""
integrations/experian_mapper.py

Maps one Experian search document (Credit_Searches.JsonData) to the dict
extract_credit_report() returns for an Experian PDF, so the rest of the app
consumes it unchanged.

Source of truth is the PDF path: integrations/credit_report.py's
_parse_experian_account() and extract_public_information(). The JSON is the
data the rendered report (Credit_Searches.HTMLData, which those PDFs are
printed from) was generated from; every value table below was checked against
the rendered report for the same search (200 searches, ~5,000 accounts, no
mismatches). Where the JSON and the PDF parser can differ, the comment says so.

Pure functions: no database access, nothing stored, raw JSON never returned.
"""

import logging
from datetime import datetime

from debt_app.integrations.credit_report import (
    RECONCILIATION_ONLY_TYPE_CODES,
    _EXPERIAN_CATEGORY_TO_TYPE,
    _ccj_amount_to_pence,
    _clean_address,
    _months_since,
    _parse_amount,
    _parse_missed_payments_last_3_months,
    match_creditor,
    normalise_start_date_iso,
)
from debt_app.integrations.experian_db import ExperianCodeTables, ExperianDataError

logger = logging.getLogger(__name__)

AGENCY = "Experian"

# CAISDetails.AccountStatus -> the wording the report prints after "Status:".
# The PDF parser .capitalize()s that wording, which leaves these unchanged.
ACCOUNT_STATUS_LABELS = {
    "A": "Active",
    "D": "Delinquent",
    "F": "Default",
    "S": "Settled",
}

# CAISDetails.WorstStatus -> the wording printed after "Worst Status:".
# "1" really is printed without its digit ("Month Delinquent").
WORST_STATUS_LABELS = {
    "0": "Satisfactory",
    "1": "Month Delinquent",
    "2": "2 Months Delinquent",
    "3": "3 Months Delinquent",
    "4": "4 Months Delinquent",
    "5": "5 Months Delinquent",
    "6": "6 Months Delinquent",
    "8": "Default",
    "D": "Dormant",
    "U": "Unclassified",
}

# PublicInfo_Type_Codes groups the report counts as "IVA or Bankruptcy Detected: Y".
INSOLVENCY_GROUPS = {"Bankruptcy", "IVA", "Debt Arrangement"}

# The group whose records render as "Type: Judgement - ..." -- the records the
# PDF parser's `type:\s*judg` anchor picks up. ("CCJ" group records render as
# "Type: CCJ - ..." and are not picked up by that anchor.)
JUDGEMENT_GROUP = "Judgement"


def _dict(value) -> dict:
    return value if isinstance(value, dict) else {}


def _list(value) -> list[dict]:
    if isinstance(value, dict):
        value = [value]
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _text(value) -> str:
    return str(value).strip() if value is not None else ""


def _iso_date(value) -> str | None:
    """'YYYY-MM-DD...' -> 'YYYY-MM-DD', or None when absent/invalid."""
    text = _text(value)[:10]
    try:
        return datetime.strptime(text, "%Y-%m-%d").date().isoformat()
    except ValueError:
        return None


def _dmy(value) -> str | None:
    """ISO date -> 'DD-MM-YYYY', the form the PDF path stores for Experian dates."""
    iso = _iso_date(value)
    return datetime.strptime(iso, "%Y-%m-%d").strftime("%d-%m-%Y") if iso else None


def _missed_payments_last_3_months(detail: dict) -> int:
    """The PDF parser's own count, run on the same payment grid.

    AccountStatusCodes is the report's payment grid, one code per month,
    newest first; its first code is the LastUpdatedDate month. It is laid back
    out as the year-label / status-row lines the PDF parser reads, and handed
    to that parser, so its rules (most recent year with a usable row, codes
    0-6 and "D", last 3 summed, a row holding "U" or "?" ignored) apply
    unchanged rather than being re-implemented here.
    """
    codes = _text(detail.get("AccountStatusCodes"))
    if not codes:
        codes = "".join(_text(b.get("Status"))[:1] for b in _list(detail.get("AccountBalances")))
    last_updated = _iso_date(detail.get("LastUpdatedDate"))
    if not codes or not last_updated:
        return 0
    year, month = int(last_updated[:4]), int(last_updated[5:7])
    rows: dict[int, list[str]] = {}
    for offset, code in enumerate(codes):
        y, m = divmod((year * 12 + month - 1) - offset, 12)
        rows.setdefault(y, []).insert(0, code)
    lines = []
    for y in sorted(rows):
        lines += [str(y), " ".join(rows[y])]
    return _parse_missed_payments_last_3_months(lines)


def _map_account(detail: dict, code_tables: ExperianCodeTables) -> dict | None:
    """One CAISDetails record -> the dict _parse_experian_account() returns."""
    raw_name = _text(detail.get("SupplyCompanyName"))
    if not raw_name:
        # The rendered report heads every account with this name; a record
        # without one has nothing to match a creditor on.
        logger.warning("[EXPERIAN MAP] CAIS record without SupplyCompanyName skipped")
        return None

    type_desc = code_tables.account_types.get(_text(detail.get("AccountType")), "")
    type_code = _EXPERIAN_CATEGORY_TO_TYPE.get(type_desc.lower(), "OT")

    balances = _list(detail.get("AccountBalances"))
    # Newest first, whole pounds. The newest is the printed "Current Balance";
    # the oldest is the printed "Start Balance".
    current_balance = _parse_amount(_text(balances[0].get("AccountBalance"))) if balances else None
    start_balance = _parse_amount(_text(balances[-1].get("AccountBalance"))) if balances else None

    worst_code = _text(detail.get("WorstStatus"))
    worst_status = WORST_STATUS_LABELS.get(worst_code)
    if worst_code and worst_status is None:
        logger.warning("[EXPERIAN MAP] unknown WorstStatus code %r", worst_code)

    status_code = _text(detail.get("AccountStatus"))
    account_status = ACCOUNT_STATUS_LABELS.get(status_code)
    if account_status is None:
        if status_code:
            logger.warning("[EXPERIAN MAP] unknown AccountStatus code %r", status_code)
        # The PDF parser's fallback when no "Status:" is printed.
        account_status = "Default" if "default" in (worst_status or "").lower() else "Open"

    start_date = normalise_start_date_iso(_iso_date(detail.get("CAISAccStartDate")))
    normalised = raw_name.lower().strip()

    return {
        "raw_name": raw_name,
        "type_code": type_code,
        "normalised_name": normalised,
        "matched_creditor": match_creditor(raw_name),
        "account_age_months": _months_since(start_date) if start_date else None,
        "missed_payments_last_3_months": _missed_payments_last_3_months(detail),
        "recent_spending": False,
        "current_balance": current_balance,
        "start_balance": start_balance,
        # Not printed on an Experian report, so None on the PDF path too.
        "credit_limit": None,
        "utilisation_pct": None,
        "account_status": account_status,
        "account_status_subjective": "",
        "worst_status": worst_status,
        "payment_history_months": 0,
        "monthly_payment": None,
        "account_number": _text(detail.get("AccountNumber")) or None,
        "start_date": start_date,
        "cais_last_updated": _dmy(detail.get("LastUpdatedDate")),
        "reconciliation_only": type_code in RECONCILIATION_ONLY_TYPE_CODES,
    }


def _client_name(response: dict) -> str:
    """The applicant's own name, without title.

    Differs from the PDF path on purpose: that takes the first "Name:" line in
    the text, which is often an account's holder name rather than the
    applicant's (34 of 100 sampled reports).
    """
    applicants = _list(response.get("Applicants"))
    person = _dict(applicants[0].get("Person")) if applicants else {}
    return " ".join(part for part in (_text(person.get("Forename")), _text(person.get("Surname"))) if part)


def _client_address(response: dict) -> str:
    """The current residence (Residencies.Type "C"), in the printed order."""
    current = next((r for r in _list(response.get("Residencies")) if _text(r.get("Type")) == "C"), None)
    if current is None:
        return ""
    location = next(
        (loc for loc in _list(response.get("Locations"))
         if loc.get("LocationIdentifier") == current.get("LocationIdentifier")),
        None,
    )
    uk = _dict(_dict(location).get("UKLocation"))
    street = " ".join(p for p in (_text(uk.get("HouseNumber")), _text(uk.get("Street"))) if p)
    parts = [_text(uk.get("Flat")), _text(uk.get("HouseName")), street, _text(uk.get("District")),
             _text(uk.get("PostTown")), _text(uk.get("County")), _text(uk.get("Postcode"))]
    return _clean_address(", ".join(p for p in parts if p))


def _ccj_amount_pence(detail: dict) -> int | None:
    """AmountPounds is the pounds; AmountPence only the pence part (0 in every
    sampled record). The report prints AmountPounds."""
    pounds = _ccj_amount_to_pence(_text(detail.get("AmountPounds")))
    pence = detail.get("AmountPence")
    if pounds is None and pence is None:
        return None
    try:
        pence = int(pence or 0)
    except (TypeError, ValueError):
        pence = 0
    return (pounds or 0) + pence


def _public_information(consumer: dict, summary: dict, code_tables: ExperianCodeTables) -> dict:
    """Same shape and rules as extract_public_information() on an Experian report."""
    groups = []
    ccjs = []
    for block in _list(consumer.get("PublicInformation")):
        for detail in _list(block.get("PublicInfoDetails")):
            group = code_tables.public_info_types.get(_text(detail.get("InformationType")))
            groups.append(group)
            if group != JUDGEMENT_GROUP:
                continue
            ccjs.append({
                "amount_pence": _ccj_amount_pence(detail),
                # The report prints no "Settled:" line, so the PDF path is None too.
                "settled": None,
                "date": _dmy(detail.get("InformationDate")),
                # Printed as "Court Order Number" when present.
                "case_number": _text(detail.get("CameraNumber")) or None,
                # No JSON field produces the printed "Court Name".
                "court_name": None,
            })

    info = {
        "has_ccj": False,
        "ccj_count": 0,
        "ccj_total_pence": None,
        "ccjs": [],
        "iva_or_bankruptcy": any(g in INSOLVENCY_GROUPS for g in groups),
        "debt_management": _text(_dict(summary.get("SummaryFlags")).get("DebtManagement")).upper() == "Y",
        # No attachment-of-earnings record type exists in Experian's public data.
        "aoe_in_place": False,
    }
    if ccjs:
        amounts = [c["amount_pence"] for c in ccjs if c["amount_pence"]]
        info.update(has_ccj=True, ccj_count=len(ccjs), ccjs=ccjs,
                    ccj_total_pence=sum(amounts) if amounts else None)
    else:
        # The PDF parser's fallback: the summary "Public Information ... Number: N"
        # counts every public record, not only judgments.
        try:
            number = int(_dict(summary.get("PublicInfoSummary")).get("Number") or 0)
        except (TypeError, ValueError):
            number = 0
        if number > 0:
            info.update(has_ccj=True, ccj_count=number)
    return info


def map_search_to_extracted_data(document: dict, code_tables: ExperianCodeTables) -> dict:
    """One Experian search document -> CreditReport.extracted_data.

    Same keys, types and units as extract_credit_report() for an Experian PDF
    (money in integer pence, start_date ISO, cais_last_updated DD-MM-YYYY).
    Raises ExperianDataError only when the document is not an Experian
    response at all; missing parts map to empty lists / None as on the PDF path.
    """
    if not isinstance(document, dict) or not isinstance(document.get("Response"), dict):
        raise ExperianDataError("Not an Experian search document (no Response object)")
    response = document["Response"]
    full = _dict(response.get("FullConsumerData"))
    consumer = _dict(full.get("ConsumerData"))
    summary = _dict(_dict(full.get("ConsumerDataSummary")).get("SummaryDetails"))

    accounts: list[dict] = []
    mortgage_accounts: list[dict] = []
    other_accounts: list[dict] = []
    unmatched: list[str] = []
    last_updated_dates = []
    for block in _list(consumer.get("CAIS")):
        for detail in _list(block.get("CAISDetails")):
            parsed = _map_account(detail, code_tables)
            if parsed is None:
                continue
            last_updated = _iso_date(detail.get("LastUpdatedDate"))
            if last_updated:
                last_updated_dates.append(last_updated)
            # Routing exactly as extract_credit_report().
            if parsed["reconciliation_only"]:
                other_accounts.append(parsed)
            elif parsed["type_code"] == "MG":
                mortgage_accounts.append(parsed)
            else:
                accounts.append(parsed)
                if parsed["matched_creditor"] == parsed["raw_name"]:
                    unmatched.append(parsed["raw_name"])

    # "Issue Date and Time" is the search date (100 of 100 sampled). Without
    # it the PDF path falls back to the latest "CAIS Last Updated".
    printed_report_date = _iso_date(_dict(full.get("ControlDetails")).get("SearchDate")) or ""
    report_date = printed_report_date or (max(last_updated_dates) if last_updated_dates else "")
    public_info = _public_information(consumer, summary, code_tables)

    return {
        "agency": AGENCY,
        "client_name": _client_name(response),
        "client_address": _client_address(response),
        "report_date": report_date,
        "printed_report_date": printed_report_date,
        "accounts": accounts,
        "mortgage_accounts": mortgage_accounts,
        "other_accounts": other_accounts,
        "unmatched_accounts": unmatched,
        "public_information": public_info,
        "has_ccj": public_info["has_ccj"],
        "aoe_in_place": public_info.get("aoe_in_place", False),
    }
