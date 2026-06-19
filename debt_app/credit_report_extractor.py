"""
credit_report_extractor.py

Extracts structured per-creditor data from Aryza Advize credit report PDFs.

PDF structure (confirmed from real report):
  - Account header:  "{Creditor Name} {TYPE_CODE}"
    TYPE_CODE suffixes: CC, UL, MG, MO, CA, UT
  - Account Status line (after pdfplumber): "Account Status: {status} {subjective}"
  - Start Date: "Start Date: YYYY-MM-DD"  → compute account_age_months
  - Current Balance: "Current Balance: £{amount}" or "N/A"
  - Credit Limit: "Credit Limit: £{amount}" or "N/A"
  - Default Balance: "Default Balance: £{amount}" or "N/A"
  - Payment history grid: year row followed by 12 integers/D values
    Each integer = missed payments that month. D = defaulted.
  - Missed payments last 3 months: sum of last 3 values in most recent year row.

Type code inclusion rules:
  MG          → always skip (secured mortgage)
  CC/UL/MO/TM → always include
  BD          → include only if balance > 0
  CA/UT       → include only if status is defaulted/late/arrangement
                skip if up to date or closed
"""

import re
import logging
from datetime import date, datetime

import pdfplumber

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Type code classification
# ---------------------------------------------------------------------------

# These suffix codes appear at the end of every account header line
SKIP_TYPE_CODES = {"MG"}                              # always skip: secured mortgage
DEBT_TYPE_CODES = {"CC", "UL", "MO", "PL", "HP", "TM", "BD"}  # always include
CONDITIONAL_TYPE_CODES = {"CA", "UT"}                 # include only if defaulted/arrears

# ---------------------------------------------------------------------------
# Creditor alias map
# Keys: lowercase stripped name from PDF (without type code suffix)
# Values: canonical name as it appears in Aryza / CreditorCriteria
# ---------------------------------------------------------------------------

CREDITOR_ALIAS_MAP = {
    # NatWest variants
    "national westminster credit cards": "Natwest Group Plc",
    "national westminster": "Natwest Group Plc",
    "natwest": "Natwest Group Plc",
    "natwest group": "Natwest Group Plc",
    "rbs": "Natwest Group Plc",
    # Lloyds variants — all map to same canonical
    "lloyds bank": "Lloyds Bank",
    "lloyds bank personal loans": "Lloyds Bank",
    "lloyds bank mortgages ltd": "Lloyds Bank",
    "lloyds banking group": "Lloyds Bank",
    "lloyds": "Lloyds Bank",
    "halifax": "Halifax",
    "bank of scotland": "Bank of Scotland",
    # MBNA
    "mbna ltd": "MBNA - IVA",
    "mbna limited": "MBNA - IVA",
    "mbna": "MBNA - IVA",
    # Link Financial
    "link financial outsourcing limited": "Link Financial Outsourcing Limited",
    "link financial": "Link Financial Outsourcing Limited",
    "link": "Link Financial Outsourcing Limited",
    # JD Williams / N Brown
    "jd williams ta jacamo": "JD WIlliams (N Brown Group)",
    "jd williams": "JD WIlliams (N Brown Group)",
    "jacamo": "JD WIlliams (N Brown Group)",
    "simply be": "JD WIlliams (N Brown Group)",
    "ambrose wilson": "JD WIlliams (N Brown Group)",
    # Barclays
    "barclaycard": "Barclaycard",
    "barclays": "Barclays",
    # HSBC
    "hsbc": "HSBC",
    "hsbc bank": "HSBC",
    # NatWest/RBS cards
    "tesco bank": "Tesco Bank",
    # Santander
    "santander": "Santander",
    "santander uk": "Santander",
    # Capital One
    "capital one": "Capital One",
    # Virgin
    "virgin money": "Virgin Money",
    "virgin credit card": "Virgin Money",
    # Vanquis
    "vanquis bank": "Vanquis Bank",
    "vanquis": "Vanquis Bank",
    # Aqua / NewDay
    "aqua": "Aqua",
    "marbles": "Marbles",
    "newday": "NewDay",
    # Shop Direct / Very
    "shop direct": "Shop Direct",
    "very": "Very",
    "littlewoods": "Littlewoods",
    # Debt purchasers
    "lowell financial": "Lowell",
    "lowell portfolio": "Lowell",
    "lowell": "Lowell",
    "pra group": "PRA Group",
    "pra": "PRA Group",
    "intrum": "Intrum",
    "cabot financial": "Cabot Financial",
    "cabot": "Cabot Financial",
    # Lending
    "ratesetter": "RateSetter",
    "zopa": "Zopa",
    "funding circle": "Funding Circle",
    "amigo loans": "Amigo Loans",
    "amigo": "Amigo Loans",
    "brighthouse": "BrightHouse",
}

