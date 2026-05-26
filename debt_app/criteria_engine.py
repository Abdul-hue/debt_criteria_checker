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
})

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


def _pass(rule_id: str, message: str = "Passed.", creditors: list = None) -> RuleResult:
    return RuleResult(rule_id=rule_id, severity="pass", triggered=False, message=message, creditors=creditors or [])


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
    gold_tx = case_json.get("gold_transactions") or []
    documents = case_json.get("documents") or []
    financial = case_json.get("financial_summary") or {}
    crm = case_json.get("crm_data") or {}
    client_info = case_json.get("clientInfo") or {}
    evidence_ledger = case_json.get("evidence_ledger") or []
    mortgage_details = case_json.get("mortgage_details") or []

    # --- Creditors ---
    from debt_app.helpers import normalise_debt_type, _SECURED_TYPES
    creditors = []
    for c in creditors_raw:
        raw_type = c.get("creditor_type", "") or c.get("debt_type", "") or c.get("debt_type_normalised", "")
        debt_type = normalise_debt_type(raw_type)
        balance = _parse_amount(c.get("balance", 0))

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
            "name": c.get("creditor_name", ""),
            "original_name": c.get("original_name", ""),
            "balance": balance,
            "crm_balance": Decimal(str(balance)),
            "creditor_type": raw_type,
            "debt_type_normalised": debt_type,
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
        })

    # --- Total debt: always computed from creditors (unsecured only) ---
    total_debt = sum(
        c["balance"] for c in creditors
        if c["debt_type_normalised"] not in _SECURED_TYPES
    )
    total_secured_debt = sum(
        c["balance"] for c in creditors
        if c["debt_type_normalised"] in _SECURED_TYPES
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
    link_creditors = [c for c in creditors if _in_set(c["name"], _LINK_NAMES)]
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
        # Property / equity
        "has_property": has_property,
        "property_value": property_value,          # TODO: missing from payload
        "available_equity": available_equity,       # None until property_value added
        "mortgage_balance": mortgage_balance,
        # Client
        "client_age": client_age,
        # Gambling
        "gambling_monthly": gambling_monthly,
        # Transaction lookups
        "gold_transactions": gold_tx,
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
        "full_and_final_from_savings": bool(case_json.get("full_and_final_from_savings", False)),
        "gambling_main_cause": bool(case_json.get("gambling_main_cause") or case_json.get("gambling_primary_cause") or crm.get("gambling_main_cause", False)),
        "income_deductions_active": bool(
            case_json.get("income_deductions_active")
            or case_json.get("benefit_income_has_deduction", False)
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
        "income_is_benefits_only": bool(case_json.get("income_is_benefits_only", False)),
        "receives_any_benefits": bool(case_json.get("receives_any_benefits", False)),
        "gamstop_registered": bool(case_json.get("gamstop_registered", False)),
        "benefit_income_amount": case_json.get("benefit_income_amount"),
        "aoe_in_place": bool(case_json.get("aoe_in_place", False)),
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
            message=f"Total debt £{actual:,.2f} is below the £{threshold:,.2f} minimum.",
            threshold=threshold, actual_value=actual,
        )
    return _pass("TIG-01", f"Total debt £{actual:,.2f} meets the £{threshold:,.2f} minimum.")


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
                message="Disposable income is below £100.00 because no income data has been entered into the Fact Find. Please complete the financial section.",
                threshold=threshold, actual_value=actual,
            )
        
        return RuleResult(
            rule_id="TIG-02", severity="hard_block", triggered=True,
            message=f"Disposable income £{actual:,.2f}/month is below the £{threshold:,.2f} minimum.",
            threshold=threshold, actual_value=actual,
        )
    return _pass("TIG-02", f"Disposable income £{actual:,.2f}/month meets the £{threshold:,.2f} minimum.")


def _tig_03(c: dict) -> RuleResult:
    """TIG-03: SFS guidelines — expenditure must comply with Standard Financial Statement limits."""
    sfs = c["sfs_expenditure_breakdown"]
    if not sfs:
        return _pass("TIG-03", "SFS expenditure breakdown not provided — rule not evaluated.")

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
        return RuleResult(
            rule_id="TIG-03", severity="flag", triggered=True,
            message=(
                f"SFS guideline breaches detected in: {', '.join(breaches)}. "
                "Expenditure must comply with SFS limits or be justified in the proposal."
            ),
            threshold=0.0,
            actual_value=float(len(breaches)),
        )
    return _pass("TIG-03", "All expenditure categories within SFS guidelines.")


def _tig_04(c: dict) -> RuleResult:
    """TIG-04: DLA/PIP income present but no disability expenses claimed — flag."""
    disability_income = c["disability_income"]
    if not disability_income:
        return _pass("TIG-04", "No DLA/PIP income — TIG-04 not applicable.")
    disability_expenses = c["disability_expenses"]
    if not disability_expenses:
        return RuleResult(
            rule_id="TIG-04", severity="flag", triggered=True,
            message=(
                "Client receives DLA/PIP income but no disability-related expenses are recorded. "
                "If income is being used for disability needs, corresponding expenses must be included in the I&E."
            ),
        )
    return _pass("TIG-04", "DLA/PIP income present and disability expenses recorded.")


def _tig_05(c: dict) -> RuleResult:
    """TIG-05: Wage slip required — one per employment income source, dated within 90 days."""
    income_source = c["income_source"]
    has_job = c["has_job"]
    is_employed = c.get("is_employed", False)

    # CIS income is validated by TIG-09 (CIS invoice) — wage slip not required for CIS
    if (income_source not in ("payslip", "employed", "salary")
            and not has_job
            and not is_employed):
        return _pass("TIG-05", "Not employed — wage slip not required.")

    payslip_docs = c["payslip_docs"]
    if not payslip_docs:
        return RuleResult(
            rule_id="TIG-05", severity="hard_block", triggered=True,
            message="No wage slip uploaded. At least one required per employment income source.",
        )

    payslip_date = c["payslip_date"]
    if payslip_date is None:
        return RuleResult(
            rule_id="TIG-05", severity="hard_block", triggered=True,
            message="Wage slip dated None is older than 90 days.",
        )

    if _days_since(payslip_date, c["assessment_date"]) > 90:
        return RuleResult(
            rule_id="TIG-05", severity="hard_block", triggered=True,
            message=f"Wage slip dated {payslip_date} is older than 90 days.",
        )

    return _pass("TIG-05", "Wage slip present and dated within 90 days.")


def _tig_06(c: dict) -> RuleResult:
    """TIG-06: Benefit income requires award letter or current-year bank statement."""
    if c["income_source"] not in ("benefits", "universal_credit", "uc"):
        return _pass("TIG-06", "No benefit income — benefit proof not required.")

    if c["benefit_letter_docs"]:
        return _pass("TIG-06", "Benefit award letter present.")

    # Accept a bank statement dated in the current calendar year
    bank_date = c["bank_stmt_date"]
    if bank_date and str(c["assessment_date"].year) in str(bank_date):
        return _pass("TIG-06", "Current-year bank statement accepted as benefit proof.")

    return RuleResult(
        rule_id="TIG-06", severity="hard_block", triggered=True,
        message="Benefit income present but no award letter or current-year bank statement uploaded.",
    )


def _tig_07(c: dict) -> RuleResult:
    """TIG-07: UC income requires UC journal dated within 90 days."""
    if c["income_source"] not in ("uc", "universal_credit"):
        return _pass("TIG-07", "No UC income — UC journal not required.")

    if not c["has_uc_journal"]:
        return RuleResult(
            rule_id="TIG-07", severity="hard_block", triggered=True,
            message="UC income present but has_uc_journal is false.",
        )

    return _pass("TIG-07", "UC journal present.")


def _tig_08(c: dict) -> RuleResult:
    """TIG-08: Self-employed requires BOTH tax return AND at least 1 month business banking."""
    if c["income_source"] != "self_employed":
        return _pass("TIG-08", "Not self-employed — self-employed proof not required.")

    has_tax_return = len(c["tax_return_docs"]) > 0
    has_business_bank_statement = len(c["bank_stmt_docs"]) >= 1

    # EXCEL_CRITERIA_REFERENCE.md — TIG: self-employed requires BOTH tax return AND bank statement
    if not (has_tax_return and has_business_bank_statement):
        missing = []
        if not has_tax_return:
            missing.append("tax return")
        if not has_business_bank_statement:
            missing.append("business bank statement")
        return RuleResult(
            rule_id="TIG-08", severity="flag", triggered=True,
            message=f"Self-employed income evidence incomplete — missing: {', '.join(missing)}.",
        )

    return _pass("TIG-08", "Tax return and business bank statement both present.")


def _tig_09(c: dict) -> RuleResult:
    """TIG-09: CIS income requires invoice showing 20% tax deduction."""
    if c["income_source"] != "cis":
        return _pass("TIG-09", "Not CIS — CIS proof not required.")

    cis_docs = c["cis_invoice_docs"]
    if not cis_docs:
        return RuleResult(
            rule_id="TIG-09", severity="hard_block", triggered=True,
            message="CIS income present but no CIS invoice uploaded.",
        )

    # Check extracted_data for 20% deduction flag if available
    first = cis_docs[0].get("extracted_data") or {}
    if first and first.get("shows_deduction") is False:
        return RuleResult(
            rule_id="TIG-09", severity="hard_block", triggered=True,
            message="CIS invoice present but does not show 20% tax deduction.",
        )

    return _pass("TIG-09", "CIS invoice with deduction present.")


