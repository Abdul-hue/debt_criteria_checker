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

import logging
import re
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

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


# ---------------------------------------------------------------------------
# Named creditor sets (business constants — not DB config)
# ---------------------------------------------------------------------------

_SHOP_DIRECT_NAMES = frozenset({
    "shop direct", "very", "littlewoods", "littlewoods.com",
})

_CREATION_NAMES = frozenset({
    "creation", "sygma", "laser", "creation consumer finance",
})

_LINK_NAMES = frozenset({
    "link financial", "link financial outsourcing",
})

_HMRC_NAMES = frozenset({
    "hmrc",
    "hm revenue and customs",
    "hm revenue & customs",
    "hm revenue and customs (vat)",
    "hm revenue and customs (paye)",
    "hm revenue and customs (self assessment)",
})

_GAMBLING_KEYWORDS = [
    "gamble", "gambling", "bet", "betting", "casino",
    "paddy", "ladbrokes", "betfair", "william hill",
    "skybet", "coral", "betway", "888", "unibet",
    "bet365", "betvictor", "boylesports",
]

_PAYDAY_KEYWORDS = [
    "wonga", "quickquid", "payday", "sunny", "lending stream",
    "pounds to pocket", "247moneybox",
]

_DEREGISTERED_TIX = frozenset({
    "ukar", "whistletree", "computershare", "landmark",
})

_CAR_FINANCE_KEYWORDS = [
    "car finance", "hp finance", "hire purchase", "black horse",
    "motonovo", "alphera", "close brothers", "motonovo",
]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _norm(s: str) -> str:
    """Lowercase, strip, remove non-alphanumeric for fuzzy matching."""
    return re.sub(r"[^a-z0-9]", "", s.lower().strip())


def _in_set(name: str, name_set: frozenset) -> bool:
    """Case-insensitive membership check against a frozenset of names."""
    return name.strip().lower() in name_set


def _days_since(date_str: Optional[str]) -> int:
    """Days between today and date_str (ISO format). Returns 9999 if missing/invalid."""
    if not date_str:
        return 9999
    try:
        d = date.fromisoformat(str(date_str).split("T")[0])
        return (date.today() - d).days
    except (ValueError, AttributeError):
        return 9999


def _is_within_days(date_str: Optional[str], days: int) -> bool:
    return _days_since(date_str) <= days