# ---------------------------------------------------------------------------
# Public name-matching helper (also used by criteria_engine)
# ---------------------------------------------------------------------------

def match_creditor(raw_name: str) -> str:
    """
    Look up raw_name in CREDITOR_ALIAS_MAP (case-insensitive, stripped).
    Returns the canonical creditor name, or raw_name if no match found.
    Never raises.
    """
    if not raw_name:
        return raw_name or ""
    try:
        return CREDITOR_ALIAS_MAP.get(raw_name.lower().strip(), raw_name)
    except Exception:
        return raw_name


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TYPE_CODE_RE = re.compile(
    r"^(.+?)\s+(CC|UL|MG|MO|CA|UT|PL|HP|ST|OT|TM|BD)$"
)

def _parse_amount(text: str) -> int | None:
    """
    Parse a sterling amount string → pence integer.
    Handles: "£8,039", "£8039", "8039", "-£30"
    Returns None for "N/A", "-", empty, or unparseable.
    """
    if not text:
        return None
    t = text.strip().replace(",", "").replace("£", "").replace(" ", "")
    if t in ("N/A", "-", "n/a", ""):
        return None
    try:
        return int(round(float(t) * 100))
    except (ValueError, TypeError):
        return None


def _months_since(date_str: str) -> int | None:
    """
    Compute months between a date string (YYYY-MM-DD) and today.
    Returns None if date_str is unparseable.
    """
    if not date_str:
        return None
    try:
        start = datetime.strptime(date_str.strip(), "%Y-%m-%d").date()
        today = date.today()
        return (today.year - start.year) * 12 + (today.month - start.month)
    except ValueError:
        return None


def _extract_field(lines: list[str], label: str) -> str:
    """
    Find the first line containing `label:` and return everything after the colon.
    Returns empty string if not found.
    """
    prefix = label.lower() + ":"
    for line in lines:
        low = line.lower()
        idx = low.find(prefix)
        if idx != -1:
            return line[idx + len(prefix):].strip()
    return ""


def _detect_agency(text: str) -> str:
    """
    Detect credit agency from report text.
    This report format is Aryza Advize — an internal aggregator.
    Falls back to bureau detection if Aryza branding absent.
    """
    sample = text[:800].lower()
    if "aryza" in sample or "advize" in sample:
        return "Aryza Advize"
    if "experian" in sample or "credit expert" in sample:
        return "Experian"
    if "equifax" in sample or "clearscore" in sample:
        return "Equifax"
    if "transunion" in sample or "credit karma" in sample:
        return "TransUnion"
    return "Unknown"


