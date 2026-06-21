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
    # ---------------------------------------------------------------------------
    # Experian CAIS format — full legal names as they appear in Experian reports
    # ---------------------------------------------------------------------------
    # Water / utilities
    "anglian water": "Anglian Water",
    "anglian water services": "Anglian Water",
    "severn trent water": "Severn Trent Water",
    "severn trent": "Severn Trent Water",
    "thames water": "Thames Water",
    "united utilities": "United Utilities",
    "yorkshire water": "Yorkshire Water",
    "southern water": "Southern Water",
    "wessex water": "Wessex Water",
    "south west water": "South West Water",
    "affinity water": "Affinity Water",
    # Telecoms / communications
    "ee": "EE",
    "ee limited": "EE",
    "bt": "BT",
    "bt group": "BT",
    "sky": "Sky",
    "sky uk limited": "Sky",
    "virgin media": "Virgin Media",
    "vodafone": "Vodafone",
    "vodafone limited": "Vodafone",
    "o2": "O2",
    "telefonica uk limited": "O2",
    "three": "Three",
    "hutchison 3g uk limited": "Three",
    # Insurance / financial
    "premium credit limited": "Premium Credit Limited",
    "premium credit": "Premium Credit Limited",
    # Debt purchasers / other
    "lowell portfolio i ltd": "Lowell",
    "lowell portfolio 1 ltd": "Lowell",
    "lowell portfolio ltd": "Lowell",
    "monzo bank ltd": "Monzo Bank",
    "monzo bank": "Monzo Bank",
    "ovo energy": "OVO Energy",
    "jc international acquisition llc": "JC International Acquisition LLC",
    "mutual": "Mutual",
    "novuna personal finance": "Novuna",
    "novuna consumer finance": "Novuna",
    "barclays bank uk plc": "Barclays",
    "hsbc uk bank plc": "HSBC",
    "lloyds bank plc": "Lloyds Bank",
    "nationwide building society": "Nationwide",
    "Yorkshire bank": "Yorkshire Bank",
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
    Also handles inline fields like "£106098 Last Update: 2025-12-31" by
    taking only the first whitespace-delimited token.
    Returns None for "N/A", "-", empty, or unparseable.
    """
    if not text:
        return None
    first_token = text.strip().split()[0] if text.strip() else ""
    t = first_token.replace(",", "").replace("£", "")
    if t.upper() in ("N/A", "-", ""):
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
# Experian CAIS format — constants and helpers
# ---------------------------------------------------------------------------

# Maps Experian account category text → internal Aryza-style type codes.
# These type codes feed into the same SKIP / CONDITIONAL filtering logic
# already used for Aryza Advize reports.
_EXPERIAN_CATEGORY_TO_TYPE: dict[str, str] = {
    "water": "UT",
    "electricity": "UT",
    "gas": "UT",
    "communications": "UT",
    "telecoms": "UT",
    "telecommunications": "UT",
    "current accounts": "CA",
    "current account": "CA",
    "savings accounts": "CA",
    "savings account": "CA",
    "credit cards": "CC",
    "credit card": "CC",
    "store cards": "CC",
    "store card": "CC",
    "personal loans": "PL",
    "personal loan": "PL",
    "unsecured loan (personal loan)": "PL",
    "unsecured loans (personal loan)": "PL",
    "unsecured loan": "UL",
    "unsecured loans": "UL",
    "secured loan": "MG",
    "secured loans": "MG",
    "running account credit": "CC",
    "revolving credit": "CC",
    "charge card": "CC",
    "hire purchase / conditional sale": "HP",
    "hire purchase": "HP",
    "conditional sale": "HP",
    "mortgages": "MG",
    "mortgage": "MG",
    "home credit": "UL",
    "mail order": "MO",
    "student loans": "UL",
    "student loan": "UL",
    "motor insurance": "OT",
    "insurance": "OT",
}

# Matches Experian CAIS account header lines: "{CREDITOR NAME} - {Category}"
# The " - " separator (space-dash-space) distinguishes headers from inline dashes.
_EXPERIAN_HEADER_RE = re.compile(
    r"^(.+?)\s+-\s+("
    # Utilities
    r"Water|Electricity|Gas|"
    # Telecoms
    r"Communications?|Telecoms?|Telecommunications|"
    # Bank accounts
    r"Current Accounts?|Savings Accounts?|"
    # Credit / revolving
    r"Credit Cards?|Store Cards?|Charge Cards?|Running Account Credit|Revolving Credit|"
    # Loans — includes Experian's "Unsecured Loan (Personal Loan)" parenthetical form
    r"Personal Loans?|Unsecured Loans?\s*(?:\([^)]*\))?|Secured Loans?|"
    # HP / conditional sale
    r"Hire Purchase.*?|Conditional Sale|"
    # Property
    r"Mortgages?|"
    # Other consumer
    r"Home Credit|Mail Order|Student Loans?|Motor Insurance|Insurance"
    r")$",
    re.IGNORECASE,
)

# Fallback for any Experian CAIS header whose category isn't in the strict list above.
# Catches lines of the form "{CREDITOR NAME} - {Title Case Category}" that the
# primary regex missed. Safety constraints that prevent false positives on inner
# account-block lines:
#   - Group 1 starts with [A-Z] (excludes bullet chars like •)
#   - Group 1 must NOT contain ':' (excludes field labels like "Status: Active - Default")
#   - Group 2 starts with [A-Z] and is 2–40 chars
# Accounts matched only by this fallback receive type_code "OT" (Other) because
# their category won't be in _EXPERIAN_CATEGORY_TO_TYPE — they pass all existing
# inclusion/exclusion filters unchanged, so they always surface for caseworker review.
_EXPERIAN_HEADER_FALLBACK_RE = re.compile(
    r"^([A-Z][^:\n]{1,59}?)\s+-\s+([A-Z][A-Za-z0-9 /()\-]{1,39})$"
)


def _months_since_dmy(date_str: str) -> int | None:
    """Parse a DD-MM-YYYY date string (Experian format) and return months since today."""
    if not date_str:
        return None
    try:
        start = datetime.strptime(date_str.strip(), "%d-%m-%Y").date()
        today = date.today()
        return (today.year - start.year) * 12 + (today.month - start.month)
    except ValueError:
        return None


def _extract_experian_report_date(text: str) -> str:
    """
    Extract the report date from an Experian consumer credit report.
    Looks for "Issue Date and Time DD/MM/YYYY" on page 1.
    Falls back to the most recent "CAIS Last Updated: DD-MM-YYYY" date.
    Returns ISO YYYY-MM-DD string, or empty string if not found.
    """
    m = re.search(r"Issue Date and Time\s+(\d{2}/\d{2}/\d{4})", text)
    if m:
        try:
            return datetime.strptime(m.group(1), "%d/%m/%Y").strftime("%Y-%m-%d")
        except ValueError:
            pass
    dates = re.findall(r"CAIS Last Updated:\s*(\d{2}-\d{2}-\d{4})", text)
    if dates:
        parsed = []
        for d in dates:
            try:
                parsed.append(datetime.strptime(d, "%d-%m-%Y"))
            except ValueError:
                pass
        if parsed:
            return max(parsed).strftime("%Y-%m-%d")
    return ""


def _parse_experian_status(lines: list[str]) -> str:
    """
    Derive internal status string from Experian "Status:" and "Worst Status:" fields.
    Experian status values: Default, Active, Settled, Satisfied, Delinquent, etc.
    """
    worst = _extract_field(lines, "Worst Status").lower()
    status = _extract_field(lines, "Status").lower()
    combined = worst + " " + status
    if "default" in combined:
        return "defaulted"
    if "delinquent" in combined:
        return "late"
    if "arrangement" in combined or "dmp" in combined:
        return "arrangement"
    if ("settled" in status or "satisfied" in status or "closed" in status) \
            and "default" not in worst:
        return "closed"
    return "open"


def _split_experian_accounts(full_text: str) -> list[tuple[str, str]]:
    """
    Split Experian CAIS report text into (header_line, block_text) tuples.
    Headers match the pattern "{CREDITOR NAME} - {Category}".
    """
    lines = full_text.split("\n")
    blocks: list[tuple[str, str]] = []
    current_header: str | None = None
    current_lines: list[str] = []

    for line in lines:
        stripped = line.strip()
        if _EXPERIAN_HEADER_RE.match(stripped) or _EXPERIAN_HEADER_FALLBACK_RE.match(stripped):
            if current_header is not None:
                blocks.append((current_header, "\n".join(current_lines)))
            current_header = stripped
            current_lines = []
        elif current_header is not None:
            current_lines.append(line)

    if current_header is not None:
        blocks.append((current_header, "\n".join(current_lines)))

    return blocks


def _parse_experian_account(header: str, block_text: str) -> dict | None:
    """
    Parse one Experian CAIS account block into the same structured dict shape
    that _parse_account_block() produces for Aryza Advize reports.
    Returns None when the account should be excluded by type/status rules.
    """
    m = _EXPERIAN_HEADER_RE.match(header)
    if not m:
        m = _EXPERIAN_HEADER_FALLBACK_RE.match(header)
    if not m:
        return None

    raw_name = m.group(1).strip()
    category = m.group(2).strip()
    type_code = _EXPERIAN_CATEGORY_TO_TYPE.get(category.lower(), "OT")

    lines = block_text.split("\n")

    # Start date is DD-MM-YYYY in Experian (not YYYY-MM-DD like Aryza)
    start_date_str = _extract_field(lines, "Start Date")
    account_age_months = _months_since_dmy(start_date_str)

    raw_balance = _extract_field(lines, "Current Balance")
    current_balance = _parse_amount(raw_balance)

    # Experian does not provide a credit limit field; utilisation not applicable
    credit_limit = None
    utilisation_pct = None

    account_status = _parse_experian_status(lines)

    # Apply the same conditional exclusion rules as the Aryza path

    # BD: include only if balance > 0 (Experian rarely uses BD, but guard anyway)
    if type_code == "BD":
        if not current_balance or current_balance <= 0:
            logger.debug(
                f"[EXPERIAN SKIP] '{raw_name}' type={type_code} — zero balance BD"
            )
            return None

    # CA / UT: include only if the account is derogatory (defaulted/late/arrangement)
    if type_code in {"CA", "UT"}:
        if account_status not in {"defaulted", "late", "arrangement"}:
            logger.debug(
                f"[EXPERIAN SKIP] '{raw_name}' type={type_code} status='{account_status}' — clean account excluded"
            )
            return None

    # Name resolution via shared alias map
    normalised = raw_name.lower().strip()
    matched = CREDITOR_ALIAS_MAP.get(normalised, raw_name)

    # Reuse the existing missed-payments parser — grid format is the same
    missed_payments_last_3_months = _parse_missed_payments_last_3_months(lines)

    balance_display = round(current_balance / 100) if current_balance else 0
    logger.debug(
        f"[EXPERIAN INCLUDE] '{raw_name}' type={type_code} balance=£{balance_display} status='{account_status}'"
    )

    return {
        "raw_name": raw_name,
        "type_code": type_code,
        "normalised_name": normalised,
        "matched_creditor": matched,
        "account_age_months": account_age_months,
        "missed_payments_last_3_months": missed_payments_last_3_months,
        "recent_spending": False,   # Payment Amount section absent in Experian format
        "current_balance": current_balance,
        "credit_limit": credit_limit,
        "utilisation_pct": utilisation_pct,
        "account_status": account_status,
        "payment_history_months": 0,
        "monthly_payment": None,    # Experian does not expose a monthly payment field
    }


# ---------------------------------------------------------------------------
# Public Information — CCJ / judgment extraction (both Aryza & Experian formats)
# ---------------------------------------------------------------------------

def _ccj_amount_to_pence(text: str) -> int | None:
    """Parse a CCJ amount string into pence. Tolerant of the '£' mojibake
    that pdfplumber sometimes produces (e.g. '�557.0')."""
    if not text:
        return None
    m = re.search(r"(\d[\d,]*\.?\d*)", text)
    if not m:
        return None
    try:
        return int(round(float(m.group(1).replace(",", "")) * 100))
    except ValueError:
        return None


def extract_public_information(full_text: str) -> dict:
    """
    Extract Public Information (CCJ / judgment, insolvency, debt-management)
    signals from a credit report, supporting both report formats:

      - Experian: a "Public Information" summary block plus per-record detail
        lines ("Type: Judgement - Judgement", "Amount: £…", "Settled: N",
        "Date: DD-MM-YYYY"). The detail records are CCJ-specific and are the
        primary signal.
      - Aryza Advize: an inline "CCJs and Insolvencies: N" combined count
        (no per-record breakdown is exposed in this format).

    Returns:
        {
            "has_ccj": bool,
            "ccj_count": int,
            "ccj_total_pence": int | None,
            "ccjs": [ {"amount_pence", "settled", "date"}, ... ],
            "iva_or_bankruptcy": bool,
            "debt_management": bool,
        }
    Never raises.
    """
    info = {
        "has_ccj": False,
        "ccj_count": 0,
        "ccj_total_pence": None,
        "ccjs": [],
        "iva_or_bankruptcy": False,
        "debt_management": False,
    }
    if not full_text:
        return info

    lines = full_text.split("\n")

    def _field_in(window: list[str], label: str) -> str:
        prefix = label.lower() + ":"
        for ln in window:
            low = ln.lower()
            idx = low.find(prefix)
            if idx != -1:
                return ln[idx + len(prefix):].strip()
        return ""

    # --- Experian: per-record judgment detail blocks ---
    # Each record is anchored on a "Type: Judgement …" line; the Date/Amount/
    # Settled fields sit within a few lines either side of it.
    records = []
    for i, ln in enumerate(lines):
        if re.search(r"type:\s*judg", ln, re.IGNORECASE):
            window = lines[max(0, i - 4): i + 6]
            settled_raw = _field_in(window, "Settled")
            records.append({
                "amount_pence": _ccj_amount_to_pence(_field_in(window, "Amount")),
                "settled": settled_raw.upper().startswith("Y") if settled_raw else None,
                "date": _field_in(window, "Date") or None,
            })

    # --- Aryza Advize: combined "CCJs and Insolvencies: N" summary ---
    aryza_m = re.search(r"CCJ['s]*\s+and\s+Insolvencies:\s*(\d+)", full_text, re.IGNORECASE)
    aryza_count = int(aryza_m.group(1)) if aryza_m else None

    # --- Experian summary fallback: "Public Information … Number: N" ---
    exp_num_m = re.search(
        r"Public Information\b[\s\S]{0,80}?Number:\s*(\d+)", full_text, re.IGNORECASE
    )
    exp_num = int(exp_num_m.group(1)) if exp_num_m else None

    if records:
        info["ccjs"] = records
        info["ccj_count"] = len(records)
        info["has_ccj"] = True
        amounts = [r["amount_pence"] for r in records if r["amount_pence"]]
        info["ccj_total_pence"] = sum(amounts) if amounts else None
    elif aryza_count is not None and aryza_count > 0:
        # Aryza exposes only a combined CCJ+insolvency count with no detail.
        info["ccj_count"] = aryza_count
        info["has_ccj"] = True
    elif exp_num is not None and exp_num > 0:
        info["ccj_count"] = exp_num
        info["has_ccj"] = True

    iva_m = re.search(r"IVA or Bankruptcy Detected:\s*(\w)", full_text, re.IGNORECASE)
    info["iva_or_bankruptcy"] = bool(iva_m and iva_m.group(1).upper() == "Y")
    dm_m = re.search(r"Debt Management:\s*(\w)", full_text, re.IGNORECASE)
    info["debt_management"] = bool(dm_m and dm_m.group(1).upper() == "Y")

    return info


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
        public_info = extract_public_information(full_text)

        accounts: list[dict] = []
        mortgage_accounts: list[dict] = []
        unmatched: list[str] = []

        if agency == "Experian":
            # ----------------------------------------------------------------
            # Experian Consumer Credit Report (CAIS format)
            # Headers: "{CREDITOR NAME} - {Category}"
            # Date format: DD-MM-YYYY
            # ----------------------------------------------------------------
            report_date = _extract_experian_report_date(full_text)
            blocks = _split_experian_accounts(full_text)
            for header, block_text in blocks:
                parsed = _parse_experian_account(header, block_text)
                if parsed is None:
                    continue
                if parsed["type_code"] == "MG":
                    mortgage_accounts.append(parsed)
                else:
                    accounts.append(parsed)
                    if parsed["matched_creditor"] == parsed["raw_name"]:
                        unmatched.append(parsed["raw_name"])
        else:
            # ----------------------------------------------------------------
            # Aryza Advize format (original path — unchanged)
            # Headers: "{Creditor Name} {TYPE_CODE}"
            # Date format: YYYY-MM-DD
            # ----------------------------------------------------------------
            report_date = _extract_report_date(full_text)
            blocks = _split_into_account_blocks(full_text)
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
            "public_information": public_info,
            "has_ccj": public_info["has_ccj"],
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