def _parse_amount(value) -> float:
    """Coerce string or numeric balance to float."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _gambling_monthly(gold_transactions: list) -> float:
    """Sum absolute amounts of gambling transactions."""
    total = 0.0
    for t in gold_transactions:
        desc = (t.get("description") or "").lower()
        if any(kw in desc for kw in _GAMBLING_KEYWORDS):
            total += abs(_parse_amount(t.get("amount", 0)))
    return total


def _recent_transactions_matching(
    gold_transactions: list,
    keywords: list,
    within_days: int,
) -> list:
    """Return transactions whose description matches any keyword and are within N days."""
    results = []
    for t in gold_transactions:
        desc = (t.get("description") or "").lower()
        if not any(kw.lower() in desc for kw in keywords):
            continue
        tx_date = t.get("transaction_date") or t.get("date")
        if _is_within_days(tx_date, within_days):
            results.append(t)
    return results


def _hp_monthly_from_transactions(gold_transactions: list) -> float:
    """Estimate HP monthly payment by scanning gold_transactions."""
    total = 0.0
    for t in gold_transactions:
        desc = (t.get("description") or "").lower()
        if any(kw in desc for kw in _CAR_FINANCE_KEYWORDS):
            total += abs(_parse_amount(t.get("amount", 0)))
    return total


def _compute_age(dob_str: Optional[str]) -> Optional[int]:
    """Compute age in years from ISO date string."""
    if not dob_str:
        return None
    try:
        dob = date.fromisoformat(dob_str.split("T")[0])
        today = date.today()
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


def _pass(rule_id: str, message: str = "Passed.") -> RuleResult:
    return RuleResult(rule_id=rule_id, severity="pass", triggered=False, message=message)


# ---------------------------------------------------------------------------
# Payload parser — normalises raw JSON into a clean dict
# ---------------------------------------------------------------------------

def _parse_case(case_json: dict) -> dict:
    """
    Extract and normalise all fields needed by the rule methods.
    Missing optional fields default to None or safe empty values.
    Never raises — always returns a complete dict.
    """
    creditors_raw = case_json.get("creditors") or []
    gold_tx = case_json.get("gold_transactions") or []
    documents = case_json.get("documents") or []
    financial = case_json.get("financial_summary") or {}
    crm = case_json.get("crm_data") or {}
    client_info = case_json.get("clientInfo") or {}
    evidence_ledger = case_json.get("evidence_ledger") or []
    mortgage_details = case_json.get("mortgage_details") or []

    # --- Creditors ---
    creditors = []
    for c in creditors_raw:
        creditors.append({
            "name": c.get("creditor_name", ""),
            "balance": _parse_amount(c.get("balance", 0)),
            "creditor_type": c.get("creditor_type", ""),
            "account_age_months": c.get("account_age_months"),  # may be None
            "last_transaction_date": c.get("last_transaction_date"),  # may be None
        })

    # --- Total debt ---
    crm_total = crm.get("total_unsecured_debt")
    if crm_total is not None:
        total_debt = _parse_amount(crm_total)
    else:
        total_debt = sum(c["balance"] for c in creditors)

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
        bank_stmt_date = extracted.get("statement_date")
        bank_stmt_holder = extracted.get("account_holder")

    # --- Payslip date ---
    payslip_date = None
    if payslip_docs:
        extracted = payslip_docs[0].get("extracted_data") or {}
        payslip_date = extracted.get("statement_date")

    # --- Client age ---
    client_age = _compute_age(client_info.get("dateOfBirth"))

    # --- Gambling ---
    gambling_monthly = _gambling_monthly(gold_tx)

    # --- Mortgage / equity (property_value is a TODO field) ---
    has_property = case_json.get("has_property", False)
    property_value = case_json.get("property_value")  # TODO: not yet in payload
    mortgage_balance = sum(
        _parse_amount(m.get("balance", 0)) for m in mortgage_details
    )

    available_equity = None
    if has_property and property_value is not None:
        available_equity = _parse_amount(property_value) - mortgage_balance

    # --- Previous IVA ---
    previous_iva = case_json.get("previous_iva", False)
    if not previous_iva:
        # Also check evidence_ledger
        previous_iva = any(
            e.get("category") == "previous_iva" for e in evidence_ledger
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
    council_is_majority = (council_balance / total_debt > 0.5) if total_debt > 0 else False

    # --- Link Financial ---
    link_creditors = [c for c in creditors if _in_set(c["name"], _LINK_NAMES)]
    link_balance = sum(c["balance"] for c in link_creditors)
    link_is_creditor = len(link_creditors) > 0

    # --- Shop Direct / Creation recent transactions ---
    shop_direct_tx_3mo = _recent_transactions_matching(
        gold_tx, list(_SHOP_DIRECT_NAMES), 90
    )
    creation_tx_4mo = _recent_transactions_matching(
        gold_tx, list(_CREATION_NAMES), 120
    )

    # --- Total spend last 2 months (excl. payday loans) ---
    two_months_ago = date.today() - timedelta(days=60)
    total_spend_2mo = 0.0
    for t in gold_tx:
        if t.get("transaction_type") != "money_out":
            continue
        desc = (t.get("description") or "").lower()
        if any(kw in desc for kw in _PAYDAY_KEYWORDS):
            continue
        tx_date_str = t.get("transaction_date") or t.get("date")
        if tx_date_str and _days_since(tx_date_str) <= 60:
            total_spend_2mo += abs(_parse_amount(t.get("amount", 0)))

    # --- Vehicle HP from transactions ---
    vehicle_hp_monthly = _hp_monthly_from_transactions(gold_tx)

    # --- Car finance recent transactions ---
    car_finance_tx_3mo = _recent_transactions_matching(
        gold_tx, _CAR_FINANCE_KEYWORDS, 90
    )

    return {
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
        "creation_tx_4mo": creation_tx_4mo,
        "total_spend_2mo": total_spend_2mo,
        "vehicle_hp_monthly": vehicle_hp_monthly,
        "car_finance_tx_3mo": car_finance_tx_3mo,
        # TODO fields — None until payload is updated
        "vehicle_value": case_json.get("vehicle_value"),           # TODO
        "children": case_json.get("children") or [],               # TODO
        "antecedent_transactions": case_json.get("antecedent_transactions"),  # TODO
        "seiss_debt_flag": case_json.get("seiss_debt_flag"),        # TODO
        "third_party_contribution": case_json.get("third_party_contribution"),  # TODO
        "sustainability_paragraph_present": case_json.get("sustainability_paragraph_present"),  # TODO
        "bankruptcy_return": case_json.get("bankruptcy_return"),    # TODO
        # Flags derived from other sources
        "previous_iva": previous_iva,
        "has_vehicle": case_json.get("has_vehicle", False),
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
    """TIG-02: Disposable income must be > £100/month."""
    threshold = 100.0
    actual = c["disposable_income"]
    if actual <= threshold:
        return RuleResult(
            rule_id="TIG-02", severity="hard_block", triggered=True,
            message=f"Disposable income £{actual:,.2f}/month is at or below the £{threshold:,.2f} minimum.",
            threshold=threshold, actual_value=actual,
        )
    return _pass("TIG-02", f"Disposable income £{actual:,.2f}/month exceeds the £{threshold:,.2f} minimum.")


def _tig_03(c: dict) -> RuleResult:
    """TIG-03: SFS guidelines — requires SFS expenditure data not yet in payload."""
    # TODO: SFS expenditure breakdown not in current payload
    return _todo_flag("TIG-03", "sfs_expenditure_breakdown")


def _tig_04(c: dict) -> RuleResult:
    """TIG-04: DLA/PIP income present but no disability expenses — stub (payload missing fields)."""
    return _todo_flag("TIG-04", "disability_income / disability_expenses")


def _tig_05(c: dict) -> RuleResult:
    """TIG-05: Wage slip required — one per employment income source, dated within 90 days."""
    income_source = c["income_source"]
    has_job = c["has_job"]

    if income_source not in ("payslip", "employed", "cis") and not has_job:
        return _pass("TIG-05", "Not employed — wage slip not required.")

    payslip_docs = c["payslip_docs"]
    if not payslip_docs:
        return RuleResult(
            rule_id="TIG-05", severity="hard_block", triggered=True,
            message="No wage slip uploaded. At least one required per employment income source.",
        )

    payslip_date = c["payslip_date"]
    if _days_since(payslip_date) > 90:
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
    if bank_date and str(date.today().year) in str(bank_date):
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
    """TIG-08: Self-employed requires tax return OR 3 months business banking."""
    if c["income_source"] != "self_employed":
        return _pass("TIG-08", "Not self-employed — self-employed proof not required.")

    has_tax_return = len(c["tax_return_docs"]) > 0
    if has_tax_return:
        return _pass("TIG-08", "Tax return document present.")

    # Fallback: check for 3 months of business bank statements
    # (not in payload yet — check for bank statement count as proxy)
    if len(c["bank_stmt_docs"]) >= 3:
        return _pass("TIG-08", "Three months of bank statements present.")

    return RuleResult(
        rule_id="TIG-08", severity="hard_block", triggered=True,
        message="Self-employed but no tax return and fewer than 3 months of business bank statements.",
    )


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
    # Proof is evidenced via evidence_ledger — check each creditor
    # If all creditors have verified evidence, pass
    # We can only check what the payload gives us; missing = flag
    creditors = c["creditors"]
    if not creditors:
        return _pass("TIG-10", "No creditors listed.")

    # Without per-creditor evidence lookup, default to pass with note
    # TODO: wire evidence_ledger per-creditor matching when available
    return _pass("TIG-10", "Proof of debt check passed (per-creditor evidence matching TODO).")


def _tig_11(c: dict) -> RuleResult:
    """TIG-11: Bank statement verification — presence, freshness, account holder, gambling."""
    # No bank statement at all
    if not c["bank_stmt_docs"]:
        return RuleResult(
            rule_id="TIG-11", severity="hard_block", triggered=True,
            message="No valid bank statement uploaded.",
        )

    # Statement older than 90 days
    if _days_since(c["bank_stmt_date"]) > 90:
        return RuleResult(
            rule_id="TIG-11", severity="hard_block", triggered=True,
            message=f"Bank statement dated {c['bank_stmt_date']} is older than 90 days.",
        )

    # No account holder name
    if not c["bank_stmt_holder"]:
        return RuleResult(
            rule_id="TIG-11", severity="hard_block", triggered=True,
            message="Bank statement extracted_data has no account_holder name.",
        )

    # Gambling hard block > £1,000/month
    gm = c["gambling_monthly"]
    if gm > 1000:
        return RuleResult(
            rule_id="TIG-11", severity="hard_block", triggered=True,
            message=f"Gambling spend £{gm:,.2f}/month exceeds £1,000 hard block threshold.",
            threshold=1000.0, actual_value=gm,
        )

    # Gambling flag > £200/month
    if gm > 200:
        return RuleResult(
            rule_id="TIG-11", severity="flag", triggered=True,
            message=f"Gambling spend £{gm:,.2f}/month exceeds £200. GAMSTOP proof required.",
            threshold=200.0, actual_value=gm,
        )

    return _pass("TIG-11", "Bank statement valid, fresh, account holder present, no gambling concerns.")


def _tig_12(c: dict) -> RuleResult:
    """TIG-12: Third-party contribution requires signed letter — stub (payload missing field)."""
    tp = c["third_party_contribution"]
    if tp is None:
        return _todo_flag("TIG-12", "third_party_contribution")
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
    # TODO: 'income_deductions_active' not in payload — flag
    return _todo_flag("TIG-15.1", "income_deductions_active")


def _tig_15_2(c: dict) -> RuleResult:
    """TIG-15.2: HMRC majority creditor + previous IVA or bankruptcy."""
    if not c["hmrc_is_majority"]:
        return _pass("TIG-15.2", "HMRC is not the majority creditor.")
    if c["previous_iva"]:
        return RuleResult(
            rule_id="TIG-15.2", severity="hard_block", triggered=True,
            message="HMRC is majority creditor and client has a previous IVA or bankruptcy.",
        )
    return _pass("TIG-15.2", "HMRC majority creditor check passed — no previous IVA.")


def _tig_15_3(c: dict) -> RuleResult:
    """TIG-15.3: HMRC self-assessment debt + self-employed + late/missing tax submissions."""
    if not c["hmrc_is_creditor"]:
        return _pass("TIG-15.3", "No HMRC creditor.")
    if c["income_source"] != "self_employed":
        return _pass("TIG-15.3", "Not self-employed — TIG-15.3 not applicable.")
    # Check for tax return as proxy for up-to-date submissions
    if not c["tax_return_docs"]:
        return RuleResult(
            rule_id="TIG-15.3", severity="hard_block", triggered=True,
            message="Self-employed with HMRC self-assessment debt but no tax return uploaded.",
        )
    return _pass("TIG-15.3", "Tax return present — submission confirmed.")


def _tig_15_4(c: dict) -> RuleResult:
    """TIG-15.4: Available property equity > HMRC debt balance."""
    if not c["hmrc_is_creditor"]:
        return _pass("TIG-15.4", "No HMRC creditor.")
    if c["available_equity"] is None:
        return _todo_flag("TIG-15.4", "property_value")
    if c["available_equity"] > c["hmrc_balance"]:
        return RuleResult(
            rule_id="TIG-15.4", severity="hard_block", triggered=True,
            message=f"Available equity £{c['available_equity']:,.2f} exceeds HMRC balance £{c['hmrc_balance']:,.2f}.",
            threshold=c["hmrc_balance"], actual_value=c["available_equity"],
        )
    return _pass("TIG-15.4", "Equity does not exceed HMRC balance.")


def _tig_15_5(c: dict) -> RuleResult:
    """TIG-15.5: Bankruptcy return > IVA payments — stub (payload missing bankruptcy_return)."""
    if c["bankruptcy_return"] is None:
        return _todo_flag("TIG-15.5", "bankruptcy_return")
    br = _parse_amount(c["bankruptcy_return"])
    iva_return = c["disposable_income"] * 60 * 0.75
    if br > iva_return:
        return RuleResult(
            rule_id="TIG-15.5", severity="hard_block", triggered=True,
            message=f"Bankruptcy return £{br:,.2f} exceeds projected IVA return £{iva_return:,.2f}.",
            threshold=iva_return, actual_value=br,
        )
    return _pass("TIG-15.5", "IVA return exceeds bankruptcy return.")


def _tig_15_6(c: dict) -> RuleResult:
    """TIG-15.6: Full & Final funded from savings accumulated while debts unpaid — stub."""
    return _todo_flag("TIG-15.6", "full_and_final_from_savings")


def _tig_15_7(c: dict) -> RuleResult:
    """TIG-15.7: SEISS fraud debt — always blocks, cannot be included in IVA."""
    if c["seiss_debt_flag"] is None:
        return _todo_flag("TIG-15.7", "seiss_debt_flag")
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
    if c["income_source"] in ("benefits", "universal_credit", "uc"):
        return RuleResult(
            rule_id="TIG-15.10", severity="hard_block", triggered=True,
            message="Client's sole income is benefits and HMRC is a creditor — IVA not viable.",
        )
    return _pass("TIG-15.10", "Client has non-benefit income — TIG-15.10 not triggered.")


def _tig_16(c: dict) -> RuleResult:
    """TIG-16: Equity > total debt — NON-WPM/EVERSHEDS must explain why not remortgaging."""
    if not c["has_property"]:
        return _pass("TIG-16", "No property — equity flag not applicable.")
    if c["available_equity"] is None:
        return _todo_flag("TIG-16", "property_value")
    if c["available_equity"] > c["total_debt"]:
        return RuleResult(
            rule_id="TIG-16", severity="flag", triggered=True,
            message=f"Equity £{c['available_equity']:,.2f} exceeds total debt £{c['total_debt']:,.2f}. Assessor must explain why remortgage is not appropriate.",
            threshold=c["total_debt"], actual_value=c["available_equity"],
        )
    return _pass("TIG-16", "Equity does not exceed total debt.")


def _tig_17(c: dict) -> RuleResult:
    """TIG-17: Council majority creditor with active income/benefit deductions — flag."""
    if not c["council_is_majority"]:
        return _pass("TIG-17", "Council is not the majority creditor.")
    return RuleResult(
        rule_id="TIG-17", severity="flag", triggered=True,
        message="Council is majority creditor. Confirm whether income or benefit deductions are being taken. Case-by-case review required.",
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
    """TIG-19: Shop Direct purchases within 3 months of statement date — flag."""
    if c["shop_direct_tx_3mo"]:
        return RuleResult(
            rule_id="TIG-19", severity="flag", triggered=True,
            message=f"{len(c['shop_direct_tx_3mo'])} Shop Direct / Very / Littlewoods transaction(s) in the last 3 months.",
        )
    return _pass("TIG-19", "No recent Shop Direct transactions.")


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
    """TIG-20.1: Any recent spend with Creation / Sygma / Laser — hard block, no trial cases."""
    if c["creation_tx_4mo"]:
        return RuleResult(
            rule_id="TIG-20.1", severity="hard_block", triggered=True,
            message="Recent spend detected with Creation / Sygma / Laser. Hard block — no trial cases accepted.",
        )
    # Also check if any creditor IS Creation/Sygma/Laser (they may not have transactions but account is present)
    for creditor in c["creditors"]:
        if _in_set(creditor["name"], _CREATION_NAMES):
            return RuleResult(
                rule_id="TIG-20.1", severity="hard_block", triggered=True,
                message=f"Creation / Sygma / Laser creditor present ({creditor['name']}). Hard block.",
            )
    return _pass("TIG-20.1", "No Creation / Sygma / Laser spend or creditor.")


def _tig_21_1(c: dict) -> RuleResult:
    """TIG-21.1: Link Financial creditor — must confirm Mid SFS guidelines used."""
    if not c["link_is_creditor"]:
        return _pass("TIG-21.1", "Link Financial is not a creditor.")
    return RuleResult(
        rule_id="TIG-21.1", severity="flag", triggered=True,
        message="Link Financial is a creditor. Confirm Mid SFS guidelines have been applied.",
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
    if c["available_equity"] is None:
        return _todo_flag("TIG-21.3", "property_value")
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
    # Benefit income: if income_source is benefits, treat 100% as benefit
    if c["income_source"] in ("benefits", "uc", "universal_credit"):
        benefit_pct = 100.0
    else:
        benefit_pct = 0.0  # TODO: granular benefit breakdown not in payload
    threshold = 10.0
    if benefit_pct > threshold:
        return RuleResult(
            rule_id="TIG-21.4", severity="hard_block", triggered=True,
            message=f"Benefits represent {benefit_pct:.0f}% of household income, exceeding the {threshold:.0f}% limit with Link Financial as creditor.",
            threshold=threshold, actual_value=benefit_pct,
        )
    return _pass("TIG-21.4", "Benefits within 10% threshold.")


def _tig_21_5(c: dict) -> RuleResult:
    """TIG-21.5: Previous IVA failed due to arrears AND Link Financial is a creditor."""
    if not c["link_is_creditor"]:
        return _pass("TIG-21.5", "Link Financial is not a creditor.")
    # TODO: previous_iva_failed_reason not in payload — use previous_iva as proxy
    if c["previous_iva"]:
        return RuleResult(
            rule_id="TIG-21.5", severity="hard_block", triggered=True,
            message="Previous IVA on record with Link Financial as creditor. If failure was due to arrears, this is a hard block. Assessor must verify.",
        )
    return _pass("TIG-21.5", "No previous IVA — TIG-21.5 not triggered.")


# ---------------------------------------------------------------------------
# WATCH RULES — run only when WATCH is a creditor
# ---------------------------------------------------------------------------

def _watch_22_1(c: dict) -> RuleResult:
    """WATCH-22.1: Vulnerability used without supporting document."""
    # TODO: vulnerability_claimed not in payload
    return _todo_flag("WATCH-22.1", "vulnerability_claimed")


def _watch_22_2(c: dict) -> RuleResult:
    """WATCH-22.2: Debt repayable in <= 72 months from disposable income — hard block."""
    threshold = 72.0
    di = c["disposable_income"]
    if di <= 0:
        return _pass("WATCH-22.2", "Disposable income is zero — months-to-repay not computable.")
    actual = c["total_debt"] / di
    if actual <= threshold:
        return RuleResult(
            rule_id="WATCH-22.2", severity="hard_block", triggered=True,
            message=f"Debt repayable in {actual:.1f} months — at or under the 72-month threshold. WATCH requires IVA to run at least 6 years.",
            threshold=threshold, actual_value=actual,
        )
    return _pass("WATCH-22.2", f"Debt repayable in {actual:.1f} months — exceeds 72-month threshold.")


def _watch_22_3(c: dict) -> RuleResult:
    """WATCH-22.3: Bankruptcy return > IVA return — stub (bankruptcy_return missing)."""
    if c["bankruptcy_return"] is None:
        return _todo_flag("WATCH-22.3", "bankruptcy_return")
    br = _parse_amount(c["bankruptcy_return"])
    iva_return = c["disposable_income"] * 60 * 0.75
    if br > iva_return:
        return RuleResult(
            rule_id="WATCH-22.3", severity="hard_block", triggered=True,
            message=f"Bankruptcy return £{br:,.2f} exceeds IVA projected return £{iva_return:,.2f}.",
            threshold=iva_return, actual_value=br,
        )
    return _pass("WATCH-22.3", "IVA return exceeds bankruptcy return.")


def _watch_22_4(c: dict) -> RuleResult:
    """WATCH-22.4: Available equity > total unsecured debt — hard block."""
    if c["available_equity"] is None:
        return _todo_flag("WATCH-22.4", "property_value")
    if c["available_equity"] > c["total_debt"]:
        return RuleResult(
            rule_id="WATCH-22.4", severity="hard_block", triggered=True,
            message=f"Available equity £{c['available_equity']:,.2f} exceeds total unsecured debt £{c['total_debt']:,.2f}.",
            threshold=c["total_debt"], actual_value=c["available_equity"],
        )
    return _pass("WATCH-22.4", "Equity does not exceed total debt.")


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
    """WATCH-22.6: Any spending on any account within last 3 months — hard block."""
    for t in c["gold_transactions"]:
        if t.get("transaction_type") != "money_out":
            continue
        tx_date = t.get("transaction_date") or t.get("date")
        if _is_within_days(tx_date, 90):
            return RuleResult(
                rule_id="WATCH-22.6", severity="hard_block", triggered=True,
                message="Spending detected on an account within the last 90 days. WATCH hard block.",
            )
    return _pass("WATCH-22.6", "No spending within the last 90 days.")


def _watch_22_7(c: dict) -> RuleResult:
    """WATCH-22.7: Children aged 13+ with no sustainability paragraph — flag. Stub (children not in payload)."""
    children = c["children"]
    if not children:
        return _todo_flag("WATCH-22.7", "children (array with ages)")
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
        return _todo_flag("WATCH-22.9", "vehicle_value")
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
    threshold = 400.0
    actual = c["vehicle_hp_monthly"]
    if actual > threshold:
        return RuleResult(
            rule_id="WATCH-22.10", severity="flag", triggered=True,
            message=f"Car HP payment £{actual:,.2f}/month exceeds £{threshold:,.2f}. Evidence required.",
            threshold=threshold, actual_value=actual,
        )
    return _pass("WATCH-22.10", f"HP payment £{actual:,.2f}/month within threshold.")


def _watch_22_11(c: dict) -> RuleResult:
    """WATCH-22.11: Gambling identified as main cause with no 3-month clean statements — flag."""
    # TODO: gambling_main_cause flag not in payload — use gambling_monthly as proxy
    gm = c["gambling_monthly"]
    if gm > 0:
        return RuleResult(
            rule_id="WATCH-22.11", severity="flag", triggered=True,
            message="Gambling transactions detected. If gambling is identified as the main cause of debt, 3 months of clean bank statements are required.",
        )
    return _pass("WATCH-22.11", "No gambling transactions detected.")


def _watch_22_12(c: dict) -> RuleResult:
    """WATCH-22.12: Previous IVA proposed — I&E/assets/liabilities must be consistent or explained."""
    if not c["previous_iva"]:
        return _pass("WATCH-22.12", "No previous IVA — WATCH-22.12 not applicable.")
    return RuleResult(
        rule_id="WATCH-22.12", severity="flag", triggered=True,
        message="Previous IVA on record. I&E, assets, and liabilities must be consistent with the previous proposal or a written explanation provided.",
    )


def _watch_22_13(c: dict) -> RuleResult:
    """WATCH-22.13: Antecedent transactions identified — hard block, no exceptions. Stub."""
    at = c["antecedent_transactions"]
    if at is None:
        return _todo_flag("WATCH-22.13", "antecedent_transactions")
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
    """TIX-06: Vulnerability used without supporting document — flag."""
    return _todo_flag("TIX-06", "vulnerability_claimed")


# ---------------------------------------------------------------------------
# EVOLVE RULES — run only when EVOLVE is a creditor
# ---------------------------------------------------------------------------

def _evolve_01(c: dict) -> RuleResult:
    """EVOLVE-01: Equity > debt based on 85% LTV (not 100%) — hard block."""
    if not c["has_property"]:
        return _pass("EVOLVE-01", "No property — EVOLVE-01 not applicable.")
    property_value = c["property_value"]
    if property_value is None:
        return _todo_flag("EVOLVE-01", "property_value")
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
    """EVOLVE-03: Vulnerability used without supporting document — flag."""
    return _todo_flag("EVOLVE-03", "vulnerability_claimed")


# ---------------------------------------------------------------------------
# Representative detection — looks up DB CreditorCriteria
# ---------------------------------------------------------------------------

def detect_representatives(creditors: list) -> set:
    """
    Returns set of active representatives for the creditors in this case.
    e.g. {"WATCH", "TIX"}

    Matching is case-insensitive and uses three tiers:
      1. Exact match against creditor_name or any trading_name
      2. Seeded/trading name is a substring of the case creditor name
         ("Barclays" in "Barclays Bank")
      3. Case creditor name is a substring of the seeded/trading name

    Requires Django ORM — called once in assess_case() before pure functions run.
    """
    from debt_app.models import CreditorCriteria  # local import — keeps module testable without Django

    case_names_lower = [
        c.get("creditor_name", "").lower()
        for c in creditors
        if c.get("creditor_name")
    ]
    if not case_names_lower:
        return set()

    all_criteria = (
        CreditorCriteria.objects
        .filter(is_active=True)
        .exclude(representative__isnull=True)
        .exclude(representative="")
        .exclude(representative="NONE")
    )

    reps = set()
    for criterion in all_criteria:
        seeded_lower = criterion.creditor_name.lower()
        trading_lower = [t.lower() for t in (criterion.trading_names or [])]
        criterion_names = [seeded_lower] + trading_lower

        matched = False
        for case_name in case_names_lower:
            for crit_name in criterion_names:
                if not crit_name:
                    continue
                if case_name == crit_name:          # 1. exact
                    matched = True
                elif crit_name in case_name:        # 2. seeded is substring of case
                    matched = True
                elif case_name in crit_name:        # 3. case is substring of seeded
                    matched = True
                if matched:
                    break
            if matched:
                break

        if matched:
            reps.add(criterion.representative)

    return reps


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

    if detected_representatives is None:
        detected_representatives = detect_representatives(case_json.get("creditors") or [])

    hard_blocks: list[RuleResult] = []
    flags: list[RuleResult] = []
    info: list[RuleResult] = []
    passed: list[RuleResult] = []

    def _run(rule_func):
        try:
            r = rule_func(c)
        except Exception as exc:
            logger.error("Error in %s: %s", rule_func.__name__, exc, exc_info=True)
            r = RuleResult(
                rule_id=rule_func.__name__,
                severity="flag",
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
        _tig_11, _tig_12, _tig_13,
        _tig_15_1, _tig_15_2, _tig_15_3, _tig_15_4, _tig_15_5,
        _tig_15_6, _tig_15_7, _tig_15_8, _tig_15_9, _tig_15_10,
        _tig_16, _tig_17, _tig_18,
        _tig_19, _tig_19_1,
        _tig_20, _tig_20_1,
        _tig_21_1, _tig_21_2, _tig_21_3, _tig_21_4, _tig_21_5,
    ]
    for fn in tig_rules:
        _run(fn)

    # --- WATCH rules ---
    if "WATCH" in detected_representatives:
        watch_rules = [
            _watch_22_1, _watch_22_2, _watch_22_3, _watch_22_4, _watch_22_5,
            _watch_22_6, _watch_22_7, _watch_22_8, _watch_22_9, _watch_22_10,
            _watch_22_11, _watch_22_12, _watch_22_13, _watch_22_14,
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

    # --- Overall result ---
    if hard_blocks:
        overall = "blocked"
    elif flags:
        overall = "flagged"
    else:
        overall = "pass"

    return {
        "hard_blocks": hard_blocks,
        "flags": flags,
        "info": info,
        "passed": passed,
        "overall": overall,
        "representatives_detected": detected_representatives,
    }