def _extract_client_name(text: str) -> str:
    """
    Extract client name from "Name: Mrs Theresa Topp" style header.
    Strips titles (Mr/Mrs/Ms/Miss/Dr).
    """
    m = re.search(
        r"Name:\s*(Mr|Mrs|Ms|Miss|Dr|Prof)\.?\s+(.+?)(?:\n|$)",
        text, re.IGNORECASE
    )
    if m:
        return m.group(2).strip()
    m = re.search(r"Name:\s*(.+?)(?:\n|$)", text, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return ""


def _extract_report_date(text: str) -> str:
    """
    Extract the most recent "Last Update" date from the report.
    Returns ISO string or empty string.
    """
    dates = re.findall(r"Last Update:\s*(\d{4}-\d{2}-\d{2})", text)
    if dates:
        # Return the most recent one
        return sorted(dates)[-1]
    return ""


def _parse_missed_payments_last_3_months(lines: list[str]) -> int:
    """
    Parse the payment history grid and return missed payment count
    for the most recent 3 months.

    Grid structure after pdfplumber extraction:
      Balance line:  "£8,039 £7,496 ..."  (12 values)
      Missed line:   "3 0 0 0 ..."        (12 integers or D)
      Year label:    "2026" or "2025"

    The year label can appear before or after the value rows.
    We want the most recent 3 non-empty values from the missed row
    of the most recent year that has data.

    Strategy: find lines that are purely space-separated integers/D/-
    and are associated with the most recent year.
    """
    payment_row_re = re.compile(
        r"^[\s\d D\-]+$"
    )
    year_re = re.compile(r"^\d{4}$")

    current_year = None
    year_data: dict[int, list[str]] = {}

    for line in lines:
        stripped = line.strip()
        if year_re.match(stripped):
            current_year = int(stripped)
        elif current_year and payment_row_re.match(stripped):
            tokens = stripped.split()
            clean = [t for t in tokens if re.match(r"^\d+$|^D$", t)]
            if 1 <= len(clean) <= 12:
                if current_year not in year_data:
                    year_data[current_year] = clean

    if not year_data:
        return 0

    best_year = max(year_data.keys())
    values = year_data[best_year]

    # Most recent 3 months = last 3 values in the row
    recent = values[-3:]

    missed = 0
    for v in recent:
        if v == "D":
            missed += 1
        else:
            try:
                missed += int(v)
            except ValueError:
                pass
    return missed


def _determine_account_status(lines: list[str], default_balance: int | None) -> str:
    """
    Determine account status from status line and default balance.

    After pdfplumber, the status line merges as:
      "Account Status: Default Bad"
      "Account Status: Late payment Bad"
      "Account Status: Up to date Good"
    """
    if default_balance is not None and default_balance > 0:
        return "defaulted"

    status_text = _extract_field(lines, "Account Status").lower()
    if "default" in status_text:
        return "defaulted"
    if "late" in status_text:
        return "late"
    if "arrangement" in status_text or "dmp" in status_text:
        return "arrangement"
    if "closed" in status_text or "settled" in status_text:
        return "closed"
    return "open"


def _extract_monthly_payment_pence(lines: list[str]) -> int | None:
    """
    Extract the most recent monthly payment from the Payment Amount section (in pence).
    Returns None if the section is absent or all values are dashes.
    """
    in_payment_section = False
    year_re = re.compile(r"^(\d{4})\s+(.+)$")
    most_recent_payments: list[str] = []
    best_year = 0

    for line in lines:
        if "Payment Amount" in line:
            in_payment_section = True
            continue
        if not in_payment_section:
            continue
        if re.match(r"^[A-Z][a-z]+ [A-Z]", line) and "£" not in line:
            break
        m = year_re.match(line.strip())
        if m:
            yr = int(m.group(1))
            if yr > best_year:
                best_year = yr
                most_recent_payments = m.group(2).split()

    for val in reversed(most_recent_payments):
        if val == "-":
            continue
        amt = _parse_amount(val)
        if amt and amt > 0:
            return amt
    return None


def _has_recent_spending(lines: list[str]) -> bool:
    """
    Detect recent spending (last 3 months) from the Payment Amount grid.
    Look for the Payment Amount section and check the last 3 non-zero values
    in the most recent year.
    """
    in_payment_section = False
    year_re = re.compile(r"^(\d{4})\s+(.+)$")

    most_recent_payments: list[str] = []
    best_year = 0

    for line in lines:
        if "Payment Amount" in line:
            in_payment_section = True
            continue
        if not in_payment_section:
            continue
        # Stop at next section header
        if re.match(r"^[A-Z][a-z]+ [A-Z]", line) and "£" not in line:
            break

        m = year_re.match(line.strip())
        if m:
            yr = int(m.group(1))
            if yr > best_year:
                best_year = yr
                tokens = m.group(2).split()
                most_recent_payments = tokens

    if not most_recent_payments:
        return False

    # Check last 3 non-dash values
    non_dash = [t for t in most_recent_payments if t != "-"][-3:]
    for val in non_dash:
        amt = _parse_amount(val)
        if amt and amt > 0:
            return True
    return False


# ---------------------------------------------------------------------------
# Account block splitter
# ---------------------------------------------------------------------------

def _split_into_account_blocks(full_text: str) -> list[tuple[str, str]]:
    """
    Split the full PDF text into (header_line, block_text) tuples.

    Account headers match: "{Name} {TYPE_CODE}" at the start of a line
    where TYPE_CODE is one of: CC UL MG MO CA UT PL HP ST OT
    """
    lines = full_text.split("\n")
    blocks: list[tuple[str, str]] = []
    current_header: str | None = None
    current_lines: list[str] = []

    for line in lines:
        m = _TYPE_CODE_RE.match(line.strip())
        if m:
            # Save previous block
            if current_header is not None:
                blocks.append((current_header, "\n".join(current_lines)))
            current_header = line.strip()
            current_lines = []
        elif current_header is not None:
            current_lines.append(line)

    # Last block
    if current_header is not None:
        blocks.append((current_header, "\n".join(current_lines)))

    return blocks


# ---------------------------------------------------------------------------
# Single account parser
# ---------------------------------------------------------------------------

def _parse_account_block(header: str, block_text: str) -> dict | None:
    """
    Parse one account block into structured data.
    Returns None if this account type should be skipped.
    """
    m = _TYPE_CODE_RE.match(header)
    if not m:
        return None

    raw_name = m.group(1).strip()
    type_code = m.group(2).strip()

    lines = block_text.split("\n")

    # --- Core fields ---
    start_date_str = _extract_field(lines, "Start Date")
    account_age_months = _months_since(start_date_str)

    raw_balance = _extract_field(lines, "Current Balance")
    current_balance = _parse_amount(raw_balance)

    raw_limit = _extract_field(lines, "Credit Limit")
    credit_limit = _parse_amount(raw_limit)

    raw_default = _extract_field(lines, "Default Balance")
    default_balance = _parse_amount(raw_default)

    # --- Utilisation ---
    utilisation_pct: float | None = None
    if current_balance is not None and credit_limit and credit_limit > 0:
        utilisation_pct = round((current_balance / credit_limit) * 100, 1)

    # --- Status ---
    account_status = _determine_account_status(lines, default_balance)

    # --- Payment history depth ---
    year_rows = re.findall(r"^\d{4}\b", block_text, re.MULTILINE)
    payment_history_months = len(set(year_rows)) * 12  # approximate

    # --- Missed payments last 3 months ---
    missed_payments_last_3_months = _parse_missed_payments_last_3_months(lines)

    # --- Recent spending ---
    recent_spending = _has_recent_spending(lines)

    # --- Monthly payment (from Payment Amount section) ---
    monthly_payment = _extract_monthly_payment_pence(lines)

    # --- Name resolution ---
    normalised = raw_name.lower().strip()
    matched = CREDITOR_ALIAS_MAP.get(normalised, raw_name)

    # --- Conditional type code filtering ---

    # MG: mortgage accounts are always included for asset reconciliation
    # (not counted as unsecured IVA debt — separated by caller)

    # BD: include only if balance > 0
    if type_code == "BD":
        if not current_balance or current_balance <= 0:
            logger.debug(
                f"[EXTRACTOR SKIP] '{raw_name}' type={type_code} status='{account_status}' — excluded from extraction"
            )
            return None

    # CA / UT: include only if defaulted or in arrears (unsecured IVA debt)
    if type_code in {"CA", "UT"}:
        if account_status not in {"defaulted", "late", "arrangement"}:
            logger.debug(
                f"[EXTRACTOR SKIP] '{raw_name}' type={type_code} status='{account_status}' — excluded from extraction"
            )
            return None

    balance_display = round(current_balance / 100) if current_balance else 0
    logger.debug(
        f"[EXTRACTOR INCLUDE] '{raw_name}' type={type_code} balance=£{balance_display}"
    )

    return {
        "raw_name": raw_name,
        "type_code": type_code,
        "normalised_name": normalised,
        "matched_creditor": matched,
        "account_age_months": account_age_months,
        "missed_payments_last_3_months": missed_payments_last_3_months,
        "recent_spending": recent_spending,
        "current_balance": current_balance,
        "credit_limit": credit_limit,
        "utilisation_pct": utilisation_pct,
        "account_status": account_status,
        "payment_history_months": payment_history_months,
        "monthly_payment": monthly_payment,
    }


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def extract_credit_report(pdf_path: str) -> dict:
    """
    Extract structured per-creditor data from an Aryza Advize credit report PDF.

    Returns:
        {
            "agency": str,
            "client_name": str,
            "report_date": str,
            "accounts": [list of parsed account dicts],
            "unmatched_accounts": [raw names with no alias map hit]
        }

    Never raises. On any exception returns dict with "extraction_error" key.
    """
    try:
        with pdfplumber.open(pdf_path) as pdf:
            full_text = "\n".join(
                page.extract_text() or "" for page in pdf.pages
            )

        agency = _detect_agency(full_text)
        client_name = _extract_client_name(full_text)
        report_date = _extract_report_date(full_text)

        blocks = _split_into_account_blocks(full_text)

        accounts: list[dict] = []
        mortgage_accounts: list[dict] = []
        unmatched: list[str] = []

        for header, block_text in blocks:
            parsed = _parse_account_block(header, block_text)
            if parsed is None:
                continue  # skipped type (current account up-to-date, utility, BD zero-balance)

            if parsed["type_code"] == "MG":
                # Mortgages are secured — excluded from IVA criteria but
                # included separately so the case assessment app can compare
                # them against CRM property data in the Assets & Property section.
                mortgage_accounts.append(parsed)
            else:
                accounts.append(parsed)
                if parsed["matched_creditor"] == parsed["raw_name"]:
                    unmatched.append(parsed["raw_name"])

        return {
            "agency": agency,
            "client_name": client_name,
            "report_date": report_date,
            "accounts": accounts,
            "mortgage_accounts": mortgage_accounts,
            "unmatched_accounts": unmatched,
        }

    except Exception as e:
        logger.error(f"Credit report extraction failed for {pdf_path}: {e}", exc_info=True)
        return {
            "agency": "Unknown",
            "client_name": "",
            "report_date": "",
            "accounts": [],
            "unmatched_accounts": [],
            "extraction_error": str(e),
        }