def _tig_10(c: dict) -> RuleResult:
    """TIG-10: Each debt must have supporting proof (hard block >= £1,000; flag < £1,000)."""
    creditors = c.get("creditors", [])
    evidence_ledger = c.get("evidence_ledger", [])

    # Map evidence ledger by ref for fast lookup
    evidence_map = {e.get("ref"): e for e in evidence_ledger if e.get("ref")}

    hard_blocks = []
    flags = []
    verified_count = 0
    creditors_detail = []

    from debt_app.helpers import DEBT_TYPE_COUNCIL_TAX, DEBT_TYPE_PCN, DEBT_TYPE_HOUSING_BENEFIT, CREDITOR_ALIAS_MAP, normalise_creditor_name
    from debt_app.models import CreditorCriteria
    _COUNCIL_TYPES = frozenset({DEBT_TYPE_COUNCIL_TAX, DEBT_TYPE_PCN, DEBT_TYPE_HOUSING_BENEFIT})

    # Pre-load representative info once — keyed by canonical creditor name
    _criteria_map = {
        c.creditor_name: (c.representative or 'NONE', c.status or 'ACCEPT')
        for c in CreditorCriteria.objects.filter(is_active=True).only(
            'creditor_name', 'representative', 'status'
        )
    }

    for creditor in creditors:
        # Council debts are evaluated by _check_council_rules, not by proof-of-debt evidence
        if creditor.get("debt_type_normalised") in _COUNCIL_TYPES:
            continue

        balance = creditor.get("balance", 0)
        # Edge case: Creditor with balance = 0: skip (no evidence needed)
        if balance <= 0:
            continue

        # Edge case: Creditor with no linked_creditor field: treat as missing evidence
        ref = creditor.get("linked_creditor")
        evidence = evidence_map.get(ref) if ref else None

        # Evidence entry exists but is_verified = False: Treat same as missing evidence
        is_verified = False
        if evidence and evidence.get("is_verified") is True:
            is_verified = True

        name = creditor.get("name", "Unknown Creditor")
        # Resolve raw Aryza name → canonical DB name via alias map before lookup
        canonical = CREDITOR_ALIAS_MAP.get(normalise_creditor_name(name)) or name
        _rep, _cstatus = _criteria_map.get(canonical) or _criteria_map.get(name, ('NONE', None))

        creditors_detail.append({
            "name": name,
            "canonical_name": canonical if canonical != name else None,
            "balance": balance,
            "is_verified": is_verified,
            "evidence_status": "verified" if is_verified else ("missing" if not ref else "unverified"),
            "debt_type": creditor.get("creditor_type") or creditor.get("debt_type_normalised") or "",
            "representative": _rep,
            "creditor_status": _cstatus,
        })

        if not is_verified:
            name = creditor.get("name", "Unknown Creditor")
            if balance >= 1000:
                hard_blocks.append(f"{name} (£{balance:,.2f})")
            else:
                flags.append(name)
        else:
            verified_count += 1

    if hard_blocks:
        return RuleResult(
            rule_id="TIG-10",
            severity="hard_block",
            triggered=True,
            message=f"Hard block: No linked verified evidence for debts >= £1,000: {', '.join(hard_blocks)}.",
            creditors=creditors_detail,
        )

    if flags:
        return RuleResult(
            rule_id="TIG-10",
            severity="flag",
            triggered=True,
            message=f"Flag: No linked verified evidence for: {', '.join(flags)}.",
            creditors=creditors_detail,
        )

    # If all creditors have verified evidence: return pass with count
    return _pass("TIG-10", f"Verified evidence present for all {verified_count} creditors.", creditors=creditors_detail)


def _tig_11(c: dict) -> RuleResult:
    """TIG-11: Bank statement verification — presence, freshness, account holder."""
    # No bank statement at all
    if not c["bank_stmt_docs"]:
        return RuleResult(
            rule_id="TIG-11", severity="hard_block", triggered=True,
            message="No valid bank statement uploaded.",
        )

    # Statement older than 90 days
    bank_date = c["bank_stmt_date"]
    if bank_date is None:
        return RuleResult(
            rule_id="TIG-11", severity="hard_block", triggered=True,
            message="Bank statement dated None is older than 90 days.",
        )

    if _days_since(bank_date, c["assessment_date"]) > 90:
        return RuleResult(
            rule_id="TIG-11", severity="hard_block", triggered=True,
            message=f"Bank statement dated {bank_date} is older than 90 days.",
        )

    # No account holder name
    if not c["bank_stmt_holder"]:
        return RuleResult(
            rule_id="TIG-11", severity="hard_block", triggered=True,
            message="Bank statement extracted_data has no account_holder name.",
        )

    return _pass("TIG-11", "Bank statement valid, fresh and account holder present.")


def _tig_11_gambling(c: dict) -> RuleResult:
    """TIG-11-GAMBLING: Gambling spend — hard block >£1,000/month, GAMSTOP flag >£200/month.

    Runs independently of TIG-11 bank statement check so gambling is always evaluated
    regardless of whether a bank statement document has been uploaded.
    """
    gm = c["gambling_monthly"]
    # EXCEL_CRITERIA_REFERENCE.md — TIG Gambling: under £1,000 is allowed; £1,000+ is hard block
    if gm >= 1000:
        return RuleResult(
            rule_id="TIG-11-GAMBLING", severity="hard_block", triggered=True,
            message=f"Gambling spend £{gm:,.2f}/month meets or exceeds £1,000 hard block threshold.",
            threshold=1000.0, actual_value=gm,
        )
    if gm > 200:
        if c.get("gamstop_registered"):
            return RuleResult(
                rule_id="TIG-11-GAMBLING", severity="flag", triggered=True,
                message=f"Gambling spend £{gm:,.2f}/month exceeds £200. Client is GAMSTOP registered — confirm registration is active.",
                threshold=200.0, actual_value=gm,
            )
        return RuleResult(
            rule_id="TIG-11-GAMBLING", severity="flag", triggered=True,
            message=f"Gambling spend £{gm:,.2f}/month exceeds £200. GAMSTOP registration proof required.",
            threshold=200.0, actual_value=gm,
        )
    if gm > 0:
        return RuleResult(
            rule_id="TIG-11-GAMBLING", severity="flag", triggered=True,
            message=f"Gambling transactions detected (£{gm:,.2f}). Review with client.",
            threshold=0.0, actual_value=gm,
        )
    return _pass("TIG-11-GAMBLING", "No gambling concerns.")


def _tig_12(c: dict) -> RuleResult:
    """TIG-12: Third-party contribution requires signed letter."""
    # EXCEL_CRITERIA_REFERENCE.md — stub replaced;
    # triggered=True without evaluation is misleading
    tp = c["third_party_contribution"]
    if tp is None:
        return RuleResult(
            rule_id="TIG-12", severity="info", triggered=False,
            message="[RULE-CANNOT-EVALUATE] Rule TIG-12 cannot be evaluated — third_party_contribution not present in payload",
        )
    if not tp:
        return _pass("TIG-12", "No third-party contribution — letter not required.")
    # If we have a value but no signed_letter flag, block
    if not tp.get("signed_letter_present", False):
        return RuleResult(
            rule_id="TIG-12", severity="hard_block", triggered=True,
            message="Third-party contribution present but no signed letter uploaded (must include name, address, signature, date, contact, amount, duration).",
        )
    return _pass("TIG-12", "Third-party signed letter present.")


def _tig_13(c: dict) -> RuleResult:
    """TIG-13: Previous IVA requires termination report."""
    if not c["previous_iva"]:
        return _pass("TIG-13", "No previous IVA — termination report not required.")
    if not c["termination_report_docs"]:
        return RuleResult(
            rule_id="TIG-13", severity="hard_block", triggered=True,
            message="Previous IVA on record but no termination report uploaded.",
        )
    return _pass("TIG-13", "Termination report present.")


def _tig_15_1(c: dict) -> RuleResult:
    """TIG-15.1: HMRC majority creditor + income/benefit deductions already being taken."""
    if not c["hmrc_is_majority"]:
        return _pass("TIG-15.1", "HMRC is not the majority creditor.")
    if not c["income_deductions_active"]:
        return _pass("TIG-15.1", "No income/benefit deductions active — HMRC majority check passed.")
    return RuleResult(
        rule_id="TIG-15.1", severity="hard_block", triggered=True,
        message=(
            "HMRC is the majority creditor and income/benefit deductions are already being taken. "
            "HMRC will reject the IVA."
        ),
    )


def _tig_15_2(c: dict) -> RuleResult:
    """TIG-15.2: HMRC majority creditor + previous IVA or bankruptcy."""
    if not c["hmrc_is_majority"]:
        return _pass("TIG-15.2", "HMRC is not the majority creditor.")
    if c["previous_iva"] or c["previous_iva_failed"]:
        return RuleResult(
            rule_id="TIG-15.2", severity="hard_block", triggered=True,
            message="HMRC is majority creditor and client has a previous IVA or bankruptcy. HMRC will reject.",
        )
    return _pass("TIG-15.2", "HMRC majority creditor check passed — no previous IVA or bankruptcy.")


