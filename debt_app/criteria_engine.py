"""
IVA Criteria Assessment Engine — Phase 3/4 rewrite

Evaluates a case JSON payload against all 58 seeded rules.
Rule keys match the DB exactly: TIG-01, WATCH-22.1, TIX-01, EVOLVE-01, etc.

Architecture:
  - assess_case() is the single entry point
  - _parse_case() normalises the raw JSON payload into a clean CaseData dict
  - Each rule is an independent method returning a RuleResult
  - WATCH / TIX / EVOLVE rules only run when the relevant representative is detected

No Django ORM calls inside rule methods.
Creditor representative lookup is done once in assess_case() and passed in.
"""

# ---------------------------------------------------------------------------
# Rule Code Reference — per-creditor codes emitted by _check_creditor_individual
# ---------------------------------------------------------------------------
# CREDITOR-UNKNOWN                  — no CreditorCriteria row found for this creditor
# CREDITOR-BLOCKED                  — creditor blocked until further notice
# CREDITOR-NO-PAYMENT               — no payment ever made; creditor requires at least one
# CREDITOR-REPOSSESSION-RISK        — vehicle arrears threshold exceeded or asset still held
# CREDITOR-ARRANGEMENT-CALL         — pre-proposal arrangement call not confirmed
# CREDITOR-FEES-CAP                 — IP fees capped at X% by this creditor (informational)
# CREDITOR-MAJORITY-SHARE-EXCEEDED  — creditor holds more than X% of total unsecured debt
# CREDITOR-SECOND-IVA-REJECT        — creditor rejects clients who have had a prior IVA
# CREDITOR-EQUITY-EXCEEDS-DEBT      — equity at 85% LTV exceeds total unsecured debt (per-creditor)
# CREDITOR-NOT-GRANT-OVERPAYMENT    — creditor only accepts grant overpayment debts
# CREDITOR-FRAUD-CLAIM-RISK         — fraud claim risk noted; caseworker review required (informational)
# CREDITOR-RECENT-SPEND-REJECT      — creditor rejects recent spend; matching transaction(s) found within N months
# CREDITOR-RECENT-SPEND-UNVERIFIED  — creditor requires no recent spend but no transaction data in payload
# CREDITOR-MANUAL-CHECK-REQUIRED    — criteria_notes is non-empty; caseworker must read and apply manually

import logging
import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from debt_app.helpers import CREDITOR_ALIAS_MAP, normalise_creditor_name

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# RuleResult dataclass
# ---------------------------------------------------------------------------

@dataclass
class RuleResult:
    rule_id: str
    severity: str           # "hard_block" | "flag" | "info" | "pass"
    triggered: bool         # True if a problem was found
    message: str            # Human-readable explanation for the caseworker
    threshold: Optional[float] = None    # Threshold compared against (numeric rules)
    actual_value: Optional[float] = None # Actual value from the case (numeric rules)
    creditors: list = field(default_factory=list)


# ---------------------------------------------------------------------------
# Engine-wide constants
# ---------------------------------------------------------------------------

WATCH_HP_MONTHLY_CAP = 400  # WATCH criteria: HP > £400/month is a flag (TIX uses £250)

# A case with this share (or more) of total debt owed to UNIDENTIFIED creditors
# is referred for manual review — the majority/assessment cannot be relied upon
# until those creditors are identified.
UNKNOWN_REFERRAL_PCT = 0.10

# Status normalisation — DB values -> canonical engine output values
_STATUS_NORMALISE = {
    "ACCEPTANCE":    "ACCEPT",
    "REJECTED":      "REJECT",
    "GENERAL":       "UNKNOWN",
    "WILL_CONSIDER": "WILL_CONSIDER",
    "DO_NOT_VOTE":   "DO_NOT_VOTE",
    "ACCEPT":        "ACCEPT",
    "REJECT":        "REJECT",
    "UNKNOWN":       "UNKNOWN",
}

# Rules that cannot be suppressed by a caseworker override code
NON_OVERRIDABLE_RULE_IDS = frozenset({
    "TIG-05",       # Core income evidence must be present
    "TIG-11",       # Bank statement required
    "TIG-13",       # HMRC majority — IVA not appropriate
    "WATCH-22.13",  # Antecedent transactions — no exceptions
})

# Rules that evaluate case-wide (body-level) data, not per-creditor data.
# These must never be used to derive a representative body outcome that gets
# stamped onto individual creditor findings — they belong in the case-level
# flags/hard_blocks lists only.
_BODY_LEVEL_ONLY_RULES = frozenset({
    "TIX-04",       # Total HP monthly payment — case-wide, not per-creditor
    "WATCH-22.10",  # Total HP monthly payment — case-wide, not per-creditor
    "TIG-18",       # Total spend vs income — case-wide transaction scan (no open banking guard)
    "TIG-19",       # Shop Direct recent purchases — case-wide transaction scan
    "TIG-19.1",     # Shop Direct account age — case-wide
    "TIG-20",       # Creation recent purchases — case-wide transaction scan
    "TIG-20.1",     # Creation recent spend hard block — case-wide
    "TIX-03",       # Creation / Sygma / Laser recent spend hard block — case-wide
    "WATCH-22.2",   # WATCH-22.2 — Debt repayable in under 6 years from DI
    "WATCH-22.4",   # Equity vs debt — case-wide property check
    "WATCH-22.5",   # Single lender — case-wide creditor composition check
})

LUXURY_CATEGORIES: frozenset[str] = frozenset({
    "gambling", "luxury", "entertainment", "holidays", "travel",
    "jewellery", "electronics", "clothing_luxury", "restaurants_fine_dining",
})


# ---------------------------------------------------------------------------
# Named creditor sets (business constants — not DB config)
# ---------------------------------------------------------------------------

_SHOP_DIRECT_NAMES = frozenset({
    "shop direct", "very", "littlewoods", "littlewoods.com",
    # EXCEL_CRITERIA_REFERENCE.md — TIG Shop Direct: JD Williams included
    "jd williams", "simply be", "jacamo", "fashion world", "marisota",
})

_CREATION_NAMES = frozenset({
    "creation", "sygma", "laser", "creation consumer finance",
})

_LINK_NAMES = frozenset({
    "link financial",
    "link financial outsourcing",
    "link financial outsourcing limited",
    "link financial ltd",
    "link financial - iva",
    "link financial - td",
})

def _is_link_financial_name(name: str) -> bool:
    """Return True for any 'Link Financial …' variant regardless of suffix/qualifier.

    Aryza and the CRM append qualifiers like '- IVA', '(LBG)', '- TD' that the
    old frozenset check missed.  Normalising to alphanumeric-only and testing a
    prefix avoids maintaining an ever-growing list of variants.
    """
    return _norm(name).startswith("linkfinancial")

_HMRC_NAMES = frozenset({
    "hmrc",
    "hm revenue and customs",
    "hm revenue & customs",
    "hm revenue and customs (vat)",
    "hm revenue and customs (paye)",
    "hm revenue and customs (self assessment)",
    "her majesty's revenue and customs",
    "his majesty's revenue and customs",
    "her majesty's revenue & customs",
    "his majesty's revenue & customs",
})

_PRIVATE_PARKING_NAMES = frozenset({
    "parkingeye",
    "parkingeye ltd",
    "excel parking services",
    "excel parking services ltd",
    "euro car parks",
    "euro car parks ltd",
    "ukpc",
    "uk parking control",
    "uk parking control ltd",
    "civil enforcement ltd",
    "civil enforcement limited",
    "ncp",
    "national car parks",
    "national car parks ltd",
    "smart parking",
    "smart parking ltd",
    "vcs",
    "vehicle control services",
    "vehicle control services ltd",
    "gemini parking solutions",
    "gemini parking solutions ltd",
    "premier park",
    "premier park ltd",
    "mil collections",
    "highview parking",
    "highview parking ltd",
    "aps parking",
    "britannia parking",
    "britannia parking group",
    "aos parking",
    "your parking space",
})

_HMRC_KNOWN_SUBTYPES = frozenset({
    "vat", "value_added_tax",
    "paye", "pay_as_you_earn",
    "tax credit", "tax_credit",
    "national insurance", "national_insurance", "ni", "ni_arrears",
    "self assessment", "self_assessment",
    "corporation tax", "corporation_tax",
    "income tax", "income_tax",
    "seiss",
})

_GAMBLING_KEYWORDS = [
    "gamble", "gambling", "bet", "betting", "casino",
    "paddy", "paddypower", "ladbrokes", "betfair", "william hill",
    "sky bet", "skybet", "coral", "betway", "888", "unibet",
    "bet365", "betvictor", "boylesports", "betfred",
    "tombola", "national lottery", "lotto",
]

_PAYDAY_KEYWORDS = [
    "wonga", "quickquid", "payday", "sunny", "lending stream",
    "pounds to pocket", "247moneybox",
]

_DEREGISTERED_TIX = frozenset({
    "ukar", "whistletree", "computershare", "landmark",
})

# Date-gated representative transitions (source: Which Representative sheet)
_MONZO_WATCH_DATE = date(2024, 4, 30)          # Monzo → WATCH from 30/04/2024
_MONZO_NAMES_LOWER = frozenset({"monzo", "monzo bank"})

_LA_REDOUTE_WATCH_DATE = date(2025, 7, 16)     # La Redoute → WATCH from 16/07/2025
_LA_REDOUTE_NAMES_LOWER = frozenset({
    "la redoute", "lr uk (retail) limited", "lr uk", "redcats uk",
    "droyds", "droyds debt & collection services",
})

_CAR_FINANCE_KEYWORDS = [
    "car finance", "hp finance", "hire purchase", "black horse",
    "motonovo", "alphera", "close brothers", "motonovo",
]

# VW Financial Services group — all brands that carry termination risk on HP
_VW_GROUP_NAMES = frozenset({
    "volkswagen financial services", "vwfs",
    "audi finance", "skoda finance", "seat finance",
    "porsche financial services",
})


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _norm(s: str) -> str:
    """Lowercase, strip, remove non-alphanumeric for fuzzy matching."""
    return re.sub(r"[^a-z0-9]", "", s.lower().strip())


def _in_set(name: str, name_set: frozenset) -> bool:
    """Case-insensitive membership check against a frozenset of names.
    Strips common legal suffixes before checking membership."""
    if not name:
        return False
    # 1. strip() and lower()
    s = name.strip().lower()
    # 2. Remove trailing: " limited", " ltd", " plc", " llp", " uk ltd", " uk limited"
    # Ordered longest first to prevent partial stripping
    suffixes = [" uk limited", " uk ltd", " limited", " ltd", " plc", " llp"]
    for suffix in suffixes:
        if s.endswith(suffix):
            s = s[:-len(suffix)].strip()
            break
    # 3. Then check membership in the set
    return s in name_set


def _contains_any(name: str, brand_set: frozenset) -> bool:
    """Returns True if the cleaned creditor name contains any brand token from brand_set.
    Uses whole-word matching for 'very' to avoid false positives on 'Recovery', 'Discovery', etc.
    All other tokens use substring match."""
    if not name:
        return False
    cleaned = name.lower().strip()
    for brand in brand_set:
        if brand == "very":
            if re.search(r'\bvery\b', cleaned):
                return True
        else:
            if brand in cleaned:
                return True
    return False


def _days_since(date_str: Optional[str], reference: Optional[date] = None) -> int:
    """Days between reference (default today) and date_str (ISO format). Returns 9999 if missing/invalid."""
    if not date_str:
        return 9999
    try:
        d = date.fromisoformat(str(date_str).split("T")[0])
        return ((reference or date.today()) - d).days
    except (ValueError, AttributeError):
        return 9999


def _is_within_days(date_str: Optional[str], days: int, reference: Optional[date] = None) -> bool:
    """True when transaction is between 0 and `days` days before reference (inclusive)."""
    d = _days_since(date_str, reference)
    return 0 <= d <= days


