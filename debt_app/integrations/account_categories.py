"""The canonical account categories, and the one place a credit-report account
gets one (Track A of the account-type mapping, 2026-11-19).

    ACCOUNT_CATEGORIES       the shared vocabulary -- CAT keeps an identical
                             copy (`case_assesment/common/account_categories.py`),
                             pinned by a test on each side
    account_category(...)    an account's category from what it already says
    type_source(...)         the source fields every parser adds to an account

⚠️ ADDITIVE ONLY. Nothing in this engine reads `account_category`: debt
classification, secured status, matching and every rule still read
`type_code` exactly as before. The category is information carried beside it.

⚠️ ONLY AGREED MAPPING DECISIONS LIVE HERE. `CATEGORY_BY_TYPE_CODE` names only
what each existing `type_code` already means; the one decision taken since,
D-01 (genuine mortgage products, `MORTGAGE_SOURCE_TYPES`), is by wording. Everything the business has not
decided stays `unknown` (decision document, principle 7): the catch-all "OT",
Advize codes with no documented meaning (BD, AL, TA, any fallback code),
codes whose category is an open decision (DP, IL, MU), and any account whose
report wording is one of the open Low-confidence descriptions -- so Experian's
"Communications", which the category map turns into UT, is `unknown`, not a
utility. Changing a row here is a business decision, not a refactor.

`type_unmapped` is kept apart from the category on purpose: it says the
report's own code or wording was not in the extractor's map (and fell to the
"OT" default), which is a fact about the source, not a classification.
"""
from __future__ import annotations

UNKNOWN = "unknown"

#: The canonical categories (decision document, section 4). The vocabulary
#: only -- which accounts take which category is `account_category` below.
ACCOUNT_CATEGORIES = (
    "card", "revolving_credit", "catalogue", "unsecured_loan", "home_credit",
    "payday_loan", "deferred_payment", "hire_purchase", "lease", "mortgage",
    "secured_loan", "mortgage_event", "current_account", "overdraft",
    "bank_account", "utility", "telecom", "tv_services", "business_telecom",
    "telecom_bundle", "vehicle_insurance", "insurance_policy",
    "insurance_arrears", "priority_debt", "rent", "goods_rental",
    "student_loan", "gambling_account", "court_judgment", "unknown",
)

#: What each existing `type_code` already means -- nothing more. A code not
#: listed is `unknown`.
CATEGORY_BY_TYPE_CODE = {
    "CC": "card", "ST": "card", "MO": "catalogue",
    "UL": "unsecured_loan", "PL": "unsecured_loan",
    "HP": "hire_purchase", "MG": "mortgage",
    "UT": "utility", "EW": "utility", "EE": "utility",
    "TM": "telecom", "CA": "current_account",
    "MI": "vehicle_insurance", "BK": "bank_account",
}

#: Report wordings whose classification is an open business decision (the
#: Low-confidence Experian descriptions, decision document section 1): an
#: account carrying one is `unknown` whatever code the map gave it.
UNCLEAR_SOURCE_TYPES = frozenset({
    "communications", "communication", "variable subscription", "unpresentable - cheques",
    "combined credit account", "contingency liability", "oil", "fuel card (not motor fuel)",
    "cable", "satellite", "business line", "education", "property rental", "other rental",
    "court actions", "asset", "mortgage and unsecured loan", "gambling",
})

#: ⚠️ DECISION D-01 (agreed 2026-11-19, decision document "Review outcome"):
#: every GENUINE mortgage product is the Mortgage category, its original type
#: kept beside it. Experian 03, 16, 25, 30-35, by the report's own wording --
#: they read "OT" today (only "Mortgage", 03, maps to MG).
#:
#: CATEGORY ONLY. `type_code` stays "OT" and the account stays in the bucket
#: it is in: moving it to MG would move it into `mortgage_accounts`, which the
#: equity rules read -- that is the secured-status decision (D-13), still
#: open. NOT here, by decision: the CML events 12-14 (possession order,
#: voluntary surrender, arrears move) and 69 "Mortgage and Unsecured Loan" --
#: both still open, so `unknown`.
MORTGAGE_SOURCE_TYPES = frozenset({
    "mortgage", "second mortgage", "flexible mortgages", "residential mortgage",
    "buy to let mortgage", "ltv mortgage", "current account offset mortgage",
    "investment offset mortgage", "shared ownership mortgage",
})

#: Where an account was read. One value per extraction path.
SOURCE_ARYZA_ADVIZE_PDF = "aryza_advize_pdf"
SOURCE_EXPERIAN_PDF = "experian_pdf"
SOURCE_EXPERIAN_VALID8_PDF = "experian_valid8_pdf"
SOURCE_EXPERIAN_JSON = "experian_json"


def _words(value) -> str:
    return " ".join(str(value or "").lower().split())


def account_category(type_code, source_account_type="") -> str:
    """The account's canonical category, or `unknown`. Reads only what the
    account already says; never changes `type_code`."""
    wording = _words(source_account_type)
    if wording in UNCLEAR_SOURCE_TYPES:
        return UNKNOWN
    if wording in MORTGAGE_SOURCE_TYPES:
        return "mortgage"                   # D-01: the wording decides, not "OT"
    return CATEGORY_BY_TYPE_CODE.get(str(type_code or "").strip().upper(), UNKNOWN)


def type_source(*, source_system, type_code, source_account_code=None,
                source_account_type="", type_unmapped=False) -> dict:
    """The source fields a parser adds beside `type_code`: where the account
    was read, the report's own code and wording exactly as given (None / ""
    when the report gives none), whether that code or wording was outside the
    extractor's map, and the canonical category.

    ⚠️ On an Aryza Advize report the PRINTED CODE alone decides the category:
    its "Account Type:" wording is the lender's description, kept as
    `source_account_type` but never read as a classification -- CAT reads an
    Advize account the same way (`ledger/credit_report.py :: _family_wording`),
    so the two never disagree on a utility / telecom account."""
    code = None if source_account_code is None else str(source_account_code)
    wording = str(source_account_type or "").strip()
    classify_by = "" if source_system == SOURCE_ARYZA_ADVIZE_PDF else wording
    return {
        "source_account_type": wording,
        "source_account_code": code,
        "source_system": source_system,
        "account_category": account_category(type_code, classify_by),
        "type_unmapped": bool(type_unmapped),
    }