def _tig_15_3(c: dict) -> RuleResult:
    """TIG-15.3: HMRC self-assessment debt + late/missing tax submissions.
    Applies to self-employed clients AND PAYE clients with SA debt (landlords, investors).
    """
    if not c["hmrc_is_creditor"]:
        return _pass("TIG-15.3", "No HMRC creditor.")
    # Detect SA debt from creditor_type or creditor name — covers PAYE clients with SA returns
    has_sa_debt = any(
        "self assessment" in (cr["creditor_type"] or "").lower()
        or "self_assessment" in (cr["creditor_type"] or "").lower()
        or "income tax" in (cr["creditor_type"] or "").lower()
        or "self assessment" in cr["name"].lower()
        for cr in c["hmrc_creditors"]
    )
    if not has_sa_debt and c["income_source"] != "self_employed":
        return _pass("TIG-15.3", "No self-assessment debt detected — TIG-15.3 not applicable.")
    # Check for tax return as proxy for up-to-date submissions
    if not c["tax_return_docs"]:
        return RuleResult(
            rule_id="TIG-15.3", severity="hard_block", triggered=True,
            message="HMRC self-assessment debt present but no tax return uploaded.",
        )
    return _pass("TIG-15.3", "Tax return present — submission confirmed.")


def _tig_15_4(c: dict) -> RuleResult:
    """TIG-15.4: Available property equity > HMRC debt balance."""
    # EXCEL_CRITERIA_REFERENCE.md — stub replaced;
    # triggered=True without evaluation is misleading
    if not c["hmrc_is_creditor"]:
        return _pass("TIG-15.4", "No HMRC creditor.")
    if c["available_equity"] is None:
        return RuleResult(
            rule_id="TIG-15.4", severity="info", triggered=False,
            message="[RULE-CANNOT-EVALUATE] Rule TIG-15.4 cannot be evaluated — property_value not present in payload",
        )
    if c["available_equity"] > c["hmrc_balance"]:
        return RuleResult(
            rule_id="TIG-15.4", severity="hard_block", triggered=True,
            message=f"Available equity £{c['available_equity']:,.2f} exceeds HMRC balance £{c['hmrc_balance']:,.2f}.",
            threshold=c["hmrc_balance"], actual_value=c["available_equity"],
        )
    return _pass("TIG-15.4", "Equity does not exceed HMRC balance.")


def _tig_15_5(c: dict) -> RuleResult:
    """TIG-15.5: Bankruptcy return > IVA payments — hard block if bankruptcy yields more."""
    if c["bankruptcy_return"] is None:
        return _pass("TIG-15.5", "Bankruptcy return not provided — rule not applicable.")
    br = _parse_amount(c["bankruptcy_return"])
    # EXCEL_CRITERIA_REFERENCE.md — IVA term from case payload, not hardcoded
    iva_return = c["disposable_income"] * c.get("iva_term_months", 60) * 0.75
    if br > iva_return:
        return RuleResult(
            rule_id="TIG-15.5", severity="hard_block", triggered=True,
            message=f"Bankruptcy return £{br:,.2f} exceeds projected IVA return £{iva_return:,.2f}.",
            threshold=iva_return, actual_value=br,
        )
    return _pass("TIG-15.5", "IVA return exceeds bankruptcy return.")


def _tig_15_6(c: dict) -> RuleResult:
    """TIG-15.6: Full & Final funded from savings accumulated while debts were unpaid — hard block."""
    if not c["full_and_final_from_savings"]:
        return _pass("TIG-15.6", "No savings-funded F&F arrangement identified.")
    return RuleResult(
        rule_id="TIG-15.6", severity="hard_block", triggered=True,
        message=(
            "Full & Final settlement funded from savings accumulated while debts were unpaid. "
            "Cannot proceed with IVA — this constitutes an antecedent concern."
        ),
    )


def _tig_15_7(c: dict) -> RuleResult:
    """TIG-15.7: SEISS fraud debt — always blocks, cannot be included in IVA."""
    if c["seiss_debt_flag"] is None:
        return _pass("TIG-15.7", "No SEISS debt flag provided — rule not applicable.")
    if c["seiss_debt_flag"]:
        return RuleResult(
            rule_id="TIG-15.7", severity="hard_block", triggered=True,
            message="SEISS fraud debt identified. Cannot be included in an IVA under any circumstances.",
        )
    return _pass("TIG-15.7", "No SEISS fraud debt.")


def _tig_15_8(c: dict) -> RuleResult:
    """TIG-15.8: HMRC removes client name, chases other party — info only, does not block."""
    if not c["hmrc_is_creditor"]:
        return _pass("TIG-15.8", "No HMRC creditor.")
    return RuleResult(
        rule_id="TIG-15.8", severity="info", triggered=False,
        message="HMRC joint debt note: if HMRC removes client name and chases other party, this does not block the IVA.",
    )


def _tig_15_9(c: dict) -> RuleResult:
    """TIG-15.9: HMRC debt < £4,000 — HMRC will not vote unless rejecting. Info only."""
    threshold = 4000.0
    if not c["hmrc_is_creditor"]:
        return _pass("TIG-15.9", "No HMRC creditor.")
    if c["hmrc_balance"] < threshold:
        return RuleResult(
            rule_id="TIG-15.9", severity="info", triggered=False,
            message=f"HMRC debt £{c['hmrc_balance']:,.2f} is under £{threshold:,.2f} — HMRC will not vote unless rejecting.",
            threshold=threshold, actual_value=c["hmrc_balance"],
        )
    return _pass("TIG-15.9", f"HMRC debt £{c['hmrc_balance']:,.2f} is above the £{threshold:,.2f} info threshold.")