def _parse_amount(value) -> float:
    """Coerce string or numeric balance to float."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _gambling_monthly(gold_transactions: list, reference: Optional[date] = None) -> float:
    """Sum absolute amounts of gambling transactions within the last 30 days."""
    total = 0.0
    for t in gold_transactions:
        desc = (t.get("description") or "").lower()
        if any(kw in desc for kw in _GAMBLING_KEYWORDS):
            tx_date = t.get("transaction_date") or t.get("date")
            if _is_within_days(tx_date, 30, reference):
                total += abs(_parse_amount(t.get("amount", 0)))
    return total


def _gambling_all_transactions(gold_transactions: list) -> list:
    """Return all gambling transactions from bank statements 
    regardless of date."""
    results = []
    for t in gold_transactions:
        desc = (t.get("description") or "").lower()
        if any(kw in desc for kw in _GAMBLING_KEYWORDS):
            results.append(t)
    return results


def _recent_transactions_matching(
    gold_transactions: list,
    keywords: list,
    within_days: int,
    reference: Optional[date] = None,
) -> list:
    """Return transactions whose description matches any keyword and are within N days of reference."""
    results = []
    for t in gold_transactions:
        desc = (t.get("description") or "").lower()
        if not any(kw.lower() in desc for kw in keywords):
            continue
        tx_date = t.get("transaction_date") or t.get("date")
        if _is_within_days(tx_date, within_days, reference):
            results.append(t)
    return results


def _hp_monthly_from_transactions(gold_transactions: list, reference: Optional[date] = None) -> float:
    """Estimate HP monthly payment by scanning gold_transactions within the last 30 days."""
    total = 0.0
    for t in gold_transactions:
        desc = (t.get("description") or "").lower()
        if any(kw in desc for kw in _CAR_FINANCE_KEYWORDS):
            tx_date = t.get("transaction_date") or t.get("date")
            if _is_within_days(tx_date, 30, reference):
                total += abs(_parse_amount(t.get("amount", 0)))
    return total


def _compute_age(dob_str: Optional[str], reference: Optional[date] = None) -> Optional[int]:
    """Compute age in years from ISO date string."""
    if not dob_str:
        return None
    try:
        dob = date.fromisoformat(dob_str.split("T")[0])
        today = reference or date.today()
        return (today - dob).days // 365
    except (ValueError, AttributeError):
        return None


def _todo_flag(rule_id: str, field_name: str) -> RuleResult:
    """Return a flag stub for rules that need payload fields not yet present."""
    return RuleResult(
        rule_id=rule_id,
        severity="flag",
        triggered=True,
        message=(
            f"TODO: cannot evaluate {rule_id} — field '{field_name}' is missing from "
            f"the case payload. Add it to enable this rule. Defaulting to flag (not block)."
        ),
    )


def _pass(rule_id: str, message: str = "Passed.", creditors: list = None,
          threshold: float = None, actual_value: float = None) -> RuleResult:
    return RuleResult(rule_id=rule_id, severity="pass", triggered=False, message=message,
                      creditors=creditors or [], threshold=threshold, actual_value=actual_value)


def _func_to_rule_id(name: str) -> str:
    """Convert Python function name (e.g. _tig_15_10) to rule ID (TIG-15.10)."""
    # Remove leading underscore
    s = name.lstrip("_")
    # Replace first underscore with hyphen (e.g. tig_01 -> tig-01)
    s = s.replace("_", "-", 1)
    # Replace remaining underscores with dots (e.g. tig-15_10 -> tig-15.10)
    s = s.replace("_", ".")
    return s.upper()


# ---------------------------------------------------------------------------
# Payload parser — normalises raw JSON into a clean dict
# ---------------------------------------------------------------------------

def _parse_case(case_json: dict) -> dict:
    """
    Extract and normalise all fields needed by the rule methods.
    Missing optional fields default to None or safe empty values.
    Never raises — always returns a complete dict.
    """
    # --- assessment_date (used for date-gated rule logic) ---
    _ad_raw = case_json.get("assessment_date")
    if isinstance(_ad_raw, date):
        assessment_date_parsed: date = _ad_raw
    elif _ad_raw:
        try:
            assessment_date_parsed = date.fromisoformat(str(_ad_raw).split("T")[0])
        except (ValueError, AttributeError):
            assessment_date_parsed = date.today()
    else:
        assessment_date_parsed = date.today()

    creditors_raw = case_json.get("creditors") or []
    gold_tx_raw = case_json.get("gold_transactions")
    gold_tx = gold_tx_raw if gold_tx_raw is not None else []
    documents = case_json.get("documents") or []
    financial = case_json.get("financial_summary") or {}
    crm = case_json.get("crm_data") or {}
    client_info = case_json.get("clientInfo") or {}
    evidence_ledger = case_json.get("evidence_ledger") or []
    mortgage_details = case_json.get("mortgage_details") or []

    # --- Creditors ---
    from debt_app.helpers import normalise_debt_type, _SECURED_TYPES
    creditors = []
    for _idx, c in enumerate(creditors_raw):
        raw_type = c.get("creditor_type", "") or c.get("debt_type", "") or c.get("debt_type_normalised", "")
        debt_type = normalise_debt_type(raw_type)
        balance = _parse_amount(c.get("balance", 0))

        # Prefer the caller's own secured/unsecured classification when it
        # sends one — the case-assessment tool already resolves Aryza's
        # inconsistent type codes ("car_hp", "hp", plural variants, an
        # explicit hp flag, and a creditor-name fallback) more robustly
        # than a single string-match here ever will. Only re-derive from
        # debt_type_normalised when the caller doesn't provide is_secured
        # at all (e.g. direct API callers, tests). This caught a live case
        # where "car_hp" wasn't recognised by normalise_debt_type and a
        # £17,007 secured car-finance debt was counted as unsecured.
        _is_secured_raw = c.get("is_secured")
        is_secured = bool(_is_secured_raw) if _is_secured_raw is not None else (debt_type in _SECURED_TYPES)

        # months_since_last_payment relative to assessment_date
        lpd_raw = c.get("last_payment_date")
        months_since_lp = None
        if lpd_raw:
            try:
                lpd = date.fromisoformat(str(lpd_raw).split("T")[0])
                if lpd <= assessment_date_parsed:
                    months_since_lp = max(0, (assessment_date_parsed - lpd).days // 30)
            except (ValueError, AttributeError):
                pass

        creditors.append({
            "_idx": _idx,
            "name": c.get("creditor_name") or c.get("name", ""),
            "original_name": c.get("original_name") or c.get("original_aryza_name") or c.get("name", ""),
            "balance": balance,
            "crm_balance": Decimal(str(balance)),
            "creditor_type": raw_type,
            "debt_type_normalised": debt_type,
            "is_secured": is_secured,
            "account_age_months": c.get("account_age_months"),
            "last_transaction_date": c.get("last_transaction_date"),
            # Phase 3 per-creditor fields
            "is_joint": bool(c.get("is_joint", False)),
            "last_payment_date": lpd_raw,
            "first_payment_made": bool(c.get("first_payment_made", False)),
            "vehicle_arrears_months": c.get("vehicle_arrears_months") or c.get("arrears_months"),
            "ie_matches_loan_application": c.get("ie_matches_loan_application"),
            "arrangement_confirmed_before_proposing": bool(c.get("arrangement_confirmed_before_proposing", False)),
            "client_still_has_asset_in_possession": bool(c.get("client_still_has_asset_in_possession", False)),
            "is_grant_overpayment": bool(c.get("is_grant_overpayment", False)),
            "guarantee_called_up": c.get("guarantee_called_up"),
            "months_since_last_payment": months_since_lp,
            "linked_creditor": c.get("linked_creditor"),
            # Credit-report cross-check fields (populated upstream by the
            # caller's CR-enrichment step, e.g. criteria_views.py matching
            # Aryza creditors to CreditReport accounts). These were being
            # silently dropped here — computed upstream, sent in the
            # payload, but never carried into the parsed creditor dict —
            # so the UI's CR Balance/Match/CR Status/Missed Pmts columns
            # were always empty regardless of whether the enrichment
            # actually found a match.
            "cr_raw_name": c.get("cr_raw_name"),
            "type_code": c.get("type_code"),
            "cr_balance": c.get("cr_balance"),
            "cr_account_status": c.get("cr_account_status"),
            "cr_account_status_subjective": c.get("cr_account_status_subjective"),
            "cr_credit_limit": c.get("cr_credit_limit"),
            "cr_account_age_months": c.get("cr_account_age_months"),
            "cr_missed_payments_3m": c.get("cr_missed_payments_3m"),
        })

    # --- Total debt: always computed from creditors (unsecured only) ---
    total_debt = sum(
        c["balance"] for c in creditors
        if not c["is_secured"]
    )
    total_secured_debt = sum(
        c["balance"] for c in creditors
        if c["is_secured"]
    )

    # --- Disposable income ---
    disposable_income = _parse_amount(financial.get("net_balance", 0))
    total_income = _parse_amount(financial.get("total_income", 0))

    # --- Income source ---
    income_source = (financial.get("income_source") or "").lower()

    # --- Documents ---
    payslip_docs = [
        d for d in documents
        if d.get("document_type") == "payslip" and d.get("is_valid", False)
    ]
    bank_stmt_docs = [
        d for d in documents
        if d.get("document_type") == "bank_statement" and d.get("is_valid", False)
    ]
    benefit_letter_docs = [
        d for d in documents
        if d.get("document_type") in ("benefit_letter", "award_letter")
    ]
    tax_return_docs = [
        d for d in documents
        if d.get("document_type") == "tax_return"
    ]
    cis_invoice_docs = [
        d for d in documents
        if d.get("document_type") == "cis_invoice"
    ]
    termination_report_docs = [
        d for d in documents
        if d.get("document_type") == "termination_report"
    ]

    # --- Bank statement fields ---
    bank_stmt = bank_stmt_docs[0] if bank_stmt_docs else None
    bank_stmt_date = None
    bank_stmt_holder = None
    if bank_stmt:
        extracted = bank_stmt.get("extracted_data") or {}
        bank_stmt_date = bank_stmt.get("document_date") or extracted.get("statement_date")
        
        # BUG 1 — TIG-11 fallback keys: account_holder -> first_name + last_name
        bank_stmt_holder = extracted.get("account_holder")
        if not bank_stmt_holder:
            fn = extracted.get("first_name")
            ln = extracted.get("last_name")
            if fn and ln:
                bank_stmt_holder = f"{fn} {ln}"

    # --- Payslip date ---
    payslip_date = None
    if payslip_docs:
        extracted = payslip_docs[0].get("extracted_data") or {}
        payslip_date = payslip_docs[0].get("document_date") or extracted.get("statement_date")

    # --- Client age ---
    # Calculate age in years from today's date
    client_age = _compute_age(client_info.get("dateOfBirth"), reference=date.today())

    # --- Gambling ---
    gambling_monthly = _gambling_monthly(gold_tx, reference=assessment_date_parsed)
    gambling_all_transactions = _gambling_all_transactions(gold_tx)

    # --- Mortgage / equity ---
    prop_data = case_json.get("property") or {}
    
    # Read nested "property" first, fall back to top-level keys
    has_property = prop_data.get("owns_property")
    if has_property is None:
        has_property = case_json.get("has_property", False)
        
    property_value = prop_data.get("property_value")
    if property_value is None:
        property_value = case_json.get("property_value")

    if mortgage_details:
        mortgage_balance = sum(_parse_amount(m.get("balance", 0)) for m in mortgage_details)
    else:
        mortgage_balance_raw = prop_data.get("mortgage_balance")
        if mortgage_balance_raw is None:
            mortgage_balance_raw = case_json.get("mortgage_balance", 0)
        mortgage_balance = _parse_amount(mortgage_balance_raw)

    available_equity = 0.0
    if has_property and property_value is not None:
        available_equity = _parse_amount(property_value) - mortgage_balance
    elif not has_property:
        available_equity = 0.0
    else:
        # has_property is True but property_value is None
        available_equity = None

    # --- Previous IVA ---
    previous_iva = case_json.get("previous_iva", False)
    if not previous_iva:
        # Also check evidence_ledger or flags
        previous_iva = any(
            e.get("category") == "previous_iva" for e in evidence_ledger
        ) or case_json.get("flags", {}).get("previous_iva", False)

    previous_iva_failed_reason = (
        case_json.get("previous_iva_failed_reason")
        or case_json.get("flags", {}).get("previous_iva_failed_reason")
    )

    # --- Phase 3 case-level flags ---
    client_block = case_json.get("client") or {}
    has_partner_on_case = bool(
        client_block.get("has_partner_on_case") or case_json.get("has_partner_on_case", False)
    )
    is_currently_in_dmp = bool(
        client_info.get("is_currently_in_dmp") or case_json.get("is_currently_in_dmp", False)
    )
    is_royal_mail_employee = bool(
        client_info.get("is_royal_mail_employee", False)
        or case_json.get("is_royal_mail_employee", False)
    )
    is_police_officer = bool(
        client_info.get("is_police_officer", False)
        or case_json.get("is_police_officer", False)
    )
    previous_iva_failed = bool(client_info.get("previous_iva_failed", False))
    bank_accounts = financial.get("bank_accounts") or []
    iva_term_months = int(case_json.get("iva_term_months") or 60)
    monthly_di = (
        Decimal(str(case_json["monthly_di"]))
        if case_json.get("monthly_di") is not None
        else Decimal(str(disposable_income))
    )

    # --- HMRC ---
    hmrc_creditors = [
        c for c in creditors
        if _in_set(c["name"], _HMRC_NAMES) or "hmrc" in c["name"].lower() or "hm revenue" in c["name"].lower()
    ]
    hmrc_balance = sum(c["balance"] for c in hmrc_creditors)
    hmrc_is_majority = (hmrc_balance / total_debt > 0.5) if total_debt > 0 else False
    hmrc_is_creditor = len(hmrc_creditors) > 0

    # --- Council creditors ---
    council_creditors = [
        c for c in creditors
        if "council" in c["name"].lower() or "local authority" in c["name"].lower()
    ]
    council_balance = sum(c["balance"] for c in council_creditors)
    # EXCEL_CRITERIA_REFERENCE.md — Council majority: >25% NO votes
    # is a blocking minority (75% threshold cannot be reached)
    council_is_majority = (council_balance / total_debt > 0.25) if total_debt > 0 else False

    # --- Link Financial ---
    link_creditors = [c for c in creditors if _is_link_financial_name(c["name"])]
    link_balance = sum(c["balance"] for c in link_creditors)
    link_is_creditor = len(link_creditors) > 0

    # --- Shop Direct / Creation recent transactions ---
    shop_direct_tx_3mo = _recent_transactions_matching(
        gold_tx, list(_SHOP_DIRECT_NAMES), 90, reference=assessment_date_parsed
    )
    shop_direct_tx_4mo = _recent_transactions_matching(
        gold_tx, list(_SHOP_DIRECT_NAMES), 120, reference=assessment_date_parsed
    )
    creation_tx_4mo = _recent_transactions_matching(
        gold_tx, list(_CREATION_NAMES), 120, reference=assessment_date_parsed
    )

    # --- Total spend last 2 months (excl. payday loans) ---
    total_spend_2mo = 0.0
    for t in gold_tx:
        if t.get("transaction_type") != "money_out":
            continue
        desc = (t.get("description") or "").lower()
        if any(kw in desc for kw in _PAYDAY_KEYWORDS):
            continue
        tx_date_str = t.get("transaction_date") or t.get("date")
        if tx_date_str and _days_since(tx_date_str, assessment_date_parsed) <= 60:
            total_spend_2mo += abs(_parse_amount(t.get("amount", 0)))

    # --- Vehicle HP from transactions ---
    vehicle_hp_monthly = _hp_monthly_from_transactions(gold_tx, reference=assessment_date_parsed)

    # --- Car finance recent transactions ---
    car_finance_tx_3mo = _recent_transactions_matching(
        gold_tx, _CAR_FINANCE_KEYWORDS, 90, reference=assessment_date_parsed
    )

    # --- Benefit income amount — compute from income dict components if not explicitly supplied ---
    _income_dict = case_json.get("income") or {}
    _explicit_benefit = case_json.get("benefit_income_amount")
    if _explicit_benefit is not None:
        benefit_income_amount = _explicit_benefit
    elif _income_dict:
        benefit_income_amount = (
            _income_dict.get("universal_credit", 0)
            + _income_dict.get("dla", 0)
            + _income_dict.get("pip", 0)
            + _income_dict.get("other_benefits", 0)
        )
    else:
        benefit_income_amount = None

    return {
        # Metadata
        "aryza_reference": case_json.get("aryza_reference") or case_json.get("application_id", ""),
        "client_name": case_json.get("client_name") or client_info.get("client_name", ""),
        # Core financials
        "total_debt": total_debt,
        "disposable_income": disposable_income,
        "total_income": total_income,
        # Creditor lists
        "creditors": creditors,
        "hmrc_creditors": hmrc_creditors,
        "hmrc_balance": hmrc_balance,
        "hmrc_is_majority": hmrc_is_majority,
        "hmrc_is_creditor": hmrc_is_creditor,
        "link_creditors": link_creditors,
        "link_balance": link_balance,
        "link_is_creditor": link_is_creditor,
        "council_is_majority": council_is_majority,
        "evidence_ledger": case_json.get("evidence_ledger") or [],
        # Documents
        "payslip_docs": payslip_docs,
        "payslip_date": payslip_date,
        "bank_stmt_docs": bank_stmt_docs,
        "bank_stmt_date": bank_stmt_date,
        "bank_stmt_holder": bank_stmt_holder,
        "benefit_letter_docs": benefit_letter_docs,
        "tax_return_docs": tax_return_docs,
        "cis_invoice_docs": cis_invoice_docs,
        "termination_report_docs": termination_report_docs,
        # Income / employment
        "income_source": income_source,
        "has_job": case_json.get("has_job", False),
        "has_uc_journal": case_json.get("has_uc_journal", False),
        "uc_journal_date": (
            date.fromisoformat(str(case_json["uc_journal_date"]).split("T")[0])
            if case_json.get("uc_journal_date") else None
        ),
        # Property / equity
        "has_property": has_property,
        "property_value": property_value,          # TODO: missing from payload
        "available_equity": available_equity,       # None until property_value added
        "mortgage_balance": mortgage_balance,
        # Client
        "client_age": client_age,
        # Gambling
        "gambling_monthly": gambling_monthly,
        "gambling_all_transactions": gambling_all_transactions,
        # Transaction lookups
        "gold_transactions": gold_tx,
        "has_open_banking": gold_tx_raw is not None,
        "shop_direct_tx_3mo": shop_direct_tx_3mo,
        "shop_direct_tx_4mo": shop_direct_tx_4mo,
        "creation_tx_4mo": creation_tx_4mo,
        "total_spend_2mo": total_spend_2mo,
        "vehicle_hp_monthly": vehicle_hp_monthly,
        "car_finance_tx_3mo": car_finance_tx_3mo,
        # Optional payload fields — pass None/False when not supplied; rules skip gracefully
        "vehicle_value": case_json.get("vehicle_value"),
        "children": case_json.get("children") or [],
        "antecedent_transactions": case_json.get("antecedent_transactions") or case_json.get("has_antecedent_transactions"),
        "seiss_debt_flag": case_json.get("seiss_debt_flag"),
        "full_and_final_from_savings": case_json.get("full_and_final_from_savings"),
        "gambling_main_cause": bool(case_json.get("gambling_main_cause") or case_json.get("gambling_primary_cause") or crm.get("gambling_main_cause", False)),
        "income_deductions_active": (
            True if (case_json.get("income_deductions_active") or case_json.get("benefit_income_has_deduction"))
            else (False if (case_json.get("income_deductions_active") is not None or case_json.get("benefit_income_has_deduction") is not None)
            else None)
        ),
        "vulnerability_claimed": bool(case_json.get("vulnerability_claimed", False)),
        "vulnerability_evidence_uploaded": bool(case_json.get("vulnerability_evidence_uploaded", False)),
        "sfs_expenditure_breakdown": case_json.get("sfs_expenditure_breakdown") or [],
        "disability_income": case_json.get("disability_income"),
        "disability_expenses": case_json.get("disability_expenses"),
        "third_party_contribution": case_json.get("third_party_contribution"),
        "sustainability_paragraph_present": case_json.get("sustainability_paragraph_present"),
        "bankruptcy_return": case_json.get("bankruptcy_return"),
        # Flags derived from other sources
        "previous_iva": previous_iva,
        "previous_iva_failed_reason": previous_iva_failed_reason,
        "has_vehicle": case_json.get("has_vehicle", False),
        # Assessment date (for date-gated rules)
        "assessment_date": assessment_date_parsed,
        # Phase 3 additions
        "total_secured_debt": total_secured_debt,
        "has_partner_on_case": has_partner_on_case,
        "is_currently_in_dmp": is_currently_in_dmp,
        "is_royal_mail_employee": is_royal_mail_employee,
        "is_police_officer": is_police_officer,
        "previous_iva_failed": previous_iva_failed,
        "bank_accounts": bank_accounts,
        "iva_term_months": iva_term_months,
        "monthly_di": monthly_di,
        # Phase 5 additions — employment / benefit / case-type flags
        "is_employed": bool(
            case_json.get("is_employed")
            or client_info.get("is_employed")
            or case_json.get("has_job", False)
        ),
        "income_is_benefits_only": bool(
            case_json.get("income_is_benefits_only", False)
            or income_source in {
                "benefits", "uc", "universal_credit", "pip", "dla",
                "esa", "pension_credit", "disability", "carer",
            }
        ),
        "receives_any_benefits": bool(case_json.get("receives_any_benefits", False)),
        "gamstop_registered": bool(case_json.get("gamstop_registered", False)),
        "benefit_income_amount": benefit_income_amount,
        "aoe_in_place": bool(case_json.get("aoe_in_place", False)),
        # has_ccj base value — overridden authoritatively by _enrich_from_credit_report
        # when a credit report is present for this case.
        "has_ccj": bool(case_json.get("has_ccj", False)),
        "dro_criteria_met": bool(case_json.get("dro_criteria_met", False)),
        "is_joint_case": bool(case_json.get("is_joint_case", False)),
        # HMRC-specific trading / PAYE / VAT flags — None means not supplied
        "is_currently_trading": case_json.get("is_currently_trading"),
        "has_vat_arrangement": case_json.get("has_vat_arrangement"),
        "employer_paye_obligations_current": case_json.get("employer_paye_obligations_current"),
    }


# ---------------------------------------------------------------------------
# TIG RULES — run for ALL cases
# ---------------------------------------------------------------------------

def _tig_01(c: dict) -> RuleResult:
    """TIG-01: Total unsecured debt must be >= £6,000."""
    threshold = 6000.0
    actual = c["total_debt"]
    if actual < threshold:
        return RuleResult(
            rule_id="TIG-01", severity="hard_block", triggered=True,
            message=(
                f"The customer's total unsecured debt is £{actual:,.2f}. "
                f"An IVA usually requires total debt of at least £{threshold:,.2f}. "
                "Because the debt is below this amount, the case does not currently meet the criteria for an IVA."
            ),
            threshold=threshold, actual_value=actual,
        )
    return _pass("TIG-01", f"The customer's total debt of £{actual:,.2f} meets the £{threshold:,.2f} minimum required for an IVA.")


def _tig_02(c: dict) -> RuleResult:
    """TIG-02: Disposable income must be >= £100/month."""
    threshold = 100.0
    actual = c["disposable_income"]
    
    if actual < threshold:
        # Check if income data is missing entirely
        total_income = c.get("total_income", 0)
        if total_income <= 0:
            return RuleResult(
                rule_id="TIG-02", severity="hard_block", triggered=True,
                message="The customer's disposable income is showing as below £100 per month because no income details have been entered into the Fact Find. The financial section needs to be completed before this can be assessed properly.",
                threshold=threshold, actual_value=actual,
            )
        
        return RuleResult(
            rule_id="TIG-02", severity="hard_block", triggered=True,
            message=f"The customer's disposable income is £{actual:,.2f} per month, which is below the £{threshold:,.2f} minimum needed for an IVA. The case does not currently meet the criteria for an IVA.",
            threshold=threshold, actual_value=actual,
        )
    total_income = c.get("total_income", 0)
    total_expenses = total_income - actual if total_income > 0 else 0
    iva_60 = actual * 60
    dividend_pence = round((iva_60 / c["total_debt"]) * 100, 1) if c.get("total_debt", 0) > 0 else 0
    income_str = f" (income £{total_income:,.2f}, expenses £{total_expenses:,.2f})" if total_income > 0 else ""
    return _pass(
        "TIG-02",
        f"The customer's disposable income is £{actual:,.2f} per month, which meets the £{threshold:,.2f} minimum{income_str}. "
        f"Over a 60-month IVA, this would total £{iva_60:,.2f} in contributions. "
        f"This gives an estimated dividend to creditors of {dividend_pence}p in the pound."
    )


def _tig_03(c: dict) -> RuleResult:
    """TIG-03: SFS guidelines — expenditure must comply with Standard Financial Statement limits."""
    sfs = c["sfs_expenditure_breakdown"]
    if not sfs:
        return _pass("TIG-03", "The customer's expenditure breakdown was not provided, so this check could not be completed.")

    breaches = []
    
    # Handle both list (payload contract) and dict (legacy/mismatch)
    if isinstance(sfs, list):
        for item in sfs:
            category = item.get("category", "Unknown")
            declared = _parse_amount(item.get("monthly_amount", 0))
            bank = _parse_amount(item.get("bank_proven_amount", 0))
            guideline = _parse_amount(item.get("sfs_guideline_max", 0))
            
            # Correct behaviour:
            # - Flag if declared > 0 AND guideline > 0 AND declared > guideline
            # - OR if bank-proven amount > 0 AND guideline > 0 AND bank > guideline
            # - Do NOT flag if guideline is 0 (missing guideline data)
            is_breach = (guideline > 0) and ((declared > guideline) or (bank > guideline))
            
            if is_breach:
                breaches.append(category)
    elif isinstance(sfs, dict):
        # Legacy support for dict of booleans/amounts
        for category, exceeds in sfs.items():
            if exceeds is True:
                breaches.append(category)

    if breaches:
        breach_details = []
        for item in sfs if isinstance(sfs, list) else []:
            category = item.get("category", "Unknown")
            declared = _parse_amount(item.get("monthly_amount", 0))
            bank = _parse_amount(item.get("bank_proven_amount", 0))
            guideline = _parse_amount(item.get("sfs_guideline_max", 0))
            is_breach = (guideline > 0) and ((declared > guideline) or (bank > guideline))
            if is_breach:
                effective = max(declared, bank)
                pct = round(((effective - guideline) / guideline) * 100) if guideline > 0 else 0
                over_amount = effective - guideline
                if declared > 0 and bank > 0:
                    amount_desc = f"has declared £{declared:,.2f} per month for {category.lower()}, with £{bank:,.2f} confirmed from the bank statement,"
                elif bank > 0:
                    amount_desc = f"has £{bank:,.2f} per month confirmed from the bank statement for {category.lower()}"
                else:
                    amount_desc = f"has declared £{declared:,.2f} per month for {category.lower()}"
                breach_details.append(
                    f"The customer {amount_desc}. The usual guideline is £{guideline:,.2f}, "
                    f"which is £{over_amount:,.2f} ({pct}%) over the limit."
                )
        detail_str = " ".join(breach_details)
        return RuleResult(
            rule_id="TIG-03", severity="flag", triggered=True,
            message=(
                f"{detail_str} These must all be explained in the IVA proposal."
            ),
            threshold=0.0,
            actual_value=float(len(breaches)),
        )
    return _pass("TIG-03", "All expenditure categories are within the usual guidelines.")


def _tig_04(c: dict) -> RuleResult:
    """TIG-04: DLA/PIP income present but no disability expenses claimed — flag."""
    disability_income = c["disability_income"]
    if not disability_income:
        return _pass("TIG-04", "The customer does not receive disability income (DLA or PIP), so this check does not apply.")
    disability_expenses = c["disability_expenses"]
    if not disability_expenses:
        # Avoid false positive: check SFS breakdown for any disability-labelled line
        sfs = c.get("sfs_expenditure_breakdown") or []
        _DISABILITY_KEYWORDS = ("disability", "care", "medical")
        if any(
            any(kw in item.get("category", "").lower() for kw in _DISABILITY_KEYWORDS)
            for item in sfs
        ):
            return _pass(
                "TIG-04",
                "The customer receives disability income (DLA or PIP), and matching disability-related costs are recorded in the expenditure breakdown.",
            )
        return RuleResult(
            rule_id="TIG-04", severity="flag", triggered=True,
            message=(
                "The customer receives disability income (DLA or PIP), but no disability-related expenses have been recorded. "
                "If this income is being used to cover disability needs, the matching expenses must be added to the income and expenditure section."
            ),
        )
    return _pass("TIG-04", "The customer receives disability income (DLA or PIP) and matching disability expenses are recorded.")


def _tig_05(c: dict) -> RuleResult:
    """TIG-05: Wage slip required — one per employment income source, dated within 90 days."""
    income_source = c["income_source"]
    has_job = c["has_job"]
    is_employed = c.get("is_employed", False)

    # CIS income is validated by TIG-09 (CIS invoice) — wage slip not required for CIS
    if (income_source not in ("payslip", "employed", "salary")
            and not has_job
            and not is_employed):
        return _pass("TIG-05", "The customer is not employed, so a wage slip is not required.")

    payslip_docs = c["payslip_docs"]
    if not payslip_docs:
        return RuleResult(
            rule_id="TIG-05", severity="hard_block", triggered=True,
            message="The customer is employed but no wage slip has been uploaded. At least one wage slip is required for each employment income source before the case can proceed.",
        )

    payslip_date = c["payslip_date"]
    if payslip_date is None:
        return RuleResult(
            rule_id="TIG-05", severity="hard_block", triggered=True,
            message="The uploaded wage slip does not have a date on record, so it cannot be confirmed as being within the last 90 days. A dated wage slip must be provided.",
        )

    if _days_since(payslip_date, c["assessment_date"]) > 90:
        return RuleResult(
            rule_id="TIG-05", severity="hard_block", triggered=True,
            message=f"The wage slip on file is dated {payslip_date}, which is more than 90 days ago. A more recent wage slip is needed before the case can proceed.",
        )

    return _pass("TIG-05", "The customer's wage slip is present and dated within the last 90 days.")


def _tig_06(c: dict) -> RuleResult:
    """TIG-06: Benefit income requires award letter or current-year bank statement."""
    if c["income_source"] not in ("benefits", "universal_credit", "uc"):
        return _pass("TIG-06", "The customer does not receive benefit income, so proof of benefits is not required.")

    if c["benefit_letter_docs"]:
        return _pass("TIG-06", "The customer's benefit award letter is on file.")

    # Accept a bank statement dated in the current calendar year
    bank_date = c["bank_stmt_date"]
    if bank_date and str(c["assessment_date"].year) in str(bank_date):
        return _pass("TIG-06", "A current-year bank statement has been accepted as proof of the customer's benefit income.")

    return RuleResult(
        rule_id="TIG-06", severity="hard_block", triggered=True,
        message="The customer receives benefit income, but no benefit award letter or current-year bank statement has been uploaded to prove it. One of these must be provided before the case can proceed.",
    )


def _tig_07(c: dict) -> RuleResult:
    """TIG-07: UC income requires UC journal dated within 90 days."""
    if c["income_source"] not in ("uc", "universal_credit", "benefits_only"):
        return _pass("TIG-07", "The customer does not receive Universal Credit, so a Universal Credit journal is not required.")

    if not c["has_uc_journal"]:
        return RuleResult(
            rule_id="TIG-07", severity="hard_block", triggered=True,
            message="The customer receives Universal Credit, but no Universal Credit journal has been uploaded. This must be provided before the case can proceed.",
        )

    journal_date = c.get("uc_journal_date")
    if journal_date is None:
        return RuleResult(
            rule_id="TIG-07", severity="flag", triggered=True,
            message="A Universal Credit journal has been uploaded, but its date could not be confirmed. The caseworker must check it is dated within the last 3 months.",
        )
    if (c["assessment_date"] - journal_date).days > 90:
        return RuleResult(
            rule_id="TIG-07", severity="hard_block", triggered=True,
            message=f"The Universal Credit journal on file is dated {journal_date}, which is more than 90 days ago. A more recent journal must be provided.",
        )

    return _pass("TIG-07", "The customer's Universal Credit journal is present and dated within the last 90 days.")


def _tig_08(c: dict) -> RuleResult:
    """TIG-08: Self-employed requires BOTH tax return AND at least 1 month business banking."""
    if c["income_source"] != "self_employed":
        return _pass("TIG-08", "The customer is not self-employed, so self-employment evidence is not required.")

    has_tax_return = len(c["tax_return_docs"]) > 0
    has_business_bank_statement = len(c["bank_stmt_docs"]) >= 1

    # Excel: only ONE of tax return OR business bank statement is required.
    if not (has_tax_return or has_business_bank_statement):
        return RuleResult(
            rule_id="TIG-08", severity="flag", triggered=True,
            message="The customer is self-employed, but neither a tax return nor a business bank statement has been uploaded. At least one of these is needed to evidence their income.",
        )

    return _pass("TIG-08", "The customer's self-employment income is evidenced by a tax return or business bank statement.")


def _tig_09(c: dict) -> RuleResult:
    """TIG-09: CIS income requires invoice showing 20% tax deduction."""
    if c["income_source"] != "cis":
        return _pass("TIG-09", "The customer is not on the Construction Industry Scheme (CIS), so CIS proof is not required.")

    cis_docs = c["cis_invoice_docs"]
    if not cis_docs:
        return RuleResult(
            rule_id="TIG-09", severity="hard_block", triggered=True,
            message="The customer's income comes from the Construction Industry Scheme (CIS), but no CIS invoice has been uploaded. This must be provided before the case can proceed.",
        )

    # Check extracted_data for 20% deduction flag if available
    first = cis_docs[0].get("extracted_data") or {}
    if first and first.get("shows_deduction") is False:
        return RuleResult(
            rule_id="TIG-09", severity="hard_block", triggered=True,
            message="A CIS invoice has been uploaded, but it does not show the usual 20% tax deduction. This needs to be checked before the case can proceed.",
        )

    return _pass("TIG-09", "A CIS invoice showing the 20% tax deduction is on file.")


def _tig_10(c: dict) -> RuleResult:
    """TIG-10: Debts must be verifiable via Aryza name, credit report match, or verbal for sub-£1,000.

    "Unverified" means the creditor could not be identified at all — Aryza
    left it as a generic "Unknown Creditor" placeholder — AND no credit
    report match confirms it. Any creditor with a real name from Aryza's own
    CRM is treated as adequately sourced (deliberately lenient: Aryza's own
    debt list is itself a form of proof, and richer evidence types the Excel
    rule allows — creditor letters, 3-way calls, CCJs — aren't modelled by
    this engine, so we don't second-guess a named entry). Escalation only
    fires for genuinely unidentified debts, per Excel: "Debts under £1,000
    can be verbal if not able to get a POD (unless it's a debt level issue)".
    """
    creditors = c.get("creditors", [])
    total_debt = float(c.get("total_debt") or 0)
    MIN_DEBT = 6000.0  # mirrors TIG-01's minimum unsecured debt threshold

    # Names that indicate the creditor could not be identified from Aryza
    _UNKNOWN_NAMES = frozenset({"unknown", "unknown creditor"})

    hard_block_unverified = []  # >= £1,000, unidentified — always hard_block
    sub_1k_unverified = []      # < £1,000, unidentified — flag, unless load-bearing

    for creditor in creditors:
        balance = creditor.get("balance", 0)
        if balance <= 0:
            continue

        name = creditor.get("name", "Unknown Creditor")

        # Any creditor with a real name (not an UNKNOWN fallback) is Aryza-sourced → verified
        is_aryza_sourced = name.strip().lower() not in _UNKNOWN_NAMES

        # Verified if the debt came from the credit report
        has_credit_report = bool(creditor.get("from_credit_report"))

        if is_aryza_sourced or has_credit_report:
            continue

        # Genuinely unidentified. Prefer original_name for the message so a
        # caseworker can still tell debts apart even though Aryza couldn't
        # classify the name.
        display_name = creditor.get("original_name") or name
        if balance >= 1000:
            hard_block_unverified.append((display_name, balance))
        else:
            sub_1k_unverified.append((display_name, balance))

    if not hard_block_unverified and not sub_1k_unverified:
        return _pass("TIG-10", "All of the customer's debts have been verified, either through Aryza's records or a credit report match.")

    severity = "flag"
    lines = []

    for name, balance in hard_block_unverified:
        lines.append(
            f"The debt with {name}, balance £{balance:,.0f}, could not be verified from Aryza's records or a credit report match. "
            "Proof of this debt must be obtained before the case can be proposed."
        )
    if hard_block_unverified:
        severity = "hard_block"

    if sub_1k_unverified:
        sub_1k_total = sum(balance for _, balance in sub_1k_unverified)
        provable = total_debt - sub_1k_total
        load_bearing = provable < MIN_DEBT
        for name, balance in sub_1k_unverified:
            if load_bearing:
                lines.append(
                    f"The debt with {name}, balance £{balance:,.0f}, is unverified and under £1,000. "
                    "Verbal confirmation would normally be acceptable for a debt this size, but removing it and the other "
                    f"unverified sub-£1,000 debts would drop the total debt to £{provable:,.0f}, below the "
                    "£6,000 minimum required for an IVA. Because this affects whether the case qualifies at all, "
                    "proof of the debt is required rather than a verbal confirmation."
                )
                severity = "hard_block"
            else:
                lines.append(
                    f"The debt with {name}, balance £{balance:,.0f}, is unverified and under £1,000. "
                    "A verbal confirmation from the customer is acceptable if proof of the debt cannot be obtained."
                )

    return RuleResult(
        rule_id="TIG-10",
        severity=severity,
        triggered=True,
        message="\n".join(lines),
    )


def _tig_11(c: dict) -> RuleResult:
    """TIG-11: Bank statement verification — presence, freshness, account holder."""
    # No bank statement at all
    if not c["bank_stmt_docs"]:
        return RuleResult(
            rule_id="TIG-11", severity="hard_block", triggered=True,
            message="No bank statement has been uploaded for the customer. A valid bank statement must be provided before the case can proceed.",
        )

    # Statement older than 90 days
    bank_date = c["bank_stmt_date"]
    if bank_date is None:
        return RuleResult(
            rule_id="TIG-11", severity="hard_block", triggered=True,
            message="The uploaded bank statement does not have a date on record, so it cannot be confirmed as being within the last 90 days. A dated bank statement must be provided.",
        )

    if _days_since(bank_date, c["assessment_date"]) > 90:
        return RuleResult(
            rule_id="TIG-11", severity="hard_block", triggered=True,
            message=f"The bank statement on file is dated {bank_date}, which is more than 90 days ago. A more recent bank statement must be provided.",
        )

    # No account holder name
    if not c["bank_stmt_holder"]:
        return RuleResult(
            rule_id="TIG-11", severity="hard_block", triggered=True,
            message="The bank statement on file does not show an account holder name. This must be confirmed before the case can proceed.",
        )

    return _pass("TIG-11", "The customer's bank statement is valid, recent, and shows the account holder's name.")


def _tig_11_gambling(c: dict) -> RuleResult:
    """TIG-11-GAMBLING: Gambling spend check against bank statements."""
    gm = c["gambling_monthly"]  # last 30 days
    all_gtx = c.get("gambling_all_transactions", [])
    
    # Build transaction detail string for caseworker
    def _tx_detail(txs):
        lines = []
        for t in txs:
            date = t.get("transaction_date") or t.get("date") or "unknown date"
            desc = t.get("description") or ""
            amt = abs(_parse_amount(t.get("amount", 0)))
            lines.append(f"{desc} £{amt:.2f} ({date})")
        return "; ".join(lines) if lines else "none"
    
    all_total = sum(
        abs(_parse_amount(t.get("amount", 0))) for t in all_gtx
    )
    
    # Hard block: last 30 days >= £1,000
    if gm >= 1000:
        detail = _tx_detail(all_gtx)
        return RuleResult(
            rule_id="TIG-11-GAMBLING", severity="hard_block", triggered=True,
            message=(
                f"The customer has spent £{gm:,.2f} on gambling in the last 30 days, which meets or exceeds "
                f"the £1,000 threshold at which the case cannot proceed. "
                f"All gambling transactions found: {detail}."
            ),
            threshold=1000.0, actual_value=gm,
        )

    # Flag: last 30 days > £200
    if gm > 200:
        detail = _tx_detail(all_gtx)
        if c.get("gamstop_registered"):
            return RuleResult(
                rule_id="TIG-11-GAMBLING", severity="flag", triggered=True,
                message=(
                    f"The customer has spent £{gm:,.2f} on gambling in the last 30 days, which is above £200. "
                    f"The customer is registered with GAMSTOP (the gambling self-exclusion scheme) — the caseworker must confirm this registration is still active. "
                    f"All gambling transactions found: {detail}."
                ),
                threshold=200.0, actual_value=gm,
            )
        return RuleResult(
            rule_id="TIG-11-GAMBLING", severity="flag", triggered=True,
            message=(
                f"The customer has spent £{gm:,.2f} on gambling in the last 30 days, which is above £200. "
                f"Proof of GAMSTOP registration (the gambling self-exclusion scheme) is required. "
                f"All gambling transactions found: {detail}."
            ),
            threshold=200.0, actual_value=gm,
        )

    # Flag: last 30 days > 0 but under £200
    if gm > 0:
        detail = _tx_detail(all_gtx)
        return RuleResult(
            rule_id="TIG-11-GAMBLING", severity="flag", triggered=True,
            message=(
                f"Some gambling transactions were found in the last 30 days, totalling £{gm:,.2f}. "
                f"This is within the acceptable limit. "
                f"All gambling transactions found: {detail}. "
                f"The caseworker should still review this with the customer."
            ),
            threshold=0.0, actual_value=gm,
        )

    # No gambling in last 30 days — check all time
    if all_total > 0:
        detail = _tx_detail(all_gtx)
        return RuleResult(
            rule_id="TIG-11-GAMBLING", severity="flag", triggered=True,
            message=(
                f"Gambling transactions were found in the customer's bank statements "
                f"(totalling £{all_total:,.2f}, all outside the last 30 days). "
                f"There has been no recent gambling, so this is within the acceptable limit. "
                f"Transactions found: {detail}. "
                f"The caseworker should still review this with the customer."
            ),
            threshold=0.0, actual_value=all_total,
        )

    return _pass("TIG-11-GAMBLING", "No gambling transactions were found in the customer's bank statements.")


def _tig_12(c: dict) -> RuleResult:
    """TIG-12: Third-party contribution requires signed letter."""
    tp = c["third_party_contribution"]
    if not tp:
        # None, 0, 0.0, False — no TPC present
        return _pass("TIG-12", "No one else is contributing to the customer's IVA payments, so a signed letter is not required.")
    if isinstance(tp, (int, float)):
        # Aryza supplies a raw amount but no letter metadata yet
        return RuleResult(
            rule_id="TIG-12", severity="flag", triggered=True,
            message=(
                f"A third party is contributing £{tp:,.2f} towards the customer's IVA payments. "
                "The caseworker must confirm a signed letter is in place covering the duration, address and contact details of the contributor."
            ),
        )
    # tp is a dict with letter metadata
    if not tp.get("signed_letter_present", False):
        return RuleResult(
            rule_id="TIG-12", severity="hard_block", triggered=True,
            message="A third party is contributing to the customer's IVA payments, but no signed letter has been uploaded. The letter must include the contributor's name, address, signature, date, contact details, amount and duration of the contribution.",
        )
    return _pass("TIG-12", "A signed letter confirming the third-party contribution is on file.")


def _tig_13(c: dict) -> RuleResult:
    """TIG-13: Previous IVA requires termination report."""
    if not c["previous_iva"]:
        return _pass("TIG-13", "The customer has no previous IVA on record, so a termination report is not required.")
    if not c["termination_report_docs"]:
        return RuleResult(
            rule_id="TIG-13", severity="hard_block", triggered=True,
            message="The customer has a previous IVA on record, but no termination report has been uploaded. This must be provided before the case can proceed.",
        )
    return _pass("TIG-13", "The termination report for the customer's previous IVA is on file.")


def _tig_15_1(c: dict) -> RuleResult:
    """TIG-15.1: HMRC majority creditor + income/benefit deductions already being taken."""
    if not c["hmrc_is_majority"]:
        return _pass("TIG-15.1", "HMRC is not the customer's largest creditor, so this check does not apply.")
    if c["income_deductions_active"] is None:
        return RuleResult(
            rule_id="TIG-15.1",
            severity="flag",
            triggered=True,
            message="HMRC is the customer's largest creditor. Before the case can be proposed, the caseworker must confirm whether any income or benefit deductions are already being taken.",
        )
    if not c["income_deductions_active"]:
        return _pass("TIG-15.1", "HMRC is the customer's largest creditor, but no income or benefit deductions are currently being taken, so this check is passed.")
    return RuleResult(
        rule_id="TIG-15.1", severity="hard_block", triggered=True,
        message=(
            "HMRC is the customer's largest creditor and deductions are already being taken from their income or benefits. "
            "HMRC is expected to reject the IVA in this situation."
        ),
    )


def _tig_15_2(c: dict) -> RuleResult:
    """TIG-15.2: HMRC majority creditor + previous IVA or bankruptcy."""
    if not c["hmrc_is_majority"]:
        return _pass("TIG-15.2", "HMRC is not the customer's largest creditor, so this check does not apply.")
    if c["previous_iva"] or c["previous_iva_failed"] or c.get("credit_report_iva_or_bankruptcy"):
        return RuleResult(
            rule_id="TIG-15.2", severity="hard_block", triggered=True,
            message="HMRC is the customer's largest creditor and the customer has a previous IVA or bankruptcy on record. HMRC is expected to reject the IVA in this situation.",
        )
    return _pass("TIG-15.2", "HMRC is the customer's largest creditor, but there is no previous IVA or bankruptcy on record, so this check is passed.")


def _tig_15_3(c: dict) -> RuleResult:
    """TIG-15.3: HMRC self-assessment debt + late/missing tax submissions.
    Applies to self-employed clients AND PAYE clients with SA debt (landlords, investors).
    """
    if not c["hmrc_is_creditor"]:
        return _pass("TIG-15.3", "HMRC is not one of the customer's creditors, so this check does not apply.")
    # Detect SA debt from creditor_type or creditor name — covers PAYE clients with SA returns
    has_sa_debt = any(
        "self assessment" in (cr["creditor_type"] or "").lower()
        or "self_assessment" in (cr["creditor_type"] or "").lower()
        or "income tax" in (cr["creditor_type"] or "").lower()
        or "self assessment" in cr["name"].lower()
        for cr in c["hmrc_creditors"]
    )
    if not has_sa_debt and c["income_source"] != "self_employed":
        return _pass("TIG-15.3", "No self-assessment debt was found for the customer, so this check does not apply.")
    # Check for tax return as proxy for up-to-date submissions
    if not c["tax_return_docs"]:
        return RuleResult(
            rule_id="TIG-15.3", severity="hard_block", triggered=True,
            message="The customer has self-assessment debt with HMRC, but no tax return has been uploaded to show their submissions are up to date. This must be provided before the case can proceed.",
        )
    return _pass("TIG-15.3", "The customer's tax return is on file, confirming their self-assessment submissions are up to date.")


def _tig_15_4(c: dict) -> RuleResult:
    """TIG-15.4: Available property equity > HMRC debt balance."""
    # EXCEL_CRITERIA_REFERENCE.md — stub replaced;
    # triggered=True without evaluation is misleading
    if not c["hmrc_is_creditor"]:
        return _pass("TIG-15.4", "HMRC is not one of the customer's creditors, so this check does not apply.")
    if c["available_equity"] is None:
        return RuleResult(
            rule_id="TIG-15.4", severity="info", triggered=False,
            message="This check could not be completed because no property value has been entered for the customer.",
        )
    if c["available_equity"] > c["hmrc_balance"]:
        return RuleResult(
            rule_id="TIG-15.4", severity="hard_block", triggered=True,
            message=f"The customer's available property equity is £{c['available_equity']:,.2f}, which is more than the £{c['hmrc_balance']:,.2f} owed to HMRC. This must be reviewed before the case can proceed.",
            threshold=c["hmrc_balance"], actual_value=c["available_equity"],
        )
    return _pass("TIG-15.4", "The customer's available property equity does not exceed the amount owed to HMRC.")


def _tig_15_5(c: dict) -> RuleResult:
    """TIG-15.5: Bankruptcy return > IVA payments — hard block if bankruptcy yields more."""
    if c["bankruptcy_return"] is None:
        return _pass("TIG-15.5", "No bankruptcy return figure has been provided for the customer, so this check does not apply.")
    br = _parse_amount(c["bankruptcy_return"])
    # EXCEL_CRITERIA_REFERENCE.md — IVA term from case payload, not hardcoded
    iva_return = c["disposable_income"] * c.get("iva_term_months", 60) * 0.75
    if br > iva_return:
        return RuleResult(
            rule_id="TIG-15.5", severity="hard_block", triggered=True,
            message=f"If the customer went bankrupt instead, creditors would get an estimated £{br:,.2f}, which is more than the £{iva_return:,.2f} projected from the IVA. This means bankruptcy would give creditors a better return, so it must be reviewed before the case can proceed.",
            threshold=iva_return, actual_value=br,
        )
    return _pass("TIG-15.5", "The projected IVA return to creditors is higher than the estimated return from bankruptcy.")


def _tig_15_6(c: dict) -> RuleResult:
    """TIG-15.6: Full & Final funded from savings accumulated while debts were unpaid — hard block."""
    val = c["full_and_final_from_savings"]
    if val is None:
        return RuleResult(
            rule_id="TIG-15.6", severity="flag", triggered=True,
            message=(
                "The customer has not confirmed where the savings for the Full & Final settlement came from. "
                "Before the case can continue, the caseworker must check whether the customer built up these savings "
                "while they were not paying their debts."
            ),
        )
    if val is True:
        return RuleResult(
            rule_id="TIG-15.6", severity="hard_block", triggered=True,
            message=(
                "The Full & Final settlement is funded from savings that were built up while the customer's debts were unpaid. "
                "This raises a concern about how the money was accumulated, so the IVA cannot proceed on this basis."
            ),
        )
    return _pass("TIG-15.6", "There is no Full & Final settlement funded from savings built up while debts were unpaid.")


def _tig_15_7(c: dict) -> RuleResult:
    """TIG-15.7: SEISS fraud debt — always blocks, cannot be included in IVA."""
    if c["seiss_debt_flag"] is None:
        return _pass("TIG-15.7", "No information on Self-Employment Income Support Scheme (SEISS) fraud debt has been provided, so this check does not apply.")
    if c["seiss_debt_flag"]:
        return RuleResult(
            rule_id="TIG-15.7", severity="hard_block", triggered=True,
            message="The customer has a Self-Employment Income Support Scheme (SEISS) fraud debt. This type of debt can never be included in an IVA, under any circumstances.",
        )
    return _pass("TIG-15.7", "The customer has no Self-Employment Income Support Scheme (SEISS) fraud debt.")


def _tig_15_8(c: dict) -> RuleResult:
    """TIG-15.8: HMRC removes client name, chases other party — info only, does not block."""
    if not c["hmrc_is_creditor"]:
        return _pass("TIG-15.8", "HMRC is not one of the customer's creditors, so this note does not apply.")
    return RuleResult(
        rule_id="TIG-15.8", severity="info", triggered=False,
        message="For information: if this is a joint debt and HMRC removes the customer's name to chase the other party instead, this does not stop the IVA from proceeding.",
    )


def _tig_15_9(c: dict) -> RuleResult:
    """TIG-15.9: HMRC debt < £4,000 — HMRC will not vote unless rejecting. Info only."""
    threshold = 4000.0
    if not c["hmrc_is_creditor"]:
        return _pass("TIG-15.9", "HMRC is not one of the customer's creditors, so this note does not apply.")
    if c["hmrc_balance"] < threshold:
        return RuleResult(
            rule_id="TIG-15.9", severity="info", triggered=False,
            message=f"The customer owes HMRC £{c['hmrc_balance']:,.2f}, which is under £{threshold:,.2f}. For information, HMRC typically will not cast a vote on the IVA unless they intend to reject it.",
            threshold=threshold, actual_value=c["hmrc_balance"],
        )
    return _pass("TIG-15.9", f"The customer owes HMRC £{c['hmrc_balance']:,.2f}, which is above the £{threshold:,.2f} threshold for this note.")


def _tig_15_10(c: dict) -> RuleResult:
    """TIG-15.10: Client's only income is benefits AND HMRC is a creditor."""
    if not c["hmrc_is_creditor"]:
        return _pass("TIG-15.10", "HMRC is not one of the customer's creditors, so this check does not apply.")
    benefits_only = (
        c.get("income_is_benefits_only", False)
        or c["income_source"] in ("benefits", "universal_credit", "uc")
    )
    if benefits_only:
        return RuleResult(
            rule_id="TIG-15.10", severity="hard_block", triggered=True,
            message="The customer's only income is from benefits, and HMRC is one of their creditors. An IVA is not viable in this situation.",
        )
    return _pass("TIG-15.10", "The customer has income from a source other than benefits, so this check is not triggered.")


# ---------------------------------------------------------------------------
# TIG HMRC RULES — run for all cases; each guards on hmrc_is_creditor
# EXCEL_CRITERIA_REFERENCE.md — Sheet: TIG Criteria, HMRC Rules
# ---------------------------------------------------------------------------

def _tig_hmrc_01(c: dict) -> RuleResult:
    """TIG-HMRC-01: Advisory flag — HMRC's agreement to the IVA cannot be assumed."""
    # EXCEL_CRITERIA_REFERENCE.md — HMRC Rule 1
    if not c["hmrc_is_creditor"]:
        return _pass("TIG-HMRC-VOTE-NOT-GUARANTEED", "No HMRC creditor.")
    return RuleResult(
        rule_id="TIG-HMRC-VOTE-NOT-GUARANTEED",
        severity="flag",
        triggered=True,
        message=(
            "HMRC is one of the customer's creditors. HMRC's agreement to the IVA cannot be assumed just because they are owed money. "
            "The caseworker must get specific confirmation from HMRC before the case is proposed."
        ),
    )


def _tig_hmrc_03(c: dict) -> RuleResult:
    """TIG-HMRC-03: VAT arrears + still trading without a payment arrangement."""
    # EXCEL_CRITERIA_REFERENCE.md — HMRC Rule 3
    if not c["hmrc_is_creditor"]:
        return _pass("TIG-HMRC-VAT-TRADING", "No HMRC creditor.")
    has_vat_debt = any(
        # EXCEL_CRITERIA_REFERENCE.md — HMRC Rule 3: VAT debt type matching
        "vat" in (cr["creditor_type"] or "").lower()
        or "value_added_tax" in (cr["creditor_type"] or "").lower()
        or "vat" in cr["name"].lower()
        for cr in c["hmrc_creditors"]
    )
    if not has_vat_debt:
        # Only flag if no HMRC creditor has any recognised sub-type
        # If sub-type is known but isn't VAT, this rule simply doesn't apply
        _any_known = any(
            any(kw in (cr["creditor_type"] or "").lower() or kw in cr["name"].lower()
                for kw in _HMRC_KNOWN_SUBTYPES)
            for cr in c["hmrc_creditors"]
        )
        if not _any_known:
            return RuleResult(
                rule_id="TIG-HMRC-VAT-TRADING",
                severity="flag",
                triggered=True,
                message="HMRC is a creditor, but the system could not tell what type of debt is owed. The caseworker must manually confirm whether this includes VAT (Value Added Tax) before the case is proposed.",
            )
        return _pass("TIG-HMRC-VAT-TRADING", "The customer has no VAT arrears with HMRC.")
    _is_trading = c.get("is_currently_trading")
    if _is_trading is None:
        return RuleResult(
            rule_id="TIG-HMRC-VAT-TRADING",
            severity="flag",
            triggered=True,
            message="The customer has VAT (Value Added Tax) debt with HMRC, but it is not known whether they are still trading. The caseworker must verify this before the case is proposed.",
        )
    if not _is_trading:
        return _pass("TIG-HMRC-VAT-TRADING", "The customer is not currently trading.")
    # is_currently_trading is True; check for arrangement
    if c["has_vat_arrangement"]:
        return _pass("TIG-HMRC-VAT-TRADING", "A VAT payment arrangement with HMRC is already in place.")
    if c.get("has_vat_arrangement") is None:
        return RuleResult(
            rule_id="TIG-HMRC-VAT-TRADING",
            severity="flag",
            triggered=True,
            message="The customer has VAT debt and is still trading. The caseworker must confirm whether a payment arrangement with HMRC is already in place before the case is proposed.",
        )
    return RuleResult(
        rule_id="TIG-HMRC-VAT-TRADING",
        severity="hard_block",
        triggered=True,
        message=(
            "The customer has VAT arrears and is still trading, with no payment arrangement in place with HMRC. "
            "HMRC is expected to reject the IVA in this situation. Trading must stop, or a payment arrangement must be agreed with HMRC, before this can proceed."
        ),
    )


def _tig_hmrc_04(c: dict) -> RuleResult:
    """TIG-HMRC-04: PAYE arrears — employer PAYE obligations must be current."""
    # EXCEL_CRITERIA_REFERENCE.md — HMRC Rule 4
    if not c["hmrc_is_creditor"]:
        return _pass("TIG-HMRC-PAYE-OBLIGATIONS", "No HMRC creditor.")
    has_paye_debt = any(
        # EXCEL_CRITERIA_REFERENCE.md — HMRC Rule 4: PAYE debt type matching
        "paye" in (cr["creditor_type"] or "").lower()
        or "pay_as_you_earn" in (cr["creditor_type"] or "").lower()
        or "paye" in cr["name"].lower()
        for cr in c["hmrc_creditors"]
    )
    if not has_paye_debt:
        # Only flag if no HMRC creditor has any recognised sub-type
        # If sub-type is known but isn't PAYE, this rule simply doesn't apply
        _any_known = any(
            any(kw in (cr["creditor_type"] or "").lower() or kw in cr["name"].lower()
                for kw in _HMRC_KNOWN_SUBTYPES)
            for cr in c["hmrc_creditors"]
        )
        if not _any_known:
            return RuleResult(
                rule_id="TIG-HMRC-PAYE-OBLIGATIONS",
                severity="flag",
                triggered=True,
                message="HMRC is a creditor, but the system could not tell what type of debt is owed. The caseworker must manually confirm whether this includes PAYE (Pay As You Earn) before the case is proposed.",
            )
        return _pass("TIG-HMRC-PAYE-OBLIGATIONS", "The customer has no PAYE arrears with HMRC.")
    paye_current = c["employer_paye_obligations_current"]
    if paye_current is None:
        return RuleResult(
            rule_id="TIG-HMRC-PAYE-OBLIGATIONS",
            severity="flag",
            triggered=True,
            message=(
                "The customer has PAYE (Pay As You Earn) arrears with HMRC. Their employer's current PAYE obligations must be up to date before the IVA can be proposed, but this could not be verified. "
                "The caseworker must check this before proceeding."
            ),
        )
    if not paye_current:
        return RuleResult(
            rule_id="TIG-HMRC-PAYE-OBLIGATIONS",
            severity="hard_block",
            triggered=True,
            message=(
                "The customer has PAYE arrears with HMRC, and their employer's current PAYE obligations are not up to date. "
                "This must be resolved before the IVA can be proposed."
            ),
        )
    return _pass("TIG-HMRC-PAYE-OBLIGATIONS", "The employer's PAYE obligations are up to date.")


def _tig_hmrc_05(c: dict) -> RuleResult:
    """TIG-HMRC-05: Tax credit overpayment debt — treated as priority; confirm DWP deductions."""
    # EXCEL_CRITERIA_REFERENCE.md — HMRC Rule 5
    if not c["hmrc_is_creditor"]:
        return _pass("TIG-HMRC-TAX-CREDITS", "No HMRC creditor.")
    has_tc_debt = any(
        # EXCEL_CRITERIA_REFERENCE.md — HMRC Rule 5: tax credit debt type matching
        "tax credit" in (cr["creditor_type"] or "").lower()
        or "tax_credit" in (cr["creditor_type"] or "").lower()
        or "tax credit" in cr["name"].lower()
        for cr in c["hmrc_creditors"]
    )
    if not has_tc_debt:
        # Only flag if no HMRC creditor has any recognised sub-type
        # If sub-type is known but isn't tax credits, this rule simply doesn't apply
        _any_known = any(
            any(kw in (cr["creditor_type"] or "").lower() or kw in cr["name"].lower()
                for kw in _HMRC_KNOWN_SUBTYPES)
            for cr in c["hmrc_creditors"]
        )
        if not _any_known:
            return RuleResult(
                rule_id="TIG-HMRC-TAX-CREDITS",
                severity="flag",
                triggered=True,
                message="HMRC is a creditor, but the system could not tell what type of debt is owed. The caseworker must manually confirm whether this includes a tax credit overpayment before the case is proposed.",
            )
        return _pass("TIG-HMRC-TAX-CREDITS", "The customer has no tax credit overpayment debt.")
    return RuleResult(
        rule_id="TIG-HMRC-TAX-CREDITS",
        severity="flag",
        triggered=True,
        message=(
            "The customer has a tax credit overpayment debt, which is treated as a priority debt. "
            "The caseworker must confirm whether the Department for Work and Pensions (DWP) is already taking deductions for this before it is included in the IVA."
        ),
    )


def _tig_hmrc_06(c: dict) -> RuleResult:
    """TIG-HMRC-06: National Insurance debt — confirm Class 2/4 treatment."""
    # EXCEL_CRITERIA_REFERENCE.md — HMRC Rule 6
    if not c["hmrc_is_creditor"]:
        return _pass("TIG-HMRC-NI-CLASS", "No HMRC creditor.")
    has_ni_debt = any(
        # EXCEL_CRITERIA_REFERENCE.md — HMRC Rule 6: NI debt type matching
        "national insurance" in (cr["creditor_type"] or "").lower()
        or "national_insurance" in (cr["creditor_type"] or "").lower()
        or (cr["creditor_type"] or "").lower() in ("ni", "ni_arrears")
        for cr in c["hmrc_creditors"]
    )
    if not has_ni_debt:
        # Only flag if no HMRC creditor has any recognised sub-type
        # If sub-type is known but isn't NI, this rule simply doesn't apply
        _any_known = any(
            any(kw in (cr["creditor_type"] or "").lower() or kw in cr["name"].lower()
                for kw in _HMRC_KNOWN_SUBTYPES)
            for cr in c["hmrc_creditors"]
        )
        if not _any_known:
            return RuleResult(
                rule_id="TIG-HMRC-NI-CLASS",
                severity="flag",
                triggered=True,
                message="HMRC is a creditor, but the system could not tell what type of debt is owed. The caseworker must manually confirm whether this includes National Insurance before the case is proposed.",
            )
        return _pass("TIG-HMRC-NI-CLASS", "The customer has no National Insurance debt.")
    return RuleResult(
        rule_id="TIG-HMRC-NI-CLASS",
        severity="flag",
        triggered=True,
        message=(
            "The customer has National Insurance debt with HMRC. "
            "The caseworker must confirm whether Class 2 and/or Class 4 National Insurance contributions are included in the IVA or are being treated separately."
        ),
    )


def _tig_hmrc_07(c: dict) -> RuleResult:
    """TIG-HMRC-07: Client is currently trading with HMRC debt — specific written confirmation required."""
    # EXCEL_CRITERIA_REFERENCE.md — HMRC Rule 7
    if not c["hmrc_is_creditor"]:
        return _pass("TIG-HMRC-ONGOING-TRADING", "No HMRC creditor.")
    _is_trading = c.get("is_currently_trading")
    if _is_trading is None:
        return RuleResult(
            rule_id="TIG-HMRC-ONGOING-TRADING",
            severity="flag",
            triggered=True,
            message="The customer has HMRC debt, but it is not known whether they are currently trading. The caseworker must verify this before the case is proposed.",
        )
    if not _is_trading:
        return _pass("TIG-HMRC-ONGOING-TRADING", "The customer is not currently trading.")
    return RuleResult(
        rule_id="TIG-HMRC-ONGOING-TRADING",
        severity="flag",
        triggered=True,
        message=(
            "The customer is still trading and has HMRC debt. HMRC rarely accepts an IVA in this situation. "
            "The caseworker must get specific written confirmation from HMRC before the case is proposed."
        ),
    )


def _tig_hmrc_08(c: dict) -> RuleResult:
    """TIG-HMRC-08: Antecedent/preferential payment to HMRC — hard block (TIG-level, WATCH-independent)."""
    # EXCEL_CRITERIA_REFERENCE.md — HMRC Rule 8
    # _watch_22_13 still catches antecedent transactions for non-HMRC creditors when WATCH is present.
    if not c["hmrc_is_creditor"]:
        return _pass("TIG-HMRC-ANTECEDENT", "No HMRC creditor.")
    at = c.get("antecedent_transactions")
    if at:
        return RuleResult(
            rule_id="TIG-HMRC-ANTECEDENT",
            severity="hard_block",
            triggered=True,
            message=(
                "The customer made a payment to HMRC that put them in a better position than their other creditors shortly before the case started. "
                "This creates a risk that the payment could later be clawed back, so the IVA is not viable and this case must be rejected."
            ),
        )
    if not at and not c.get("has_open_banking"):
        return RuleResult(
            rule_id="TIG-HMRC-ANTECEDENT",
            severity="flag",
            triggered=True,
            message="There is no bank transaction data available to check for this. The caseworker must confirm the customer made no preferential payments to HMRC in the last two years.",
        )
    return _pass("TIG-HMRC-ANTECEDENT", "No preferential payments to HMRC were identified.")


def _tig_16(c: dict) -> RuleResult:
    """TIG-16: Property equity exceeds liabilities — flag (non-WPM cases only).

    Excel (General Rejection / Watch Flags): "Equity Exceeds Liabilities —
    greater return in Bankruptcy (only for NON WPM or Eversheds cases). Reason
    needed for why they aren't remortgaging to repay debts."

    So this is: equity > total debt (liabilities), a FLAG requiring a reason —
    NOT a flat £5,000 hard block (the old £5,000 figure had no Excel basis and
    was hard-rejecting any homeowner with >£5k equity even when their debt far
    exceeded it). WPM/WATCH cases are excluded here because WATCH-22.4 already
    evaluates equity-vs-debt (at 85% LTV) for them; Eversheds and all other
    non-WATCH cases are covered by this rule.
    """
    has_property = c.get("has_property", False)

    # WPM (WATCH) cases are handled by WATCH-22.4 — TIG-16 is for NON-WPM cases.
    if "WATCH" in (c.get("detected_representatives") or set()):
        if not has_property:
            return _pass(
                "TIG-16",
                "The customer does not own a property, so this check does not apply.",
            )
        pv = _parse_amount(c.get("property_value") or 0)
        if pv <= 0:
            mb = c.get("mortgage_balance", 0)
            return RuleResult(
                rule_id="TIG-16",
                severity="flag",
                triggered=True,
                message=(
                    f"The customer owns a property with a mortgage balance of £{mb:,.2f}, but no valuation is recorded in the system. "
                    "The equity in the property cannot be worked out until a valuation is provided. "
                    "The caseworker must get a valuation before the case can proceed."
                ),
            )
        equity = pv - c["mortgage_balance"]
        liabilities = c["total_debt"]
        return _pass(
            "TIG-16",
            "This is a WATCH case, so the equity in the property is assessed under the WATCH equity rule instead of this check.",
            threshold=liabilities,
            actual_value=equity,
        )

    if not has_property:
        return _pass("TIG-16", "The customer does not own a property.")

    pv = _parse_amount(c.get("property_value", 0))
    # Owns property but no valuation in the system — can't compute equity → flag.
    if pv <= 0:
        mb = c.get("mortgage_balance", 0)
        return RuleResult(
            rule_id="TIG-16", severity="flag", triggered=True,
            message=(
                f"The customer owns a property with a mortgage balance of £{mb:,.2f}, but no valuation is recorded in the system. "
                "The equity cannot be worked out until a valuation is provided, so the caseworker must get one before this can be assessed."
            )
        )

    equity = pv - c["mortgage_balance"]
    liabilities = c["total_debt"]
    if equity > liabilities:
        return RuleResult(
            rule_id="TIG-16", severity="flag", triggered=True,
            message=(
                f"The customer's equity in their property is £{equity:,.2f}, which is more than their total debt of £{liabilities:,.2f}. "
                "In this situation, creditors are likely to get more money back through bankruptcy than through an IVA. "
                "The proposal must explain why the customer is not remortgaging to repay their debts instead."
            ),
            threshold=liabilities, actual_value=equity,
        )
    return _pass("TIG-16", f"The customer's equity of £{equity:,.2f} does not exceed their total debt of £{liabilities:,.2f}.",
                 threshold=liabilities, actual_value=equity)


def _tig_17(c: dict) -> RuleResult:
    """TIG-17: Council majority creditor with active income/benefit deductions — flag.

    Excel: "Council Majority — MUST NOT have a deduction from income or benefits
    (will reject). Case by case — check council list."
    Only fires when both conditions are true.
    """
    if not c["council_is_majority"]:
        return _pass("TIG-17", "The council is not the majority creditor.")
    if c["income_deductions_active"] is None:
        return RuleResult(
            rule_id="TIG-17",
            severity="flag",
            triggered=True,
            message="The council is the majority creditor. The caseworker must confirm whether any deductions are currently being taken from the customer's income or benefits before the case is proposed.",
        )
    if not c["income_deductions_active"]:
        return _pass("TIG-17", "The council is the majority creditor, but no income or benefit deductions are currently active.")
    return RuleResult(
        rule_id="TIG-17", severity="flag", triggered=True,
        message=(
            "The council holds more than 25% of the total debt by value, and deductions are currently being taken from the customer's income or benefits. "
            "The council is expected to reject the IVA while these deductions remain in place. "
            "The caseworker must review this case individually and check it against the council list."
        ),
    )


def _tig_18(c: dict) -> RuleResult:
    """TIG-18: Total spend in last 2 months >= monthly income (excl. payday loans) — flag only."""
    if not c.get("has_open_banking"):
        return RuleResult(
            rule_id="TIG-18",
            severity="flag",
            triggered=True,
            message="There is no open banking data loaded, so the recent spending check could not be completed. The caseworker must verify this manually.",
        )
    monthly_income = c["total_income"]
    spend = c["total_spend_2mo"]
    if monthly_income <= 0:
        return _pass("TIG-18", "There is no income data available, so this check has been skipped.")
    if spend >= monthly_income:
        return RuleResult(
            rule_id="TIG-18", severity="flag", triggered=True,
            message=f"The customer spent £{spend:,.2f} in the last two months. Their monthly income is £{monthly_income:,.2f}. The spending is at or above their income, so an assessor must review the case.",
            threshold=monthly_income, actual_value=spend,
        )
    return _pass("TIG-18", f"The customer's recent spend of £{spend:,.2f} is within their monthly income of £{monthly_income:,.2f}.")


def _tig_19(c: dict) -> RuleResult:
    """TIG-19: Shop Direct purchases within 3 months of statement date — hard block."""
    if not c.get("has_open_banking"):
        return RuleResult(
            rule_id="TIG-19",
            severity="flag",
            triggered=True,
            message="There is no open banking data loaded, so the check for recent Shop Direct spending could not be completed. The caseworker must verify this manually.",
        )
    if c["shop_direct_tx_3mo"]:
        return RuleResult(
            rule_id="TIG-19", severity="hard_block", triggered=True,
            # EXCEL_CRITERIA_REFERENCE.md — TIG Shop Direct: 3-month spend = hard reject
            message=f"The customer's bank statements show {len(c['shop_direct_tx_3mo'])} transaction(s) with Shop Direct, Very, or Littlewoods in the last three months. Recent spending with these creditors within three months is not allowed, so this case cannot proceed.",
        )
    return _pass(
        "TIG-19",
        "No transactions with Shop Direct, Very, Littlewoods, JD Williams, Simply Be, "
        "Jacamo, Fashion World, or Marisota were found in the bank statements from the last three months."
    )


def _tig_19_review(c: dict) -> RuleResult:
    """TIG-SHOP-DIRECT-4MO-REVIEW: Shop Direct spend in the 3–4 month window only — flag for review."""
    # EXCEL_CRITERIA_REFERENCE.md — TIG Shop Direct: 4-month window = flag for review
    if c["shop_direct_tx_4mo"] and not c["shop_direct_tx_3mo"]:
        return RuleResult(
            rule_id="TIG-SHOP-DIRECT-4MO-REVIEW", severity="flag", triggered=True,
            message="The customer's bank statements show spending with Shop Direct between three and four months ago. This falls outside the strict three-month block, but the caseworker must still review it before the case proceeds.",
        )
    return _pass("TIG-SHOP-DIRECT-4MO-REVIEW", "No Shop Direct spending was found in the three-to-four month window.")


def _tig_19_1(c: dict) -> RuleResult:
    """TIG-19.1: Shop Direct account < 6 months old — hard block."""
    for creditor in c["creditors"]:
        if not _contains_any(creditor["name"], _SHOP_DIRECT_NAMES):
            continue
        age = creditor.get("account_age_months")
        if age is None:
            return RuleResult(
                rule_id="TIG-19.1",
                severity="flag",
                triggered=True,
                message=f"The customer has a Shop Direct account with {creditor['name']}, but its age could not be verified. The caseworker must confirm the account is at least six months old before the case is proposed.",
            )
        if age < 6:
            return RuleResult(
                rule_id="TIG-19.1", severity="hard_block", triggered=True,
                message=f"The customer's Shop Direct account with {creditor['name']} is only {age} months old. The account must be at least 6 months old, so this case cannot proceed.",
                threshold=6.0, actual_value=float(age),
            )
    return _pass("TIG-19.1", "The customer has no Shop Direct account under six months old.")


def _tig_20(c: dict) -> RuleResult:
    """TIG-20: Creation purchases within 3 months — flag (TIG-20.1 is the hard block)."""
    if not c.get("has_open_banking"):
        return RuleResult(
            rule_id="TIG-20",
            severity="flag",
            triggered=True,
            message="There is no open banking data loaded, so the check for recent Creation, Sygma, or Laser spending could not be completed. The caseworker must verify this manually.",
        )
    if c["creation_tx_4mo"]:
        return RuleResult(
            rule_id="TIG-20", severity="flag", triggered=True,
            message=f"The customer's bank statements show {len(c['creation_tx_4mo'])} transaction(s) with Creation, Sygma, or Laser in the last four months. This is checked further below, but the caseworker should be aware of it.",
        )
    return _pass("TIG-20", "No recent transactions with Creation, Sygma, or Laser were found.")


def _tig_20_1(c: dict) -> RuleResult:
    """TIG-20.1: Recent spend with Creation / Sygma / Laser — hard block, no trial cases.

    Excel source: 'PLEASE CAN WE NOT RUN ANY FURTHER TRIALS ON RECENT SPEND WITH
    SYGMA / CREATION / LASER REGARDLESS OF THE REASON.'
    The block is on recent SPEND only; having a dormant Creation account is not a block.
    """
    if not c.get("has_open_banking"):
        return RuleResult(
            rule_id="TIG-20.1",
            severity="flag",
            triggered=True,
            message="There is no open banking data loaded, so the check for recent Creation, Sygma, or Laser spending could not be completed. The caseworker must verify this manually.",
        )
    if c["creation_tx_4mo"]:
        return RuleResult(
            rule_id="TIG-20.1", severity="hard_block", triggered=True,
            message="The customer has recent spending with Creation, Sygma, or Laser. Cases with recent spending on these accounts are not accepted under any circumstances, so this case cannot proceed.",
        )
    return _pass("TIG-20.1", "No recent spending with Creation, Sygma, or Laser was found.")


def _tig_21_1(c: dict) -> RuleResult:
    """TIG-21.1: Link Financial creditor — must confirm Mid SFS guidelines used."""
    if not c["link_is_creditor"]:
        return _pass("TIG-21.1", "Link Financial is not one of the customer's creditors.")
    link_bal = c["link_balance"]
    total_debt = c.get("total_debt", 0)
    debt_ok = "this is met" if total_debt >= 12000 else f"this is NOT met, as total debt is £{total_debt:,.2f}"
    return RuleResult(
        rule_id="TIG-21.1", severity="flag", triggered=True,
        message=(
            f"Link Financial is one of the customer's creditors, with a balance of £{link_bal:,.2f}. "
            f"Link Financial's mid-level income and expenditure guidelines must be applied to this case. "
            f"Total debt must be at least £12,000 — {debt_ok}. "
            "Benefits must not make up more than 10% of the customer's income. "
            "If the customer owns property, the caseworker must manually check the equity before proposing."
        ),
        threshold=0.0,
        actual_value=float(link_bal),
    )


def _tig_21_2(c: dict) -> RuleResult:
    """TIG-21.2: total_debt < £12,000 AND Link Financial is a creditor — hard block."""
    if not c["link_is_creditor"]:
        return _pass("TIG-21.2", "Link Financial is not one of the customer's creditors.")
    threshold = 12000.0
    actual = c["total_debt"]
    if actual < threshold:
        return RuleResult(
            rule_id="TIG-21.2", severity="hard_block", triggered=True,
            message=f"The customer's total debt is £{actual:,.2f}, which is below the £{threshold:,.2f} minimum required when Link Financial is a creditor. This case cannot proceed.",
            threshold=threshold, actual_value=actual,
        )
    return _pass("TIG-21.2", f"The customer's total debt of £{actual:,.2f} meets the minimum required for Link Financial.")


def _tig_21_3(c: dict) -> RuleResult:
    """TIG-21.3: Property equity > Link Financial balance — hard block."""
    if not c["link_is_creditor"]:
        return _pass("TIG-21.3", "Link Financial is not one of the customer's creditors.")

    has_property = c.get("has_property", False)
    pv = _parse_amount(c.get("property_value", 0))

    # Edge case: owns_property is True but property_value is unknown
    if has_property and pv <= 0:
        return RuleResult(
            rule_id="TIG-21.3", severity="flag", triggered=True,
            message=(
                "The customer owns a property, but no valuation is recorded in the system. "
                "The caseworker must get a valuation and check the equity before the case can proceed."
            )
        )

    if not has_property:
        return _pass("TIG-21.3", "The customer does not own a property.")

    if c["available_equity"] is None:
        return RuleResult(
            rule_id="TIG-21.3", severity="info", triggered=False,
            message="This check could not be completed because the property value was not provided.",
        )
    if c["available_equity"] > c["link_balance"]:
        return RuleResult(
            rule_id="TIG-21.3", severity="hard_block", triggered=True,
            message=f"The customer's available equity of £{c['available_equity']:,.2f} is more than the Link Financial balance of £{c['link_balance']:,.2f}. This case cannot proceed.",
            threshold=c["link_balance"], actual_value=c["available_equity"],
        )
    return _pass("TIG-21.3", "The customer's available equity does not exceed the Link Financial balance.")


def _tig_21_4(c: dict) -> RuleResult:
    """TIG-21.4: Benefits > 10% of household income AND Link Financial is a creditor."""
    if not c["link_is_creditor"]:
        return _pass("TIG-21.4", "Link Financial is not one of the customer's creditors.")
    total_income = c["total_income"]
    if total_income <= 0:
        return _pass("TIG-21.4", "There is no income data available, so this check has been skipped.")
    
    benefit_amount = c.get("benefit_income_amount")
    if benefit_amount is None:
        if c["income_source"] in ("benefits", "uc", "universal_credit"):
            benefit_pct = 100.0
        else:
            # If not a benefits-only source and amount is None, assume 0
            # This ensures the rule passes cleanly instead of showing a TODO flag.
            benefit_pct = 0.0
    else:
        benefit_pct = float(benefit_amount) / float(total_income) * 100.0

    threshold = 10.0
    if benefit_pct > threshold:
        return RuleResult(
            rule_id="TIG-21.4", severity="hard_block", triggered=True,
            message=f"Benefits make up {benefit_pct:.0f}% of the customer's household income, which is above the {threshold:.0f}% limit allowed when Link Financial is a creditor. This case cannot proceed as it stands.",
            threshold=threshold, actual_value=benefit_pct,
        )
    return _pass("TIG-21.4", "Benefits make up no more than 10% of the customer's household income.")


def _tig_21_5(c: dict) -> RuleResult:
    """
    TIG-21.5: Previous IVA failure evaluation for Link Financial.
    - Pass if no previous IVA or completed successfully.
    - Hard block if failed due to breach/arrears (Excel: "REJECT if previous IVA
      failed due to arrears").
    - Hard block if terminated due to fraud/misrepresentation.
    - Flag for other/unspecified failure reasons (review required).
    """
    if not c["link_is_creditor"]:
        return _pass("TIG-21.5", "Link Financial is not one of the customer's creditors.")

    if not c["previous_iva"]:
        return _pass("TIG-21.5", "The customer has no previous IVA, so this check does not apply.")

    _raw_reason = c.get("previous_iva_failed_reason")
    if _raw_reason is None and c.get("previous_iva_failed"):
        _raw_reason = "unknown_reason"
    reason = (_raw_reason or "").lower()

    # 1. Pass if no failure reason or explicitly completed
    if not reason or "completed" in reason:
        return _pass("TIG-21.5", "The customer has a previous IVA on record, but there is no failure reason recorded against it.")

    # 2. Hard block if terminated due to fraud or misrepresentation
    if "fraud" in reason or "misrepresentation" in reason:
        return RuleResult(
            rule_id="TIG-21.5", severity="hard_block", triggered=True,
            message=f"The customer's previous IVA was ended because of fraud or misrepresentation (recorded reason: '{reason}'). Link Financial is expected to reject the IVA, so this case cannot proceed.",
        )

    # 3. Hard block if failed due to client breach or missed payments (arrears) —
    #    Excel (Link Financial): "REJECT if previous IVA failed due to arrears."
    breach_keywords = ["breach", "arrears", "missed", "payment", "contribution", "default"]
    if any(kw in reason for kw in breach_keywords):
        return RuleResult(
            rule_id="TIG-21.5", severity="hard_block", triggered=True,
            message=f"The customer's previous IVA failed because they fell behind or missed payments (recorded reason: '{reason}'). Link Financial is expected to reject the IVA, so this case cannot proceed.",
        )

    # 4. Default to flag for other failures
    return RuleResult(
        rule_id="TIG-21.5", severity="flag", triggered=True,
        message=f"The customer's previous IVA failed for the following recorded reason: '{reason}'. The caseworker must review this with Link Financial before proceeding.",
    )


# ---------------------------------------------------------------------------
# WATCH RULES — run only when WATCH is a creditor
# ---------------------------------------------------------------------------

def _watch_22_1(c: dict) -> RuleResult:
    """WATCH-22.1: Vulnerability claimed but no supporting evidence uploaded — flag + advisory."""
    if not c["vulnerability_claimed"]:
        return _pass("WATCH-22.1", "No vulnerability claim — rule not applicable.")
    if not c["vulnerability_evidence_uploaded"]:
        return RuleResult(
            rule_id="WATCH-22.1", severity="flag", triggered=True,
            message=(
                "The customer has been recorded as vulnerable, but no supporting evidence for this has been uploaded. "
                "The caseworker must speak to Tom or Debra before proceeding, and the evidence must be obtained and documented."
            ),
        )
    return _pass("WATCH-22.1", "Vulnerability claimed and supporting evidence uploaded.")


def _watch_22_2(c: dict) -> RuleResult:
    """WATCH-22.2: Debt repayable in <= 72 months from disposable income — hard block."""
    threshold = 72.0
    di = c["disposable_income"]
    if di <= 0:
        return RuleResult(
            rule_id="WATCH-22.2",
            severity="hard_block",
            triggered=True,
            message=(
                "The customer has no disposable income (it is zero or negative), so their debt could never be repaid "
                "within 72 months even outside an IVA. WATCH requires an IVA to run for at least 6 years, so this creditor "
                "is expected to reject the IVA."
            ),
            threshold=72.0,
            actual_value=None,
        )
    actual = c["total_debt"] / di
    if actual <= threshold:
        return RuleResult(
            rule_id="WATCH-22.2", severity="hard_block", triggered=True,
            message=(
                f"Based on the customer's disposable income, their debt could be repaid in {actual / 12:.1f} years, "
                "which is within 6 years. WATCH rejects cases where the debt could be repaid without an IVA within "
                "6 years, so this creditor is expected to reject the IVA."
            ),
            threshold=threshold, actual_value=actual,
        )
    return _pass("WATCH-22.2", f"Debt repayable in {actual / 12:.1f} years — exceeds 6 years, WATCH-22.2 not triggered.")


def _watch_22_3(c: dict) -> RuleResult:
    """WATCH-22.3: Bankruptcy return > IVA return — hard block if bankruptcy yields more."""
    if c["bankruptcy_return"] is None:
        return _pass("WATCH-22.3", "Bankruptcy return not provided — rule not applicable.")
    br = _parse_amount(c["bankruptcy_return"])
    # EXCEL_CRITERIA_REFERENCE.md — IVA term from case payload, not hardcoded
    iva_return = c["disposable_income"] * c.get("iva_term_months", 60) * 0.75
    if br > iva_return:
        return RuleResult(
            rule_id="WATCH-22.3", severity="hard_block", triggered=True,
            message=(
                f"If the customer went bankrupt instead, creditors would get back an estimated £{br:,.2f}, which is more "
                f"than the £{iva_return:,.2f} they are projected to receive from the IVA. Because bankruptcy would pay "
                "creditors more, this creditor is expected to reject the IVA."
            ),
            threshold=iva_return, actual_value=br,
        )
    return _pass("WATCH-22.3", "IVA return exceeds bankruptcy return.")


def _watch_22_4(c: dict) -> RuleResult:
    """WATCH-22.4: Available equity > total unsecured debt — hard block."""
    # EXCEL_CRITERIA_REFERENCE.md — Watch Criteria: 85% LTV (same as EVOLVE)
    # EXCEL_CRITERIA_REFERENCE.md — stub replaced;
    # triggered=True without evaluation is misleading
    if not c["has_property"]:
        return _pass("WATCH-22.4", "No property — WATCH-22.4 not applicable.")
    property_value = c["property_value"]
    if property_value is None:
        return RuleResult(
            rule_id="WATCH-22.4", severity="info", triggered=False,
            message="This check could not be completed because the property value was not provided. Please verify manually.",
        )
    pv = _parse_amount(property_value)
    equity_at_85 = (pv * 0.85) - c["mortgage_balance"]
    if equity_at_85 > c["total_debt"]:
        return RuleResult(
            rule_id="WATCH-22.4", severity="hard_block", triggered=True,
            message=(
                f"The customer's property has an estimated £{equity_at_85:,.2f} of equity available (based on 85% of its "
                f"value, after the mortgage), which is more than their total unsecured debt of £{c['total_debt']:,.2f}. "
                "WATCH expects available equity like this to be used to pay off the debt, so this creditor is expected "
                "to reject the IVA."
            ),
            threshold=c["total_debt"], actual_value=equity_at_85,
        )
    return _pass("WATCH-22.4", f"Equity at 85% LTV £{equity_at_85:,.2f} does not exceed total debt.")


def _count_qualifying_lenders(creditors: list, threshold: float) -> int:
    """Count DISTINCT lenders whose TOTAL balance exceeds `threshold`.

    Balances are SUMMED per lender BEFORE the threshold test. Brands of the same
    banking group are collapsed to one lender via `parent_group` (attached to
    each case creditor in assess_case from CreditorCriteria); when no
    parent_group is known the creditor name is the grouping key, so multiple
    debts to the same named creditor are also summed into one lender.

    Source (Watch/Evolve criteria): "Client only has debt with 1 lender — need a
    separate lender of more than £500"; the Evolve example treats a NatWest
    loan + credit card + overdraft + bounceback as ONE lender. So the £500 test
    is the client's TOTAL exposure to a lender, not any single debt row — two
    £400 accounts with one lender (£800 total) qualify that lender.
    """
    totals: dict[str, float] = {}
    display_names: dict[str, str] = {}
    for cr in creditors:
        key = (cr.get("parent_group") or "").strip().lower() \
            or (cr.get("name") or "").strip().lower()
        if not key:
            continue
        try:
            bal = float(cr.get("balance") or 0)
        except (TypeError, ValueError):
            bal = 0.0
        totals[key] = totals.get(key, 0.0) + bal
        # Keep the most readable display name for this lender key
        if key not in display_names:
            display_names[key] = (cr.get("parent_group") or cr.get("name") or key).strip()
    qualifying_names = sorted(
        display_names[k] for k, v in totals.items() if v > threshold
    )
    return qualifying_names


def _watch_22_5(c: dict) -> RuleResult:
    """WATCH-22.5: Only 1 qualifying lender (balance > £500) — hard block.
    Banking-group brands count as a single lender (see _count_qualifying_lenders)."""
    threshold = 500.0
    qualifying_names = _count_qualifying_lenders(c["creditors"], threshold)
    count = len(qualifying_names)
    names_str = ", ".join(qualifying_names) if qualifying_names else "none"
    if count <= 1:
        return RuleResult(
            rule_id="WATCH-22.5", severity="hard_block", triggered=True,
            message=(
                f"The customer only has {count} lender ({names_str}) with a balance above £{threshold:,.2f}. WATCH "
                "requires at least two separate lenders above this amount, so this creditor is expected to reject "
                "the IVA."
            ),
            threshold=threshold, actual_value=float(count),
        )
    return _pass("WATCH-22.5", f"{count} qualifying lenders with balance > £{threshold:,.2f}: {names_str}.",
                 threshold=threshold, actual_value=float(count))


def _watch_22_6(c: dict) -> RuleResult:
    """WATCH-22.6: Excessive luxury/non-essential spend in last 3 months."""
    if not c.get("has_open_banking"):
        return RuleResult(
            rule_id="WATCH-22.6", severity="flag", triggered=True,
            message="Open banking data was not available, so luxury or non-essential spending in the last 3 months could not be checked. Please verify manually.",
        )

    assessment_date = c["assessment_date"]
    recent_out = [
        t for t in c["gold_transactions"]
        if t.get("transaction_type") == "money_out"
        and _is_within_days(
            t.get("transaction_date") or t.get("date"), 90, reference=assessment_date
        )
    ]

    has_categories = any(
        t.get("category") or t.get("transaction_category") for t in recent_out
    )

    if has_categories:
        luxury_txs = [
            t for t in recent_out
            if (t.get("category") or t.get("transaction_category") or "").lower()
            in LUXURY_CATEGORIES
        ]
        if luxury_txs:
            luxury_total = sum(_parse_amount(t.get("amount", 0)) for t in luxury_txs)
            return RuleResult(
                rule_id="WATCH-22.6", severity="flag", triggered=True,
                message=(
                    f"The customer spent £{luxury_total:,.2f} on luxury or non-essential items in the last 90 days. "
                    "This spending must be discussed with the customer before the solution is proposed."
                ),
                actual_value=luxury_total,
            )

    return _pass("WATCH-22.6", "No excessive luxury spend identified in the last 3 months.")


def _watch_22_7(c: dict) -> RuleResult:
    """WATCH-22.7: Children OVER 13 (age > 13) with no sustainability paragraph —
    hard block.

    Excel (Watch Rejection Rules): "Client has children over 13 and no
    sustainability paragraph (Drafter) → Reject". Boundary is strictly > 13 per
    "over 13".

    NOTE: this rule is currently is_active=False in GlobalCriteria, so the engine
    discards its result (disabled). The code is kept Excel-correct so enabling the
    rule (is_active=True) makes it hard-block immediately. (Decision 2026-06-21:
    fix code, leave disabled pending the WATCH-config-drift review.)
    """
    children = c["children"]
    if not children:
        return _pass("WATCH-22.7", "No children on record — rule not applicable.")
    has_teen = any(_parse_amount(child.get("age", 0)) > 13 for child in children)
    if not has_teen:
        return _pass("WATCH-22.7", "No children aged over 13.")
    if not c["sustainability_paragraph_present"]:
        return RuleResult(
            rule_id="WATCH-22.7", severity="hard_block", triggered=True,
            message=(
                "The customer has one or more children aged over 13, and the IVA proposal does not include a "
                "sustainability paragraph explaining how the plan will be maintained. This must be added before "
                "the case can proceed."
            ),
        )
    return _pass("WATCH-22.7", "Sustainability paragraph present.")


def _watch_22_8(c: dict) -> RuleResult:
    """WATCH-22.8: Client aged 80+ — WATCH will abstain. Info only, does not block."""
    age = c["client_age"]
    if age is None:
        return _pass("WATCH-22.8", "Client age unknown — WATCH-22.8 not evaluated.")
    if age >= 80:
        return RuleResult(
            rule_id="WATCH-22.8", severity="info", triggered=False,
            message=(
                f"The customer is {age} years old. WATCH will abstain rather than vote on cases where the customer "
                "is 80 or older, so this should be noted in the proposal."
            ),
            threshold=80.0, actual_value=float(age),
        )
    return _pass("WATCH-22.8", f"Client aged {age} — under 80, WATCH-22.8 not triggered.")


def _watch_22_9(c: dict) -> RuleResult:
    """WATCH-22.9: Vehicle value > £9,000 — flag."""
    threshold = 9000.0
    vehicle_value = c["vehicle_value"]
    if vehicle_value is None:
        return _pass("WATCH-22.9", "Vehicle value not provided — rule not applicable.")
    actual = _parse_amount(vehicle_value)
    if actual > threshold:
        return RuleResult(
            rule_id="WATCH-22.9", severity="flag", triggered=True,
            message=(
                f"The customer's vehicle is worth £{actual:,.2f}, which is above WATCH's £{threshold:,.2f} guideline. "
                "WATCH may ask for this to be reduced to a car worth no more than £4,500."
            ),
            threshold=threshold, actual_value=actual,
        )
    return _pass("WATCH-22.9", f"Vehicle value £{actual:,.2f} within threshold.")


def _watch_22_10(c: dict) -> RuleResult:
    """WATCH-22.10: Car HP payment > £400/month — flag."""
    threshold = float(WATCH_HP_MONTHLY_CAP)
    actual = c["vehicle_hp_monthly"]
    if not c.get("has_open_banking"):
        return RuleResult(
            rule_id="WATCH-22.10",
            severity="flag",
            triggered=True,
            message="Open banking data was not available, so the customer's car finance (HP) monthly payment could not be checked. Please confirm the payment amount manually.",
        )
    if actual > threshold:
        return RuleResult(
            rule_id="WATCH-22.10", severity="flag", triggered=True,
            message=(
                f"The customer pays £{actual:,.2f} a month towards car finance, which is above WATCH's £{threshold:,.2f} "
                "monthly guideline. Evidence supporting this payment must be provided."
            ),
            threshold=threshold, actual_value=actual,
        )
    return _pass("WATCH-22.10", f"HP payment £{actual:,.2f}/month within threshold.")


def _watch_22_11(c: dict) -> RuleResult:
    """WATCH-22.11: Gambling as main cause of debt — 3 months of clean bank statements required."""
    if not c["gambling_main_cause"]:
        return _pass("WATCH-22.11", "Gambling not identified as main cause of debt.")
    return RuleResult(
        rule_id="WATCH-22.11", severity="flag", triggered=True,
        message=(
            "Gambling has been identified as the main cause of the customer's debt. Before the case can proceed, "
            "3 months of bank statements showing no gambling activity are required."
        ),
    )


def _watch_22_12(c: dict) -> RuleResult:
    """WATCH-22.12: Previous IVA proposed — I&E/assets/liabilities must be consistent or explained."""
    if not c["previous_iva"]:
        return _pass("WATCH-22.12", "No previous IVA — WATCH-22.12 not applicable.")
    failed = c.get("previous_iva_failed", False)
    reason = c.get("previous_iva_failed_reason") or ""
    if failed and reason:
        failure_str = f"It failed, and the recorded reason is: '{reason}'. "
    elif failed:
        failure_str = "It failed, but no reason has been recorded for this. "
    else:
        failure_str = "No failure reason has been detected. "
    return RuleResult(
        rule_id="WATCH-22.12", severity="flag", triggered=True,
        message=(
            f"The customer has had a previous IVA. {failure_str}"
            "WATCH requires the income and expenditure, assets and liabilities in this case to be consistent with the "
            "previous proposal, or a written explanation to be provided for any differences. A termination report "
            "for the previous IVA is also required before this case can proceed."
        ),
        threshold=0.0,
        actual_value=1.0,
    )


def _watch_22_13(c: dict) -> RuleResult:
    """WATCH-22.13: Antecedent transactions identified — hard block, no exceptions."""
    at = c["antecedent_transactions"]
    if at is True:
        return RuleResult(
            rule_id="WATCH-22.13", severity="hard_block", triggered=True,
            message=(
                "Antecedent transactions (payments made shortly before insolvency that unfairly favour one creditor) "
                "have been identified on this case. WATCH does not allow any exceptions for this, so the case cannot "
                "proceed."
            ),
        )
    if at is None:
        return RuleResult(
            rule_id="WATCH-22.13", severity="flag", triggered=True,
            message="The check for antecedent transactions could not be completed. Please verify manually that none exist before proceeding.",
        )
    if not c.get("has_open_banking"):
        return RuleResult(
            rule_id="WATCH-22.13", severity="flag", triggered=True,
            message="Open banking data was not available, so please confirm manually that no antecedent transactions exist before proceeding.",
        )
    return _pass("WATCH-22.13", "No antecedent transactions identified.")


_VEHICLE_HP_LENDER_NAMES = frozenset({
    "black horse", "motonovo", "alphera", "close brothers",
    "volkswagen financial services", "vwfs", "audi finance",
    "skoda finance", "seat finance", "porsche financial services",
})


def _is_vehicle_hp_creditor(cr: dict) -> bool:
    """normalise_debt_type() buckets ALL hire-purchase debt (furniture,
    appliances, logbook loans, cars) under the single DEBT_TYPE_HP value —
    WATCH-22.14 is specifically about car finance, so a raw-type or lender-name
    signal is needed to exclude non-vehicle HP from the credit-report check."""
    raw = (cr.get("creditor_type") or "").lower()
    if any(kw in raw for kw in ("car", "vehicle", "motor", "auto", "logbook", "log book")):
        return True
    return _contains_any(cr.get("name", ""), _VEHICLE_HP_LENDER_NAMES)


def _tx_matches_creditor_name(tx: dict, creditor_name: str) -> bool:
    desc = _norm(tx.get("description") or "")
    name = _norm(creditor_name or "")
    if not desc or not name:
        return False
    return name in desc or desc in name


def _watch_22_14(c: dict) -> RuleResult:
    """WATCH-22.14: New car finance (HP) agreement taken out in the last 3 months — hard block.

    Only a *new* HP agreement is a hard block, verified via the credit report's
    account start date (account_age_months, set by _enrich_from_credit_report).
    Ongoing repayments on the bank statement are not evidence of a new
    agreement on their own — an HP account can be years old and still show a
    monthly debit — so bank-statement activity alone never hard-blocks.

    Each car-finance transaction is checked against the specific vehicle-HP
    creditor it belongs to (by name), not just "is any HP creditor on the case
    old" — otherwise one old, confirmed HP account (or an unrelated non-vehicle
    HP debt) would silently clear the flag for a second, undeclared car
    finance agreement that happens to also show up on the bank statement.
    """
    from debt_app.helpers import DEBT_TYPE_HP

    hp_creditors = [
        cr for cr in c["creditors"]
        if cr.get("debt_type_normalised") == DEBT_TYPE_HP and _is_vehicle_hp_creditor(cr)
    ]

    new_hp = [
        cr for cr in hp_creditors
        if cr.get("account_age_months") is not None and cr["account_age_months"] < 3
    ]
    if new_hp:
        names = ", ".join(cr["name"] for cr in new_hp)
        return RuleResult(
            rule_id="WATCH-22.14", severity="hard_block", triggered=True,
            message=(
                f"The credit report shows a hire purchase / car finance agreement with {names} taken out within "
                "the last 3 months. This can cause the IVA to be rejected unless there is evidence explaining why "
                "the car finance was needed — for example the old car was scrapped, damaged in an accident, or the "
                "car is needed for work. Until this evidence is provided, this creditor is expected to reject the IVA."
            ),
        )

    # Old/confirmed HP creditors (known age, so >= 3 months since they didn't
    # match new_hp above) — their transactions are just ongoing instalments.
    old_hp = [cr for cr in hp_creditors if cr.get("account_age_months") is not None]

    unexplained_tx = [
        t for t in c["car_finance_tx_3mo"]
        if not any(_tx_matches_creditor_name(t, cr["name"]) for cr in old_hp)
    ]

    if unexplained_tx:
        return RuleResult(
            rule_id="WATCH-22.14", severity="flag", triggered=True,
            message=(
                "Car finance / hire purchase repayments were identified on the bank statements, but no matching "
                "hire purchase agreement could be confirmed on the credit report, so it's not possible to tell "
                "whether this is an existing agreement or one taken out in the last 3 months. Please request "
                "evidence of when the agreement was taken out before proceeding."
            ),
        )

    return _pass("WATCH-22.14", "No new car finance (HP) agreement identified in the last 3 months.")


# ---------------------------------------------------------------------------
# TIX RULES — run only when TIX is a creditor
# ---------------------------------------------------------------------------

def _tix_01(c: dict) -> RuleResult:
    """TIX-01: Shop Direct / Very / Littlewoods spend in last 3 months — hard block."""
    shop_direct_is_creditor = any(_contains_any(cr["name"], _SHOP_DIRECT_NAMES) for cr in c["creditors"])
    if not shop_direct_is_creditor:
        return _pass("TIX-01", "No Shop Direct / Very / Littlewoods creditor in case — TIX-01 not applicable.")
    if not c.get("has_open_banking"):
        return RuleResult(
            rule_id="TIX-01",
            severity="flag",
            triggered=True,
            message="Open banking data was not available, so recent spending with Shop Direct, Very or Littlewoods could not be checked. Please verify manually.",
        )
    if c["shop_direct_tx_3mo"]:
        count = len(c["shop_direct_tx_3mo"])
        return RuleResult(
            rule_id="TIX-01", severity="hard_block", triggered=True,
            message=(
                f"The customer has made {count} transaction(s) with Shop Direct, Very or Littlewoods in the last "
                "3 months. TIX does not allow this, so this creditor is expected to reject the IVA."
            ),
        )
    return _pass("TIX-01", "No recent Shop Direct transactions.")


def _tix_02(c: dict) -> RuleResult:
    """TIX-02: Shop Direct account < 6 months old — hard block."""
    for creditor in c["creditors"]:
        if not _contains_any(creditor["name"], _SHOP_DIRECT_NAMES):
            continue
        age = creditor.get("account_age_months")
        if age is None:
            return RuleResult(
                rule_id="TIX-02",
                severity="flag",
                triggered=True,
                message=(
                    f"The customer has a Shop Direct account with {creditor['name']}, but its age could not be "
                    "confirmed. Please confirm the account is at least 6 months old before the solution is proposed."
                ),
            )
        if age < 6:
            return RuleResult(
                rule_id="TIX-02", severity="hard_block", triggered=True,
                message=(
                    f"The customer's account with {creditor['name']} is only {age} month(s) old. TIX requires "
                    "accounts to be at least 6 months old, so this creditor is expected to reject the IVA."
                ),
                threshold=6.0, actual_value=float(age),
            )
    return _pass("TIX-02", "No Shop Direct account under 6 months old.")


def _tix_03(c: dict) -> RuleResult:
    """TIX-03: Creation / Sygma / Laser spend in last 4 months — hard block."""
    creation_is_creditor = any(_contains_any(cr["name"], _CREATION_NAMES) for cr in c["creditors"])
    if not creation_is_creditor:
        return _pass("TIX-03", "No Creation / Sygma / Laser creditor in case — TIX-03 not applicable.")
    if not c.get("has_open_banking"):
        return RuleResult(
            rule_id="TIX-03",
            severity="flag",
            triggered=True,
            message="Open banking data was not available, so recent spending with Creation, Sygma or Laser could not be checked. Please verify manually.",
        )
    if c["creation_tx_4mo"]:
        count = len(c["creation_tx_4mo"])
        return RuleResult(
            rule_id="TIX-03", severity="hard_block", triggered=True,
            message=(
                f"The customer has made {count} transaction(s) with Creation, Sygma or Laser in the last 4 months. "
                "TIX does not allow this, so this creditor is expected to reject the IVA."
            ),
        )
    return _pass("TIX-03", "No recent Creation / Sygma / Laser transactions.")


def _tix_04(c: dict) -> RuleResult:
    """TIX-04: Car HP payment > £250/month — flag. NOTE: TIX threshold is £250, WATCH is £400."""
    threshold = 250.0
    actual = c["vehicle_hp_monthly"]
    if not c.get("has_open_banking"):
        return RuleResult(
            rule_id="TIX-04",
            severity="flag",
            triggered=True,
            message="Open banking data was not available, so the customer's car finance (HP) monthly payment could not be checked. Please confirm the payment amount manually.",
        )
    if actual > threshold:
        return RuleResult(
            rule_id="TIX-04", severity="flag", triggered=True,
            message=(
                f"The customer pays £{actual:,.2f} a month towards car finance, which is above TIX's £{threshold:,.2f} "
                "monthly guideline. Evidence supporting this payment must be provided."
            ),
            threshold=threshold, actual_value=actual,
        )
    return _pass("TIX-04", f"HP payment £{actual:,.2f}/month within TIX threshold.")


def _tix_05(c: dict) -> RuleResult:
    """TIX-05: UKAR / Whistletree / Computershare / Landmark no longer TIX after 30 June 2023 — info."""
    for creditor in c["creditors"]:
        if _in_set(creditor["name"], _DEREGISTERED_TIX):
            return RuleResult(
                rule_id="TIX-05", severity="info", triggered=False,
                message=f"{creditor['name']} has not been represented by TIX since 30 June 2023, so TIX's positions no longer apply to this creditor.",
            )
    return _pass("TIX-05", "No deregistered TIX creditors present.")


def _tix_06(c: dict) -> RuleResult:
    """TIX-06: Vulnerability claimed but no supporting evidence uploaded — flag + advisory."""
    if not c["vulnerability_claimed"]:
        return _pass("TIX-06", "No vulnerability claim — rule not applicable.")
    if not c["vulnerability_evidence_uploaded"]:
        return RuleResult(
            rule_id="TIX-06", severity="flag", triggered=True,
            message=(
                "The customer has been recorded as vulnerable, but no supporting evidence for this has been uploaded. "
                "The caseworker must speak to Tom or Debra before proceeding, and the evidence must be obtained and documented."
            ),
        )
    return _pass("TIX-06", "Vulnerability claimed and supporting evidence uploaded.")


# ---------------------------------------------------------------------------
# EVOLVE RULES — run only when EVOLVE is a creditor
# ---------------------------------------------------------------------------

def _evolve_01(c: dict) -> RuleResult:
    """EVOLVE-01: Equity > debt based on 85% LTV (not 100%) — hard block."""
    # EXCEL_CRITERIA_REFERENCE.md — stub replaced;
    # triggered=True without evaluation is misleading
    if not c["has_property"]:
        return _pass("EVOLVE-01", "No property — EVOLVE-01 not applicable.")
    property_value = c["property_value"]
    if property_value is None:
        return RuleResult(
            rule_id="EVOLVE-01", severity="info", triggered=False,
            message="This check could not be completed because the property value was not provided. Please verify manually.",
        )
    # EVOLVE uses 85% LTV
    pv = _parse_amount(property_value)
    equity_at_85 = (pv * 0.85) - c["mortgage_balance"]
    if equity_at_85 > c["total_debt"]:
        return RuleResult(
            rule_id="EVOLVE-01", severity="hard_block", triggered=True,
            message=(
                f"The customer's property has an estimated £{equity_at_85:,.2f} of equity available (based on 85% of "
                f"its value, after the mortgage), which is more than their total debt of £{c['total_debt']:,.2f}. "
                "EVOLVE expects available equity like this to be used to pay off the debt, so this creditor is "
                "expected to reject the IVA."
            ),
            threshold=c["total_debt"], actual_value=equity_at_85,
        )
    return _pass("EVOLVE-01", f"Equity at 85% LTV £{equity_at_85:,.2f} does not exceed total debt.")


def _evolve_02(c: dict) -> RuleResult:
    """EVOLVE-02: Single lender (NatWest group counts as one lender) — hard block.
    Banking-group brands are grouped via parent_group (see _count_qualifying_lenders)."""
    threshold = 500.0
    qualifying_names = _count_qualifying_lenders(c["creditors"], threshold)
    count = len(qualifying_names)
    names_str = ", ".join(qualifying_names) if qualifying_names else "none"
    if count <= 1:
        return RuleResult(
            rule_id="EVOLVE-02", severity="hard_block", triggered=True,
            message=(
                f"The customer only has {count} lender ({names_str}) with a balance above £{threshold:,.2f}. EVOLVE "
                "requires at least two separate lenders above this amount, so this creditor is expected to reject "
                "the IVA."
            ),
            threshold=threshold, actual_value=float(count),
        )
    return _pass("EVOLVE-02", f"{count} qualifying lenders with balance > £{threshold:,.2f}: {names_str}.",
                 threshold=threshold, actual_value=float(count))


def _evolve_03(c: dict) -> RuleResult:
    """EVOLVE-03: Vulnerability claimed but no supporting evidence uploaded — flag + advisory."""
    if not c["vulnerability_claimed"]:
        return _pass("EVOLVE-03", "No vulnerability claim — rule not applicable.")
    if not c["vulnerability_evidence_uploaded"]:
        return RuleResult(
            rule_id="EVOLVE-03", severity="flag", triggered=True,
            message=(
                "The customer has been recorded as vulnerable, but no supporting evidence for this has been uploaded. "
                "The caseworker must speak to Tom or Debra before proceeding, and the evidence must be obtained and documented."
            ),
        )
    return _pass("EVOLVE-03", "Vulnerability claimed and supporting evidence uploaded.")


# ---------------------------------------------------------------------------
# MODULE 4 RULES — VW termination, DMP reject, county council routing
# ---------------------------------------------------------------------------

def _phase4_vw_termination(c: dict, criteria_map: dict) -> RuleResult:
    """PHASE4-VW-TERMINATION: HP debt with VW Finance group creditor — hard block."""
    from debt_app.helpers import DEBT_TYPE_HP

    for creditor in c["creditors"]:
        name = creditor["name"]
        name_lower = name.lower()
        is_vw = name_lower in _VW_GROUP_NAMES
        is_hp = creditor["debt_type_normalised"] == DEBT_TYPE_HP

        if not is_vw and not is_hp:
            continue

        if is_vw and not is_hp:
            return RuleResult(
                rule_id="PHASE4-VW-TERMINATION",
                severity="flag",
                triggered=True,
                message=(
                    f"{name} is a VW Group creditor, but the debt is recorded as "
                    f"'{creditor['debt_type_normalised']}' rather than hire purchase. Please confirm whether the "
                    "vehicle is actually on hire purchase, as this affects whether the creditor may terminate the "
                    "agreement."
                ),
            )

        if name_lower in _VW_GROUP_NAMES:
            return RuleResult(
                rule_id="PHASE4-VW-TERMINATION", severity="hard_block", triggered=True,
                message=(
                    f"{name} is a VW Financial Services group creditor and the customer's vehicle is on hire "
                    "purchase with them. This creditor can terminate the agreement and repossess the vehicle, so "
                    "this creditor is expected to reject the IVA."
                ),
            )

        criteria = criteria_map.get(name)
        if criteria and criteria.termination_risk_if_vehicle_on_finance:
            return RuleResult(
                rule_id="PHASE4-VW-TERMINATION", severity="hard_block", triggered=True,
                message=(
                    f"{name} is known to terminate vehicle finance agreements when a customer enters an IVA. "
                    "This creditor is expected to reject the IVA."
                ),
            )

    return _pass("PHASE4-VW-TERMINATION", "No VW Finance group HP creditors found.")


def _phase4_dmp_reject(c: dict, criteria_map: dict) -> RuleResult:
    """PHASE4-DMP-REJECT: Client in DMP and a creditor rejects DMP cases — hard block."""
    if not c["is_currently_in_dmp"]:
        return _pass("PHASE4-DMP-REJECT", "Client is not currently in a DMP.")

    for creditor in c["creditors"]:
        criteria = criteria_map.get(creditor["name"])
        if criteria and criteria.reject_if_in_dmp:
            return RuleResult(
                rule_id="PHASE4-DMP-REJECT", severity="hard_block", triggered=True,
                message=(
                    f"The customer is currently in a Debt Management Plan (DMP), and {creditor['name']} does not "
                    "accept IVA cases where the customer is currently in a DMP. This creditor is expected to reject "
                    "the IVA."
                ),
            )

    return _pass("PHASE4-DMP-REJECT", "No DMP-rejecting creditors found.")


def _phase4_county_council(c: dict) -> tuple:  # EXCEL_CRITERIA_REFERENCE.md — County Councils: district rules must be evaluated
    """PHASE4-COUNTY-COUNCIL: County council routing found — resolve district and evaluate its CouncilRule."""
    from debt_app.helpers import DEBT_TYPE_COUNCIL_TAX
    from debt_app.models import CountyCouncilRouting, CouncilRule, CountyCouncil  # EXCEL_CRITERIA_REFERENCE.md — County Councils: district rules must be evaluated

    council_tax_creditors = [
        cr for cr in c["creditors"]
        if cr["debt_type_normalised"] == DEBT_TYPE_COUNCIL_TAX
    ]
    if not council_tax_creditors:
        return [_pass("PHASE4-COUNTY-COUNCIL", "No council tax creditors.")], []  # EXCEL_CRITERIA_REFERENCE.md — County Councils: district rules must be evaluated

    routing_messages = []
    extra_results = []  # EXCEL_CRITERIA_REFERENCE.md — County Councils: district rules must be evaluated
    county_council_positions = []  # EXCEL_CRITERIA_REFERENCE.md — County Councils: district rules must be evaluated

    for cr in council_tax_creditors:
        county_name = cr["name"]
        routings = list(
            CountyCouncilRouting.objects.filter(county_name__iexact=county_name)
            .select_related("council_rule", "county")
        )
        if not routings:
            continue

        routing_messages.append(
            f"{county_name} County Council routes council tax through its districts: "
            + ", ".join(r.district_name for r in routings)
            + ". Each district's own position is evaluated separately below."
        )

        # The district vote below is calculated the normal way regardless — this
        # only surfaces a flag when the COUNTY ITSELF (not any of its districts)
        # has recorded criteria of its own (e.g. Buckinghamshire's accept/reject
        # note). Almost every county has none — they delegate council tax to
        # their districts entirely — so this fires rarely by design. It is
        # deliberately NOT auto-applied: the recorded criteria is often a
        # one-off historical case note rather than a clean general rule, so a
        # human should read it and decide rather than the engine guessing.
        county_obj = routings[0].county or CountyCouncil.objects.filter(
            county_name__iexact=county_name
        ).first()
        if county_obj is not None and county_obj.status != 'NO_CRITERIA':
            extra_results.append(RuleResult(
                rule_id="COUNTY-COUNCIL-OWN-CRITERIA",
                severity="flag",
                triggered=True,
                message=(
                    f"{county_obj.county_name} County Council has its own recorded position "
                    f"(status: {county_obj.get_status_display()}), separate from its districts. The caseworker must "
                    "review this before finalising the district-level decision below. "
                    f"Recorded notes: {county_obj.blocked_reason or 'none recorded'}."
                ),
            ))

        for routing in routings:  # EXCEL_CRITERIA_REFERENCE.md — County Councils: district rules must be evaluated
            district_name = routing.district_name
            # Prefer an explicit council_rule FK when set (pinned routing — no
            # fuzzy-match risk; required for reorganised unitaries and composite
            # rule names). Fall back to the tolerant name resolver otherwise:
            # district names in routing use abbreviations ("Wycombe DC", "Swale BC")
            # that rarely match CouncilRule.council_name exactly.
            matched_rule = routing.council_rule or _match_council_rule(district_name)
            if matched_rule is None:  # EXCEL_CRITERIA_REFERENCE.md — County Councils: district rules must be evaluated
                extra_results.append(RuleResult(  # EXCEL_CRITERIA_REFERENCE.md — County Councils: district rules must be evaluated
                    rule_id="COUNTY-COUNCIL-NO-DISTRICT-RULE",
                    severity="info",
                    triggered=False,
                    message=(
                        f"{district_name} (a district of {county_name}) has no recorded council tax position on "
                        "file. The caseworker must review this manually."
                    ),
                ))
                continue
            # Pass the canonical council name so _check_council_rules resolves the
            # same rule and the resulting position carries the canonical name.
            synthetic_cr = {**cr, "name": matched_rule.council_name}  # EXCEL_CRITERIA_REFERENCE.md — County Councils: district rules must be evaluated
            synthetic_case = {**c, "creditors": [synthetic_cr]}  # EXCEL_CRITERIA_REFERENCE.md — County Councils: district rules must be evaluated
            district_positions = _check_council_rules(synthetic_case)  # EXCEL_CRITERIA_REFERENCE.md — County Councils: district rules must be evaluated
            county_council_positions.extend(district_positions)  # EXCEL_CRITERIA_REFERENCE.md — County Councils: district rules must be evaluated

    rule_results = []
    if routing_messages:
        rule_results.append(RuleResult(
            rule_id="PHASE4-COUNTY-COUNCIL", severity="flag", triggered=True,
            message=" | ".join(routing_messages),
        ))
    else:
        rule_results.append(_pass("PHASE4-COUNTY-COUNCIL", "No county council routing applicable."))
    rule_results.extend(extra_results)  # EXCEL_CRITERIA_REFERENCE.md — County Councils: district rules must be evaluated

    return rule_results, county_council_positions  # EXCEL_CRITERIA_REFERENCE.md — County Councils: district rules must be evaluated


# ---------------------------------------------------------------------------
# Module 5 — Per-creditor and per-council evaluation
# ---------------------------------------------------------------------------

def _build_creditor_reason(criteria, cr: dict, case: dict) -> str:
    """
    Build a human-readable profile description for a creditor from seeded DB data
    plus the calculated balance/share for this specific case.  Stored as
    checks_description so _apply_representative_outcomes can append the rep body
    outcome idempotently.  Case-specific rule evaluation is shown in findings.
    """
    canonical = criteria.creditor_name
    rep = (criteria.representative or "NONE").upper()
    group = (criteria.parent_group or "").strip()
    status_label = _STATUS_NORMALISE.get(criteria.status, criteria.status)

    # --- Balance and share of total debt (case-specific) ---
    balance = float(cr.get("balance") or 0)
    total_debt = float(case.get("total_debt") or 0)
    if total_debt > 0 and balance > 0:
        share = (balance / total_debt) * 100
        balance_str = f"{canonical} is owed £{balance:,.0f}, which is {share:.1f}% of the customer's total debt."
    elif balance > 0:
        balance_str = f"{canonical} is owed £{balance:,.0f}."
    else:
        balance_str = ""

    _STANCE_PHRASE = {
        "ACCEPT":        "normally accepts an IVA",
        "REJECT":        "normally rejects an IVA",
        "WILL_CONSIDER": "reviews IVA proposals on a case-by-case basis",
        "DO_NOT_VOTE":   "does not vote on IVA proposals — it only submits a proof of debt",
        "UNKNOWN":       "has no recorded standing position on IVA proposals",
    }
    stance = _STANCE_PHRASE.get(status_label, f"has standing position {status_label}")

    # --- Profile header ---
    if rep in ("WATCH", "TIX", "EVOLVE", "EVERYDAY_LOANS"):
        rep_label = "an EVERYDAY LOANS" if rep == "EVERYDAY_LOANS" else f"a {rep}"
        group_str = f" (part of {group})" if group else ""
        header = f"{canonical} is represented by {rep_label} body{group_str}, which {stance}."
    else:
        group_str = f" (part of {group})" if group else ""
        header = f"{canonical}{group_str} {stance}."

    # --- Configured conditions (creditor policy, not case-specific evaluation) ---
    conditions = []

    if criteria.blocked_until_cleared:
        reason = (criteria.blocked_reason or "blocked until further notice").strip()
        conditions.append(f"This creditor is currently blocked — {reason}.")
    if criteria.reject_if_never_made_payment:
        conditions.append("It will reject if the customer has not made at least one payment.")
    if criteria.reject_if_ccj:
        conditions.append("It will reject if a CCJ appears on the customer's credit file.")
    if criteria.reject_if_aoe:
        conditions.append("It will reject if an attachment of earnings is in place.")
    if criteria.reject_if_second_iva:
        conditions.append("It will reject if the customer has had a previous IVA.")
    if criteria.reject_if_equity_exceeds_debt:
        conditions.append(
            "It will reject if the customer's property equity (at 85% loan-to-value) "
            "exceeds their total unsecured debt."
        )
    if criteria.reject_if_client_still_has_asset:
        conditions.append("It will reject if the financed asset is still in the customer's possession.")
    if criteria.account_age_months is not None:
        conditions.append(f"It will reject if the account is less than {criteria.account_age_months} months old.")
    if criteria.reject_if_majority_share_exceeds_pct is not None:
        conditions.append(
            "It will reject if this creditor holds more than "
            f"{criteria.reject_if_majority_share_exceeds_pct:.0f}% of the customer's total debt."
        )
    if criteria.reject_if_debt_repayable_within_months is not None:
        conditions.append(
            "It will reject if the debt could be repaid within "
            f"{criteria.reject_if_debt_repayable_within_months} months from disposable income."
        )
    if criteria.requires_arrangement_call_before_proposing:
        conditions.append("An arrangement call with this creditor is required before proposing.")
    if criteria.requires_grant_overpayment_only:
        conditions.append("This creditor only accepts grant overpayment debts.")
    if criteria.vehicle_arrears_repossession_months is not None:
        conditions.append(
            "It will reject if vehicle arrears exceed "
            f"{criteria.vehicle_arrears_repossession_months} months."
        )
    if criteria.fees_cap_percentage is not None:
        conditions.append(f"Insolvency practitioner fees are capped at {criteria.fees_cap_percentage:.0f}% for this creditor.")
    if criteria.fraud_claim_risk:
        conditions.append("There is a known fraud claim risk — the caseworker must review this before proposing.")
    if criteria.termination_risk_if_vehicle_on_finance:
        conditions.append("This creditor may terminate the agreement if the vehicle is on finance.")

    # --- Dividend / conditional voter ---
    dividend_parts = []
    if criteria.min_dividend_pence is not None:
        dividend_parts.append(f"The minimum dividend for this creditor is {criteria.min_dividend_pence}p in the pound.")
    if criteria.conditional_voter:
        cv = criteria.conditional_voter_min_dividend_pence
        if cv is not None:
            dividend_parts.append(f"This creditor only votes if the dividend offered is at least {cv}p in the pound.")
        else:
            dividend_parts.append("This creditor is a conditional voter.")

    # --- Notes from spreadsheet ---
    notes = (criteria.criteria_notes or criteria.dividend_notes or "").strip()

    # --- Compose ---
    parts = [header]
    if balance_str:
        parts.append(balance_str)
    parts.extend(conditions)
    parts.extend(dividend_parts)
    if notes:
        parts.append(f"Note: {notes}")

    return " ".join(parts)


def _build_council_reason(rule, cr: dict, case: dict, effective_status: str) -> str:
    """
    Build a human-readable profile description for a council creditor from seeded
    DB data plus the calculated balance/share for this case.  Describes the
    council's base position and configured conditional rejection policy.
    Case-specific evaluation is shown in findings.
    """
    name = rule.council_name
    base_status = (rule.status or "UNKNOWN").upper()

    _STATUS_DESC = {
        "REJECT":            "normally rejects IVA proposals",
        "ACCEPT":            "normally accepts IVA proposals",
        "DO_NOT_VOTE":       "does not vote on IVA proposals — it only submits a proof of debt",
        "WILL_CONSIDER":     "reviews IVA proposals on a case-by-case basis",
        "CONDITIONAL_VOTER": "votes on IVA proposals based on the dividend offered",
    }
    base_desc = _STATUS_DESC.get(base_status, f"has base status: {base_status}")

    # --- Balance and share of total debt (case-specific) ---
    balance = float(cr.get("balance") or 0)
    total_debt = float(case.get("total_debt") or 0)
    if total_debt > 0 and balance > 0:
        share = (balance / total_debt) * 100
        balance_str = f"{name} is owed £{balance:,.0f}, which is {share:.1f}% of the customer's total debt."
    elif balance > 0:
        balance_str = f"{name} is owed £{balance:,.0f}."
    else:
        balance_str = ""

    # --- Configured conditional rejection rules (policy) ---
    conditions = []
    if rule.reject_if_employed:
        conditions.append("It will reject if the customer is employed.")
    if rule.reject_if_unemployed_and_homeowner:
        conditions.append("It will reject if the customer is unemployed and owns their property.")
    if rule.reject_if_benefits_only:
        conditions.append("It will reject if the customer's income is from benefits only.")
    if rule.reject_if_any_benefits:
        conditions.append("It will reject if the customer receives any benefits.")
    if rule.reject_if_previous_iva:
        conditions.append("It will reject if the customer has had a previous IVA.")
    if rule.reject_if_dro_criteria_met:
        conditions.append("It will reject if the customer meets the Debt Relief Order criteria.")
    if rule.reject_if_aoe_in_place:
        conditions.append("It will reject if an attachment of earnings is in place.")
    if rule.reject_if_sole:
        conditions.append("It will reject sole IVA applications.")
    if rule.reject_if_joint_one_party_only:
        conditions.append("It will reject if a joint debt is included in a sole IVA.")
    if rule.reject_if_joint_both_parties:
        conditions.append("It will reject joint IVA proposals.")
    if rule.reject_if_joint_one_employed:
        conditions.append("It will reject joint cases where one party is employed.")

    # --- Informational flags ---
    info_parts = []
    if rule.do_not_chase:
        info_parts.append("Do not contact this council proactively — it may reject the case if chased.")
    if rule.include_current_year_ct:
        info_parts.append(
            "Current-year council tax should be included in the proposal even if it is not yet in arrears."
        )
    if rule.min_dividend_pence is not None:
        info_parts.append(f"The minimum dividend for this council is {rule.min_dividend_pence}p in the pound.")

    # blocked_reason stores raw notes from the Excel sheet (operational instructions,
    # email contacts, submission requirements etc.) — always surface them.
    raw_notes = (rule.blocked_reason or "").strip()

    # --- Compose ---
    parts = [f"{name} {base_desc}."]
    if balance_str:
        parts.append(balance_str)
    parts.extend(conditions)
    parts.extend(info_parts)
    if raw_notes:
        parts.append(f"Caseworker notes: {raw_notes}")

    return " ".join(parts)


def _check_creditor_individual(case: dict, estimated_dividend_pence: Optional[int] = None) -> list[dict]:
    """
    Evaluate each non-council creditor against its CreditorCriteria DB row.

    Returns one position dict per creditor (including UNKNOWN when no DB row
    matches).  Council-type debts are skipped here — handled by
    _check_council_rules().
    """
    from debt_app.helpers import (
        DEBT_TYPE_COUNCIL_TAX, DEBT_TYPE_PCN, DEBT_TYPE_HOUSING_BENEFIT,
        get_creditor_by_trading_name, fuzzy_lookup_creditor,
    )
    from debt_app.models import CreditorCriteria, CreditorResolutionMiss

    _COUNCIL_TYPES = frozenset({DEBT_TYPE_COUNCIL_TAX, DEBT_TYPE_PCN, DEBT_TYPE_HOUSING_BENEFIT})

    if estimated_dividend_pence is None:
        estimated_dividend_pence = calculate_estimated_dividend_pence(case)

    # Resolve council name set — use pre-loaded value from assess_case() when available
    # (one DB query for the whole assessment); fall back to loading here for standalone calls.
    _council_names_lower = case.get("_council_rule_names_lower")
    if _council_names_lower is None:
        from debt_app.models import CouncilRule as _CR
        _council_names_lower = frozenset(
            v.lower()
            for n in _CR.objects.values_list("council_name", flat=True)
            for v in _ampersand_variants(n)
        )

    # Pre-load all active creditor names once for fuzzy matching
    _all_creditor_names = list(
        CreditorCriteria.objects.filter(is_active=True)
        .values_list("creditor_name", flat=True)
    )

    positions = []
    for cr in case.get("creditors", []):
        # Skip council-type debts — handled entirely by _check_council_rules().
        # Also skip creditors whose name matches a CouncilRule entry even when Aryza
        # has tagged them with a generic debt type (e.g. GENERAL instead of council_tax).
        if cr["debt_type_normalised"] in _COUNCIL_TYPES:
            continue
        if cr.get("name", "").lower() in _council_names_lower:
            continue

        name = cr.get("name", "Unknown Creditor")
        original_name = cr.get("original_name") or name
        balance = cr["crm_balance"]

        # Resolve via alias map first
        normalised_input = normalise_creditor_name(name)
        resolved_name = CREDITOR_ALIAS_MAP.get(normalised_input, name)

        try:
            criteria = get_creditor_by_trading_name(resolved_name,
                                                    all_names=_all_creditor_names)
        except CreditorCriteria.DoesNotExist:
            # PART 2: Log the miss (fire-and-forget)
            try:
                CreditorResolutionMiss.objects.create(
                    raw_name=name,
                    normalised_name=normalise_creditor_name(name) or name,
                    case_reference=case.get("aryza_reference", ""),
                    client_name=case.get("client_name", ""),
                    balance=cr.get("crm_balance"),
                )
            except Exception as e:
                logger.error(f"Failed to log CreditorResolutionMiss for {name}: {e}")

            positions.append({
                "creditor_name": original_name,
                "display_name": None,
                "original_aryza_name": None,
                "resolved_canonical_name": original_name,
                "representative": "NONE",
                "effective_status": "UNKNOWN",
                "findings": [{"code": "CREDITOR-UNKNOWN", "reason": "This creditor has no matching record in our database."}],
                "reason": "This creditor has no matching record in our database.",
                "rule_ids": ["CREDITOR-UNKNOWN"],
                "balance": balance,
                "is_secured": bool(cr.get("is_secured", False)),
                "debt_type_normalised": cr.get("debt_type_normalised"),
                "_creditor_idx": cr.get("_idx"),
                "cr_raw_name": cr.get("cr_raw_name"),
                "type_code": cr.get("type_code"),
                "cr_balance": cr.get("cr_balance"),
                "cr_account_status": cr.get("cr_account_status"),
                "cr_account_status_subjective": cr.get("cr_account_status_subjective"),
                "cr_missed_payments_3m": cr.get("cr_missed_payments_3m"),
            })
            continue

        findings = []
        reject_level = False

        min_div = criteria.min_dividend_pence
        if min_div is not None and min_div > 0:
            if estimated_dividend_pence >= min_div:
                findings.append({
                    "code": "DIVIDEND-CHECK-PASS",
                    "reason": f"Minimum dividend met: {estimated_dividend_pence}p/£ ≥ {min_div}p/£",
                    "severity": "pass",
                })
            else:
                findings.append({
                    "code": "DIVIDEND-CHECK-FAIL",
                    "reason": f"Minimum dividend NOT met: {estimated_dividend_pence}p/£ < {min_div}p/£",
                    "severity": "flag",
                })

        if criteria.blocked_until_cleared:
            findings.append({
                "code": "CREDITOR-BLOCKED",
                "reason": criteria.blocked_reason or "Blocked until further notice — contact Debra",
            })
            reject_level = True

        if criteria.reject_if_never_made_payment:
            _fpm = cr.get("first_payment_made")
            if _fpm is False:
                findings.append({"code": "CREDITOR-NO-PAYMENT", "reason": f"{name}: no payment ever made — creditor requires at least one payment before proposing"})
                reject_level = True
            elif _fpm is None:
                findings.append({"code": "CREDITOR-PAYMENT-UNVERIFIED", "reason": f"{name} rejects if no payment has ever been made — confirm with client that at least one payment has been made before proposing", "severity": "flag"})

        arrears_threshold = criteria.vehicle_arrears_repossession_months
        arrears_months = cr.get("vehicle_arrears_months")
        if arrears_threshold is not None:
            if arrears_months is not None and arrears_months >= arrears_threshold:
                findings.append({"code": "CREDITOR-REPOSSESSION-RISK", "reason": f"{name}: vehicle is {arrears_months} month(s) in arrears — meets or exceeds {arrears_threshold}-month repossession threshold"})
            elif arrears_months is not None:
                findings.append({"code": "CREDITOR-ARREARS-OK", "reason": f"{name}: vehicle {arrears_months} month(s) in arrears — below {arrears_threshold}-month repossession threshold", "severity": "pass"})
            else:
                findings.append({"code": "CREDITOR-ARREARS-UNVERIFIED", "reason": f"{name} may repossess vehicle if arrears reach {arrears_threshold} month(s) — confirm current arrears status before proposing", "severity": "flag"})

        # General Creditor: financed asset must be returned before proposing —
        # otherwise the creditor rejects (e.g. Advantage Finance "car needs to
        # have gone back"). Own branch (not chained to the arrears flag above)
        # and a REJECT, not just a flag.
        if criteria.reject_if_client_still_has_asset:
            _asset = cr.get("client_still_has_asset_in_possession")
            if _asset is True:
                findings.append({"code": "CREDITOR-ASSET-NOT-RETURNED-REJECT", "reason": f"{name}: client still holds the financed asset — creditor requires it be returned before proposing"})
                reject_level = True
            elif _asset is None:
                findings.append({"code": "CREDITOR-ASSET-STATUS-UNVERIFIED", "reason": f"{name} requires the financed asset to have been returned — confirm with client whether asset is still in their possession before proposing", "severity": "flag"})

        if criteria.requires_arrangement_call_before_proposing and not cr.get("arrangement_confirmed_before_proposing", False):
            findings.append({
                "code": "CREDITOR-ARRANGEMENT-CALL",
                "reason": "Pre-proposal arrangement call required but not yet confirmed",
            })

        if criteria.fees_cap_percentage is not None:
            findings.append({
                "code": "CREDITOR-FEES-CAP",
                "reason": f"IP fees capped at {criteria.fees_cap_percentage}% by this creditor",
            })

        # EXCEL_CRITERIA_REFERENCE.md — General Creditor: majority share block
        if criteria.reject_if_majority_share_exceeds_pct is not None:
            total_unsecured = case["total_debt"]
            if total_unsecured > 0:
                creditor_share_pct = (cr["balance"] / total_unsecured) * 100
                if creditor_share_pct > criteria.reject_if_majority_share_exceeds_pct:
                    findings.append({
                        "code": "CREDITOR-MAJORITY-SHARE-EXCEEDED",
                        "reason": (
                            f"{name} holds {creditor_share_pct:.1f}% of total debt — "
                            f"exceeds creditor's {criteria.reject_if_majority_share_exceeds_pct}% limit"
                        ),
                    })
                    reject_level = True

        # EXCEL_CRITERIA_REFERENCE.md — General Creditor: second IVA reject
        if criteria.reject_if_second_iva and case.get("previous_iva", False):
            findings.append({
                "code": "CREDITOR-SECOND-IVA-REJECT",
                "reason": f"{name} rejects clients with a prior IVA",
            })
            reject_level = True

        # General Creditor: CCJ reject — has_ccj is sourced from the credit report
        # (Experian Public Information / Aryza "CCJs and Insolvencies") by
        # _enrich_from_credit_report.
        if criteria.reject_if_ccj and case.get("has_ccj", False):
            findings.append({
                "code": "CREDITOR-CCJ-REJECT",
                "reason": f"{name} rejects clients with a County Court Judgment on their credit file",
            })
            reject_level = True
        elif criteria.reject_if_ccj and case.get("credit_report_status", "absent") != "present":
            # No confirmed credit report — cannot verify CCJ status; flag for upload.
            findings.append({
                "code": "CREDITOR-CCJ-REPORT-REQUIRED",
                "reason": (
                    f"{name} rejects if CCJ present — upload a credit report to verify "
                    "CCJ status before proceeding"
                ),
                "severity": "flag",
            })

        # General Creditor: Attachment of Earnings reject
        if criteria.reject_if_aoe and case.get("aoe_in_place", False):
            findings.append({
                "code": "CREDITOR-AOE-REJECT",
                "reason": f"{name} rejects clients with an Attachment of Earnings order already in place",
            })
            reject_level = True

        # General Creditor: I&E match
        # ie_matches_loan_application is parsed per-creditor at line 380.
        if criteria.reject_if_ie_doesnt_match_application:
            ie_status = cr.get("ie_matches_loan_application")
            if ie_status is False:
                findings.append({
                    "code": "CREDITOR-IE-MISMATCH-REJECT",
                    "reason": (
                        f"{name}: income and expenditure does not match "
                        "the original loan application — creditor rejects"
                    ),
                })
                reject_level = True
            elif ie_status is None:
                findings.append({
                    "code": "CREDITOR-IE-MATCH-UNVERIFIED",
                    "reason": (
                        f"{name}: requires I&E to match loan application "
                        "— not confirmed in payload, verify before proposing"
                    ),
                    "severity": "flag",
                })
            # ie_status is True → criteria satisfied, no finding

        # General Creditor: minimum loan age — creditor rejects loans younger than
        # N months (e.g. "REJECT IF LOAN LESS THAN 6 MONTHS OLD"). The client's loan
        # age is sourced from the credit report (account Start Date) and attached to
        # the creditor by _enrich_from_credit_report. account_age_months is None when
        # it could not be verified (no credit report, or no matched account) — in that
        # case FLAG for caseworker confirmation, never treat unknown as 0 (which would
        # wrongly reject). Only a verified age below the minimum is a REJECT.
        if criteria.account_age_months is not None:
            client_loan_age = cr.get("account_age_months")
            if client_loan_age is None:
                findings.append({
                    "code": "CREDITOR-LOAN-AGE-UNVERIFIED",
                    "reason": (
                        f"{name} rejects loans under {criteria.account_age_months} month(s) old; "
                        "loan age could not be verified from the credit report — confirm before proposing"
                    ),
                })
            elif client_loan_age < criteria.account_age_months:
                findings.append({
                    "code": "CREDITOR-LOAN-TOO-RECENT-REJECT",
                    "reason": (
                        f"{name}: loan is {client_loan_age} month(s) old — under the creditor's "
                        f"{criteria.account_age_months}-month minimum"
                    ),
                })
                reject_level = True

        # General Creditor: recent spend rejection
        # Uses _recent_transactions_matching with creditor name and
        # trading names as keywords. Any match within N months = reject.
        if criteria.reject_if_recent_spend_months is not None:
            _months = criteria.reject_if_recent_spend_months
            _gold_tx = case.get("gold_transactions") or []
            _keywords = [name] + list(criteria.trading_names or [])
            if _gold_tx:
                _recent = _recent_transactions_matching(
                    _gold_tx,
                    _keywords,
                    _months * 30,
                    reference=case.get("assessment_date"),
                )
                if _recent:
                    findings.append({
                        "code": "CREDITOR-RECENT-SPEND-REJECT",
                        "reason": (
                            f"{name}: {len(_recent)} transaction(s) found "
                            f"in the last {_months} month(s) — creditor "
                            "rejects recent spend on account"
                        ),
                    })
                    reject_level = True
            else:
                # No gold transactions — fall back to credit report recent_spending signal
                _cr_recent = cr.get("recent_spending")  # bool | None — set by _enrich_from_credit_report
                if _cr_recent is True:
                    # Credit report confirms recent spend on this account
                    findings.append({
                        "code": "CREDITOR-RECENT-SPEND-REJECT",
                        "reason": (
                            f"{name} rejects clients with spend in the last "
                            f"{_months} month(s) — recent activity detected on credit report."
                        ),
                        "severity": "flag",
                    })
                    reject_level = True
                elif _cr_recent is False:
                    # Credit report confirms no recent spend — condition satisfied
                    findings.append({
                        "code": "CREDITOR-RECENT-SPEND-PASS",
                        "reason": (
                            f"{name}: no recent spend detected on credit report "
                            f"within the {_months}-month window — condition satisfied."
                        ),
                        "severity": "pass",
                    })
                else:
                    # Neither gold transactions nor credit report — genuinely unverified
                    findings.append({
                        "code": "CREDITOR-RECENT-SPEND-UNVERIFIED",
                        "reason": (
                            f"{name} rejects clients with spend in the last "
                            f"{_months} month(s) — upload a credit report or open banking "
                            f"data to verify before proposing."
                        ),
                        "severity": "flag",
                    })

        # EXCEL_CRITERIA_REFERENCE.md — General Creditor: per-creditor equity block (85% LTV)
        if criteria.reject_if_equity_exceeds_debt and case.get("has_property", False):
            property_value = case["property_value"]
            if property_value is not None:
                available_equity = (_parse_amount(property_value) * 0.85) - case["mortgage_balance"]
                if available_equity > case["total_debt"]:
                    findings.append({
                        "code": "CREDITOR-EQUITY-EXCEEDS-DEBT",
                        "reason": f"{name}: available equity at 85% LTV exceeds total unsecured debt",
                    })
                    reject_level = True

        # EXCEL_CRITERIA_REFERENCE.md — General Creditor: grant overpayment only
        if criteria.requires_grant_overpayment_only and not cr.get("is_grant_overpayment", False):
            findings.append({
                "code": "CREDITOR-NOT-GRANT-OVERPAYMENT",
                "reason": (
                    f"{name} only participates when debt is a grant overpayment — "
                    f"debt type is {cr['creditor_type']}"
                ),
            })
            reject_level = True

        # EXCEL_CRITERIA_REFERENCE.md — General Creditor: fraud claim risk flag
        if criteria.fraud_claim_risk:
            findings.append({
                "code": "CREDITOR-FRAUD-CLAIM-RISK",
                "reason": f"{name}: fraud claim risk noted — caseworker review required before proposing",
            })

        # For representative-body creditors (WATCH/TIX/EVOLVE) the voter status is
        # determined entirely by _apply_representative_outcomes from the rules that
        # fired — criteria.status is an invisible DB default (always ACCEPT) and must
        # not be used. For non-representative creditors (NONE) criteria.status IS the
        # explicit position set by the seeding team (e.g. WILL_CONSIDER, DO_NOT_VOTE).
        _rep = (criteria.representative or "NONE").upper()
        if reject_level:
            effective_status = "REJECT"
        elif _rep in ("WATCH", "TIX", "EVOLVE", "EVERYDAY_LOANS"):
            effective_status = "PENDING_REP_OUTCOME"  # overwritten by _apply_representative_outcomes
        else:
            effective_status = _STATUS_NORMALISE.get(criteria.status, criteria.status)

        canonical = criteria.creditor_name

        # Build a per-creditor audit description covering every check the engine
        # ran and its outcome.  Stored as checks_description so
        # _apply_representative_outcomes can append the rep body result without
        # re-accessing the criteria object — making the function idempotent on
        # a second call from the view layer.
        # Surface unmappable criteria_notes as a caseworker warning.
        # Fires when criteria_notes contains conditions not covered by structured fields.
        # If min_dividend_pence is set, strip any pure dividend-minimum text from the
        # notes before checking — that condition is already evaluated automatically.
        _manual_notes = (criteria.criteria_notes or "").strip()
        if criteria.min_dividend_pence is not None and _manual_notes:
            # Strip "Note:" / "Note :" labels immediately before the dividend sentence
            _manual_notes = re.sub(
                r'(?i)(?:note\s*:\s*)?require[sd]?\s+(?:a\s+)?minimum\s+dividend\s+of\s+\d+\s*p(?:ence)?'
                r'(?:\s*/\s*[£$])?[^.;]*[.;]?\s*',
                '', _manual_notes,
            ).strip().strip('.,;-').strip()
            # Also strip any dangling "Note:" / "Note :" that was the sole remaining token
            _manual_notes = re.sub(r'(?i)^note\s*:\s*$', '', _manual_notes).strip()
        if _manual_notes:
            findings.append({
                "code": "CREDITOR-MANUAL-CHECK-REQUIRED",
                "reason": (
                    f"{name}: additional criteria must be checked "
                    f"manually before proposing — "
                    f"{_manual_notes}"
                ),
                "severity": "flag",
            })

        # --- Pass findings emission ---
        existing_codes = {f["code"] for f in findings}

        PASS_CHECKS = [
            (
                criteria.reject_if_ccj,
                "CREDITOR-CCJ-REJECT", "CREDITOR-CCJ-REPORT-REQUIRED",
                "CREDITOR-CCJ-PASS",
                f"{criteria.creditor_name}: no CCJ on credit file — condition satisfied."
            ),
            (
                criteria.reject_if_aoe,
                "CREDITOR-AOE-REJECT", None,
                "CREDITOR-AOE-PASS",
                f"{criteria.creditor_name}: no attachment of earnings in place — condition satisfied."
            ),
            (
                criteria.reject_if_never_made_payment,
                "CREDITOR-NO-PAYMENT", None,
                "CREDITOR-NO-PAYMENT-PASS",
                f"{criteria.creditor_name}: first payment confirmed — condition satisfied."
            ),
            (
                criteria.reject_if_second_iva,
                "CREDITOR-SECOND-IVA-REJECT", None,
                "CREDITOR-SECOND-IVA-PASS",
                f"{criteria.creditor_name}: no previous IVA — condition satisfied."
            ),
            (
                criteria.reject_if_equity_exceeds_debt,
                "CREDITOR-EQUITY-EXCEEDS-DEBT", None,
                "CREDITOR-EQUITY-PASS",
                f"{criteria.creditor_name}: equity does not exceed total debt — condition satisfied."
            ),
            (
                criteria.reject_if_majority_share_exceeds_pct is not None,
                "CREDITOR-MAJORITY-SHARE-EXCEEDED", None,
                "CREDITOR-MAJORITY-SHARE-PASS",
                f"{criteria.creditor_name}: creditor share within permitted threshold — condition satisfied."
            ),
        ]

        for (active, fail_code, flag_code, pass_code, pass_reason) in PASS_CHECKS:
            if not active:
                continue
            blocking_codes = {fail_code, flag_code} - {None}
            if not blocking_codes.intersection(existing_codes):
                findings.append({
                    "code": pass_code,
                    "reason": pass_reason,
                    "severity": "pass"
                })

        # account_age_months — only pass if neither reject nor unverified fired
        if criteria.account_age_months is not None:
            if "CREDITOR-LOAN-TOO-RECENT-REJECT" not in existing_codes \
                    and "CREDITOR-LOAN-AGE-UNVERIFIED" not in existing_codes:
                findings.append({
                    "code": "CREDITOR-LOAN-AGE-PASS",
                    "reason": f"{criteria.creditor_name}: account age meets the {criteria.account_age_months}-month minimum — condition satisfied.",
                    "severity": "pass"
                })

        # reject_if_recent_spend_months — only pass if neither reject nor unverified fired
        if criteria.reject_if_recent_spend_months is not None:
            if "CREDITOR-RECENT-SPEND-REJECT" not in existing_codes \
                    and "CREDITOR-RECENT-SPEND-UNVERIFIED" not in existing_codes:
                findings.append({
                    "code": "CREDITOR-RECENT-SPEND-PASS",
                    "reason": f"{criteria.creditor_name}: no recent spend within the restricted {criteria.reject_if_recent_spend_months}-month window — condition satisfied.",
                    "severity": "pass"
                })

        _checks_description = _build_creditor_reason(criteria, cr, case)

        positions.append({
            "criteria_id": criteria.id,
            "creditor_name": canonical,
            "display_name": None,  # UI will fallback to creditor_name (canonical)
            "original_aryza_name": original_name if original_name != canonical else None,
            "resolved_canonical_name": canonical,
            "representative": criteria.representative or "NONE",
            "effective_status": effective_status,
            "findings": findings,
            "checks_description": _checks_description,
            "reason": _checks_description,
            "rule_ids": [f["code"] for f in findings],
            "balance": balance,
            "criteria_notes": criteria.criteria_notes or "",
            "dividend_notes": criteria.dividend_notes or "",
            "is_secured": bool(cr.get("is_secured", False)),
            "debt_type_normalised": cr.get("debt_type_normalised"),
            "_creditor_idx": cr.get("_idx"),
            "cr_raw_name": cr.get("cr_raw_name"),
            "type_code": cr.get("type_code"),
            "cr_balance": cr.get("cr_balance"),
            "cr_account_status": cr.get("cr_account_status"),
            "cr_account_status_subjective": cr.get("cr_account_status_subjective"),
            "cr_missed_payments_3m": cr.get("cr_missed_payments_3m"),
        })

    return positions


def _ampersand_variants(name: str) -> list[str]:
    """Return the name plus '&'<->'and' variants for tolerant council matching.

    Aryza supplies names like 'Brighton & Hove City Council' while the
    CouncilRule table stores 'Brighton and Hove city Council' — without this the
    exact/icontains lookup misses and the council silently drops out of the vote.
    """
    variants = [name]
    for v in (re.sub(r"\s*&\s*", " and ", name), re.sub(r"\s+and\s+", " & ", name)):
        v = re.sub(r"\s+", " ", v).strip()
        if v and v not in variants:
            variants.append(v)
    return variants


# Generic / ambiguous tokens that must never resolve to a council on their own.
# A creditor literally named "OTHER" must NOT match "R-other- District Council".
_COUNCIL_MATCH_STOPWORDS = frozenset({
    "other", "misc", "miscellaneous", "unknown", "general", "none", "n a",
    "various", "sundry", "council", "tax", "city", "county", "borough",
    "district", "metropolitan", "rent", "arrears", "",
})

# Council-type/suffix words removed during normalisation so abbreviations and
# qualifiers collapse to the discriminating part of the name.
_COUNCIL_SUFFIX_WORDS = (
    "metropolitan", "borough", "district", "city", "county", "council",
    "mbc", "rbc", "dc", "bc", "cc",
)

_COUNCIL_FUZZY_CUTOFF = 92      # last-resort fuzzy: high bar
_COUNCIL_FUZZY_MARGIN = 6       # best must beat runner-up by this much (no near-ties)


def _normalise_council_name(s: str) -> str:
    """Reduce a council name to its discriminating core for exact comparison.

    Drops parenthetical qualifiers ('(Grimsby)'), trailing '/ ...' notes, '&'/'and',
    and council-type suffix words, so e.g. both 'North East Lincolnshire Council' and
    'North East Lincolnshire Council (Grimsby)' normalise to 'north east lincolnshire'
    — while 'North Lincolnshire Council' stays distinct ('north lincolnshire').
    """
    if not s:
        return ""
    s = s.lower()
    s = re.sub(r"\([^)]*\)", " ", s)        # drop parenthetical qualifiers
    s = s.split("/")[0]                       # drop trailing "/ ..." notes
    s = re.sub(r"[^a-z0-9 &]", " ", s)        # keep alnum / space / &
    s = s.replace("&", " and ")
    s = re.sub(r"\band\b", " ", s)            # treat 'and'/'&' as a separator only
    for w in _COUNCIL_SUFFIX_WORDS:
        s = re.sub(rf"\b{w}\b", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _match_council_rule(name: str):
    """Resolve a council name to a CouncilRule. Returns the rule or None.

    Strategy (precise, no substring guessing):
      1. Exact `iexact` match on '&'/'and' variants (handles the canonical DB name).
      2. Normalised-exact match: compare discriminating cores (parentheticals,
         '/'-notes and suffix words stripped). Must be UNIQUE.
      3. Strict fuzzy last resort: token_sort_ratio on normalised forms, high cutoff
         AND a clear margin over the runner-up.

    This prevents false positives such as the literal creditor name "OTHER" being
    substring-matched to "Rother District Council" (the old `icontains` + `.first()`
    behaviour that mis-classified rent-arrears debts as council tax), and the
    genuine ambiguity between 'North Lincolnshire' and 'North East Lincolnshire'.
    """
    from debt_app.models import CouncilRule
    from rapidfuzz import fuzz

    candidates = _ampersand_variants(name)
    for cand in candidates:
        try:
            return CouncilRule.objects.get(council_name__iexact=cand)
        except CouncilRule.DoesNotExist:
            continue
        except CouncilRule.MultipleObjectsReturned:
            # Duplicate rows differing only by case (data-entry dupes). Prefer the
            # authoritative source (lowest source_priority), then most recently
            # reviewed, rather than crashing the whole assessment.
            rows = list(
                CouncilRule.objects.filter(council_name__iexact=cand).order_by(
                    "source_priority", "-last_reviewed"
                )
            )
            return rows[0]

    council_names = list(CouncilRule.objects.values_list("council_name", flat=True))
    if not council_names:
        return None

    target = _normalise_council_name(name)
    if not target or target in _COUNCIL_MATCH_STOPWORDS or len(target) < 4:
        return None

    norm_map = [(cn, _normalise_council_name(cn)) for cn in council_names]

    # 2. Normalised-exact, unique.
    exact = [cn for cn, norm in norm_map if norm and norm == target]
    if len(exact) == 1:
        try:
            return CouncilRule.objects.get(council_name=exact[0])
        except CouncilRule.DoesNotExist:
            pass
    if len(exact) > 1:
        return None  # ambiguous — refuse to guess

    # 3. Strict fuzzy last resort over normalised forms.
    scored = sorted(
        ((fuzz.token_sort_ratio(target, norm), cn) for cn, norm in norm_map if norm),
        key=lambda t: t[0],
        reverse=True,
    )
    if scored:
        best_score, best_name = scored[0]
        second_score = scored[1][0] if len(scored) > 1 else 0
        if best_score >= _COUNCIL_FUZZY_CUTOFF and (best_score - second_score) >= _COUNCIL_FUZZY_MARGIN:
            try:
                return CouncilRule.objects.get(council_name=best_name)
            except CouncilRule.DoesNotExist:
                pass
    return None


def _check_council_rules(case: dict) -> list[dict]:
    """
    Evaluate each council-type creditor against its CouncilRule DB row.

    Debt-type-specific votes (DebtTypeCouncilVote) take precedence over the
    council's base status.  County councils with no CouncilRule entry are
    silently skipped (they're routing-only via CountyCouncilRouting).
    """
    from debt_app.helpers import DEBT_TYPE_COUNCIL_TAX, DEBT_TYPE_PCN, DEBT_TYPE_HOUSING_BENEFIT
    from debt_app.models import CouncilRule, DebtTypeCouncilVote

    _COUNCIL_TYPES = frozenset({DEBT_TYPE_COUNCIL_TAX, DEBT_TYPE_PCN, DEBT_TYPE_HOUSING_BENEFIT})
    _DTCV_MAP = {
        DEBT_TYPE_COUNCIL_TAX: "COUNCIL_TAX",
        DEBT_TYPE_PCN: "PCN",
        DEBT_TYPE_HOUSING_BENEFIT: "HOUSING_BENEFIT",
    }

    # Resolve council name set — use pre-loaded value from assess_case() when available;
    # fall back to loading here for standalone calls (e.g. _phase4_county_council).
    # synthetic_case = {**c, ...} in _phase4_county_council carries _council_rule_names_lower
    # automatically, so the DB is only hit once per assessment in the normal path.
    _council_names_lower = case.get("_council_rule_names_lower")
    if _council_names_lower is None:
        _council_names_lower = frozenset(
            v.lower()
            for n in CouncilRule.objects.values_list("council_name", flat=True)
            for v in _ampersand_variants(n)
        )

    positions = []
    for cr in case.get("creditors", []):
        # Include if debt type is a recognised council type OR if the creditor's name
        # matches a CouncilRule entry — the latter catches councils whose debt_type
        # arrives from Aryza as GENERAL rather than council_tax (e.g. Mansfield District
        # Council). Without this, those councils were silently routed through
        # _check_creditor_individual() and their council-specific rejection rules never ran.
        is_council_type = cr["debt_type_normalised"] in _COUNCIL_TYPES
        is_council_name = cr.get("name", "").lower() in _council_names_lower
        if not (is_council_type or is_council_name):
            continue

        name = cr["name"]
        rule = _match_council_rule(name)
        if rule is None:
            continue

        dtcv_key = _DTCV_MAP.get(cr["debt_type_normalised"])
        base_status = rule.status
        if dtcv_key:
            try:
                dtcv = DebtTypeCouncilVote.objects.get(council=rule, debt_type=dtcv_key)
                base_status = dtcv.status
            except DebtTypeCouncilVote.DoesNotExist:
                pass

        findings = []
        reject_override = False

        if rule.do_not_chase:
            findings.append({
                "code": "INFO-DO-NOT-CHASE",
                "reason": "Do not chase — council will reject if chased",
            })

        if rule.include_current_year_ct:
            findings.append({
                "code": "INFO-INCLUDE-CURRENT-YEAR-CT",
                "reason": "Include current-year council tax in proposal even if not yet formally in arrears",
            })

        if rule.min_dividend_pence is not None:
            findings.append({
                "code": "INFO-MIN-DIVIDEND",
                "reason": f"Minimum dividend: {rule.min_dividend_pence}p/£1",
            })

        if rule.reject_if_sole:
            is_joint_debt = cr.get("is_joint", False)
            has_partner = case.get("has_partner_on_case", False)
            if not is_joint_debt and not has_partner:
                findings.append({"code": "COUNCIL-SOLE-REJECT", "reason": "Sole IVA — council rejects sole applications"})
                reject_override = True
            elif is_joint_debt and not has_partner:
                findings.append({"code": "COUNCIL-SOLE-POD-ONLY", "reason": "Joint debt, sole IVA — council submits POD only"})

        if rule.reject_if_employed and case.get("is_employed", False):
            findings.append({"code": "COUNCIL-TRIGGER-EMPLOYED", "reason": "Client employed — council can apply AOE; will reject"})
            reject_override = True

        if rule.reject_if_benefits_only and case.get("income_is_benefits_only", False):
            findings.append({"code": "COUNCIL-TRIGGER-BENEFITS-ONLY", "reason": "Benefits-only income — council rejects"})
            reject_override = True

        if rule.reject_if_any_benefits and case.get("receives_any_benefits", False):
            findings.append({"code": "COUNCIL-TRIGGER-ANY-BENEFITS", "reason": "Client receives benefits — council rejects"})
            reject_override = True

        if rule.reject_if_previous_iva and case.get("previous_iva", False):
            findings.append({"code": "COUNCIL-TRIGGER-PREVIOUS-IVA", "reason": "Previous IVA on record — council rejects"})
            reject_override = True

        if rule.reject_if_dro_criteria_met and case.get("dro_criteria_met", False):
            findings.append({"code": "COUNCIL-TRIGGER-DRO-CRITERIA", "reason": "DRO criteria met — council rejects"})
            reject_override = True

        if rule.reject_if_aoe_in_place and case.get("aoe_in_place", False):
            findings.append({"code": "COUNCIL-TRIGGER-AOE-IN-PLACE", "reason": "AOE already in place — council rejects"})
            reject_override = True

        if rule.reject_if_joint_one_employed and case.get("is_joint_case", False) and case.get("is_employed", False):
            findings.append({"code": "COUNCIL-TRIGGER-JOINT-ONE-EMPLOYED", "reason": "Joint case, one party employed — council rejects"})
            reject_override = True

        # EXCEL_CRITERIA_REFERENCE.md — Sheet: Councils, reject flags
        if (
            rule.reject_if_unemployed_and_homeowner
            and not case.get("is_employed", False)
            and case.get("has_property", False)
        ):
            findings.append({"code": "COUNCIL-TRIGGER-UNEMPLOYED-HOMEOWNER", "reason": "Client unemployed and homeowner — council rejects"})
            reject_override = True

        # EXCEL_CRITERIA_REFERENCE.md — Sheet: Councils, reject flags
        if (
            rule.reject_if_joint_one_party_only
            and not case.get("is_joint_case", False)
            and cr.get("is_joint", False)
        ):
            findings.append({"code": "COUNCIL-TRIGGER-JOINT-ONE-PARTY-ONLY", "reason": "Joint debt but only one party in IVA — council rejects"})
            reject_override = True

        # EXCEL_CRITERIA_REFERENCE.md — Sheet: Councils, reject flags
        if rule.reject_if_joint_both_parties and case.get("is_joint_case", False):
            findings.append({"code": "COUNCIL-TRIGGER-JOINT-BOTH-PARTIES", "reason": "Joint IVA proposed — council rejects"})
            reject_override = True

        # Effective status is the council's real position:
        #   - a triggered conditional flag ADDS a reject (reject_override)
        #   - otherwise the council keeps its documented base status.
        # We must NOT force ACCEPT just because a council has conditional flags that
        # didn't fire — that hardcodes an over-optimistic vote and masks the real
        # position. Ground truth (Councils sheet) confirms: e.g. Doncaster BC ["Will
        # Consider"], Mid Suffolk ["pod only"/DO_NOT_VOTE], Shropshire ["Reject"]
        # are NOT acceptances when their reject condition is simply absent — they
        # stay at their base status (Will Consider / Do Not Vote / Reject).
        if reject_override:
            effective_status = "REJECT"
        else:
            effective_status = base_status

        # Carry the RAW Aryza name (from original_name, falling back to name) so the
        # majority calc can match this council's balance to the case creditor (whose
        # original_name is the raw '&' form) and the UI can show the real name. Must
        # use original_name because cr["name"] may already be the resolved canonical.
        _raw_name = cr.get("original_name") or name
        reason = _build_council_reason(rule, cr, case, effective_status)
        positions.append({
            "council_name": rule.council_name,
            "creditor_name": rule.council_name,
            "original_aryza_name": _raw_name if _raw_name != rule.council_name else None,
            "effective_status": effective_status,
            "findings": findings,
            "reason": reason,
            "_creditor_idx": cr.get("_idx"),
            "debt_type_normalised": cr.get("debt_type_normalised"),
        })

    return positions


def _council_status_reason(name: str, status: str) -> str:
    """Human-readable, calculated reason for a council's effective vote status."""
    s = (status or "").upper()
    if s == "REJECT":
        return f"{name} — council rejects inclusion in this IVA (council policy / alternative recovery available)."
    if s == "ACCEPT":
        return f"{name} — council accepts inclusion in the IVA under standard terms."
    if s == "DO_NOT_VOTE":
        return f"{name} — council does not participate in the creditor vote (proof of debt only)."
    if s == "WILL_CONSIDER":
        return f"{name} — council reviews each IVA proposal individually; outcome depends on dividend and case factors."
    if s == "CONDITIONAL_VOTER":
        return f"{name} — council votes conditionally; outcome depends on the dividend offered."
    return f"{name} — vote status calculated by council rules."


# Reason shown for a creditor the engine could not assess at all. NEVER ACCEPT.
CREDITOR_NOT_ASSESSED_REASON = (
    "Creditor could not be identified — manual review required before the vote can be relied upon."
)


def reconcile_creditor_positions(result: dict, prepared_creditors: list) -> list:
    """Combine engine `creditor_positions` with any prepared creditor the engine
    routed elsewhere (councils → `council_positions`) or could not assess.

    Single source of truth shared by every assessment view, so the displayed
    creditor table always shows the engine's CALCULATED status:
      - a creditor matched in `council_positions` reuses that council's real
        effective_status / findings / reason;
      - a creditor in neither list becomes UNKNOWN with a manual-review reason.

    It must NEVER hardcode ACCEPT (the old STEP 7 bug that masked REJECT councils
    such as Rother District Council).
    """
    from debt_app.helpers import CREDITOR_ALIAS_MAP, normalise_creditor_name

    engine_positions = result.get("creditor_positions", []) or []
    council_positions = result.get("council_positions", []) or []

    positioned = set()
    for p in engine_positions:
        for key in (p.get("creditor_name"), p.get("original_aryza_name")):
            if key:
                positioned.add(key.strip().lower())

    council_by_name = {}
    for cp in council_positions:
        for key in (cp.get("creditor_name"), cp.get("council_name")):
            if key:
                council_by_name[key.strip().lower()] = cp

    backfilled = []
    for c in (prepared_creditors or []):
        cname = (c.get("creditor_name") or c.get("name") or "").strip()
        if not cname:
            continue
        original = (c.get("original_name") or c.get("name") or cname).strip()
        alias = CREDITOR_ALIAS_MAP.get(normalise_creditor_name(cname), cname).strip().lower()
        if (cname.lower() in positioned
                or original.lower() in positioned
                or alias in positioned):
            continue  # already represented in engine output

        balance = float(c.get("crm_balance") or c.get("balance") or 0)
        council_pos = (
            council_by_name.get(cname.lower())
            or council_by_name.get(original.lower())
            or council_by_name.get(alias)
        )
        if council_pos:
            # Reuse the council's REAL calculated position — never invent ACCEPT.
            canonical = council_pos.get("council_name") or council_pos.get("creditor_name") or cname
            findings = council_pos.get("findings") or []
            status = council_pos.get("effective_status", "UNKNOWN")
            reason = council_pos.get("reason") or _council_status_reason(canonical, status)
            backfilled.append({
                "creditor_name": canonical,
                "resolved_canonical_name": canonical,
                "original_aryza_name": original if original != canonical else None,
                "representative": "NONE",
                "effective_status": status,
                "findings": findings,
                "reason": reason,
                "rule_ids": [f.get("code", "") for f in findings],
                "balance": balance,
                "cr_raw_name": c.get("cr_raw_name"),
                "type_code": c.get("type_code"),
                "cr_balance": c.get("cr_balance"),
                "cr_account_status": c.get("cr_account_status"),
                "cr_account_status_subjective": c.get("cr_account_status_subjective"),
                "cr_credit_limit": c.get("cr_credit_limit"),
                "cr_account_age_months": c.get("cr_account_age_months"),
                "cr_missed_payments_3m": c.get("cr_missed_payments_3m"),
                "debt_type_normalised": c.get("debt_type_normalised"),
            })
        else:
            backfilled.append({
                "creditor_name": cname,
                "resolved_canonical_name": cname,
                "original_aryza_name": original if original != cname else None,
                "representative": c.get("representative") or "NONE",
                "effective_status": "UNKNOWN",
                "findings": [],
                "reason": CREDITOR_NOT_ASSESSED_REASON,
                "rule_ids": ["CREDITOR-NOT-ASSESSED"],
                "balance": balance,
                "cr_raw_name": c.get("cr_raw_name"),
                "type_code": c.get("type_code"),
                "cr_balance": c.get("cr_balance"),
                "cr_account_status": c.get("cr_account_status"),
                "cr_account_status_subjective": c.get("cr_account_status_subjective"),
                "cr_credit_limit": c.get("cr_credit_limit"),
                "cr_account_age_months": c.get("cr_account_age_months"),
                "cr_missed_payments_3m": c.get("cr_missed_payments_3m"),
                "debt_type_normalised": c.get("debt_type_normalised"),
            })

    return engine_positions + backfilled


# ---------------------------------------------------------------------------
# Module 6 — Special Employer, I&E Match, Repayability, Guarantors, Conditional Voters
# ---------------------------------------------------------------------------

def _check_special_employer(case: dict) -> list:
    """
    Module 6: Special employer creditor rules.

    Royal Mail / Penny Post: If client is a Royal Mail employee and Penny Post CU
    is a creditor, emit an info note for the caseworker.
    Source: GENERAL CREDITOR sheet — "If client is a Royal Mail employee, flag
    Penny Post CU information."

    Police officer / Copperpot: If client is a serving police officer and any
    creditor has reject_if_police_employed=True in CreditorCriteria, hard block.
    Source: GENERAL CREDITOR sheet — "Some creditors reject police officers —
    check reject_if_police_employed flag."
    """
    from debt_app.helpers import get_creditor_by_trading_name
    from debt_app.models import CreditorCriteria

    results = []

    if case.get("is_royal_mail_employee"):
        for cr in case.get("creditors", []):
            if "penny post" in cr["name"].lower():
                results.append(RuleResult(
                    rule_id="SPECIAL-EMPLOYER-PENNY-POST",
                    severity="info",
                    triggered=False,
                    message=(
                        f"The client is a Royal Mail employee and {cr['name']} is one of their "
                        "creditors. Penny Post Credit Union has special rules for Royal Mail "
                        "staff, so the caseworker should review this before proceeding."
                    ),
                ))
                break

    if case.get("is_police_officer"):
        for cr in case.get("creditors", []):
            try:
                criteria = get_creditor_by_trading_name(cr["name"])
            except CreditorCriteria.DoesNotExist:
                continue
            if criteria.reject_if_police_employed:
                results.append(RuleResult(
                    rule_id="SPECIAL-EMPLOYER-COPPERPOT",
                    severity="hard_block",
                    triggered=True,
                    message=(
                        f"The client is a serving police officer, and {cr['name']} does not "
                        "accept IVA proposals in this situation. This means the IVA cannot "
                        "proceed with this creditor included."
                    ),
                ))

    return results


def _check_ie_match(case: dict) -> list:
    """
    Module 6: I&E match check per creditor.

    If a creditor has a CreditorOpenBankingRule with ie_must_match_exactly=True
    and the case reports ie_matches_loan_application=False, emit IE-MATCH-FAIL.
    Source: GENERAL CREDITOR sheet — reject_if_ie_doesnt_match_application;
    supplementary check via CreditorOpenBankingRule.ie_must_match_exactly.
    """
    from debt_app.helpers import get_creditor_by_trading_name
    from debt_app.models import CreditorCriteria, CreditorOpenBankingRule

    results = []
    for cr in case.get("creditors", []):
        if cr.get("ie_matches_loan_application") is not False:
            continue

        try:
            criteria = get_creditor_by_trading_name(cr["name"])
        except CreditorCriteria.DoesNotExist:
            continue

        try:
            ob_rule = CreditorOpenBankingRule.objects.get(creditor=criteria)
        except CreditorOpenBankingRule.DoesNotExist:
            continue

        if ob_rule.ie_must_match_exactly:
            results.append(RuleResult(
                rule_id="IE-MATCH-FAIL",
                severity="flag",
                triggered=True,
                message=(
                    f"The client's income and expenditure figures do not match what was "
                    f"declared on the original loan application with {cr['name']}. This "
                    "creditor requires the two to be consistent, so a caseworker needs to "
                    "review and explain the difference before the IVA can proceed."
                ),
            ))

    return results


def _check_debt_repayability(case: dict) -> list:
    """
    Module 6: Per-creditor debt repayability threshold.

    If reject_if_debt_repayable_within_months is set for a creditor and the
    creditor's balance divided by monthly DI is below that threshold (months),
    emit DEBT-REPAYABILITY-REJECT (hard block).
    Source: GENERAL CREDITOR sheet — reject_if_debt_repayable_within_months field.
    """
    from debt_app.helpers import get_creditor_by_trading_name
    from debt_app.models import CreditorCriteria

    results = []
    monthly_di = case.get("monthly_di", Decimal("0"))
    if not monthly_di or monthly_di <= 0:
        return results

    for cr in case.get("creditors", []):
        try:
            criteria = get_creditor_by_trading_name(cr["name"])
        except CreditorCriteria.DoesNotExist:
            continue

        threshold = criteria.reject_if_debt_repayable_within_months
        if threshold is None:
            continue

        balance = float(cr["crm_balance"])
        if balance <= 0:
            continue

        months_to_repay = balance / float(monthly_di)
        if months_to_repay < threshold:
            results.append(RuleResult(
                rule_id="DEBT-REPAYABILITY-REJECT",
                severity="hard_block",
                triggered=True,
                message=(
                    f"The debt of £{balance:,.2f} owed to {cr['name']} could be repaid in "
                    f"about {months_to_repay:.1f} months out of the client's available "
                    f"income, which is faster than this creditor's {threshold}-month "
                    "threshold for considering an IVA appropriate. Because the debt could "
                    "be cleared quickly through other means, this creditor is expected to "
                    "reject the IVA."
                ),
                threshold=float(threshold),
                actual_value=months_to_repay,
            ))

    return results


def _check_guarantor_rules(case: dict) -> list:
    """
    Module 6: Personal guarantee / guarantor call-up checks.

    If a creditor has requires_pg_called_up=True and the case reports
    guarantee_called_up=False for that creditor, emit GUARANTOR-NOT-CALLED-UP.
    Source: GENERAL CREDITOR sheet — requires_pg_called_up and guarantee_called_up fields.
    """
    from debt_app.helpers import get_creditor_by_trading_name
    from debt_app.models import CreditorCriteria

    results = []
    for cr in case.get("creditors", []):
        try:
            criteria = get_creditor_by_trading_name(cr["name"])
        except CreditorCriteria.DoesNotExist:
            continue

        if not criteria.requires_pg_called_up:
            continue

        if cr.get("guarantee_called_up") is False:
            results.append(RuleResult(
                rule_id="GUARANTOR-NOT-CALLED-UP",
                severity="flag",
                triggered=True,
                message=(
                    f"{cr['name']} holds a personal guarantee on this debt, but it has not "
                    "yet been called up. This creditor requires the guarantee to be called "
                    "before an IVA proposal can be put forward."
                ),
            ))

    return results


def _check_conditional_voters(case: dict, positions: list) -> list:
    """
    Module 6: Conditional voter majority analysis.

    Identifies CONDITIONAL_VOTER creditors in positions and determines whether
    the 75%-by-value majority is achievable counting only ACCEPT/WILL_CONSIDER votes.

    - Achievable without them: CONDITIONAL-VOTER-NOT-NEEDED (info)
    - NOT achievable: CONDITIONAL-VOTER-REQUIRED (flag)
    - If ConditionalVoterRule.contact_required: also CONDITIONAL-VOTER-CONTACT-REQUIRED

    Source: GENERAL CREDITOR sheet — conditional_voter flag;
    Which Representative sheet — 75% majority threshold.
    """
    from debt_app.helpers import get_creditor_by_trading_name
    from debt_app.models import CreditorCriteria, ConditionalVoterRule

    results = []
    cv_positions = [p for p in positions if p.get("effective_status") == "CONDITIONAL_VOTER"]
    if not cv_positions:
        return results

    balance_by_name = {cr["name"]: cr["crm_balance"] for cr in case.get("creditors", [])}
    total = sum(cr["crm_balance"] for cr in case.get("creditors", []))
    if total <= 0:
        return results

    threshold = (total * Decimal("0.75")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    non_cv_statuses = frozenset({"ACCEPT", "WILL_CONSIDER"})
    cv_names = {p["creditor_name"] for p in cv_positions}

    non_cv_voting = sum(
        (balance_by_name.get(p["creditor_name"], Decimal("0"))
         for p in positions
         if p.get("effective_status") in non_cv_statuses
         and p["creditor_name"] not in cv_names),
        Decimal("0"),
    )
    majority_achievable = non_cv_voting >= threshold

    for pos in cv_positions:
        cname = pos["creditor_name"]
        if majority_achievable:
            results.append(RuleResult(
                rule_id="CONDITIONAL-VOTER-NOT-NEEDED",
                severity="info",
                triggered=False,
                message=(
                    f"{cname} is a conditional voter, but the 75% majority needed to pass "
                    "the IVA can still be reached without their vote. Their conditions "
                    "should still be noted, but no further action is needed to secure "
                    "the majority."
                ),
            ))
        else:
            results.append(RuleResult(
                rule_id="CONDITIONAL-VOTER-REQUIRED",
                severity="flag",
                triggered=True,
                message=(
                    f"{cname} is a conditional voter, and the 75% majority needed to pass "
                    "the IVA cannot be reached without their vote. Their conditions must "
                    "be met for the IVA to have a chance of passing."
                ),
            ))
            try:
                criteria = get_creditor_by_trading_name(cname)
                cv_rule = ConditionalVoterRule.objects.get(creditor=criteria)
                if cv_rule.contact_required:
                    results.append(RuleResult(
                        rule_id="CONDITIONAL-VOTER-CONTACT-REQUIRED",
                        severity="flag",
                        triggered=True,
                        message=(
                            f"{cname} requires direct contact before the IVA proposal is "
                            f"sent. Please contact {cv_rule.contact_name or 'the creditor (see creditor notes for details)'} "
                            "before proceeding."
                        ),
                    ))
            except (CreditorCriteria.DoesNotExist, ConditionalVoterRule.DoesNotExist):
                pass

    return results


# ---------------------------------------------------------------------------
# Evidence completeness, outcome derivation, majority/dividend analysis
# ---------------------------------------------------------------------------

def is_core_evidence_complete(c: dict) -> bool:
    """True when required evidence documents are present for this case."""
    bank_accounts = c.get("bank_accounts") or []
    bank_stmt_count = len(c.get("bank_stmt_docs") or [])
    required_stmts = max(1, len(bank_accounts))
    if bank_stmt_count < required_stmts:
        return False
    income_source = c.get("income_source", "")
    if income_source in ("payslip", "employed", "salary") or c.get("has_job"):
        if not c.get("payslip_docs"):
            return False
    return True


def _derive_recommended_solution(
    hard_blocks: list,
    flags: list,
    creditor_positions: list,
    case: Optional[dict] = None,
) -> str:
    """Map assessment results to a recommended solution string."""
    # HIGHEST PRECEDENCE — HMRC previous-year VAT debt (manual checklist tick).
    # A confirmed previous-year VAT debt owed to HMRC is an automatic IVA fail:
    # the case must be forced to a DMP REGARDLESS of every other criterion. This
    # sits at the very TOP of the precedence chain — above hard_blocks — because
    # it is an unconditional override: even a case with zero hard blocks and zero
    # flags must still be routed to DMP when this tick is set. The signal is read
    # from the manual DMP checklist (case["dmp_checklist"]); the tick itself is
    # only offered when HMRC is a creditor, reusing the existing hmrc_is_creditor
    # detection (no creditor-name re-matching happens here).
    if case is not None:
        _checklist = case.get("dmp_checklist") or {}
        if _checklist.get("hmrc_previous_year_vat"):
            return "FORCED_DMP_VAT"
    if hard_blocks:
        return "IVA_NOT_VIABLE"
    for pos in creditor_positions:
        if pos.get("effective_status") == "DO_NOT_VOTE":
            return "REVIEW_REQUIRED"
    if flags:
        return "IVA_WITH_CONDITIONS"
    return "IVA_VIABLE"


def _equity_age(c: dict) -> RuleResult:
    """EQUITY-AGE: Property equity vs debt / £100k ceiling, with a 55+ WATCH skip.

    IVA-eligible on this criterion when equity is LOW on EITHER count —
    available_equity < total_debt OR available_equity < £100,000. The client is
    only INELIGIBLE (hard block) when equity is high on BOTH counts: it exceeds
    the total debt AND is at least £100,000, i.e. there is enough property equity
    that an IVA is not the appropriate route.

    Exception: a client aged 55 or over on a WATCH case skips this check entirely
    (treated as not applicable / passed).

    available_equity is in POUNDS (property_value − mortgage_balance, computed
    once in _parse_case), so the £100,000 ceiling is a plain 100000. When equity
    cannot be computed (owns property but no valuation) the rule emits a
    RULE-CANNOT-EVALUATE info result and never blocks — matching TIG-15.4 /
    WATCH-22.4 / TIG-21.3.
    """
    EQUITY_CEILING = 100000.0  # pounds

    age = c.get("client_age")
    reps = c.get("detected_representatives") or set()
    if age is not None and age >= 55 and "WATCH" in reps:
        return _pass(
            "EQUITY-AGE",
            f"The client is aged {age} on a WATCH case, so the property equity check does "
            "not apply here.",
        )

    equity = c.get("available_equity")
    if equity is None:
        return RuleResult(
            rule_id="EQUITY-AGE",
            severity="info",
            triggered=True,
            message=(
                "The property equity check could not be completed because a property "
                "valuation was not provided. This will need to be supplied before the "
                "check can be assessed."
            ),
        )

    total_debt = c.get("total_debt", 0)
    if equity < total_debt or equity < EQUITY_CEILING:
        return _pass(
            "EQUITY-AGE",
            f"The client has £{equity:,.2f} of available property equity, which is below "
            f"the total debt of £{total_debt:,.2f} and/or the £{EQUITY_CEILING:,.2f} "
            "ceiling used for this check. This means the client is eligible for an IVA "
            "on this criterion.",
            threshold=EQUITY_CEILING, actual_value=equity,
        )
    return RuleResult(
        rule_id="EQUITY-AGE",
        severity="hard_block",
        triggered=True,
        message=(
            f"The client has £{equity:,.2f} of available property equity, which is more "
            f"than both the total debt of £{total_debt:,.2f} and the £{EQUITY_CEILING:,.2f} "
            "ceiling used for this check. Because there is enough equity in the property "
            "to cover the debt, an IVA is not considered the appropriate solution."
        ),
        threshold=EQUITY_CEILING, actual_value=equity,
    )


# ---------------------------------------------------------------------------
# Representative-body vote mapping
# ---------------------------------------------------------------------------
# WATCH / TIX / EVOLVE creditors do not have an independent per-creditor vote:
# their vote is the OUTCOME of their representative body's rules for this case.
# We derive that outcome from the triggered rule results and stamp it onto each
# governed creditor's effective_status, so the payload (and the microservice UI)
# show the true conditional vote instead of the stored base status (ACCEPT).
#
# This mirrors case-assessment's CriteriaCheckService._rep_body_outcomes
# (criteria_check_service.py) so both systems speak the same vocabulary, plus
# abstain handling (WATCH, client 80+) which that implementation omits.

_REP_BODY_PREFIXES = (
    ("WATCH-", "WATCH"),
    ("TIX-", "TIX"),
    ("EVOLVE-", "EVOLVE"),
)

# effective_status values representing an explicit non-vote — a representative
# body outcome must never override these (the creditor isn't casting a ballot).
_REP_NON_VOTING_STATUSES = frozenset({"DO_NOT_VOTE", "POD_ONLY"})

# Finding code set on a position when the creditor could not be resolved to any
# CreditorCriteria row at all (see CREDITOR-UNKNOWN in _check_creditor_individual).
# A representative-body outcome must never promote such a position to a real
# status/reason — that would silently contradict the "no matching record" finding
# still sitting in `findings`.
_CREDITOR_UNKNOWN_CODE = "CREDITOR-UNKNOWN"


def _rep_body_for_rule(rule_id: str):
    """Return the representative body a rule_id belongs to, or None."""
    rid = (rule_id or "").upper()
    for prefix, body in _REP_BODY_PREFIXES:
        if rid.startswith(prefix):
            return body
    return None


def _derive_representative_outcomes(case: dict, hard_blocks: list, flags: list) -> dict:
    """
    Collapse each representative body's triggered rules into a single vote.

    Precedence (most severe wins):
        REJECT        — any WATCH/TIX/EVOLVE hard block triggered
        ABSTAIN       — WATCH only, client aged 80+ (Watch_Criteria.md / WATCH-22.8)
        WILL_CONSIDER — a WATCH/TIX/EVOLVE flag triggered (modification/condition)
        ACCEPT        — body criteria fully satisfied

    NOTE: this faithfully reflects each rule's engine severity. If a rule's
    severity does not match the truth-source sheet (e.g. a sheet "reject" coded
    as a flag), that classification flows through here — fix the rule, not this.

    Returns {body: {"status": str, "rule_id": str|None, "message": str|None}}.
    `hard_blocks`/`flags` already contain only triggered rules (see _run).
    """
    # Capture the first triggering rule per body, per severity, for explainability.
    # Body-level rules that evaluate case-wide data are excluded: they appear in the
    # case-level hard_blocks/flags lists but must not drive a per-creditor outcome.
    reject_rule: dict = {}
    flag_rule: dict = {}
    for r in hard_blocks:
        if r.rule_id in _BODY_LEVEL_ONLY_RULES:
            continue
        body = _rep_body_for_rule(getattr(r, "rule_id", ""))
        if body and body not in reject_rule:
            reject_rule[body] = (r.rule_id, r.message)
    for r in flags:
        if r.rule_id in _BODY_LEVEL_ONLY_RULES:
            continue
        body = _rep_body_for_rule(getattr(r, "rule_id", ""))
        if body and body not in flag_rule:
            flag_rule[body] = (r.rule_id, r.message)

    # WATCH-22.8: client aged 80+ — WATCH abstains rather than votes.
    watch_abstains = (case.get("client_age") or 0) >= 80

    outcomes = {}
    for body in ("WATCH", "TIX", "EVOLVE"):
        if body in reject_rule:
            rid, msg = reject_rule[body]
            outcomes[body] = {"status": "REJECT", "rule_id": rid, "message": msg}
        elif body == "WATCH" and watch_abstains:
            outcomes[body] = {
                "status": "ABSTAIN", "rule_id": "WATCH-22.8",
                "message": "Client aged 80+ — WATCH abstains rather than votes.",
            }
        elif body in flag_rule:
            rid, msg = flag_rule[body]
            outcomes[body] = {"status": "WILL_CONSIDER", "rule_id": rid, "message": msg}
        else:
            outcomes[body] = {"status": "ACCEPT", "rule_id": None, "message": None}
    return outcomes


def _apply_representative_outcomes(positions: list, outcomes: dict) -> list:
    """
    Stamp each representative creditor's effective_status with its body outcome.

    A per-creditor REJECT (e.g. blocked-until-cleared) and explicit non-voting
    statuses are never softened or overridden. Abstain is emitted on the wire as
    DO_NOT_VOTE — a non-vote, excluded from the majority denominator exactly like
    an abstention — so existing consumers and the UI render it consistently.

    The reason is ALWAYS rewritten on override (the rep body now governs the
    vote, so a stale per-creditor reason would be misleading) and names the
    triggering rule. Tolerant of both the rich dict outcome and a bare status
    string. Idempotent. Detailed per-creditor findings remain in `findings`.
    """
    for pos in positions:
        rep = (pos.get("representative") or "NONE").upper()
        outcome = outcomes.get(rep)
        if not outcome:
            continue
        if isinstance(outcome, dict):
            status = outcome.get("status")
            rule_id = outcome.get("rule_id")
            message = outcome.get("message")
        else:  # bare string fallback
            status, rule_id, message = outcome, None, None
        current = (pos.get("effective_status") or "").upper()

        # Never soften a per-creditor hard reject or non-voting status.
        if current in _REP_NON_VOTING_STATUSES or current == "REJECT":
            continue

        # Never promote a genuinely unmatched creditor (no CreditorCriteria row
        # found at all) to a representative-body status. It has no real rule to
        # defer to, and the CREDITOR-UNKNOWN finding must stay accurate.
        if current == "UNKNOWN" and any(
            f.get("code") == _CREDITOR_UNKNOWN_CODE for f in (pos.get("findings") or [])
        ):
            continue

        # PENDING_REP_OUTCOME means the engine deferred to the rep body.
        # Rebuild reason from checks_description (the per-creditor audit trail
        # written by _build_creditor_reason) + the rep body result.  Using
        # checks_description rather than pos["reason"] makes this idempotent:
        # a second call from the view layer reads the same source and produces
        # the same string, so there is no duplication.
        checks_desc = (pos.get("checks_description") or "").rstrip(" .")

        def _rep_outcome_line(rep_name: str, outcome: dict) -> str:
            st  = outcome.get("status", "ACCEPT")
            rid = outcome.get("rule_id")
            msg = outcome.get("message")

            if st == "ACCEPT":
                return (
                    f"There are no issues affecting {rep_name}'s vote on this case. "
                    "This creditor is expected to accept the IVA."
                )
            if st == "REJECT":
                if rid and msg:
                    return msg
                return (
                    f"{rep_name}'s criteria have not been met on this case, so this "
                    "creditor is expected to reject the IVA."
                )
            if st == "WILL_CONSIDER":
                if rid and msg:
                    return (
                        f"{msg} As a result, a modification may be required before this "
                        "creditor will consider the IVA."
                    )
                return (
                    f"{rep_name} raised a concern on this case, so a modification may be "
                    "required before this creditor will consider the IVA."
                )
            if st == "DO_NOT_VOTE":
                if rid:
                    return f"{rep_name} is not expected to vote on this case."
                return f"{rep_name} is not expected to vote on this case."
            return f"{rep_name}'s outcome on this case is {st}."

        # Normalise ABSTAIN → DO_NOT_VOTE for the outcome line so the new
        # function's DO_NOT_VOTE branch handles the WATCH-22.8 abstain case.
        _normalised_status = "DO_NOT_VOTE" if status == "ABSTAIN" else status
        _outcome_for_line = {"status": _normalised_status, "rule_id": rule_id, "message": message}

        if status == "ACCEPT" or current == "PENDING_REP_OUTCOME":
            if status == "ABSTAIN":
                pos["effective_status"] = "DO_NOT_VOTE"
            elif status == "ACCEPT":
                pos["effective_status"] = "ACCEPT"
            else:
                pos["effective_status"] = status
            line = _rep_outcome_line(rep, _outcome_for_line)
            pos["reason"] = f"{checks_desc.rstrip('.')}. {line}".strip() if checks_desc else line
            if _normalised_status != "ACCEPT":
                _new_code = f"{rep}-{_normalised_status}"
                _existing_codes = {f.get("code") for f in pos.get("findings", [])}
                if _new_code not in _existing_codes:
                    pos.setdefault("findings", []).append({
                        "code": _new_code,
                        "reason": line,
                    })
            continue

        if status == "ABSTAIN":
            pos["effective_status"] = "DO_NOT_VOTE"
        else:
            pos["effective_status"] = status
        line = _rep_outcome_line(rep, _outcome_for_line)
        pos["reason"] = f"{checks_desc} {line}".strip() if checks_desc else line
        if _normalised_status != "ACCEPT":
            _new_code = f"{rep}-{_normalised_status}"
            _existing_codes = {f.get("code") for f in pos.get("findings", [])}
            if _new_code not in _existing_codes:
                pos.setdefault("findings", []).append({
                    "code": _new_code,
                    "reason": line,
                })

        rule_ids = pos.setdefault("rule_ids", [])
        for tag in (f"REP-{rep}-{status}", rule_id):
            if tag and tag not in rule_ids:
                rule_ids.append(tag)
    return positions


def _compute_majority_analysis(case: dict, positions: list, council_positions: list = None, estimated_dividend_pence: int = 0) -> dict:  # EXCEL_CRITERIA_REFERENCE.md — Council Majority / DO_NOT_VOTE denominator rule
    """Compute whether a 75%-by-value creditor majority is achievable."""
    from debt_app.models import CreditorCriteria
    from debt_app.helpers import get_creditor_by_trading_name

    creditors = case.get("creditors", [])

    # Merge council_positions into a unified position list so councils count toward the majority.  # EXCEL_CRITERIA_REFERENCE.md — Council Majority / DO_NOT_VOTE denominator rule
    # _check_council_rules() uses "council_name"; normalise to "creditor_name" for unified lookup.  # EXCEL_CRITERIA_REFERENCE.md — Council Majority / DO_NOT_VOTE denominator rule
    all_positions = list(positions or [])
    for cp in (council_positions or []):  # EXCEL_CRITERIA_REFERENCE.md — Council Majority / DO_NOT_VOTE denominator rule
        all_positions.append({
            "creditor_name": cp.get("creditor_name") or cp.get("council_name", ""),  # EXCEL_CRITERIA_REFERENCE.md — Council Majority / DO_NOT_VOTE denominator rule
            # Preserve the raw Aryza name so the yes-vote fallback can match the
            # case creditor when the council canonical name differs (e.g. '&'/'and').
            "original_aryza_name": cp.get("original_aryza_name"),
            "effective_status": cp.get("effective_status", "DO_NOT_VOTE"),
            "_creditor_idx": cp.get("_creditor_idx"),
        })

    # Match positions to case creditors by the stable per-creditor index
    # (_creditor_idx, set in _parse_case) wherever available — NOT by name
    # string. Two distinct debts can resolve to (or simply be entered under)
    # the exact same display name — e.g. two "Monzo Credit Card" rows that
    # are actually a current-account overdraft and a separate credit card —
    # and name-based set membership let one creditor's YES/DO_NOT_VOTE vote
    # silently leak onto an unrelated creditor sharing that string, corrupting
    # both the voting-pool denominator and the yes-vote numerator. Falls back
    # to the old name-matching behaviour only for positions that don't carry
    # an index (hand-built positions, e.g. in tests).
    position_by_idx = {}
    name_positions = []
    for pos in all_positions:
        idx = pos.get("_creditor_idx")
        if idx is not None:
            position_by_idx[idx] = pos
        else:
            name_positions.append(pos)

    def _names_from_position(pos):
        return [pos.get("creditor_name"), pos.get("original_aryza_name")]

    # Exclude DO_NOT_VOTE creditors from the denominator (total voting pool).  # EXCEL_CRITERIA_REFERENCE.md — Council Majority / DO_NOT_VOTE denominator rule
    do_not_vote_idxs = {
        idx for idx, pos in position_by_idx.items()
        if pos.get("effective_status") == "DO_NOT_VOTE"
    }
    do_not_vote_names = {  # EXCEL_CRITERIA_REFERENCE.md — Council Majority / DO_NOT_VOTE denominator rule
        n for pos in name_positions if pos.get("effective_status") == "DO_NOT_VOTE"
        for n in _names_from_position(pos) if n
    }
    # WATCH-22.8: client aged 80+ — WATCH creditors abstain, remove from denominator
    client_age = case.get("client_age") or 0
    if client_age >= 80:
        for idx, pos in position_by_idx.items():
            if idx in do_not_vote_idxs:
                continue
            try:
                from debt_app.helpers import get_creditor_by_trading_name
                from debt_app.models import CreditorCriteria
                criteria = get_creditor_by_trading_name(pos.get("creditor_name"))
                if criteria.representative == "WATCH":
                    do_not_vote_idxs.add(idx)
            except CreditorCriteria.DoesNotExist:
                pass
        for pos in name_positions:
            names = [n for n in _names_from_position(pos) if n]
            if any(n in do_not_vote_names for n in names):
                continue
            try:
                from debt_app.helpers import get_creditor_by_trading_name
                from debt_app.models import CreditorCriteria
                criteria = get_creditor_by_trading_name(pos.get("creditor_name"))
                if criteria.representative == "WATCH":
                    do_not_vote_names.update(names)
            except CreditorCriteria.DoesNotExist:
                pass

    def _is_do_not_vote(c):
        idx = c.get("_idx")
        if idx is not None and idx in position_by_idx:
            return idx in do_not_vote_idxs
        return c["name"] in do_not_vote_names

    # Voting pool: creditors who can actually vote (excludes DO_NOT_VOTE).
    # Used to determine which balances count toward voting_debt.
    total = sum(  # EXCEL_CRITERIA_REFERENCE.md — Council Majority / DO_NOT_VOTE denominator rule
        c["crm_balance"]
        for c in creditors
        if not _is_do_not_vote(c)
    )
    # The 75% threshold is calculated against ALL unsecured debt, not just the
    # voting pool — a large non-voting creditor (e.g. council) reduces the
    # achievable majority even when they abstain.
    full_total = Decimal(str(case.get("total_debt") or 0))
    if not full_total:
        return {
            "total_debt": Decimal("0"), "threshold": Decimal("0"),
            "voting_debt": Decimal("0"), "voting_debt_optimistic": Decimal("0"),
            "unknown_debt": Decimal("0"), "shortfall": Decimal("0"),
            "achievable": True, "indeterminate": False,
        }
    threshold = (full_total * Decimal("0.75")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    # A confirmed YES vote. UNKNOWN is NOT a yes — an unidentified creditor's vote
    # is genuinely unknown and must not be assumed supportive.
    # EXCEL_CRITERIA_REFERENCE.md — CONDITIONAL_VOTER: only votes YES if dividend meets threshold
    def _counts_as_yes(pos: dict) -> bool:
        status = pos.get("effective_status")
        if status in ("ACCEPT", "WILL_CONSIDER"):
            return True
        if status == "CONDITIONAL_VOTER":
            try:
                criteria = get_creditor_by_trading_name(pos["creditor_name"])
                min_div = criteria.conditional_voter_min_dividend_pence
                if min_div and estimated_dividend_pence < min_div:
                    return False  # dividend below threshold — counts as NO
            except CreditorCriteria.DoesNotExist:
                pass
            return True
        return False

    def _is_unknown(pos: dict) -> bool:
        # An explicit UNKNOWN vote — could flip either way once identified.
        return (pos.get("effective_status") or "").upper() == "UNKNOWN"

    if all_positions:
        # Name-based fallback sets, used ONLY for positions with no
        # _creditor_idx (councils' canonical name differs from the raw
        # '&'/'and' form, but they now carry an idx too — this path is
        # mainly for hand-built positions in tests).
        yes_names: set = set()
        unknown_names: set = set()
        all_positioned_names: set = set()
        for pos in name_positions:
            names = [n for n in _names_from_position(pos) if n]
            all_positioned_names.update(names)
            if _counts_as_yes(pos):
                yes_names.update(names)
            elif _is_unknown(pos):
                unknown_names.update(names)

        def _creditor_names(c):
            return [n for n in (c.get("creditor_name"), c.get("original_name"), c.get("name")) if n]

        voting_debt = Decimal("0")
        unknown_debt = Decimal("0")
        for c in creditors:
            if _is_do_not_vote(c):
                continue
            idx = c.get("_idx")
            if idx is not None and idx in position_by_idx:
                # Authoritative: this creditor row was resolved to a specific
                # position by identity, not by a name it might share with an
                # unrelated creditor.
                pos = position_by_idx[idx]
                if _counts_as_yes(pos):
                    voting_debt += c["crm_balance"]
                elif _is_unknown(pos):
                    unknown_debt += c["crm_balance"]
                continue
            names = _creditor_names(c)
            if any(n in yes_names for n in names):
                voting_debt += c["crm_balance"]
            elif any(n in unknown_names for n in names) or not any(n in all_positioned_names for n in names):
                # Explicit UNKNOWN, or a creditor with no position at all:
                # excluded from voting_debt, but tracked as a could-flip balance.
                unknown_debt += c["crm_balance"]
    else:
        # No positions computed — treat the whole book as unidentified, not as yes.
        voting_debt = Decimal("0")
        unknown_debt = full_total

    voting_debt_optimistic = voting_debt + unknown_debt
    shortfall = max(Decimal("0"), threshold - voting_debt)
    achievable = voting_debt >= threshold
    # Indeterminate: cannot confirm a majority now, but identifying the unknown
    # creditors could reach it. NOT a true impossibility.
    indeterminate = (not achievable) and (voting_debt_optimistic >= threshold)
    return {
        "total_debt": full_total,
        "threshold": threshold,
        "voting_debt": voting_debt,
        "voting_debt_optimistic": voting_debt_optimistic,
        "unknown_debt": unknown_debt,
        "shortfall": shortfall,
        "achievable": achievable,
        "indeterminate": indeterminate,
    }


def calculate_estimated_dividend_pence(case: dict) -> int:
    """Calculate overall estimated dividend in pence per pound for a case."""
    from debt_app.helpers import _SECURED_TYPES
    creditors = case.get("creditors", [])
    monthly_di = max(Decimal("0"), Decimal(str(case.get("monthly_di") or "0")))
    iva_term_months = case.get("iva_term_months", 60)
    total = sum(
        c["crm_balance"] for c in creditors
        if not c.get("is_secured", c.get("debt_type_normalised", "") in _SECURED_TYPES)
    )
    if total > 0:
        # total is a plain float (summed from crm_balance) — Decimal can't be
        # divided by float directly, so bring it into the same Decimal domain
        # as monthly_di before dividing.
        return int((monthly_di * iva_term_months / Decimal(str(total))) * 100)
    return 0


def _compute_dividend_analysis(case: dict, positions: list) -> dict:
    """Estimate dividend pence-per-pound and flag creditors whose minimums aren't met."""
    from debt_app.models import CreditorCriteria, CouncilRule
    from debt_app.helpers import (
        get_creditor_by_trading_name,
        DEBT_TYPE_COUNCIL_TAX, DEBT_TYPE_PCN, DEBT_TYPE_HOUSING_BENEFIT,
    )

    _COUNCIL_TYPES = frozenset({DEBT_TYPE_COUNCIL_TAX, DEBT_TYPE_PCN, DEBT_TYPE_HOUSING_BENEFIT})

    creditors = case.get("creditors", [])
    estimated_pence = calculate_estimated_dividend_pence(case)
    below_min = []
    max_min_required = 0
    for cr in creditors:
        resolved_name = CREDITOR_ALIAS_MAP.get(cr["name"].lower(), cr["name"])
        try:
            crit_obj = get_creditor_by_trading_name(resolved_name)
        except CreditorCriteria.DoesNotExist:
            continue
        min_p = crit_obj.min_dividend_pence
        if min_p and min_p > 0:
            max_min_required = max(max_min_required, min_p)
            if estimated_pence < min_p:
                below_min.append({
                    "creditor_name": crit_obj.creditor_name,
                    "min_dividend_pence": min_p,
                    "estimated_pence": estimated_pence,
                    "shortfall_pence": min_p - estimated_pence,
                    "code": "CREDITOR-DIVIDEND-BELOW-MIN",
                })

    # EXCEL_CRITERIA_REFERENCE.md — Dividends sheet: council min dividend
    for cr in creditors:
        if cr.get("debt_type_normalised", "") not in _COUNCIL_TYPES:
            continue
        name = cr["name"]
        try:
            council_rule = CouncilRule.objects.get(council_name__iexact=name)
        except CouncilRule.DoesNotExist:
            name_part = re.sub(
                r"\s+(District|Borough|City|County)\s+Council$", "", name, flags=re.IGNORECASE
            ).strip()
            name_part = re.sub(r"\s+(DC|BC|CC|MBC|RBC)$", "", name_part, flags=re.IGNORECASE).strip()
            council_rule = CouncilRule.objects.filter(council_name__icontains=name_part).first()
            if council_rule is None:
                continue
        except CouncilRule.MultipleObjectsReturned:
            # Duplicate rows differing only by case — prefer the authoritative
            # source (lowest source_priority), then most recently reviewed.
            council_rule = (
                CouncilRule.objects.filter(council_name__iexact=name)
                .order_by("source_priority", "-last_reviewed")
                .first()
            )
        if council_rule.min_dividend_pence is not None:
            min_p = council_rule.min_dividend_pence
            max_min_required = max(max_min_required, min_p)
            if estimated_pence < min_p:
                below_min.append({
                    "creditor_name": name,
                    "balance": cr["balance"],
                    "min_dividend_pence": min_p,
                    "estimated_pence": estimated_pence,
                    "shortfall_pence": min_p - estimated_pence,
                    "code": "COUNCIL-DIVIDEND-BELOW-MIN",
                })

    # EXCEL_CRITERIA_REFERENCE.md — Dividends: Ratesetter two-tier (25p ≥6mo, 50p <6mo)
    for cr in creditors:
        try:
            crit_obj = get_creditor_by_trading_name(cr["name"])
        except CreditorCriteria.DoesNotExist:
            continue
        if crit_obj.creditor_name.lower() != "ratesetter":
            continue
        account_age_months = cr.get("account_age_months")
        effective_min = 50 if (account_age_months is not None and account_age_months < 6) else 25
        max_min_required = max(max_min_required, effective_min)
        if estimated_pence < effective_min:
            below_min.append({
                "creditor_name": cr["name"],
                "balance": cr["balance"],
                "min_dividend_pence": effective_min,
                "estimated_pence": estimated_pence,
                "shortfall_pence": effective_min - estimated_pence,
                "code": "CREDITOR-DIVIDEND-BELOW-MIN",
            })

    return {
        "estimated_pence": estimated_pence,
        "below_min": below_min,
        "min_required_pence": max_min_required,
    }


# ---------------------------------------------------------------------------
# Representative detection — looks up DB CreditorCriteria
# ---------------------------------------------------------------------------

def detect_representatives(creditors: list, assessment_date: Optional[date] = None) -> set:
    """
    Returns set of active representatives for the creditors in this case.
    e.g. {"WATCH", "TIX"}

    assessment_date gates date-conditional representative assignments (e.g. Monzo
    only became WATCH from 30/04/2024; La Redoute from 16/07/2025).
    Defaults to today when not supplied.

    Matching uses the engine's standard resolution logic (normalisation, aliases, substrings).
    Requires Django ORM — called once in assess_case() before pure functions run.
    """
    from debt_app.helpers import get_creditor_by_trading_name
    from debt_app.models import CreditorCriteria

    if assessment_date is None:
        assessment_date = date.today()

    rep_triggers: dict[str, set[str]] = {}
    
    for cr in creditors:
        name = cr.get("creditor_name") or cr.get("name")
        if not name:
            continue
            
        try:
            criteria = get_creditor_by_trading_name(name)
            rep = (criteria.representative or "NONE").upper().strip()
            if rep != "NONE":
                rep_triggers.setdefault(rep, set()).add(name.lower())
        except CreditorCriteria.DoesNotExist:
            continue

    reps: set[str] = set(rep_triggers.keys())

    # Date-gate: Monzo → WATCH only from 30/04/2024
    if "WATCH" in reps and assessment_date < _MONZO_WATCH_DATE:
        watch_triggers = rep_triggers.get("WATCH", set())
        monzo_triggers = watch_triggers & _MONZO_NAMES_LOWER
        if monzo_triggers:
            remaining = watch_triggers - monzo_triggers
            if not remaining:
                reps.discard("WATCH")

    # Date-gate: La Redoute → WATCH only from 16/07/2025
    if "WATCH" in reps and assessment_date < _LA_REDOUTE_WATCH_DATE:
        watch_triggers = rep_triggers.get("WATCH", set())
        lr_triggers = watch_triggers & _LA_REDOUTE_NAMES_LOWER
        if lr_triggers:
            remaining = watch_triggers - lr_triggers
            if not remaining:
                reps.discard("WATCH")

    # Belt-and-suspenders: warn if a deregistered TIX creditor appears as TIX
    if "TIX" in reps and assessment_date >= date(2023, 7, 1):
        tix_triggers = rep_triggers.get("TIX", set())
        deregistered_in_case = tix_triggers & _DEREGISTERED_TIX
        if deregistered_in_case:
            logger.warning(
                "Deregistered TIX creditor(s) %s detected as TIX — check seed data.",
                deregistered_in_case,
            )

    return reps


# ---------------------------------------------------------------------------
# Credit report enrichment
# ---------------------------------------------------------------------------

def _cross_check_property_from_credit_report(c: dict, credit_report_data: dict) -> list:
    """
    Cross-checks Aryza property data against credit report mortgage accounts.
    Mutates c in place; returns a list of RuleResult flags for caseworker review.

    Three cases (Theresa Topp gap fix, case 324991):
      Case 1 – Aryza property tables empty + credit report has mortgage account(s):
               populate mortgage_balance as fallback, flag for caseworker.
               property_value is NOT set (credit reports show debt, not market value)
               — available_equity is left as None, triggering [RULE-CANNOT-EVALUATE]
               in all equity rules rather than silently passing.
      Case 2 – Aryza has property data: no action, Aryza wins.
      Case 3 – Both sources present and disagree by > £50: use higher balance
               conservatively, flag with both values for caseworker verification.
    """
    findings = []

    cr_mortgage_accounts = credit_report_data.get("mortgage_accounts") or []

    # Only active mortgages imply current property ownership. A closed or
    # settled mortgage (status "closed") means the debt is repaid — the client
    # may have sold the property or remortgaged, so we cannot infer has_property.
    # Require both a live status AND a positive balance: a "late" account with
    # zero balance is ambiguous, and a "closed" account with a residual pence
    # balance is an extraction artefact. Both conditions together are unambiguous.
    _ACTIVE_MORTGAGE_STATUSES = {"open", "active", "up to date", "late", "late payment", "defaulted", "default", "arrangement"}
    cr_active_mortgages = [
        acct for acct in cr_mortgage_accounts
        if (acct.get("account_status") or "").lower() in _ACTIVE_MORTGAGE_STATUSES
        and (acct.get("current_balance") or 0) > 0
    ]
    if not cr_active_mortgages:
        return findings

    # current_balance from extractor is in pence — convert to pounds
    cr_mortgage_balance = sum(
        (acct.get("current_balance") or 0) for acct in cr_active_mortgages
    ) / 100.0

    aryza_has_property = bool(c.get("has_property"))
    aryza_mortgage_balance = float(c.get("mortgage_balance") or 0.0)
    # Use owns_property as the sole ownership signal — a non-zero mortgage_balance
    # alone is not conclusive because it may come from a secured creditor typed
    # as 'mortgage' in Aryza (e.g. an HP agreement), not from the property table.
    # When owns_property is explicitly False, treat as "no Aryza property data"
    # and let the credit report be the authoritative source.
    aryza_has_data = aryza_has_property

    if not aryza_has_data:
        # Case 1 — Aryza property tables empty, credit report has active mortgage(s).
        # type_code "MG" with a live status and positive balance means a mortgage
        # still being serviced — inferring has_property=True is safe.
        logger.warning("[PROPERTY CROSSCHECK] Case 1: Aryza empty, CR has mortgage. Setting has_property=True, balance=£%s", cr_mortgage_balance)
        c["has_property"] = True
        c["mortgage_balance"] = cr_mortgage_balance
        # No property valuation signal exists in credit report data — only the debt
        # balance is present. Explicitly set property_value to None so the
        # [RULE-CANNOT-EVALUATE] path in equity rules fires correctly rather than
        # computing a spurious equity figure from a 0-valued payload default.
        c["property_value"] = None
        c["available_equity"] = None
        c["property_data_source"] = "credit_report_fallback"

        logger.info(
            "[PROPERTY CROSSCHECK] Using credit report mortgage balance £%s as authoritative source (Aryza property tables empty).",
            cr_mortgage_balance,
        )

        # Surface this to the caseworker — the state mutation above (silently)
        # flips has_property to True from credit-report data alone, with no
        # property valuation available, so every equity rule downstream will
        # short-circuit via [RULE-CANNOT-EVALUATE] instead of computing a real
        # figure. Without a visible flag, a caseworker has no way to know that
        # happened (this was the actual Theresa Topp gap — the mutation existed,
        # the visibility didn't).
        lender_names = ", ".join(sorted({
            (acct.get("raw_name") or "").strip()
            for acct in cr_active_mortgages if acct.get("raw_name")
        }))
        findings.append(RuleResult(
            rule_id="PROPERTY-DATA-FROM-CREDIT-REPORT",
            severity="flag",
            triggered=True,
            message=(
                f"The customer's case file has no property details recorded, but the "
                f"credit report shows an active mortgage with "
                f"{lender_names or 'an unidentified lender'} with a balance of "
                f"£{cr_mortgage_balance:,.2f}. This balance has been used as a stand-in, "
                f"but the property's value cannot be worked out from a credit report, so "
                f"the amount of equity in the property cannot be calculated automatically. "
                f"The caseworker must confirm the customer owns this property and get a "
                f"valuation before this can be resolved."
            ),
        ))

    elif cr_mortgage_balance > 0:
        # Case 3 — both sources have mortgage data: check for significant disagreement.
        diff = abs(aryza_mortgage_balance - cr_mortgage_balance)
        if diff > 50.0:
            higher = max(aryza_mortgage_balance, cr_mortgage_balance)
            higher_source = (
                "case file" if aryza_mortgage_balance >= cr_mortgage_balance else "credit report"
            )
            c["mortgage_balance"] = higher
            # Recompute available_equity with the corrected balance where property
            # value is known; leave None if property_value is absent.
            pv = c.get("property_value")
            if pv is not None:
                c["available_equity"] = _parse_amount(pv) - higher
            findings.append(RuleResult(
                rule_id="PROPERTY-DATA-CONFLICT",
                severity="flag",
                triggered=True,
                message=(
                    f"The customer's case file and the credit report disagree on the "
                    f"mortgage balance: the case file shows £{aryza_mortgage_balance:,.2f}, "
                    f"while the credit report shows £{cr_mortgage_balance:,.2f} — a "
                    f"difference of £{diff:,.2f}. To be cautious, the higher figure of "
                    f"£{higher:,.2f} (from the {higher_source}) has been used for now. "
                    f"The caseworker must check with the customer or the lender to confirm "
                    f"the correct balance."
                ),
            ))
    # Case 2 — Aryza has data and credit report agrees or has no mortgage: no action.

    return findings


def _enrich_from_credit_report(case_data: dict) -> str:
    """
    Looks up CreditReport by aryza_reference from case_data and enriches
    per-creditor fields and evidence_ledger in-place. Never raises.
    Returns "present" | "absent" | "extraction_failed".
    """
    try:
        from debt_app.models import CreditReport, CreditorCriteria

        ref = case_data.get("aryza_reference")
        if not ref:
            return "absent"

        # Determine status — check for record existence separately from extraction
        any_report = CreditReport.objects.filter(aryza_reference=ref).order_by("-created_at").first()
        report = CreditReport.objects.filter(
            aryza_reference=ref,
            extraction_status="extracted",
        ).order_by("-created_at").first()

        logger.info("[CREDIT REPORT] ref=%s report=%s", ref, "found" if report else "NOT FOUND")

        if not any_report:
            status = "absent"
        elif not report or not (report.extracted_data or {}).get("accounts"):
            status = "extraction_failed"
        else:
            status = "present"

        # Surface credit report status into case dict so per-creditor checks
        # can flag when a ccj/aoe-sensitive creditor has no report uploaded.
        case_data["credit_report_status"] = status

        # Surface the Public Information CCJ signal from the credit report
        # regardless of per-account matching status — a report can carry a CCJ
        # even when its account list fails to match the case creditors. The
        # credit report is the authoritative source for has_ccj.
        _ccj_report = report or any_report
        if _ccj_report and _ccj_report.extracted_data and "has_ccj" in _ccj_report.extracted_data:
            case_data["has_ccj"] = bool(_ccj_report.extracted_data.get("has_ccj"))
            case_data["credit_report_public_information"] = (
                _ccj_report.extracted_data.get("public_information") or {}
            )

        # AoE — credit report is authoritative over Aryza payload
        if _ccj_report and _ccj_report.extracted_data and "aoe_in_place" in _ccj_report.extracted_data:
            case_data["aoe_in_place"] = bool(_ccj_report.extracted_data.get("aoe_in_place"))

        # credit_report_iva_or_bankruptcy — surfaced from the credit report's
        # combined "IVA or Bankruptcy Detected" field (public_information),
        # which cannot distinguish a previous IVA from a previous bankruptcy.
        # Deliberately kept SEPARATE from case_data["previous_iva"]: TIG-13,
        # TIG-21.5 and WATCH-22.12 require an IVA specifically (they demand an
        # IVA termination report, which doesn't exist for a bankruptcy), so
        # blindly upgrading previous_iva from this ambiguous flag produced an
        # unresolvable false hard block for clients whose credit report hit
        # was actually a bankruptcy, not an IVA. TIG-15.2 wants either — it
        # reads this field explicitly alongside previous_iva.
        _pub_info = case_data.get("credit_report_public_information") or {}
        if _ccj_report and _pub_info and "iva_or_bankruptcy" in _pub_info:
            case_data["credit_report_iva_or_bankruptcy"] = bool(_pub_info.get("iva_or_bankruptcy"))

        # is_currently_in_dmp — credit report detection supplements Aryza payload
        # _phase4_dmp_reject uses c["is_currently_in_dmp"] as a hard dict access
        # so we must never remove or None this key — only upgrade False → True
        if _ccj_report and _pub_info and "debt_management" in _pub_info:
            if bool(_pub_info.get("debt_management")):
                # Only upgrade to True — Aryza True must never be overwritten to False
                case_data["is_currently_in_dmp"] = True

        # Cross-check Aryza property data against credit report mortgage accounts.
        # Uses same fallback pattern as has_ccj above — works on any available report,
        # not just fully-extracted ones, since mortgage_accounts may be present even
        # when unsecured account extraction partially failed.
        _prop_cr_data = (_ccj_report.extracted_data or {}) if _ccj_report else {}
        _prop_findings = _cross_check_property_from_credit_report(case_data, _prop_cr_data)
        if _prop_findings:
            case_data["property_report_findings"] = _prop_findings

        if status == "present":
            from rapidfuzz import fuzz, process as rfprocess
            accounts = report.extracted_data["accounts"]

            # Build lookup pool: case creditors with a positive balance
            case_creditors = [c for c in case_data.get("creditors", []) if (c.get("balance") or 0) > 0]

            # Index every case creditor under BOTH its resolved canonical name AND
            # its raw Aryza name. The PDF extractor and the engine normalise names
            # through DIFFERENT alias maps, so matching only the resolved name
            # silently dropped accounts whose two pipelines diverged. Worst case:
            # the extractor shortens 'Nationwide Building Society' → 'Nationwide'
            # while the engine keeps the full name (token_sort_ratio 54 < 80), and
            # 'Octopus Energy Limited' → 'Octopus Energy' scored 78 < 80 — both
            # >= £1,000 debts that then hard-blocked on missing proof of debt.
            # The raw Aryza name and the PDF raw_name both come from full legal
            # names and align almost exactly, so indexing both recovers the match.
            name_to_creditors: dict[str, list] = {}
            for c in case_creditors:
                for nm in (c.get("name"), c.get("original_name")):
                    if nm:
                        name_to_creditors.setdefault(nm, []).append(c)
            search_names = list(name_to_creditors.keys())

            evidence_ledger = case_data.setdefault("evidence_ledger", [])
            existing_refs = {e.get("ref") for e in evidence_ledger}
            unmatched = []

            # claimed_ids ensures accounts with a real balance claim rows first,
            # preventing null-balance accounts from always grabbing the lowest-balance row
            claimed_ids: set[int] = set()

            # Process accounts with a real balance first so the tiebreaker works
            # correctly before null-balance accounts fall through to claim-and-exclude.
            # current_balance from extractor is pence; None sorts last (True > False).
            accounts = sorted(
                accounts,
                key=lambda a: a.get("current_balance") is None,
            )

            for account in accounts:
                matched_creditor = account.get("matched_creditor", "")
                # Prefer the raw PDF name for display/matching; it aligns with the
                # case creditor's raw Aryza name. matched_creditor is also tried as
                # a query below so the extractor's alias output still contributes.
                raw_name = account.get("raw_name", "") or matched_creditor
                if not raw_name and not matched_creditor:
                    logger.warning("[ENRICH] account skipped — no name resolved: %s", account)
                    continue

                # Match BOTH PDF name forms (raw PDF name and the extractor's
                # alias-mapped name) against the dual-name index, keeping the best
                # score. This bridges the extractor/engine alias-map divergence.
                best_result = None
                for query in (raw_name, matched_creditor):
                    if not query:
                        continue
                    r = rfprocess.extractOne(
                        query,
                        search_names,
                        scorer=fuzz.token_sort_ratio,
                        score_cutoff=80,
                        processor=lambda s: s.lower(),
                    )
                    if r and (best_result is None or r[1] > best_result[1]):
                        best_result = r

                if best_result is None:
                    logger.info("[CREDIT REPORT MATCH] '%s' → no match (below cutoff)", raw_name)
                    unmatched.append(raw_name)
                    continue

                matched_name, score, _ = best_result
                logger.info("[CREDIT REPORT MATCH] '%s' → '%s' (score=%s)", raw_name, matched_name, score)

                # When multiple creditors share the same name, pick by balance proximity.
                # Exclude rows already claimed by a previous account to prevent two PDF
                # accounts from landing on the same case creditor row.
                candidates = [
                    c for c in name_to_creditors.get(matched_name, [])
                    if id(c) not in claimed_ids
                ]

                if not candidates:
                    if name_to_creditors.get(matched_name):
                        logger.warning(
                            "[ENRICH] '%s' — all candidates claimed, no row available",
                            raw_name,
                        )
                    else:
                        logger.warning(
                            "[ENRICH] '%s' fuzzy-matched to '%s' but no case creditor row found",
                            raw_name, matched_name,
                        )
                    unmatched.append(raw_name)
                    continue

                # current_balance from extractor is pence; case creditor balance is pounds.
                # Convert pence → pounds so the tiebreaker arithmetic is in the same unit.
                account_balance_pounds = (account.get("current_balance") or 0) / 100.0
                best_creditor = min(
                    candidates,
                    key=lambda c: abs((c.get("balance") or 0) - account_balance_pounds),
                )

                claimed_ids.add(id(best_creditor))
                logger.debug(
                    "[ENRICH] claimed '%s' (id=%s) for pdf account '%s'",
                    best_creditor.get("name"), id(best_creditor), raw_name,
                )
                logger.debug(
                    "[ENRICH] '%s' → best_creditor '%s' balance=£%.2f (pdf balance=£%.2f)",
                    raw_name,
                    best_creditor.get("name"),
                    best_creditor.get("balance") or 0,
                    account_balance_pounds,
                )

                # Enrich per-creditor fields on the matched creditor row
                if best_creditor.get("account_age_months") is None and account.get("account_age_months") is not None:
                    best_creditor["account_age_months"] = account["account_age_months"]
                best_creditor["missed_payments_last_3_months"] = account.get("missed_payments_last_3_months")
                best_creditor["recent_spending"] = account.get("recent_spending")
                best_creditor["credit_report_balance"] = account.get("current_balance")
                best_creditor["payment_history_months"] = account.get("payment_history_months")
                best_creditor["worst_status"] = account.get("worst_status")

                # Infer first_payment_made from account_status OR worst_status.
                # worst_status (Experian only) can show derogatory history even
                # when account_status reads "Active" (e.g. an account that
                # defaulted then recovered) — same "check both fields" fix
                # already applied to the extraction-time inclusion filter.
                # "defaulted" and "arrangement" require prior billing history — strong signal
                # "late" implies active account with arrears — sufficient signal
                # Upgrade-only: never overwrite Aryza True with False
                _fpm_before = best_creditor.get("first_payment_made")
                if not best_creditor.get("first_payment_made"):
                    _acct_status = (account.get("account_status") or "").lower()
                    _worst_status = (account.get("worst_status") or "").lower()
                    _status_derog = _acct_status in {"defaulted", "default", "arrangement", "late", "late payment"}
                    _worst_derog = any(
                        kw in _worst_status
                        for kw in ("default", "delinquent", "arrangement", "late", "arrears", "collections")
                    )
                    if _status_derog or _worst_derog:
                        best_creditor["first_payment_made"] = True

                # Infer first_payment_made from a real balance reduction — catches
                # a clean/Active account that has genuinely paid down (the
                # status-based check above never fires for Active). Only
                # Experian accounts carry start_balance; Aryza-format accounts
                # don't, so this is a no-op there. Same upgrade-only safety.
                if not best_creditor.get("first_payment_made"):
                    _start_bal = account.get("start_balance")
                    _cur_bal = account.get("current_balance")
                    if _start_bal is not None and _cur_bal is not None and _cur_bal < _start_bal:
                        best_creditor["first_payment_made"] = True

                # Inject evidence entries keyed by linked_creditor AND name so
                # _tig_10 hits on whichever key it uses for lookup
                account_balance_pence = account.get("current_balance") or 0
                for ref_key in [best_creditor.get("linked_creditor"), best_creditor.get("name")]:
                    if ref_key is not None and ref_key not in existing_refs:
                        evidence_ledger.append({
                            "ref": ref_key,
                            "is_verified": True,
                            "category": "credit_report",
                            "source": "credit_report",
                            "raw_name": raw_name,
                            "matched_engine_name": matched_name,
                            "match_score": score,
                            "account_age_months": account.get("account_age_months"),
                            "missed_payments_last_3_months": account.get("missed_payments_last_3_months"),
                            "account_status": account.get("account_status"),
                        })
                        existing_refs.add(ref_key)
                    elif ref_key is not None:
                        logger.warning(
                            "[ENRICH] evidence entry skipped for '%s' — already present. "
                            "Second account balance=£%.2f", ref_key, account_balance_pounds
                        )

            if unmatched:
                case_data["credit_report_unmatched_accounts"] = unmatched

        # Check requires_credit_report flag regardless of status
        for creditor in case_data.get("creditors", []):
            try:
                criteria = CreditorCriteria.objects.get(creditor_name=creditor.get("name", ""))
                if criteria.requires_credit_report and status == "absent":
                    case_data.setdefault("credit_report_flags", []).append({
                        "creditor": creditor["name"],
                        "message": (
                            f"A credit report is needed for {creditor['name']} before this "
                            "creditor's criteria can be fully checked. Please upload the "
                            "customer's credit report to complete this assessment."
                        ),
                    })
            except CreditorCriteria.DoesNotExist:
                pass

        return status

    except Exception as exc:
        logger.error("_enrich_from_credit_report failed: %s", exc, exc_info=True)
        return "extraction_failed"


DMP_MIN_TOTAL_DEBT = 3000


def _evaluate_dmp_eligibility(c: dict) -> dict:
    """
    Standalone DMP eligibility check (separate from the hard_block/flag pipeline
    and from _derive_recommended_solution). Reads c["dmp_checklist"] (the 11-field
    checklist dict) and c["total_debt"].

    Confirmed with user 2026-07-15: "current gas/electricity bills cannot
    be included" means exclude that specific debt from the DMP arrangement, NOT
    reject the whole case. The original checkbox framing (flat true/false, no amount)
    lost that nuance — current_gas_bill/current_electric_bill/current_phone_contract
    are therefore non-blocking notes here, not rejection triggers.

    previous_gas_provider_debt/previous_electric_provider_debt/current_water_bill
    have no rejection rule (these "can be included" in the DMP total) —
    they surface as informational notes only, never rejection triggers.

    Returns {"status": "DMP_ELIGIBLE" | "DMP_REJECTED" | "DMP_NOT_EVALUATED",
    "reasons": [...], "notes": [...]}. "reasons" explains a REJECTED status;
    "notes" are informational only and never affect status.
    """
    checklist = c.get("dmp_checklist")
    if not checklist:
        return {"status": "DMP_NOT_EVALUATED", "reasons": [], "notes": []}

    reasons: list[str] = []
    notes: list[str] = []

    total_debt = float(c.get("total_debt") or 0)
    if total_debt <= DMP_MIN_TOTAL_DEBT:
        reasons.append(
            f"The customer's total debt is £{total_debt:,.2f}, which is at or below the "
            f"£{DMP_MIN_TOTAL_DEBT:,.2f} minimum needed for a debt management plan. This "
            "case cannot proceed as a DMP unless the total debt is higher than this."
        )

    if (
        checklist.get("current_year_council_tax")
        and checklist.get("previous_year_council_tax")
        and checklist.get("lost_right_to_pay_instalments")
    ):
        reasons.append(
            "The customer has lost the right to pay their council tax by "
            "instalments, and has council tax arrears for both the current year "
            "and the previous year. This case cannot proceed as a DMP."
        )

    # HMRC/self-employment split
    if c.get("hmrc_is_creditor"):
        income_source = c.get("income_source", "").lower()
        if income_source == "self_employed":
            notes.append(
                "The customer owes HMRC money. Because they are self-employed, "
                "this debt is left out of the DMP total."
            )
        else:
            notes.append(
                "The customer owes HMRC money. Because they are not "
                "self-employed, this debt is included in the DMP total."
            )

    excluded_bills = [
        label for field, label in (
            ("current_gas_bill", "current gas bill"),
            ("current_electric_bill", "current electricity bill"),
            ("current_phone_contract", "current phone contract"),
            ("council_parking_fine", "council parking fine"),
        )
        if checklist.get(field)
    ]
    if excluded_bills:
        notes.append(
            "The following debt(s) must be left out of the DMP arrangement: "
            + ", ".join(excluded_bills) + "."
        )

    if checklist.get("previous_gas_provider_debt"):
        notes.append(
            "The customer has a debt with a previous gas provider. This is "
            "included in the DMP total."
        )
    if checklist.get("previous_electric_provider_debt"):
        notes.append(
            "The customer has a debt with a previous electricity provider. "
            "This is included in the DMP total."
        )
    if checklist.get("current_water_bill"):
        notes.append(
            "The customer's current water bill is included in the DMP total."
        )

    status = "DMP_REJECTED" if reasons else "DMP_ELIGIBLE"
    return {"status": status, "reasons": reasons, "notes": notes}


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def assess_case(case_json: dict, detected_representatives: Optional[set] = None) -> dict:
    """
    Assess a case JSON payload against all active rules.

    Args:
        case_json: Raw JSON payload from the case assessment microservice.
        detected_representatives: Optional pre-computed set of representative strings
            {"WATCH", "TIX", "EVOLVE"}. If None, detect_representatives() is called
            (requires Django). Pass an empty set in unit tests to suppress DB lookup.

    Returns:
        {
            "hard_blocks": [RuleResult, ...],
            "flags":       [RuleResult, ...],
            "info":        [RuleResult, ...],
            "passed":      [RuleResult, ...],
            "overall":     "blocked" | "flagged" | "pass",
            "representatives_detected": set,
        }
    """
    c = _parse_case(case_json)
    credit_report_status = _enrich_from_credit_report(c)

    logger.warning("[PROPERTY ENRICH] ref=%s has_property=%s property_value=%s mortgage_balance=%s enrich_status=%s",
        c.get("aryza_reference"), c["has_property"], c["property_value"], c["mortgage_balance"], credit_report_status)

    if detected_representatives is None:
        detected_representatives = detect_representatives(
            case_json.get("creditors") or [],
            assessment_date=c["assessment_date"],
        )

    # Expose detected representatives to the always-run rules (e.g. TIG-16 scopes
    # itself to NON-WPM cases — WATCH/WPM equity is handled by WATCH-22.4).
    c["detected_representatives"] = detected_representatives
    c["dmp_checklist"] = case_json.get("dmp_checklist")

    # Load disabled rule_keys once — single DB query for the whole assessment.
    try:
        from debt_app.models import GlobalCriteria as _GC
        _disabled_rules: frozenset = frozenset(
            _GC.objects.filter(is_active=False).values_list("rule_key", flat=True)
        )
    except Exception:
        _disabled_rules = frozenset()

    hard_blocks: list[RuleResult] = []
    flags: list[RuleResult] = []
    info: list[RuleResult] = []
    passed: list[RuleResult] = []

    def _run(rule_func, *args):
        if _func_to_rule_id(rule_func.__name__) in _disabled_rules:
            return  # skip execution entirely — rule is disabled in DB
        try:
            r = rule_func(c, *args)
        except Exception as exc:
            logger.error("Error in %s: %s", rule_func.__name__, exc, exc_info=True)
            r = RuleResult(
                rule_id=_func_to_rule_id(rule_func.__name__),
                severity="hard_block",
                triggered=True,
                message=f"This check could not be completed due to a system error ({exc}). A caseworker must review this case manually.",
            )
        if r.severity == "hard_block" and r.triggered:
            hard_blocks.append(r)
        elif r.severity == "flag" and r.triggered:
            flags.append(r)
        elif r.severity == "info":
            info.append(r)
        else:
            passed.append(r)

    # --- TIG rules (always) ---
    tig_rules = [
        _tig_01, _tig_02, _tig_03, _tig_04, _tig_05,
        _tig_06, _tig_07, _tig_08, _tig_09, _tig_10,
        _tig_11, _tig_11_gambling, _tig_12, _tig_13,
        _tig_15_1, _tig_15_2, _tig_15_3, _tig_15_4, _tig_15_5,
        _tig_15_6, _tig_15_7, _tig_15_8, _tig_15_9, _tig_15_10,
        # HMRC-specific TIG rules (Rules 1, 3–8) — EXCEL_CRITERIA_REFERENCE.md HMRC Rules
        _tig_hmrc_01,
        _tig_hmrc_03, _tig_hmrc_04, _tig_hmrc_05, _tig_hmrc_06,
        _tig_hmrc_07, _tig_hmrc_08,
        _tig_16, _tig_17, _tig_18,
        _equity_age,  # property equity vs debt / £100k ceiling, 55+ WATCH skip
        _tig_19, _tig_19_review, _tig_19_1,
        _tig_20, _tig_20_1,
        _tig_21_1, _tig_21_2, _tig_21_3, _tig_21_4, _tig_21_5,
        _watch_22_12,  # IVA consistency check — applies to all cases, not just WATCH
        # Universal pastoral rules — apply regardless of representative
        _watch_22_7,   # children 13+ sustainability paragraph
        _watch_22_11,  # gambling as primary cause of debt
    ]
    for fn in tig_rules:
        _run(fn)

    # --- Module 4 rules (always) ---
    # Pre-fetch relevant CreditorCriteria for Module 4 rules to avoid ORM calls in rules
    from debt_app.models import CreditorCriteria

    case_creditor_names = {cr["name"] for cr in c["creditors"] if cr.get("name")}
    lookup_names = set(case_creditor_names)
    for name in case_creditor_names:
        alias = CREDITOR_ALIAS_MAP.get(name.lower())
        if alias:
            lookup_names.add(alias)

    # Single bulk query as requested
    criteria_qs = CreditorCriteria.objects.filter(
        is_active=True,
        creditor_name__in=lookup_names
    )
    criteria_lookup = {crit.creditor_name.lower(): crit for crit in criteria_qs}

    # Map back to the original names used in the case
    module4_criteria_data = {}
    for name in case_creditor_names:
        name_lower = name.lower()
        if name_lower in criteria_lookup:
            module4_criteria_data[name] = criteria_lookup[name_lower]
        else:
            alias = CREDITOR_ALIAS_MAP.get(name_lower)
            if alias and alias.lower() in criteria_lookup:
                module4_criteria_data[name] = criteria_lookup[alias.lower()]

    # Attach parent_group (banking group) to each case creditor from its
    # CreditorCriteria row, so the single-lender rules (WATCH-22.5 / EVOLVE-02)
    # can collapse brands of one bank into a single lender. ORM stays out of the
    # rule functions — the lookup happens here once, reusing the bulk prefetch.
    for cr in c["creditors"]:
        crit = module4_criteria_data.get(cr.get("name"))
        if crit and getattr(crit, "parent_group", None):
            cr["parent_group"] = crit.parent_group

    # _phase4_county_council is called later (after _route is defined) so its district
    # positions can be merged into council_positions before majority analysis.
    for fn in [_phase4_vw_termination, _phase4_dmp_reject]:
        _run(fn, module4_criteria_data)

    # --- WATCH rules ---
    if "WATCH" in detected_representatives:
        watch_rules = [
            _watch_22_1, _watch_22_2, _watch_22_3, _watch_22_4, _watch_22_5,
            _watch_22_6, _watch_22_8, _watch_22_9, _watch_22_10,
            _watch_22_13, _watch_22_14,  # _watch_22_12/22_7/22_11 run for all cases
        ]
        for fn in watch_rules:
            _run(fn)

    # --- TIX rules ---
    if "TIX" in detected_representatives:
        tix_rules = [_tix_01, _tix_02, _tix_03, _tix_04, _tix_05, _tix_06]
        for fn in tix_rules:
            _run(fn)

    # --- EVOLVE rules ---
    if "EVOLVE" in detected_representatives:
        evolve_rules = [_evolve_01, _evolve_02, _evolve_03]
        for fn in evolve_rules:
            _run(fn)

    # --- Module 5: per-creditor and per-council positions ---
    # Pre-load all CouncilRule names (+ &/and variants) into a lowercase frozenset once.
    # Both _check_creditor_individual() and _check_council_rules() read this from c so
    # council routing is consistent regardless of the debt_type tagged in Aryza (e.g.
    # a council whose debt_type arrives as GENERAL instead of council_tax is still
    # routed through _check_council_rules() if its name matches a CouncilRule entry).
    try:
        from debt_app.models import CouncilRule as _CouncilRuleModel
        _raw_council_names = list(
            _CouncilRuleModel.objects.values_list("council_name", flat=True)
        )
        c["_council_rule_names_lower"] = frozenset(
            variant.lower()
            for raw in _raw_council_names
            for variant in _ampersand_variants(raw)
        )
    except Exception as _e:
        logger.warning("Could not pre-load CouncilRule names: %s", _e)
        c["_council_rule_names_lower"] = frozenset()

    estimated_pence = calculate_estimated_dividend_pence(c)
    _all_creditor_positions = _check_creditor_individual(c, estimated_dividend_pence=estimated_pence)
    for _pos in _all_creditor_positions:
        for _finding in _pos.get("findings", []):
            if _finding.get("code") == "CREDITOR-BLOCKED":
                hard_blocks.append(RuleResult(
                    rule_id="CREDITOR-BLOCKED",
                    severity="hard_block",
                    triggered=True,
                    message=f"{_pos['creditor_name']} is expected to block this IVA. Reason: {_finding['reason']}",
                ))
    council_positions = _check_council_rules(c)

    # --- Module 6: special employer, I&E match, repayability, guarantors, conditional voters ---
    def _route(r: RuleResult):
        if r.severity == "hard_block" and r.triggered:
            hard_blocks.append(r)
        elif r.severity == "flag" and r.triggered:
            flags.append(r)
        elif r.severity == "info":
            info.append(r)
        else:
            passed.append(r)

    # EXCEL_CRITERIA_REFERENCE.md — County Councils: district rules must be evaluated
    _county_results, _county_positions = _phase4_county_council(c)  # EXCEL_CRITERIA_REFERENCE.md — County Councils: district rules must be evaluated
    for _r in _county_results:  # EXCEL_CRITERIA_REFERENCE.md — County Councils: district rules must be evaluated
        _route(_r)  # EXCEL_CRITERIA_REFERENCE.md — County Councils: district rules must be evaluated
    council_positions.extend(_county_positions)  # EXCEL_CRITERIA_REFERENCE.md — County Councils: district rules must be evaluated

    # TIG-17 propagation: when a council will reject due to active income/benefit
    # deductions, override effective_status to REJECT so majority analysis reflects
    # the true NO vote rather than the council's stored base status.
    #
    # Uses flags (not the raw condition) so GlobalCriteria.is_active=False for TIG-17
    # suppresses this override automatically.
    #
    # Limitation: income_deductions_active is case-level — it does not identify which
    # specific council holds the deduction order. All non-REJECT/DO_NOT_VOTE council
    # positions are overridden conservatively. Per-creditor deduction tracking is a
    # separate follow-up; without it this is the correct conservative behaviour.
    _tig17_fired = any(r.rule_id == "TIG-17" for r in flags)
    if _tig17_fired:
        for _cp in council_positions:
            if (_cp.get("effective_status") or "").upper() not in ("REJECT", "DO_NOT_VOTE"):
                _cp["effective_status"] = "REJECT"
                _cp.setdefault("findings", []).append({
                    "code": "COUNCIL-TIG17-INCOME-DEDUCTION",
                    "reason": (
                        "The customer already has money being taken directly from their "
                        "income or benefits to pay this council. Because of this, the "
                        "council is expected to reject the IVA."
                    ),
                })
                _cp["reason"] = (
                    "This council is already taking money directly from the customer's "
                    "income or benefits, so it is expected to reject the IVA. "
                    + (_cp.get("reason") or "")
                ).strip()

    for r in _check_special_employer(c):
        _route(r)
    for r in _check_ie_match(c):
        _route(r)
    for r in _check_debt_repayability(c):
        _route(r)
    for r in _check_guarantor_rules(c):
        _route(r)
    for r in _check_conditional_voters(c, _all_creditor_positions):
        _route(r)

    # Add any credit report required flags emitted by _enrich_from_credit_report
    if "CREDIT-REPORT-REQUIRED" not in _disabled_rules:
        for _cr_flag in c.get("credit_report_flags", []):
            flags.append(RuleResult(
                rule_id="CREDIT-REPORT-REQUIRED",
                severity="flag",
                triggered=True,
                message=_cr_flag["message"],
            ))

    # Property data cross-check findings from _enrich_from_credit_report
    for _pf in c.get("property_report_findings", []):
        if _pf.rule_id not in _disabled_rules:
            _route(_pf)

    # --- Overall result ---
    if hard_blocks:
        overall = "blocked"
    elif flags:
        overall = "flagged"
    else:
        overall = "pass"

    # --- Representative-body vote mapping ---
    # WATCH/TIX/EVOLVE creditors inherit their representative body's vote for this
    # case (derived from the triggered rules) rather than their stored base status.
    # Applied before majority/dividend so the voting pool reflects the true votes.
    representative_outcomes = _derive_representative_outcomes(c, hard_blocks, flags)
    _apply_representative_outcomes(_all_creditor_positions, representative_outcomes)

    # Full list drives majority/dividend analysis (ACCEPT creditors must be counted).
    # Dividend is computed first so estimated_pence can gate CONDITIONAL_VOTER majority votes.
    dividend_analysis = _compute_dividend_analysis(c, _all_creditor_positions)
    majority_analysis = _compute_majority_analysis(  # EXCEL_CRITERIA_REFERENCE.md — Council Majority / DO_NOT_VOTE denominator rule
        c, _all_creditor_positions, council_positions,
        estimated_dividend_pence=dividend_analysis["estimated_pence"],
    )

    # EXCEL_CRITERIA_REFERENCE.md — Dividends: below-minimum surfaced as actionable flag
    for entry in dividend_analysis["below_min"]:
        cname = entry["creditor_name"] if isinstance(entry, dict) else entry
        min_p = entry["min_dividend_pence"] if isinstance(entry, dict) else "?"
        est_p = entry.get("estimated_pence", dividend_analysis["estimated_pence"]) if isinstance(entry, dict) else dividend_analysis["estimated_pence"]
        flags.append(RuleResult(
            rule_id="DIVIDEND-BELOW-MIN",
            severity="flag",
            triggered=True,
            message=(
                f"{cname} would receive an estimated {est_p}p in the pound, but this "
                f"creditor requires at least {min_p}p in the pound to accept an IVA. "
                "Because the amount on offer is too low, this creditor is expected to "
                "reject the IVA."
            ),
        ))

    # EXCEL_CRITERIA_REFERENCE.md — Council Majority: if 75% majority is mathematically
    # impossible (e.g. council tax creditor holds a blocking minority and does not vote),
    # the IVA cannot proceed regardless of other rules — hard block.
    #
    # BUT only when TRULY impossible: even counting every UNKNOWN/unidentified
    # creditor as a YES (voting_debt_optimistic) the 75% threshold still cannot be
    # reached. When the shortfall is only down to unidentified creditors
    # (indeterminate), identifying them could pass it — so that is a REFERRAL flag,
    # never a hard block. This prevents a false INELIGIBLE driven purely by an
    # unidentified creditor.
    if majority_analysis["total_debt"] > 0 and not majority_analysis["achievable"]:
        if majority_analysis.get("indeterminate"):
            flags.append(RuleResult(
                rule_id="MAJORITY-INDETERMINATE",
                severity="flag",
                triggered=True,
                message=(
                    f"To approve the IVA, creditors holding at least "
                    f"£{majority_analysis['threshold']:,.2f} of the debt must vote in "
                    f"favour. So far, only £{majority_analysis['voting_debt']:,.2f} of "
                    f"confirmed support is in place, and "
                    f"£{majority_analysis['unknown_debt']:,.2f} of debt belongs to "
                    f"creditor(s) who have not yet been identified. The caseworker must "
                    "identify these creditor(s) before this vote can be relied upon, as "
                    "their support could still be enough to reach the required majority."
                ),
                threshold=float(majority_analysis["threshold"]),
                actual_value=float(majority_analysis["voting_debt"]),
            ))
        else:
            hard_blocks.append(RuleResult(
                rule_id="MAJORITY-IMPOSSIBLE",
                severity="hard_block",
                triggered=True,
                message=(
                    f"To approve the IVA, creditors holding at least "
                    f"£{majority_analysis['threshold']:,.2f} of the debt must vote in "
                    f"favour. Even if every undecided creditor voted yes, only "
                    f"£{majority_analysis['voting_debt_optimistic']:,.2f} of support "
                    "could be reached, which is not enough. This case cannot proceed as "
                    "an IVA unless more creditor support is found."
                ),
            ))
            overall = "blocked"

    # Material unidentified debt → manual review (REFERRED via flag). Independent of
    # the majority maths: any case with >=UNKNOWN_REFERRAL_PCT of total debt owed to
    # creditors the engine could not identify cannot be relied upon until resolved.
    _unknown_debt = majority_analysis.get("unknown_debt") or Decimal("0")
    _total_debt_maj = majority_analysis.get("total_debt") or Decimal("0")
    if _total_debt_maj > 0:
        _unknown_pct = float(_unknown_debt) / float(_total_debt_maj)
        if _unknown_pct >= UNKNOWN_REFERRAL_PCT:
            flags.append(RuleResult(
                rule_id="CREDITOR-UNIDENTIFIED-MATERIAL",
                severity="flag",
                triggered=True,
                message=(
                    f"£{float(_unknown_debt):,.2f} of the customer's debt "
                    f"({_unknown_pct * 100:.1f}% of the total) is owed to creditor(s) that "
                    "could not be identified. The caseworker must identify them before "
                    "relying on this assessment, because it is not known how they would "
                    "vote or whether any creditor-specific rules apply to them."
                ),
                threshold=float(UNKNOWN_REFERRAL_PCT * 100),
                actual_value=float(_unknown_pct * 100),
            ))

    recommended_solution = _derive_recommended_solution(hard_blocks, flags, _all_creditor_positions, c)
    tig_eligible = len(hard_blocks) == 0
    dmp_eligibility = _evaluate_dmp_eligibility(c)

    # SFS guideline comparison — non-blocking, appended to result
    from debt_app.sfs_calculator import derive_household_key, get_guideline_rate, apply_guideline_constraint
    from debt_app.models import ExpenditureGuideline

    sfs_breakdown = case_json.get('sfs_expenditure_breakdown', {})
    dependants = case_json.get('dependants', {})
    _sfs_adults = dependants.get('adults', 1) if isinstance(dependants, dict) else 1
    _sfs_children = dependants.get('children', 0) if isinstance(dependants, dict) else 0
    hh_key = derive_household_key(_sfs_adults, _sfs_children)

    guideline_map = {
        g.category: g
        for g in ExpenditureGuideline.objects.select_related('category_group').all()
    }

    sfs_results = []
    if not isinstance(sfs_breakdown, dict):
        sfs_breakdown = {}
    for category_slug, declared_pence in sfs_breakdown.items():
        guideline = guideline_map.get(category_slug)
        if not guideline:
            continue
        declared_pounds = (declared_pence or 0) / 100.0
        rate = get_guideline_rate(guideline, hh_key)
        constraint = apply_guideline_constraint(rate, guideline.min, guideline.max, declared_pounds)
        sfs_results.append({
            'category': category_slug,
            'label': guideline.label,
            'declared': declared_pounds,
            'hh_key': hh_key,
            **constraint,
        })

    return {
        "hard_blocks": hard_blocks,
        "flags": flags,
        "info": info,
        "passed": passed,
        "overall": overall,
        "overall_status": overall.upper(),
        "disposable_income": float(c["disposable_income"]),
        "total_unsecured_debt": float(c["total_debt"]),
        "total_secured_debt": float(c.get("total_secured_debt") or 0),
        "passes_all_hard_blocks": tig_eligible,
        "recommended_solution": recommended_solution,
        "dmp_eligibility": dmp_eligibility,
        "tig_eligible": tig_eligible,
        "creditor_positions": _all_creditor_positions,
        "council_positions": council_positions,
        "majority_analysis": majority_analysis,
        "dividend_analysis": dividend_analysis,
        "representatives_detected": detected_representatives,
        "representative_outcomes": representative_outcomes,
        "sfs_guideline_results": sfs_results,
        "sfs_household_key": hh_key,
        "credit_report_status": credit_report_status,
        "hmrc_is_creditor": c["hmrc_is_creditor"],
    }