def _tig_15_10(c: dict) -> RuleResult:
    """TIG-15.10: Client's only income is benefits AND HMRC is a creditor."""
    if not c["hmrc_is_creditor"]:
        return _pass("TIG-15.10", "No HMRC creditor.")
    benefits_only = (
        c.get("income_is_benefits_only", False)
        or c["income_source"] in ("benefits", "universal_credit", "uc")
    )
    if benefits_only:
        return RuleResult(
            rule_id="TIG-15.10", severity="hard_block", triggered=True,
            message="Client's sole income is benefits and HMRC is a creditor — IVA not viable.",
        )
    return _pass("TIG-15.10", "Client has non-benefit income — TIG-15.10 not triggered.")


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
            "HMRC is a creditor — HMRC's agreement to the IVA cannot be assumed. "
            "Specific HMRC confirmation required before proposing."
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
        for cr in c["hmrc_creditors"]
    )
    if not has_vat_debt:
        return _pass("TIG-HMRC-VAT-TRADING", "No VAT arrears present.")
    if not c["is_currently_trading"]:
        return _pass("TIG-HMRC-VAT-TRADING", "Client is not currently trading.")
    # is_currently_trading is True; check for arrangement
    if c["has_vat_arrangement"]:
        return _pass("TIG-HMRC-VAT-TRADING", "VAT payment arrangement is in place.")
    return RuleResult(
        rule_id="TIG-HMRC-VAT-TRADING",
        severity="hard_block",
        triggered=True,
        message=(
            "VAT arrears present and client is still trading without a payment arrangement — "
            "HMRC will not accept IVA. Trading must have ceased or an arrangement must be in place."
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
        for cr in c["hmrc_creditors"]
    )
    if not has_paye_debt:
        return _pass("TIG-HMRC-PAYE-OBLIGATIONS", "No PAYE arrears present.")
    paye_current = c["employer_paye_obligations_current"]
    if paye_current is None:
        return RuleResult(
            rule_id="TIG-HMRC-PAYE-OBLIGATIONS",
            severity="flag",
            triggered=True,
            message=(
                "PAYE arrears present — employer PAYE obligations must be current before IVA can be proposed. "
                "Unable to verify PAYE obligations status."
            ),
        )
    if not paye_current:
        return RuleResult(
            rule_id="TIG-HMRC-PAYE-OBLIGATIONS",
            severity="hard_block",
            triggered=True,
            message=(
                "PAYE arrears present — employer PAYE obligations must be current before IVA can be proposed."
            ),
        )
    return _pass("TIG-HMRC-PAYE-OBLIGATIONS", "PAYE obligations are current.")


def _tig_hmrc_05(c: dict) -> RuleResult:
    """TIG-HMRC-05: Tax credit overpayment debt — treated as priority; confirm DWP deductions."""
    # EXCEL_CRITERIA_REFERENCE.md — HMRC Rule 5
    if not c["hmrc_is_creditor"]:
        return _pass("TIG-HMRC-TAX-CREDITS", "No HMRC creditor.")
    has_tc_debt = any(
        # EXCEL_CRITERIA_REFERENCE.md — HMRC Rule 5: tax credit debt type matching
        "tax credit" in (cr["creditor_type"] or "").lower()
        or "tax_credit" in (cr["creditor_type"] or "").lower()
        for cr in c["hmrc_creditors"]
    )
    if not has_tc_debt:
        return _pass("TIG-HMRC-TAX-CREDITS", "No tax credit overpayment debt present.")
    return RuleResult(
        rule_id="TIG-HMRC-TAX-CREDITS",
        severity="flag",
        triggered=True,
        message=(
            "Tax credit overpayment debt present — treated as priority debt. "
            "Confirm whether DWP is already making deductions before including in IVA."
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
        return _pass("TIG-HMRC-NI-CLASS", "No National Insurance debt present.")
    return RuleResult(
        rule_id="TIG-HMRC-NI-CLASS",
        severity="flag",
        triggered=True,
        message=(
            "National Insurance debt present — confirm whether Class 2 and/or Class 4 "
            "are included in the IVA or treated separately."
        ),
    )


def _tig_hmrc_07(c: dict) -> RuleResult:
    """TIG-HMRC-07: Client is currently trading with HMRC debt — specific written confirmation required."""
    # EXCEL_CRITERIA_REFERENCE.md — HMRC Rule 7
    if not c["hmrc_is_creditor"]:
        return _pass("TIG-HMRC-ONGOING-TRADING", "No HMRC creditor.")
    if not c["is_currently_trading"]:
        return _pass("TIG-HMRC-ONGOING-TRADING", "Client is not currently trading.")
    return RuleResult(
        rule_id="TIG-HMRC-ONGOING-TRADING",
        severity="flag",
        triggered=True,
        message=(
            "Client is currently trading with HMRC debt — HMRC rarely accepts IVAs in this situation. "
            "Specific written confirmation from HMRC required before proposing."
        ),
    )


def _tig_hmrc_08(c: dict) -> RuleResult:
    """TIG-HMRC-08: Antecedent/preferential payment to HMRC — hard block (TIG-level, WATCH-independent)."""
    # EXCEL_CRITERIA_REFERENCE.md — HMRC Rule 8
    # _watch_22_13 still catches antecedent transactions for non-HMRC creditors when WATCH is present.
    if not c["hmrc_is_creditor"]:
        return _pass("TIG-HMRC-ANTECEDENT", "No HMRC creditor.")
    at = c["antecedent_transactions"]
    if at:
        return RuleResult(
            rule_id="TIG-HMRC-ANTECEDENT",
            severity="hard_block",
            triggered=True,
            message=(
                "Preferential/antecedent payment to HMRC detected — hard reject. "
                "Potential clawback risk makes IVA non-viable."
            ),
        )
    return _pass("TIG-HMRC-ANTECEDENT", "No antecedent transactions to HMRC identified.")


def _tig_16(c: dict) -> RuleResult:
    """TIG-16: Property equity > £5,000 — hard block."""
    has_property = c.get("has_property", False)
    pv = _parse_amount(c.get("property_value", 0))

    # Case 3: owns_property is True AND property_value is 0.0 or None
    if has_property and pv <= 0:
        return RuleResult(
            rule_id="TIG-16", severity="flag", triggered=True,
            message=(
                "Client owns property but no valuation found in system. "
                "Manual check required before proceeding."
            )
        )

    # Case 1: owns_property is False AND property_value is 0.0
    if not has_property:
        return _pass("TIG-16", "Client does not own property.")

    # Case 2: owns_property is True AND property_value > 0.0
    equity = pv - c["mortgage_balance"]
    threshold = 5000.0
    if equity > threshold:
        return RuleResult(
            rule_id="TIG-16", severity="hard_block", triggered=True,
            message=(
                f"Equity £{equity:,.2f} exceeds threshold "
                f"£{threshold:,.2f}. Client has sufficient equity to repay debts — "
                "IVA is not appropriate. Remortgage or asset realisation should be explored."
            ),
            threshold=threshold, actual_value=equity,
        )
    return _pass("TIG-16", f"Equity £{equity:,.2f} does not exceed £{threshold:,.2f}.")


def _tig_17(c: dict) -> RuleResult:
    """TIG-17: Council majority creditor with active income/benefit deductions — flag."""
    if not c["council_is_majority"]:
        return _pass("TIG-17", "Council is not the majority creditor.")
    return RuleResult(
        rule_id="TIG-17", severity="flag", triggered=True,
        message="Council creditor holds >25% of debt by value — a blocking minority under the 75% rule. Confirm whether income or benefit deductions are being taken. Case-by-case review required.",
    )


def _tig_18(c: dict) -> RuleResult:
    """TIG-18: Total spend in last 2 months >= monthly income (excl. payday loans) — flag only."""
    monthly_income = c["total_income"]
    spend = c["total_spend_2mo"]
    if monthly_income <= 0:
        return _pass("TIG-18", "No income data — TIG-18 skipped.")
    if spend >= monthly_income:
        return RuleResult(
            rule_id="TIG-18", severity="flag", triggered=True,
            message=f"Total spend in last 2 months £{spend:,.2f} equals or exceeds monthly income £{monthly_income:,.2f}. Assessor review required.",
            threshold=monthly_income, actual_value=spend,
        )
    return _pass("TIG-18", f"Recent spend £{spend:,.2f} is within monthly income £{monthly_income:,.2f}.")


def _tig_19(c: dict) -> RuleResult:
    """TIG-19: Shop Direct purchases within 3 months of statement date — hard block."""
    if c["shop_direct_tx_3mo"]:
        return RuleResult(
            rule_id="TIG-19", severity="hard_block", triggered=True,
            # EXCEL_CRITERIA_REFERENCE.md — TIG Shop Direct: 3-month spend = hard reject
            message=f"{len(c['shop_direct_tx_3mo'])} Shop Direct / Very / Littlewoods transaction(s) in the last 3 months.",
        )
    return _pass("TIG-19", "No recent Shop Direct transactions.")


def _tig_19_review(c: dict) -> RuleResult:
    """TIG-SHOP-DIRECT-4MO-REVIEW: Shop Direct spend in the 3–4 month window only — flag for review."""
    # EXCEL_CRITERIA_REFERENCE.md — TIG Shop Direct: 4-month window = flag for review
    if c["shop_direct_tx_4mo"] and not c["shop_direct_tx_3mo"]:
        return RuleResult(
            rule_id="TIG-SHOP-DIRECT-4MO-REVIEW", severity="flag", triggered=True,
            message="Shop Direct spend detected in the 3–4 month window — flag for caseworker review",
        )
    return _pass("TIG-SHOP-DIRECT-4MO-REVIEW", "No Shop Direct spend in the 3–4 month window only.")


def _tig_19_1(c: dict) -> RuleResult:
    """TIG-19.1: Shop Direct account < 6 months old — hard block."""
    for creditor in c["creditors"]:
        if not _in_set(creditor["name"], _SHOP_DIRECT_NAMES):
            continue
        age = creditor.get("account_age_months")
        if age is not None and age < 6:
            return RuleResult(
                rule_id="TIG-19.1", severity="hard_block", triggered=True,
                message=f"{creditor['name']}: account is only {age} months old (minimum 6 months required).",
                threshold=6.0, actual_value=float(age),
            )
    return _pass("TIG-19.1", "No Shop Direct account under 6 months old.")


def _tig_20(c: dict) -> RuleResult:
    """TIG-20: Creation purchases within 3 months — flag (TIG-20.1 is the hard block)."""
    if c["creation_tx_4mo"]:
        return RuleResult(
            rule_id="TIG-20", severity="flag", triggered=True,
            message=f"{len(c['creation_tx_4mo'])} Creation / Sygma / Laser transaction(s) in the last 4 months. See TIG-20.1.",
        )
    return _pass("TIG-20", "No recent Creation / Sygma / Laser transactions.")


def _tig_20_1(c: dict) -> RuleResult:
    """TIG-20.1: Recent spend with Creation / Sygma / Laser — hard block, no trial cases.

    Excel source: 'PLEASE CAN WE NOT RUN ANY FURTHER TRIALS ON RECENT SPEND WITH
    SYGMA / CREATION / LASER REGARDLESS OF THE REASON.'
    The block is on recent SPEND only; having a dormant Creation account is not a block.
    """
    if c["creation_tx_4mo"]:
        return RuleResult(
            rule_id="TIG-20.1", severity="hard_block", triggered=True,
            message="Recent spend detected with Creation / Sygma / Laser. Hard block — no trial cases accepted.",
        )
    return _pass("TIG-20.1", "No recent Creation / Sygma / Laser spend.")


def _tig_21_1(c: dict) -> RuleResult:
    """TIG-21.1: Link Financial creditor — must confirm Mid SFS guidelines used."""
    if not c["link_is_creditor"]:
        return _pass("TIG-21.1", "Link Financial is not a creditor.")
    return RuleResult(
        rule_id="TIG-21.1", severity="flag", triggered=True,
        message="Link Financial is a creditor. Confirm Mid SFS guidelines have been applied.",
        threshold=0.0,
        actual_value=float(c["link_balance"]),
    )


def _tig_21_2(c: dict) -> RuleResult:
    """TIG-21.2: total_debt < £12,000 AND Link Financial is a creditor — hard block."""
    if not c["link_is_creditor"]:
        return _pass("TIG-21.2", "Link Financial is not a creditor.")
    threshold = 12000.0
    actual = c["total_debt"]
    if actual < threshold:
        return RuleResult(
            rule_id="TIG-21.2", severity="hard_block", triggered=True,
            message=f"Total debt £{actual:,.2f} is below the £{threshold:,.2f} minimum required when Link Financial is a creditor.",
            threshold=threshold, actual_value=actual,
        )
    return _pass("TIG-21.2", f"Total debt £{actual:,.2f} meets Link Financial minimum.")


def _tig_21_3(c: dict) -> RuleResult:
    """TIG-21.3: Property equity > Link Financial balance — hard block."""
    if not c["link_is_creditor"]:
        return _pass("TIG-21.3", "Link Financial is not a creditor.")

    has_property = c.get("has_property", False)
    pv = _parse_amount(c.get("property_value", 0))

    # Edge case: owns_property is True but property_value is unknown
    if has_property and pv <= 0:
        return RuleResult(
            rule_id="TIG-21.3", severity="flag", triggered=True,
            message=(
                "Client owns property but no valuation found in system. "
                "Manual check required before proceeding."
            )
        )

    if not has_property:
        return _pass("TIG-21.3", "Client does not own property.")

    if c["available_equity"] is None:
        return RuleResult(
            rule_id="TIG-21.3", severity="info", triggered=False,
            message="[RULE-CANNOT-EVALUATE] Rule TIG-21.3 cannot be evaluated — property_value not present in payload",
        )
    if c["available_equity"] > c["link_balance"]:
        return RuleResult(
            rule_id="TIG-21.3", severity="hard_block", triggered=True,
            message=f"Available equity £{c['available_equity']:,.2f} exceeds Link Financial balance £{c['link_balance']:,.2f}.",
            threshold=c["link_balance"], actual_value=c["available_equity"],
        )
    return _pass("TIG-21.3", "Equity does not exceed Link Financial balance.")


def _tig_21_4(c: dict) -> RuleResult:
    """TIG-21.4: Benefits > 10% of household income AND Link Financial is a creditor."""
    if not c["link_is_creditor"]:
        return _pass("TIG-21.4", "Link Financial is not a creditor.")
    total_income = c["total_income"]
    if total_income <= 0:
        return _pass("TIG-21.4", "No income data — TIG-21.4 skipped.")
    
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
            message=f"Benefits represent {benefit_pct:.0f}% of household income, exceeding the {threshold:.0f}% limit with Link Financial as creditor.",
            threshold=threshold, actual_value=benefit_pct,
        )
    return _pass("TIG-21.4", "Benefits within 10% threshold.")


def _tig_21_5(c: dict) -> RuleResult:
    """
    TIG-21.5: Previous IVA failure evaluation for Link Financial.
    - Pass if no previous IVA or completed successfully.
    - Flag if failed due to breach/arrears (requires discretion).
    - Hard block if terminated due to fraud/misrepresentation.
    """
    if not c["link_is_creditor"]:
        return _pass("TIG-21.5", "Link Financial is not a creditor.")

    if not c["previous_iva"]:
        return _pass("TIG-21.5", "No previous IVA — TIG-21.5 not triggered.")

    _raw_reason = c.get("previous_iva_failed_reason")
    if _raw_reason is None and c.get("previous_iva_failed"):
        _raw_reason = "unknown_reason"
    reason = (_raw_reason or "").lower()

    # 1. Pass if no failure reason or explicitly completed
    if not reason or "completed" in reason:
        return _pass("TIG-21.5", "Previous IVA on record but no failure reason detected.")

    # 2. Hard block if terminated due to fraud or misrepresentation
    if "fraud" in reason or "misrepresentation" in reason:
        return RuleResult(
            rule_id="TIG-21.5", severity="hard_block", triggered=True,
            message=f"Previous IVA terminated due to fraud or misrepresentation: '{reason}'. Link Financial will reject.",
        )

    # 3. Flag if failed due to client breach or missed payments (arrears)
    breach_keywords = ["breach", "arrears", "missed", "payment", "contribution", "default"]
    if any(kw in reason for kw in breach_keywords):
        return RuleResult(
            rule_id="TIG-21.5", severity="flag", triggered=True,
            message=f"Previous IVA failed due to arrears/breach: '{reason}'. Link Financial requires creditor discretion.",
        )

    # 4. Default to flag for other failures
    return RuleResult(
        rule_id="TIG-21.5", severity="flag", triggered=True,
        message=f"Previous IVA failed for reason: '{reason}'. Link Financial review required.",
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
                "Vulnerability has been claimed but no supporting evidence has been uploaded. "
                "Speak to Tom or Debra before proceeding. Evidence must be obtained and documented."
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
                "Disposable income is zero or negative "
                "— debt can never be repaid within 72 "
                "months. WATCH requires IVA to run at "
                "least 6 years."
            ),
            threshold=72.0,
            actual_value=None,
        )
    actual = c["total_debt"] / di
    if actual <= threshold:
        return RuleResult(
            rule_id="WATCH-22.2", severity="hard_block", triggered=True,
            message=(
                f"Debt repayable in {actual / 12:.1f} years — within the 6-year "
                "threshold. WATCH rejects cases where debt can be repaid "
                "without an IVA within 6 years."
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
            message=f"Bankruptcy return £{br:,.2f} exceeds IVA projected return £{iva_return:,.2f}.",
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
            message="[RULE-CANNOT-EVALUATE] Rule WATCH-22.4 cannot be evaluated — property_value not present in payload",
        )
    pv = _parse_amount(property_value)
    equity_at_85 = (pv * 0.85) - c["mortgage_balance"]
    if equity_at_85 > c["total_debt"]:
        return RuleResult(
            rule_id="WATCH-22.4", severity="hard_block", triggered=True,
            message=f"Equity at 85% LTV £{equity_at_85:,.2f} exceeds total unsecured debt £{c['total_debt']:,.2f}.",
            threshold=c["total_debt"], actual_value=equity_at_85,
        )
    return _pass("WATCH-22.4", f"Equity at 85% LTV £{equity_at_85:,.2f} does not exceed total debt.")


def _watch_22_5(c: dict) -> RuleResult:
    """WATCH-22.5: Only 1 creditor, or second creditor balance <= £500 — hard block."""
    threshold = 500.0
    qualifying = [cr for cr in c["creditors"] if cr["balance"] > threshold]
    if len(qualifying) <= 1:
        return RuleResult(
            rule_id="WATCH-22.5", severity="hard_block", triggered=True,
            message=f"Only {len(qualifying)} creditor(s) with balance > £{threshold:,.2f}. WATCH requires at least two qualifying creditors.",
            threshold=threshold, actual_value=float(len(qualifying)),
        )
    return _pass("WATCH-22.5", f"{len(qualifying)} creditors with balance > £{threshold:,.2f}.")


def _watch_22_6(c: dict) -> RuleResult:
    """WATCH-22.6: Excessive luxury/non-essential spend in last 3 months."""
    # EXCEL_CRITERIA_REFERENCE.md — Watch Criteria: luxury/non-essential spend only, assessment_date reference
    assessment_date = c["assessment_date"]
    recent_out = [
        t for t in c["gold_transactions"]
        if t.get("transaction_type") == "money_out"
        and _is_within_days(
            t.get("transaction_date") or t.get("date"), 90, reference=assessment_date
        )
    ]
    if not recent_out:
        return _pass("WATCH-22.6", "No outgoing transactions within the last 90 days.")

    has_categories = any(
        t.get("category") or t.get("transaction_category") for t in recent_out
    )

    if has_categories:
        luxury_total = sum(
            _parse_amount(t.get("amount", 0))
            for t in recent_out
            if (t.get("category") or t.get("transaction_category") or "").lower()
            in LUXURY_CATEGORIES
        )
        threshold = c["total_income"] * 0.5
        if luxury_total > threshold:
            return RuleResult(
                rule_id="WATCH-22.6", severity="hard_block", triggered=True,
                message=(
                    f"Luxury/non-essential spend of £{luxury_total:,.2f} in last 90 days "
                    f"exceeds 50% of monthly income (£{threshold:,.2f})."
                ),
                threshold=threshold, actual_value=luxury_total,
            )
        return _pass("WATCH-22.6", f"Luxury spend £{luxury_total:,.2f} within threshold.")

    return RuleResult(
        rule_id="WATCH-22.6", severity="info", triggered=False,
        message="Transaction categories were not available so the rule could not be fully evaluated.",
    )


def _watch_22_7(c: dict) -> RuleResult:
    """WATCH-22.7: Children aged 13+ with no sustainability paragraph — flag."""
    children = c["children"]
    if not children:
        return _pass("WATCH-22.7", "No children on record — rule not applicable.")
    has_teen = any(_parse_amount(child.get("age", 0)) >= 13 for child in children)
    if not has_teen:
        return _pass("WATCH-22.7", "No children aged 13 or above.")
    if not c["sustainability_paragraph_present"]:
        return RuleResult(
            rule_id="WATCH-22.7", severity="flag", triggered=True,
            message="Client has child(ren) aged 13 or above. Sustainability paragraph required in IVA proposal.",
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
            message=f"Client is {age} years old. WATCH will abstain rather than vote. Note this in the proposal.",
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
            message=f"Vehicle value £{actual:,.2f} exceeds £{threshold:,.2f}. WATCH may request reduction to £4,500.",
            threshold=threshold, actual_value=actual,
        )
    return _pass("WATCH-22.9", f"Vehicle value £{actual:,.2f} within threshold.")


def _watch_22_10(c: dict) -> RuleResult:
    """WATCH-22.10: Car HP payment > £400/month — flag."""
    threshold = float(WATCH_HP_MONTHLY_CAP)
    actual = c["vehicle_hp_monthly"]
    if actual > threshold:
        return RuleResult(
            rule_id="WATCH-22.10", severity="flag", triggered=True,
            message=f"Car HP payment £{actual:,.2f}/month exceeds £{threshold:,.2f}. Evidence required.",
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
            "Gambling identified as the main cause of debt. "
            "3 months of clean bank statements are required before proceeding."
        ),
    )


def _watch_22_12(c: dict) -> RuleResult:
    """WATCH-22.12: Previous IVA proposed — I&E/assets/liabilities must be consistent or explained."""
    if not c["previous_iva"]:
        return _pass("WATCH-22.12", "No previous IVA — WATCH-22.12 not applicable.")
    return RuleResult(
        rule_id="WATCH-22.12", severity="flag", triggered=True,
        message="Previous IVA on record. I&E, assets, and liabilities must be consistent with the previous proposal or a written explanation provided.",
        threshold=0.0,
        actual_value=1.0,
    )


def _watch_22_13(c: dict) -> RuleResult:
    """WATCH-22.13: Antecedent transactions identified — hard block, no exceptions."""
    at = c["antecedent_transactions"]
    if at is None:
        return _pass("WATCH-22.13", "No antecedent transactions identified.")
    if at:
        return RuleResult(
            rule_id="WATCH-22.13", severity="hard_block", triggered=True,
            message="Antecedent transactions identified. WATCH hard block — no exceptions.",
        )
    return _pass("WATCH-22.13", "No antecedent transactions.")


def _watch_22_14(c: dict) -> RuleResult:
    """WATCH-22.14: Car finance taken in last 3 months — hard block unless valid evidence."""
    if c["car_finance_tx_3mo"]:
        return RuleResult(
            rule_id="WATCH-22.14", severity="hard_block", triggered=True,
            message="Car finance transaction within the last 3 months detected. Hard block unless evidence provided (old car scrapped, accident, employment requirement).",
        )
    return _pass("WATCH-22.14", "No car finance in the last 3 months.")


# ---------------------------------------------------------------------------
# TIX RULES — run only when TIX is a creditor
# ---------------------------------------------------------------------------

def _tix_01(c: dict) -> RuleResult:
    """TIX-01: Shop Direct / Very / Littlewoods spend in last 3 months — hard block."""
    if c["shop_direct_tx_3mo"]:
        return RuleResult(
            rule_id="TIX-01", severity="hard_block", triggered=True,
            message=f"{len(c['shop_direct_tx_3mo'])} Shop Direct / Very / Littlewoods transaction(s) in the last 3 months. TIX hard block.",
        )
    return _pass("TIX-01", "No recent Shop Direct transactions.")


def _tix_02(c: dict) -> RuleResult:
    """TIX-02: Shop Direct account < 6 months old — hard block."""
    for creditor in c["creditors"]:
        if not _in_set(creditor["name"], _SHOP_DIRECT_NAMES):
            continue
        age = creditor.get("account_age_months")
        if age is not None and age < 6:
            return RuleResult(
                rule_id="TIX-02", severity="hard_block", triggered=True,
                message=f"{creditor['name']}: account is {age} months old (minimum 6 required). TIX hard block.",
                threshold=6.0, actual_value=float(age),
            )
    return _pass("TIX-02", "No Shop Direct account under 6 months old.")


def _tix_03(c: dict) -> RuleResult:
    """TIX-03: Creation / Sygma / Laser spend in last 4 months — hard block."""
    if c["creation_tx_4mo"]:
        return RuleResult(
            rule_id="TIX-03", severity="hard_block", triggered=True,
            message=f"{len(c['creation_tx_4mo'])} Creation / Sygma / Laser transaction(s) in the last 4 months. TIX hard block.",
        )
    return _pass("TIX-03", "No recent Creation / Sygma / Laser transactions.")


def _tix_04(c: dict) -> RuleResult:
    """TIX-04: Car HP payment > £250/month — flag. NOTE: TIX threshold is £250, WATCH is £400."""
    threshold = 250.0
    actual = c["vehicle_hp_monthly"]
    if actual > threshold:
        return RuleResult(
            rule_id="TIX-04", severity="flag", triggered=True,
            message=f"Car HP payment £{actual:,.2f}/month exceeds TIX threshold £{threshold:,.2f}. Evidence required.",
            threshold=threshold, actual_value=actual,
        )
    return _pass("TIX-04", f"HP payment £{actual:,.2f}/month within TIX threshold.")


def _tix_05(c: dict) -> RuleResult:
    """TIX-05: UKAR / Whistletree / Computershare / Landmark no longer TIX after 30 June 2023 — info."""
    for creditor in c["creditors"]:
        if _in_set(creditor["name"], _DEREGISTERED_TIX):
            return RuleResult(
                rule_id="TIX-05", severity="info", triggered=False,
                message=f"{creditor['name']} is no longer represented by TIX after 30 June 2023.",
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
                "Vulnerability has been claimed but no supporting evidence has been uploaded. "
                "Speak to Tom or Debra before proceeding. Evidence must be obtained and documented."
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
            message="[RULE-CANNOT-EVALUATE] Rule EVOLVE-01 cannot be evaluated — property_value not present in payload",
        )
    # EVOLVE uses 85% LTV
    pv = _parse_amount(property_value)
    equity_at_85 = (pv * 0.85) - c["mortgage_balance"]
    if equity_at_85 > c["total_debt"]:
        return RuleResult(
            rule_id="EVOLVE-01", severity="hard_block", triggered=True,
            message=f"Equity at 85% LTV £{equity_at_85:,.2f} exceeds total debt £{c['total_debt']:,.2f}. EVOLVE hard block.",
            threshold=c["total_debt"], actual_value=equity_at_85,
        )
    return _pass("EVOLVE-01", f"Equity at 85% LTV £{equity_at_85:,.2f} does not exceed total debt.")


def _evolve_02(c: dict) -> RuleResult:
    """EVOLVE-02: Single creditor (NatWest group counts as one lender) — hard block."""
    threshold = 500.0
    # Group creditors by parent_group — same parent = same lender
    # Without parent_group data in the parsed case, count distinct creditor names
    qualifying = [cr for cr in c["creditors"] if cr["balance"] > threshold]
    if len(qualifying) <= 1:
        return RuleResult(
            rule_id="EVOLVE-02", severity="hard_block", triggered=True,
            message=f"Only {len(qualifying)} creditor(s) with balance > £{threshold:,.2f}. EVOLVE requires at least two separate lenders.",
            threshold=threshold, actual_value=float(len(qualifying)),
        )
    return _pass("EVOLVE-02", f"{len(qualifying)} creditors with balance > £{threshold:,.2f}.")


def _evolve_03(c: dict) -> RuleResult:
    """EVOLVE-03: Vulnerability claimed but no supporting evidence uploaded — flag + advisory."""
    if not c["vulnerability_claimed"]:
        return _pass("EVOLVE-03", "No vulnerability claim — rule not applicable.")
    if not c["vulnerability_evidence_uploaded"]:
        return RuleResult(
            rule_id="EVOLVE-03", severity="flag", triggered=True,
            message=(
                "Vulnerability has been claimed but no supporting evidence has been uploaded. "
                "Speak to Tom or Debra before proceeding. Evidence must be obtained and documented."
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
        if creditor["debt_type_normalised"] != DEBT_TYPE_HP:
            continue
        name = creditor["name"]
        name_lower = name.lower()
        if name_lower in _VW_GROUP_NAMES:
            return RuleResult(
                rule_id="PHASE4-VW-TERMINATION", severity="hard_block", triggered=True,
                message=(
                    f"{name} is a VW Financial Services group creditor on hire purchase. "
                    "Termination risk — hard block."
                ),
            )
        
        criteria = criteria_map.get(name)
        if criteria and criteria.termination_risk_if_vehicle_on_finance:
            return RuleResult(
                rule_id="PHASE4-VW-TERMINATION", severity="hard_block", triggered=True,
                message=(
                    f"{name} has termination risk flagged on vehicle finance. Hard block."
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
                    f"{creditor['name']} rejects cases where the client is currently "
                    "in a DMP. Hard block."
                ),
            )

    return _pass("PHASE4-DMP-REJECT", "No DMP-rejecting creditors found.")


def _phase4_county_council(c: dict) -> tuple:  # EXCEL_CRITERIA_REFERENCE.md — County Councils: district rules must be evaluated
    """PHASE4-COUNTY-COUNCIL: County council routing found — resolve district and evaluate its CouncilRule."""
    from debt_app.helpers import DEBT_TYPE_COUNCIL_TAX
    from debt_app.models import CountyCouncilRouting, CouncilRule  # EXCEL_CRITERIA_REFERENCE.md — County Councils: district rules must be evaluated

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
            .values_list("district_name", flat=True)
        )
        if not routings:
            continue

        routing_messages.append(
            f"{county_name}: county council routing found — districts: "
            + ", ".join(routings)
            + "."
        )

        for district_name in routings:  # EXCEL_CRITERIA_REFERENCE.md — County Councils: district rules must be evaluated
            try:
                CouncilRule.objects.get(council_name__iexact=district_name)  # EXCEL_CRITERIA_REFERENCE.md — County Councils: district rules must be evaluated
            except CouncilRule.DoesNotExist:  # EXCEL_CRITERIA_REFERENCE.md — County Councils: district rules must be evaluated
                extra_results.append(RuleResult(  # EXCEL_CRITERIA_REFERENCE.md — County Councils: district rules must be evaluated
                    rule_id="COUNTY-COUNCIL-NO-DISTRICT-RULE",
                    severity="info",
                    triggered=False,
                    message=(
                        f"{county_name} → {district_name}: district has no CouncilRule"
                        " — manual review required"
                    ),
                ))
                continue
            synthetic_cr = {**cr, "name": district_name}  # EXCEL_CRITERIA_REFERENCE.md — County Councils: district rules must be evaluated
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

def _check_creditor_individual(case: dict) -> list[dict]:
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

    # Pre-load all active creditor names once for fuzzy matching
    _all_creditor_names = list(
        CreditorCriteria.objects.filter(is_active=True)
        .values_list("creditor_name", flat=True)
    )

    positions = []
    for cr in case.get("creditors", []):
        if cr["debt_type_normalised"] in _COUNCIL_TYPES:
            continue

        name = cr["name"]
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

            original_name = cr.get("original_name") or ""
            positions.append({
                "creditor_name": name,
                "display_name": None,
                "original_aryza_name": original_name if original_name and original_name != name else None,
                "resolved_canonical_name": resolved_name,
                "representative": "NONE",
                "effective_status": "UNKNOWN",
                "findings": [{"code": "CREDITOR-UNKNOWN", "reason": "No criteria row for this creditor"}],
                "reason": "No criteria row for this creditor",
                "rule_ids": ["CREDITOR-UNKNOWN"],
                "balance": balance,
            })
            continue

        findings = []
        reject_level = False

        if criteria.blocked_until_cleared:
            findings.append({
                "code": "CREDITOR-BLOCKED",
                "reason": criteria.blocked_reason or "Blocked until further notice — contact Debra",
            })
            reject_level = True

        if criteria.reject_if_never_made_payment and not cr.get("first_payment_made", False):
            findings.append({
                "code": "CREDITOR-NO-PAYMENT",
                "reason": "No payment ever made — creditor requires at least one payment before proposing",
            })
            reject_level = True

        arrears_threshold = criteria.vehicle_arrears_repossession_months
        arrears_months = cr.get("vehicle_arrears_months")
        if arrears_threshold is not None and arrears_months is not None and arrears_months >= arrears_threshold:
            findings.append({
                "code": "CREDITOR-REPOSSESSION-RISK",
                "reason": (
                    f"Vehicle is {arrears_months} month(s) in arrears "
                    f"(threshold: {arrears_threshold}) — repossession risk"
                ),
            })
        elif criteria.reject_if_client_still_has_asset and cr.get("client_still_has_asset_in_possession", False):
            findings.append({
                "code": "CREDITOR-REPOSSESSION-RISK",
                "reason": "Client still holds the financed asset — creditor may seek repossession",
            })

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

        effective_status = "REJECT" if reject_level else _STATUS_NORMALISE.get(criteria.status, criteria.status)

        original_name = cr.get("original_name") or ""
        canonical = criteria.creditor_name
        positions.append({
            "creditor_name": name,
            "display_name": canonical if canonical != name else None,
            "original_aryza_name": original_name if original_name and original_name != name else None,
            "resolved_canonical_name": canonical,
            "representative": criteria.representative,
            "effective_status": effective_status,
            "findings": findings,
            "reason": findings[0]["reason"] if findings else (criteria.dividend_notes or ""),
            "rule_ids": [f["code"] for f in findings],
            "balance": balance,
        })

    return positions


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

    positions = []
    for cr in case.get("creditors", []):
        if cr["debt_type_normalised"] not in _COUNCIL_TYPES:
            continue

        name = cr["name"]
        try:
            rule = CouncilRule.objects.get(council_name__iexact=name)
        except CouncilRule.DoesNotExist:
            # Fuzzy fallback: strip common council suffixes then icontains search
            name_part = re.sub(
                r"\s+(District|Borough|City|County)\s+Council$", "", name, flags=re.IGNORECASE
            ).strip()
            name_part = re.sub(r"\s+(DC|BC|CC|MBC|RBC)$", "", name_part, flags=re.IGNORECASE).strip()
            rule = CouncilRule.objects.filter(council_name__icontains=name_part).first()
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

        # If the council has conditional-reject flags and none triggered, it
        # is effectively ACCEPT (the Excel notes confirm acceptance when conditions
        # are met, e.g. "ACCEPT UNEMPLOYED — REJECT IF EMPLOYED").
        _has_conditional_reject = any([
            rule.reject_if_employed,
            rule.reject_if_unemployed_and_homeowner,
            rule.reject_if_benefits_only,
            rule.reject_if_any_benefits,
            rule.reject_if_previous_iva,
            rule.reject_if_dro_criteria_met,
            rule.reject_if_aoe_in_place,
            rule.reject_if_joint_one_party_only,
            rule.reject_if_joint_both_parties,
            rule.reject_if_sole,
            rule.reject_if_joint_one_employed,
        ])
        if reject_override:
            effective_status = "REJECT"
        elif _has_conditional_reject:
            effective_status = "ACCEPT"
        else:
            effective_status = base_status

        positions.append({
            "council_name": rule.council_name,
            "creditor_name": rule.council_name,
            "effective_status": effective_status,
            "findings": findings,
        })

    return positions


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
                        f"{cr['name']}: client is a Royal Mail employee — "
                        "Penny Post Credit Union has special employment implications. "
                        "Note for caseworker."
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
                        f"{cr['name']}: creditor rejects IVA proposals where the client "
                        "is a serving police officer. Hard block."
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
                    f"{cr['name']}: I&E does not match the original loan application. "
                    "Creditor requires I&E consistency — flag for caseworker review."
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
                    f"{cr['name']}: balance £{balance:,.2f} is repayable in "
                    f"{months_to_repay:.1f} months from DI — under the "
                    f"{threshold}-month threshold. Creditor rejects where IVA "
                    "is not the most appropriate solution."
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
                    f"{cr['name']}: personal guarantee has not been called up. "
                    "This creditor requires the guarantee to be called before "
                    "an IVA can be proposed."
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
                    f"{cname}: conditional voter — majority achievable without their vote. "
                    "Note their conditions but no blocking action needed."
                ),
            ))
        else:
            results.append(RuleResult(
                rule_id="CONDITIONAL-VOTER-REQUIRED",
                severity="flag",
                triggered=True,
                message=(
                    f"{cname}: conditional voter — majority is NOT achievable without "
                    "their vote. Their conditions must be satisfied for the IVA to pass."
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
                            f"{cname}: pre-proposal contact is required before the IVA "
                            f"can be sent. Contact: {cv_rule.contact_name or 'see creditor notes'}."
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
) -> str:
    """Map assessment results to a recommended solution string."""
    if hard_blocks:
        return "IVA_NOT_VIABLE"
    for pos in creditor_positions:
        if pos.get("effective_status") == "DO_NOT_VOTE":
            return "REVIEW_REQUIRED"
    if flags:
        return "IVA_WITH_CONDITIONS"
    return "IVA_VIABLE"


def _compute_majority_analysis(case: dict, positions: list, council_positions: list = None, estimated_dividend_pence: int = 0) -> dict:  # EXCEL_CRITERIA_REFERENCE.md — Council Majority / DO_NOT_VOTE denominator rule
    """Compute whether a 75%-by-value creditor majority is achievable."""
    from debt_app.models import CreditorCriteria
    from debt_app.helpers import get_creditor_by_trading_name

    creditors = case.get("creditors", [])
    balance_by_name = {c["name"]: c["crm_balance"] for c in creditors}

    # Merge council_positions into a unified position list so councils count toward the majority.  # EXCEL_CRITERIA_REFERENCE.md — Council Majority / DO_NOT_VOTE denominator rule
    # _check_council_rules() uses "council_name"; normalise to "creditor_name" for unified lookup.  # EXCEL_CRITERIA_REFERENCE.md — Council Majority / DO_NOT_VOTE denominator rule
    all_positions = list(positions or [])
    for cp in (council_positions or []):  # EXCEL_CRITERIA_REFERENCE.md — Council Majority / DO_NOT_VOTE denominator rule
        all_positions.append({
            "creditor_name": cp.get("creditor_name") or cp.get("council_name", ""),  # EXCEL_CRITERIA_REFERENCE.md — Council Majority / DO_NOT_VOTE denominator rule
            "effective_status": cp.get("effective_status", "DO_NOT_VOTE"),
        })

    # Exclude DO_NOT_VOTE creditors from the denominator (total voting pool).  # EXCEL_CRITERIA_REFERENCE.md — Council Majority / DO_NOT_VOTE denominator rule
    do_not_vote_names = {  # EXCEL_CRITERIA_REFERENCE.md — Council Majority / DO_NOT_VOTE denominator rule
        pos["creditor_name"]
        for pos in all_positions
        if pos.get("effective_status") == "DO_NOT_VOTE"
    }
    # WATCH-22.8: client aged 80+ — WATCH creditors abstain, remove from denominator
    client_age = case.get("client_age") or 0
    if client_age >= 80:
        for pos in all_positions:
            if pos["creditor_name"] in do_not_vote_names:
                continue
            try:
                from debt_app.helpers import get_creditor_by_trading_name
                from debt_app.models import CreditorCriteria
                criteria = get_creditor_by_trading_name(pos["creditor_name"])
                if criteria.representative == "WATCH":
                    do_not_vote_names.add(pos["creditor_name"])
            except CreditorCriteria.DoesNotExist:
                pass
    total = sum(  # EXCEL_CRITERIA_REFERENCE.md — Council Majority / DO_NOT_VOTE denominator rule
        c["crm_balance"]
        for c in creditors
        if c["name"] not in do_not_vote_names
    )
    if not total:
        return {
            "total_debt": Decimal("0"), "threshold": Decimal("0"),
            "voting_debt": Decimal("0"), "shortfall": Decimal("0"),
            "achievable": True,
        }
    threshold = (total * Decimal("0.75")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    # EXCEL_CRITERIA_REFERENCE.md — CONDITIONAL_VOTER: only votes YES if dividend meets threshold
    def _counts_as_yes(pos: dict) -> bool:
        status = pos.get("effective_status")
        if status in ("ACCEPT", "WILL_CONSIDER", "UNKNOWN"):
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

    if all_positions:
        # Build a set of names that count as yes votes, then sum ALL creditor rows
        # with those names. Using a set avoids the stale-balance problem when
        # multiple creditors share the same name (e.g. three Halifax entries).
        yes_names = {
            pos["creditor_name"]
            for pos in all_positions
            if _counts_as_yes(pos)
        }
        voting_debt = sum(
            c["crm_balance"]
            for c in creditors
            if c["name"] in yes_names and c["name"] not in do_not_vote_names
        )
    else:
        voting_debt = total
    shortfall = max(Decimal("0"), threshold - voting_debt)
    return {
        "total_debt": total,
        "threshold": threshold,
        "voting_debt": voting_debt,
        "shortfall": shortfall,
        "achievable": shortfall == Decimal("0"),
    }


def _compute_dividend_analysis(case: dict, positions: list) -> dict:
    """Estimate dividend pence-per-pound and flag creditors whose minimums aren't met."""
    from debt_app.models import CreditorCriteria, CouncilRule
    from debt_app.helpers import (
        get_creditor_by_trading_name,
        DEBT_TYPE_COUNCIL_TAX, DEBT_TYPE_PCN, DEBT_TYPE_HOUSING_BENEFIT,
    )

    _COUNCIL_TYPES = frozenset({DEBT_TYPE_COUNCIL_TAX, DEBT_TYPE_PCN, DEBT_TYPE_HOUSING_BENEFIT})

    creditors = case.get("creditors", [])
    monthly_di = Decimal(str(case.get("monthly_di", "0")))
    iva_term_months = case.get("iva_term_months", 60)
    total = sum(c["crm_balance"] for c in creditors)
    if total > 0:
        estimated_pence = int((monthly_di * iva_term_months / total) * 100)
    else:
        estimated_pence = 0
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

def _enrich_from_credit_report(case_data: dict) -> str:
    """
    Looks up CreditReport by aryza_reference from case_data and enriches
    per-creditor fields and evidence_ledger in-place. Never raises.
    Returns "present" | "absent" | "extraction_failed".
    """
    try:
        from rapidfuzz import fuzz, process as rfprocess
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

        if status == "present":
            accounts = report.extracted_data["accounts"]

            # Build lookup pool: case creditors with a positive balance
            case_creditors = [c for c in case_data.get("creditors", []) if (c.get("balance") or 0) > 0]
            creditor_names = [c["name"] for c in case_creditors]

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
                raw_name = matched_creditor or account.get("raw_name", "")
                key_used = "matched_creditor" if matched_creditor else "raw_name"
                logger.debug("[ENRICH] account resolved: '%s' (via %s)", raw_name, key_used)
                if not raw_name:
                    logger.warning("[ENRICH] account skipped — no name resolved: %s", account)
                    continue

                # Fuzzy-match the raw PDF name against live case creditor names
                result = rfprocess.extractOne(
                    raw_name,
                    creditor_names,
                    scorer=fuzz.token_sort_ratio,
                    score_cutoff=80,
                )
                if result is None:
                    logger.info("[CREDIT REPORT MATCH] '%s' → no match (below cutoff)", raw_name)
                    unmatched.append(raw_name)
                    continue

                matched_name, score, _ = result
                logger.info("[CREDIT REPORT MATCH] '%s' → '%s' (score=%s)", raw_name, matched_name, score)

                # When multiple creditors share the same name, pick by balance proximity.
                # Exclude rows already claimed by a previous account to prevent two PDF
                # accounts from landing on the same case creditor row.
                candidates = [
                    c for c in case_creditors
                    if c["name"] == matched_name and id(c) not in claimed_ids
                ]

                if not candidates:
                    # Fall back: check linked_creditor field, also excluding claimed rows
                    candidates = [
                        c for c in case_creditors
                        if c.get("linked_creditor") == matched_name
                        and id(c) not in claimed_ids
                    ]
                    if candidates:
                        logger.info(
                            "[ENRICH FALLBACK] '%s' matched via linked_creditor", matched_name
                        )
                    else:
                        if any(
                            c["name"] == matched_name or c.get("linked_creditor") == matched_name
                            for c in case_creditors
                        ):
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
                            f"{creditor['name']}: upload a credit report to "
                            "complete evaluation of this creditor's criteria"
                        ),
                    })
            except CreditorCriteria.DoesNotExist:
                pass

        return status

    except Exception as exc:
        logger.error("_enrich_from_credit_report failed: %s", exc, exc_info=True)
        return "extraction_failed"


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

    logger.info("DEBUG: has_property=%s, property_value=%s, mortgage_balance=%s, disposable_income=%s",
        c["has_property"], c["property_value"], c["mortgage_balance"], c["disposable_income"])

    if detected_representatives is None:
        detected_representatives = detect_representatives(
            case_json.get("creditors") or [],
            assessment_date=c["assessment_date"],
        )

    hard_blocks: list[RuleResult] = []
    flags: list[RuleResult] = []
    info: list[RuleResult] = []
    passed: list[RuleResult] = []

    def _run(rule_func, *args):
        try:
            r = rule_func(c, *args)
        except Exception as exc:
            logger.error("Error in %s: %s", rule_func.__name__, exc, exc_info=True)
            r = RuleResult(
                rule_id=_func_to_rule_id(rule_func.__name__),
                severity="hard_block",
                triggered=True,
                message=f"Rule evaluation error: {exc}",
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
    _all_creditor_positions = _check_creditor_individual(c)
    for _pos in _all_creditor_positions:
        for _finding in _pos.get("findings", []):
            if _finding.get("code") == "CREDITOR-BLOCKED":
                hard_blocks.append(RuleResult(
                    rule_id="CREDITOR-BLOCKED",
                    severity="hard_block",
                    triggered=True,
                    message=f"{_pos['creditor_name']}: {_finding['reason']}",
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
    for _cr_flag in c.get("credit_report_flags", []):
        flags.append(RuleResult(
            rule_id="CREDIT-REPORT-REQUIRED",
            severity="flag",
            triggered=True,
            message=_cr_flag["message"],
        ))

    # --- Overall result ---
    if hard_blocks:
        overall = "blocked"
    elif flags:
        overall = "flagged"
    else:
        overall = "pass"

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
                f"{cname}: estimated dividend {est_p}p is below required minimum {min_p}p"
                " — creditor likely to reject"
            ),
        ))

    # EXCEL_CRITERIA_REFERENCE.md — Council Majority: if 75% majority is mathematically
    # impossible (e.g. council tax creditor holds a blocking minority and does not vote),
    # the IVA cannot proceed regardless of other rules — hard block.
    if not majority_analysis["achievable"] and majority_analysis["total_debt"] > 0:
        hard_blocks.append(RuleResult(
            rule_id="MAJORITY-IMPOSSIBLE",
            severity="hard_block",
            triggered=True,
            message=(
                f"75% creditor majority is not achievable: only "
                f"£{majority_analysis['voting_debt']:,.2f} of the required "
                f"£{majority_analysis['threshold']:,.2f} threshold can be reached "
                f"(shortfall £{majority_analysis['shortfall']:,.2f}). "
                "The IVA cannot be approved without additional creditor support."
            ),
        ))
        overall = "blocked"

    recommended_solution = _derive_recommended_solution(hard_blocks, flags, _all_creditor_positions)
    tig_eligible = len(hard_blocks) == 0

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
        "passes_all_hard_blocks": tig_eligible,
        "recommended_solution": recommended_solution,
        "tig_eligible": tig_eligible,
        "creditor_positions": _all_creditor_positions,
        "council_positions": council_positions,
        "majority_analysis": majority_analysis,
        "dividend_analysis": dividend_analysis,
        "representatives_detected": detected_representatives,
        "sfs_guideline_results": sfs_results,
        "sfs_household_key": hh_key,
        "credit_report_status": credit_report_status,
    }
